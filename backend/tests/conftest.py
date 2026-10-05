import pytest


@pytest.fixture
def dummy_session():
    """Fake session for tests that do not really touch the DB (only needs to be passed through mocked functions)."""
    return object()


class _ImmediateFuture:
    """A fake `Future` running the function right in the test process, synchronously."""

    def __init__(self, value):
        self._value = value

    def result(self):
        return self._value


@pytest.fixture(autouse=True)
def _fake_worker_pool(monkeypatch: pytest.MonkeyPatch):
    """No test may really spawn a process pool (`app.core.worker_pool`,
    Phase: performance optimization P2) — slow/flaky, and `monkeypatch` does not reach
    into the child process (the worker would import the original module, not seeing the mocked version).
    Run the function directly in the test process instead of sending it to a real pool, keeping
    the mock behavior of each test (`monkeypatch.setattr(module, "func", ...)`
    still takes effect because the function is resolved at call time, in the same process)."""
    from app.core import worker_pool

    monkeypatch.setattr(
        worker_pool,
        "submit",
        lambda func, *args, **kwargs: _ImmediateFuture(func(*args, **kwargs)),
    )
