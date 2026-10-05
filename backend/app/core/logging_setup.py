"""Write the backend log to a file so it can be viewed from the UI.

The Tauri packaged build runs the backend without a console window (to avoid showing cmd when
opening the app), so nobody reads stdout/stderr any more — this file is the only place left.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import BACKEND_DIR, app_data_dir, is_frozen

LOG_FILE_NAME = "backend.log"
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 3
# uvicorn sets propagate=False on these loggers, so the root handler does not receive them.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# Requests that repeat constantly (UI polling progress, waiting for the backend, reading the log) —
# writing them all to the file would bury the lines worth reading and rotate the file very fast.
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
    """Attach a file handler to root + uvicorn. Calling it many times still attaches only once."""
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
        # Being unable to write the file (read-only disk...) must not crash the backend.
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
