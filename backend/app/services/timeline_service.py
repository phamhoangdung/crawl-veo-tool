"""Lưu/đọc draft timeline + render bản cuối — xem docs/phases/phase-13-timeline-editor.md.

Nguyên tắc cốt lõi: AI chỉ gợi ý (điền sẵn `timeline_json`), render CHỈ xảy ra khi
người dùng chủ động gọi `render_timeline_for_video` (nút riêng ở UI, không tự động).
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.adapters import ffmpeg
from app.models.video import Video

_VALID_TRACK_TYPES = {"video", "audio", "overlay", "image", "blur"}


class TimelineValidationError(ValueError):
    pass


class VideoNotFoundError(ValueError):
    pass


def validate_operations(operations: dict) -> None:
    """Kiểm tra hình dạng timeline. Hàm thuần, không chạm DB — nên dùng được cho
    cả timeline của `Video` (Phase 13) và của dự án nhiều cảnh (Phase 15)."""
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
                # Vùng che logo/phụ đề gốc: cần đủ toạ độ và kích thước, thời
                # gian là tuỳ chọn (không có = che suốt video).
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
                # Logo/watermark chỉ bắt buộc có file nguồn: hiện suốt video là
                # mặc định hợp lý, còn start/end là tuỳ chọn để hiện theo mốc.
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
    validate_operations(operations)
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


def get_audio_stems(db: Session, video_id: int) -> dict[str, str | None]:
    """Đường dẫn các track audio đã tách, để timeline dựng track riêng cho từng loại.

    Bước lồng tiếng (dubbing_service) ghi ra `voice_timeline.mp3` (giọng đọc
    tiếng Việt) và demucs tách `no_vocals.wav` (nhạc nền gốc). Tách riêng thì
    chỉnh được âm lượng từng loại — bản `dubbed.mp4` đã trộn sẵn nên không tách
    lại được.
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
        # Bản trộn sẵn — dùng khi chưa tách được stem riêng.
        "mixed": video.dubbed_path,
    }
