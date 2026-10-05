"""Import videos already on the machine into the library (skipping the download-from-platform step).

An imported video has `platform=LOCAL` and is in the DOWNLOADED state right away, so it continues through
the same pipeline as a downloaded video: transcribe → translate → dub → merge.
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
    """Save the file uploaded by the user into storage, create the Job + Video, read the duration and
    extract a cover image (the last 2 are best-effort, not mandatory)."""
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
        # This column has a UniqueConstraint by platform — a local video has no platform
        # id so a random id is used, allowing the same file to be imported many times.
        platform_video_id=uuid.uuid4().hex,
        title=title,
        source_url=f"local://{name}",
        status=VideoStatus.QUEUED,
    )
    db.add(video)
    db.flush()

    video_dir = storage_dir() / str(job.id) / str(video.id)
    # The destination file name is fixed, NOT taken from the user-supplied name — avoids path traversal.
    dest = video_dir / f"original{ext}"
    try:
        video_dir.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as out:
            shutil.copyfileobj(stream, out, _COPY_CHUNK)
    except Exception:
        db.rollback()
        shutil.rmtree(video_dir, ignore_errors=True)
        try:
            video_dir.parent.rmdir()  # the job directory, can only be removed if already empty
        except OSError:
            pass
        raise

    duration = ffmpeg.probe_duration_seconds(dest)
    cover_ok = False
    try:
        ffmpeg.extract_thumbnail(dest, video_dir / COVER_FILE_NAME)
        cover_ok = True
    except Exception as exc:  # noqa: BLE001 — a missing cover image must not block the import
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
