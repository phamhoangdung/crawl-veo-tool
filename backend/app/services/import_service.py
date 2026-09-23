"""Nhập video có sẵn trên máy vào thư viện (không qua bước tải từ nền tảng).

Video nhập vào có `platform=LOCAL` và ở trạng thái DOWNLOADED ngay, nên đi tiếp
đúng pipeline như video tải về: tách lời → dịch → lồng tiếng → ghép.
"""

import logging
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.adapters import ffmpeg
from app.core.config import storage_dir
from app.models.job import Job, JobStatus, Platform
from app.models.video import Video, VideoStatus

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = frozenset(
    {".mp4", ".mkv", ".mov", ".avi", ".webm", ".flv", ".m4v", ".ts", ".wmv"}
)
_COPY_CHUNK = 1024 * 1024
COVER_FILE_NAME = "cover.jpg"


class UnsupportedVideoFormatError(ValueError):
    pass


def import_local_video(
    db: Session, user_id: int, filename: str, stream: BinaryIO
) -> Video:
    """Lưu file người dùng gửi lên vào kho, tạo Job + Video, đọc thời lượng và
    trích ảnh bìa (2 việc sau làm được thì làm, không bắt buộc)."""
    name = Path(filename).name
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedVideoFormatError(
            f"Định dạng '{ext or name}' chưa hỗ trợ. Dùng: "
            + ", ".join(sorted(ALLOWED_EXTENSIONS))
        )
    title = Path(name).stem or "Video nhập từ máy"

    job = Job(
        user_id=user_id,
        platform=Platform.LOCAL,
        keyword=f"[Nhập từ máy] {title}",
        status=JobStatus.RUNNING,
    )
    db.add(job)
    db.flush()
    video = Video(
        user_id=user_id,
        job_id=job.id,
        platform=Platform.LOCAL,
        # Cột này có UniqueConstraint theo platform — video local không có id
        # nền tảng nên dùng id ngẫu nhiên, cho phép nhập trùng file nhiều lần.
        platform_video_id=uuid.uuid4().hex,
        title=title,
        source_url=f"local://{name}",
        status=VideoStatus.QUEUED,
    )
    db.add(video)
    db.flush()

    video_dir = storage_dir() / str(job.id) / str(video.id)
    # Tên file đích cố định, KHÔNG lấy từ tên người dùng gửi — tránh path traversal.
    dest = video_dir / f"original{ext}"
    try:
        video_dir.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as out:
            shutil.copyfileobj(stream, out, _COPY_CHUNK)
    except Exception:
        db.rollback()
        shutil.rmtree(video_dir, ignore_errors=True)
        try:
            video_dir.parent.rmdir()  # thư mục job, chỉ xoá được nếu đã rỗng
        except OSError:
            pass
        raise

    duration = ffmpeg.probe_duration_seconds(dest)
    cover_ok = False
    try:
        ffmpeg.extract_thumbnail(dest, video_dir / COVER_FILE_NAME)
        cover_ok = True
    except Exception as exc:  # noqa: BLE001 — thiếu ảnh bìa không được chặn việc nhập
        logger.warning("Không trích được ảnh bìa cho %s: %s", dest, exc)

    video.local_path = str(dest)
    video.duration_seconds = round(duration) if duration is not None else None
    video.cover_url = f"/api/videos/{video.id}/cover" if cover_ok else None
    video.status = VideoStatus.DOWNLOADED
    job.status = JobStatus.COMPLETED
    db.commit()
    db.refresh(video)
    return video


def cover_path_for(video: Video) -> Path | None:
    if not video.local_path:
        return None
    path = Path(video.local_path).parent / COVER_FILE_NAME
    return path if path.is_file() else None
