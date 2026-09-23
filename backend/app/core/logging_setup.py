"""Ghi nhật ký backend ra file để xem lại từ giao diện.

Bản đóng gói Tauri chạy backend không kèm cửa sổ console (tránh hiện cmd khi mở
app) nên stdout/stderr không còn ai đọc — file này là nơi duy nhất còn lại.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import BACKEND_DIR, app_data_dir, is_frozen

LOG_FILE_NAME = "backend.log"
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 3
# uvicorn đặt propagate=False cho các logger này, nên root handler không nhận được.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# Các request lặp liên tục (giao diện poll tiến độ, chờ backend, tự đọc nhật ký) —
# ghi hết vào file thì lấp mất dòng đáng đọc và làm file xoay vòng rất nhanh.
_NOISY_ACCESS_PATHS = (
    "GET /health ",
    "/api/downloads/progress",
    "/api/downloads/stream",
    "/api/system/logs",
)

_handler: RotatingFileHandler | None = None


class _AccessNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "uvicorn.access":
            return True
        message = record.getMessage()
        return not any(path in message for path in _NOISY_ACCESS_PATHS)


def log_file_path() -> Path:
    base = app_data_dir() if is_frozen() else BACKEND_DIR / "storage"
    return base / "logs" / LOG_FILE_NAME


def setup_file_logging() -> None:
    """Gắn handler ghi file vào root + uvicorn. Gọi nhiều lần vẫn chỉ gắn một lần."""
    global _handler
    if _handler is not None:
        return
    path = log_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
    except OSError:
        # Không ghi được file (ổ đĩa chỉ đọc...) không được làm sập backend.
        return
    handler.addFilter(_AccessNoiseFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(min(root.level or logging.INFO, logging.INFO))
    for logger in (root, *(logging.getLogger(n) for n in _UVICORN_LOGGERS)):
        logger.addHandler(handler)
    _handler = handler
