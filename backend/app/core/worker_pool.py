"""Dedicated process pool for pure CPU/GPU compute (faster-whisper, SpeechBrain
diarization) — separated from the main server process (Phase: performance optimization P2).

ONLY put PURE functions here (no DB session, no `progress_service` calls):
workers run in a child process and share no memory with the parent — any state
in `progress_service` (module-level dict) or a SQLAlchemy `Session` can NOT
cross processes. ffmpeg/Demucs do NOT need to go here: both already run as
their own subprocess (`subprocess.run`), so they were already separated from the Python process —
wrapping them in a process pool would only add serialization cost without adding any
isolation (see docs/performance-optimization/plan.md, section P2).
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
    """Send a heavy compute function to the process pool, returning a `Future`.

    Safe to call `.result()` (blocking) right after — callers of `submit` are always in
    a background thread (Starlette threadpool or `asyncio.to_thread`), not the main
    event loop thread, so blocking here does not affect the server.
    """
    pool = get_pool()
    future = pool.submit(func, *args, **kwargs)
    future.add_done_callback(lambda done: _discard_if_broken(pool, done))
    return future


def _discard_if_broken(pool: ProcessPoolExecutor, future: "Future[Any]") -> None:
    """A worker dying abruptly (out of RAM, native crash) breaks the pool permanently — every
    later `submit` fails until the app restarts. Drop the broken pool so the next call
    creates a new one; the user only has to run the action again."""
    global _pool
    if not future.cancelled() and isinstance(future.exception(), BrokenProcessPool):
        if _pool is pool:
            _pool = None
        pool.shutdown(wait=False)


def shutdown() -> None:
    """Call on app shutdown — do not leave orphan worker processes (see `app/main.py`)."""
    global _pool
    if _pool is not None:
        _pool.shutdown(wait=False, cancel_futures=False)
        _pool = None
