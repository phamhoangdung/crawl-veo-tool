import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent / "storage"
_JOB_DIR_PATTERN = "*"  # storage/<job_id>/<video_id>/...


def cleanup_old_job_folders(max_age_days: int = 30) -> list[str]:
    """Xoá thư mục job (`storage/<job_id>/`) cũ hơn `max_age_days` (tính theo mtime).

    Chỉ xoá thư mục job (video gốc, audio, dubbed, burned...) — không đụng tới
    `app.db`, `_zips/`, hay các file/thư mục khác nằm ngoài pattern `<số>/`.
    Trả về danh sách thư mục đã xoá để log/hiển thị lại cho người dùng.
    """
    if not _STORAGE_ROOT.exists():
        return []

    cutoff = time.time() - (max_age_days * 86400)
    removed: list[str] = []
    for job_dir in _STORAGE_ROOT.glob(_JOB_DIR_PATTERN):
        if not job_dir.is_dir() or not job_dir.name.isdigit():
            continue
        if job_dir.stat().st_mtime < cutoff:
            shutil.rmtree(job_dir, ignore_errors=True)
            removed.append(job_dir.name)
            logger.info("Removed stale job folder: %s", job_dir)
    return removed


def get_storage_usage_bytes() -> int:
    if not _STORAGE_ROOT.exists():
        return 0
    return sum(f.stat().st_size for f in _STORAGE_ROOT.rglob("*") if f.is_file())
