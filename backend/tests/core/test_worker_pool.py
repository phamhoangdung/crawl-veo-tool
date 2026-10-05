import os
from concurrent.futures.process import BrokenProcessPool

import pytest
from app.core import worker_pool


@pytest.fixture(autouse=True)
def _fake_worker_pool():
    """Shadows the global fake fixture of the same name (`conftest.py`, same name so pytest
    prefers the one in this module) — this file tests the real process pool itself
    (Phase: performance optimization P2), not the synchronous mock version."""
    yield
    worker_pool.shutdown()


def _square(x: int) -> int:
    """Module-level: `ProcessPoolExecutor` needs a function picklable by import path,
    nested functions/lambdas would fail."""
    return x * x


def _die() -> None:
    os._exit(1)


def _add(a: int, b: int = 0) -> int:
    return a + b


class TestSubmit:
    def test_submit_runs_and_returns_result(self) -> None:
        future = worker_pool.submit(_square, 7)
        assert future.result(timeout=60) == 49

    def test_pool_is_reused_across_submits(self) -> None:
        pool_first = worker_pool.get_pool()
        worker_pool.submit(_square, 2).result(timeout=60)
        pool_second = worker_pool.get_pool()
        assert pool_first is pool_second

    def test_pool_recreated_after_worker_dies(self) -> None:
        with pytest.raises(BrokenProcessPool):
            worker_pool.submit(_die).result(timeout=60)
        # The callback runs right after the future completes; the next call must use a new pool.
        assert worker_pool.submit(_square, 5).result(timeout=60) == 25

    def test_kwargs_forwarded(self) -> None:
        future = worker_pool.submit(_add, 3, b=4)
        assert future.result(timeout=60) == 7
