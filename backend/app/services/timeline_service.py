"""Save/read the timeline draft + render the final version — see docs/phases/phase-13-timeline-editor.md.

Core principle: AI only suggests (pre-fills `timeline_json`), rendering happens ONLY when
the user explicitly calls `render_timeline_for_video` (a separate button in the UI, never automatic).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from app.adapters import ffmpeg
from app.core.config import storage_dir
from app.models.generation_project import GenerationProject
from app.models.video import Video

_VALID_TRACK_TYPES = {"video", "audio", "overlay", "image", "blur"}

# A timeline anchors to 2 kinds of subjects: crawled videos (Phase 13) and multi-scene
# projects built with AI (Phase 14/16). They share exactly one `timeline_json` + one
# renderer, differing only in where the working directory comes from.
SubjectType = Literal["video", "project"]


class TimelineValidationError(ValueError):
    pass


class SubjectNotFoundError(ValueError):
    pass


class VideoNotFoundError(SubjectNotFoundError):
    pass


class ProjectNotFoundError(SubjectNotFoundError):
    pass


@dataclass(frozen=True)
class _Subject:
    """The subject holding the timeline — wraps the parts that differ between `Video` and a project."""

    row: Video | GenerationProject
    work_dir: Path


def _resolve_subject(db: Session, subject_type: SubjectType, subject_id: int) -> _Subject:
    if subject_type == "video":
        video = db.get(Video, subject_id)
        if video is None:
            raise VideoNotFoundError(f"Video {subject_id} không tồn tại")
        work_dir = (
            Path(video.local_path).parent
            if video.local_path
            else storage_dir() / str(subject_id)
        )
        return _Subject(row=video, work_dir=work_dir)

    if subject_type == "project":
        project = db.get(GenerationProject, subject_id)
        if project is None:
            raise ProjectNotFoundError(f"Dự án {subject_id} không tồn tại")
        return _Subject(row=project, work_dir=storage_dir() / "projects" / str(subject_id))

    raise ValueError(f"Loại chủ thể không hợp lệ: {subject_type!r}")


def validate_operations(operations: dict) -> None:
    """Validate the timeline shape. A pure function, touching no DB — so usable for
    both the `Video` timeline (Phase 13) and the multi-scene project timeline (Phase 15)."""
    tracks = operations.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        raise TimelineValidationError("Timeline cần trường 'tracks' dạng list, không rỗng")

    has_video_track = False
    for track in tracks:
        track_type = track.get("type")
        if track_type not in _VALID_TRACK_TYPES:
            raise TimelineValidationError(
                f"Loại track không hợp lệ: {track_type!r} (chỉ nhận {_VALID_TRACK_TYPES})"
            )
        clips = track.get("clips", [])
        if not isinstance(clips, list):
            raise TimelineValidationError("'clips' của track phải là list")
        for clip in clips:
            if track_type in ("video", "audio"):
                if "source" not in clip or "start" not in clip or "end" not in clip:
                    raise TimelineValidationError(
                        "Clip video/audio cần đủ 'source', 'start', 'end'"
                    )
                if clip["end"] <= clip["start"]:
                    raise TimelineValidationError("Clip có 'end' phải lớn hơn 'start'")
            elif track_type == "overlay":
                if "text" not in clip or "start" not in clip or "end" not in clip:
                    raise TimelineValidationError("Clip overlay cần đủ 'text', 'start', 'end'")
            elif track_type == "blur":
                # Region hiding the original logo/subtitles: needs full coordinates and size, the time
                # range is optional (absent = hide for the whole video).
                missing = [k for k in ("x", "y", "width", "height") if k not in clip]
                if missing:
                    raise TimelineValidationError(
                        f"Vùng làm mờ cần đủ 'x', 'y', 'width', 'height' (thiếu: {missing})"
                    )
                if clip["width"] <= 0 or clip["height"] <= 0:
                    raise TimelineValidationError("Vùng làm mờ phải có kích thước dương")
                if clip.get("mode", "blur") not in ("blur", "pixelate"):
                    raise TimelineValidationError(
                        f"Chế độ làm mờ không hợp lệ: {clip.get('mode')!r} (chỉ 'blur' hoặc 'pixelate')"
                    )
                has_start = clip.get("start") is not None
                has_end = clip.get("end") is not None
                if has_start != has_end:
                    raise TimelineValidationError(
                        "Vùng làm mờ phải có cả 'start' và 'end', hoặc không có cái nào"
                    )
            elif track_type == "image":
                # Logo/watermark only requires a source file: showing for the whole video is
                # a sensible default, while start/end are optional to show by time range.
                if "source" not in clip:
                    raise TimelineValidationError("Clip ảnh cần 'source'")
                has_start = clip.get("start") is not None
                has_end = clip.get("end") is not None
                if has_start != has_end:
                    raise TimelineValidationError(
                        "Clip ảnh phải có cả 'start' và 'end', hoặc không có cái nào "
                        "(hiện suốt video)"
                    )
                if has_start and clip["end"] <= clip["start"]:
                    raise TimelineValidationError("Clip ảnh có 'end' phải lớn hơn 'start'")
        if track_type == "video" and clips:
            has_video_track = True

    if not has_video_track:
        raise TimelineValidationError("Timeline cần ít nhất 1 track video có clip")


def get_timeline_for(
    db: Session, subject_type: SubjectType, subject_id: int
) -> dict | None:
    return _resolve_subject(db, subject_type, subject_id).row.timeline_json


def save_timeline_for(
    db: Session, subject_type: SubjectType, subject_id: int, operations: dict
) -> dict:
    """Save the draft — validates the basic shape but does NOT render. Allows calling
    many times to refine gradually (each call overwrites the whole old draft)."""
    subject = _resolve_subject(db, subject_type, subject_id)
    validate_operations(operations)
    subject.row.timeline_json = operations
    db.commit()
    return operations


def render_timeline_for(
    db: Session, subject_type: SubjectType, subject_id: int
) -> Path:
    """Render the saved draft into a finished file — only called when the user explicitly
    clicks the render button (never automatically after save_timeline)."""
    subject = _resolve_subject(db, subject_type, subject_id)
    if not subject.row.timeline_json:
        raise TimelineValidationError("Chưa có timeline nào được lưu cho mục này")

    subject.work_dir.mkdir(parents=True, exist_ok=True)
    output_path = subject.work_dir / "timeline_rendered.mp4"

    ffmpeg.render_timeline(subject.row.timeline_json, output_path)

    subject.row.timeline_rendered_path = str(output_path)
    db.commit()
    return output_path


def get_timeline(db: Session, video_id: int) -> dict | None:
    return get_timeline_for(db, "video", video_id)


def save_timeline(db: Session, video_id: int, operations: dict) -> dict:
    return save_timeline_for(db, "video", video_id, operations)


def render_timeline_for_video(db: Session, video_id: int) -> Path:
    return render_timeline_for(db, "video", video_id)


def get_audio_stems(db: Session, video_id: int) -> dict[str, str | None]:
    """Paths of the separated audio tracks, so the timeline builds a separate track for each kind.

    The dubbing step (dubbing_service) writes `voice_timeline.mp3` (the Vietnamese
    narration) and demucs separates `no_vocals.wav` (the original background music). Kept separate,
    each kind's volume can be adjusted — the `dubbed.mp4` is already mixed so it cannot be
    separated again.
    """
    video = db.get(Video, video_id)
    if video is None:
        raise VideoNotFoundError(video_id)
    if not video.local_path:
        return {"voice": None, "background": None, "mixed": None}

    video_dir = Path(video.local_path).parent
    voice = video_dir / "voice_timeline.mp3"
    background = video_dir / "demucs_out" / "htdemucs" / "original_audio" / "no_vocals.wav"

    return {
        "voice": str(voice) if voice.exists() else None,
        "background": str(background) if background.exists() else None,
        # Pre-mixed version — used when separate stems could not be extracted.
        "mixed": video.dubbed_path,
    }
