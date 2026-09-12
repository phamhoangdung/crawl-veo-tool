import asyncio
import logging
import shutil
import time

from app.core.config import _storage_dir

logger = logging.getLogger(__name__)

# Lấy từ config chứ không tự ghép đường dẫn: bản đóng gói (Phase 12) để storage
# trong thư mục dữ liệu người dùng, hard-code `backend/storage` sẽ khiến dọn dẹp
# im lặng không tìm thấy gì.
_STORAGE_ROOT = _storage_dir()
_JOB_DIR_PATTERN = "*"  # storage/<job_id>/<video_id>/...

# Mặc định 1 ngày/lần: dọn file quá 30 ngày thì chạy dày hơn cũng không dọn thêm
# được gì, mà mỗi lần chạy phải quét toàn bộ storage.
CLEANUP_INTERVAL_SECONDS = 24 * 3600
DEFAULT_MAX_AGE_DAYS = 30


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


async def run_periodic_cleanup(
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    interval_seconds: float = CLEANUP_INTERVAL_SECONDS,
) -> None:
    """Vòng lặp dọn dẹp chạy nền trong chính process backend.

    Chọn cách này thay vì cron ngoài/APScheduler: tool này được đóng gói thành
    desktop app (Phase 12) nên không có crontab để cài, còn APScheduler là thêm
    hẳn một dependency cho đúng một việc mà `asyncio.sleep` làm được.

    Chạy dọn NGAY lần đầu rồi mới ngủ: máy cá nhân thường tắt/mở liên tục, đợi
    đủ 24h mới dọn lần đầu thì có khi không bao giờ tới lượt.
    """
    while True:
        try:
            # Quét toàn bộ storage là việc chạm đĩa nặng — đẩy sang thread khác
            # để không chặn event loop (mọi request khác sẽ đứng hình).
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
            # Lỗi dọn dẹp không được phép giết vòng lặp: lần sau thử lại.
            logger.exception("Dọn dẹp định kỳ thất bại, sẽ thử lại ở chu kỳ sau")
        await asyncio.sleep(interval_seconds)
