import asyncio
import logging
import shutil
import time

from app.core.config import storage_dir

logger = logging.getLogger(__name__)

# Taken from config rather than assembling the path ourselves: the packaged build (Phase 12) puts storage
# in the user data directory, hard-coding `backend/storage` would make cleanup
# silently find nothing.
_STORAGE_ROOT = storage_dir()
_JOB_DIR_PATTERN = "*"  # storage/<job_id>/<video_id>/...

# Default once a day: cleaning files older than 30 days gains nothing when run more often,
# yet each run has to scan the whole storage.
CLEANUP_INTERVAL_SECONDS = 24 * 3600
DEFAULT_MAX_AGE_DAYS = 30


def cleanup_old_job_folders(max_age_days: int = 30) -> list[str]:
    """Delete job directories (`storage/<job_id>/`) older than `max_age_days` (by mtime).

    Only deletes job directories (source video, audio, dubbed, burned...) — does not touch
    `app.db`, `_zips/`, or other files/directories outside the `<number>/` pattern.
    Returns the list of deleted directories to log/show back to the user.
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


async def run_periodic_cleanup(
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    interval_seconds: float = CLEANUP_INTERVAL_SECONDS,
) -> None:
    """Cleanup loop running in the background inside the backend process itself.

    This approach is chosen over external cron/APScheduler: this tool is packaged as a
    desktop app (Phase 12) so there is no crontab to install, and APScheduler is a whole
    extra dependency for something `asyncio.sleep` can do.

    Clean RIGHT AWAY the first time, then sleep: a personal machine is often turned off/on, and waiting
    a full 24h before the first cleanup may mean it never gets its turn.
    """
    while True:
        try:
            # Scanning the whole storage is heavy disk work — push it to another thread
            # so the event loop is not blocked (every other request would freeze).
            removed = await asyncio.to_thread(cleanup_old_job_folders, max_age_days)
            if removed:
                logger.info(
                    "Dọn dẹp định kỳ: đã xoá %d thư mục job cũ (%s)",
                    len(removed),
                    ", ".join(removed),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            # A cleanup error must not be allowed to kill the loop: retry next time.
            logger.exception("Dọn dẹp định kỳ thất bại, sẽ thử lại ở chu kỳ sau")
        await asyncio.sleep(interval_seconds)
