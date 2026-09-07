"""Quản lý file đã tải: liệt kê, tính dung lượng, xoá.

Tool chạy local nên người dùng cần thấy file thật đang chiếm bao nhiêu đĩa và
xoá được thứ không cần nữa — khác với web app nơi file nằm trên server.
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
    """Mọi video đã có ít nhất 1 file trên đĩa, kèm dung lượng thật."""
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
    """Tổng quan dung lượng, gồm cả file mồ côi không còn video nào trỏ tới."""
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
    """Xoá 1 biến thể file, xoá cả đường dẫn trong DB. Trả về True nếu đã xoá file."""
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
    # Xoá file gốc thì video phải quay về trạng thái chưa tải, nếu không UI vẫn
    # tưởng file còn đó và các bước sau sẽ lỗi khi mở file.
    if variant == "original":
        video.status = VideoStatus.QUEUED
    db.commit()
    return deleted


def delete_video_files(db: Session, video_id: int) -> int:
    """Xoá toàn bộ thư mục của 1 video. Trả về số byte đã giải phóng."""
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
    """Xoá thư mục không còn video nào trỏ tới (do xoá bản ghi hoặc job lỗi)."""
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
        # Job không còn video nào thì bỏ luôn thư mục rỗng.
        if not any(job_dir.iterdir()):
            job_dir.rmdir()

    return freed


def get_dashboard_stats(db: Session, user_id: int) -> dict[str, int]:
    """Đếm video theo tiến độ pipeline để hiển thị ở trang tổng quan."""
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
