"""Manage downloaded files: list, compute size, delete.

The tool runs locally so users need to see how much disk the real files take and
to delete what is no longer needed — unlike a web app where files live on the server.
"""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.video import Video, VideoStatus
from app.services import download_service, progress_service

logger = logging.getLogger(__name__)


@dataclass
class FileEntry:
    variant: str
    path: str
    size_bytes: int
    exists: bool


@dataclass
class VideoFiles:
    video_id: int
    title: str
    status: str
    cover_url: str | None
    video_dir: str | None
    files: list[FileEntry]
    total_bytes: int


def _entry(variant: str, raw_path: str | None) -> FileEntry | None:
    if not raw_path:
        return None
    path = Path(raw_path)
    exists = path.exists()
    return FileEntry(
        variant=variant,
        path=str(path),
        size_bytes=path.stat().st_size if exists else 0,
        exists=exists,
    )


def list_video_files(db: Session, user_id: int) -> list[VideoFiles]:
    """Every video with at least 1 file on disk, with its real size."""
    videos = (
        db.query(Video)
        .filter(Video.user_id == user_id, Video.local_path.isnot(None))
        .order_by(Video.created_at.desc())
        .all()
    )

    result: list[VideoFiles] = []
    for video in videos:
        entries = [
            entry
            for entry in (
                _entry("original", video.local_path),
                _entry("dubbed", video.dubbed_path),
                _entry("burned", video.burned_path),
            )
            if entry is not None
        ]
        video_dir = Path(video.local_path).parent if video.local_path else None
        result.append(
            VideoFiles(
                video_id=video.id,
                title=video.title,
                status=video.status.value,
                cover_url=video.cover_url,
                video_dir=str(video_dir) if video_dir else None,
                files=entries,
                total_bytes=sum(e.size_bytes for e in entries),
            )
        )
    return result


def get_storage_summary(db: Session, user_id: int) -> dict[str, object]:
    """Storage overview, including orphan files that no video points to any more."""
    entries = list_video_files(db, user_id)
    tracked_dirs = {e.video_dir for e in entries if e.video_dir}

    root = download_service.get_storage_root()
    orphan_bytes = 0
    if root.exists():
        for job_dir in root.iterdir():
            if not job_dir.is_dir():
                continue
            for video_dir in job_dir.iterdir():
                if video_dir.is_dir() and str(video_dir) not in tracked_dirs:
                    orphan_bytes += sum(
                        f.stat().st_size for f in video_dir.rglob("*") if f.is_file()
                    )

    return {
        "storage_root": str(root),
        "video_count": len(entries),
        "total_bytes": sum(e.total_bytes for e in entries),
        "orphan_bytes": orphan_bytes,
    }


def delete_variant(db: Session, video_id: int, variant: str) -> bool:
    """Delete 1 file variant, also clearing the path in the DB. Returns True if the file was deleted."""
    video = db.get(Video, video_id)
    if video is None:
        raise ValueError("Video không tồn tại")

    field_by_variant = {
        "original": "local_path",
        "dubbed": "dubbed_path",
        "burned": "burned_path",
    }
    field = field_by_variant.get(variant)
    if field is None:
        raise ValueError(f"Biến thể không hợp lệ: {variant}")

    raw_path = getattr(video, field)
    if not raw_path:
        return False

    path = Path(raw_path)
    deleted = False
    if path.exists():
        path.unlink()
        deleted = True

    setattr(video, field, None)
    # If the source file is deleted the video must return to the not-downloaded state, otherwise the UI still
    # thinks the file is there and later steps will fail when opening the file.
    if variant == "original":
        video.status = VideoStatus.QUEUED
    db.commit()
    return deleted


def delete_video_files(db: Session, video_id: int) -> int:
    """Delete the whole directory of 1 video. Returns the number of bytes freed."""
    video = db.get(Video, video_id)
    if video is None:
        raise ValueError("Video không tồn tại")
    if not video.local_path:
        return 0

    video_dir = Path(video.local_path).parent
    freed = 0
    if video_dir.exists():
        freed = sum(f.stat().st_size for f in video_dir.rglob("*") if f.is_file())
        shutil.rmtree(video_dir, ignore_errors=True)

    video.local_path = None
    video.dubbed_path = None
    video.burned_path = None
    video.status = VideoStatus.QUEUED
    db.commit()
    return freed


def delete_orphan_files(db: Session, user_id: int) -> int:
    """Delete directories no video points to any more (after deleting a record or a failed job)."""
    entries = list_video_files(db, user_id)
    tracked_dirs = {e.video_dir for e in entries if e.video_dir}

    root = download_service.get_storage_root()
    freed = 0
    if not root.exists():
        return 0

    for job_dir in root.iterdir():
        if not job_dir.is_dir():
            continue
        for video_dir in job_dir.iterdir():
            if video_dir.is_dir() and str(video_dir) not in tracked_dirs:
                freed += sum(f.stat().st_size for f in video_dir.rglob("*") if f.is_file())
                shutil.rmtree(video_dir, ignore_errors=True)
        # If a job has no videos left, also remove the empty directory.
        if not any(job_dir.iterdir()):
            job_dir.rmdir()

    return freed


def get_dashboard_stats(db: Session, user_id: int) -> dict[str, int]:
    """Count videos by pipeline progress to display on the overview page."""
    videos = db.query(Video).filter(Video.user_id == user_id).all()

    downloaded = sum(1 for v in videos if v.local_path)
    transcribed = sum(1 for v in videos if v.transcript_json)
    translated = sum(
        1
        for v in videos
        if any((s.get("translated_text") or "").strip() for s in (v.transcript_json or []))
    )
    dubbed = sum(1 for v in videos if v.dubbed_path)
    failed = sum(1 for v in videos if v.status.value.startswith("failed_"))

    entries = list_video_files(db, user_id)

    return {
        "total_videos": len(videos),
        "downloaded": downloaded,
        "transcribed": transcribed,
        "translated": translated,
        "dubbed": dubbed,
        "failed": failed,
        "total_bytes": sum(e.total_bytes for e in entries),
        "running_tasks": sum(1 for p in progress_service.snapshot() if p.is_running),
    }
