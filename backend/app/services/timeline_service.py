"""Lưu/đọc draft timeline + render bản cuối — xem docs/phases/phase-13-timeline-editor.md.

Nguyên tắc cốt lõi: AI chỉ gợi ý (điền sẵn `timeline_json`), render CHỈ xảy ra khi
người dùng chủ động gọi `render_timeline_for_video` (nút riêng ở UI, không tự động).
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.adapters import ffmpeg
from app.models.video import Video

_VALID_TRACK_TYPES = {"video", "audio", "overlay"}


class TimelineValidationError(ValueError):
    pass


class VideoNotFoundError(ValueError):
    pass


def _validate_operations(operations: dict) -> None:
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
        if track_type == "video" and clips:
            has_video_track = True

    if not has_video_track:
        raise TimelineValidationError("Timeline cần ít nhất 1 track video có clip")


def get_timeline(db: Session, video_id: int) -> dict | None:
    video = db.get(Video, video_id)
    if video is None:
        raise VideoNotFoundError(f"Video {video_id} không tồn tại")
    return video.timeline_json


def save_timeline(db: Session, video_id: int, operations: dict) -> dict:
    """Lưu draft — validate hình dạng cơ bản nhưng KHÔNG render. Cho phép gọi
    nhiều lần để sửa dần (mỗi lần gọi ghi đè toàn bộ draft cũ)."""
    video = db.get(Video, video_id)
    if video is None:
        raise VideoNotFoundError(f"Video {video_id} không tồn tại")
    _validate_operations(operations)
    video.timeline_json = operations
    db.commit()
    return operations


def render_timeline_for_video(db: Session, video_id: int) -> Path:
    """Render draft đã lưu thành file hoàn chỉnh — chỉ gọi khi người dùng chủ động
    bấm nút render (không tự động sau save_timeline)."""
    video = db.get(Video, video_id)
    if video is None:
        raise VideoNotFoundError(f"Video {video_id} không tồn tại")
    if not video.timeline_json:
        raise TimelineValidationError("Chưa có timeline nào được lưu cho video này")

    video_dir = Path(video.local_path).parent if video.local_path else Path("storage") / str(video_id)
    output_path = video_dir / "timeline_rendered.mp4"

    ffmpeg.render_timeline(video.timeline_json, output_path)

    video.timeline_rendered_path = str(output_path)
    db.commit()
    return output_path
