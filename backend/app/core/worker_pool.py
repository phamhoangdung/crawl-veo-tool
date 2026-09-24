"""Process pool riêng cho compute thuần CPU/GPU (faster-whisper, SpeechBrain
diarization) — tách khỏi process server chính (Phase: tối ưu hiệu năng P2).

CHỈ đưa vào đây hàm THUẦN (không đụng DB session, không gọi `progress_service`):
worker chạy trong process con, không chia sẻ bộ nhớ với process cha — mọi state
trong `progress_service` (dict module-level) hay SQLAlchemy `Session` đều KHÔNG
xuyên process được. ffmpeg/Demucs KHÔNG cần đưa vào đây: cả hai đã tự chạy dưới
dạng subprocess riêng (`subprocess.run`) nên đã tách khỏi process Python từ
trước — bọc thêm process pool chỉ tổ tốn chi phí serialize mà không tăng cách
ly gì thêm (xem docs/performance-optimization/plan.md mục P2).
"""

from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from typing import Any, TypeVar

from app.core.config import get_settings

_T = TypeVar("_T")

_pool: ProcessPoolExecutor | None = None


def get_pool() -> ProcessPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=get_settings().cpu_worker_count)
    return _pool


def submit(func: Callable[..., _T], /, *args: Any, **kwargs: Any) -> "Future[_T]":
    """Gửi 1 hàm compute nặng sang process pool, trả về `Future`.

    An toàn gọi `.result()` (chặn) ngay sau đó — hàm gọi `submit` luôn đã ở
    trong 1 thread nền (Starlette threadpool hoặc `asyncio.to_thread`), không
    phải thread của event loop chính, nên chặn ở đây không ảnh hưởng server.
    """
    pool = get_pool()
    future = pool.submit(func, *args, **kwargs)
    future.add_done_callback(lambda done: _discard_if_broken(pool, done))
    return future


def _discard_if_broken(pool: ProcessPoolExecutor, future: "Future[Any]") -> None:
    """Worker chết đột ngột (hết RAM, crash native) làm pool hỏng vĩnh viễn — mọi
    lần `submit` sau đều lỗi cho tới khi khởi động lại app. Bỏ pool hỏng để lần gọi
    kế tiếp tạo pool mới, người dùng chỉ cần bấm chạy lại."""
    global _pool
    if not future.cancelled() and isinstance(future.exception(), BrokenProcessPool):
        if _pool is pool:
            _pool = None
        pool.shutdown(wait=False)


def shutdown() -> None:
    """Gọi khi tắt app — không để worker process mồ côi (xem `app/main.py`)."""
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=False)
        _pool = None
