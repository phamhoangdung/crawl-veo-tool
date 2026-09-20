import pytest


@pytest.fixture
def dummy_session():
    """Session giả cho test không thực sự chạm DB (chỉ cần truyền qua các hàm bị mock)."""
    return object()


class _ImmediateFuture:
    """`Future` giả chạy hàm ngay trong process test, đồng bộ."""

    def __init__(self, value):
        self._value = value

    def result(self):
        return self._value


@pytest.fixture(autouse=True)
def _fake_worker_pool(monkeypatch: pytest.MonkeyPatch):
    """Không test nào được thật sự spawn process pool (`app.core.worker_pool`,
    Phase: tối ưu hiệu năng P2) — chậm/flaky, và `monkeypatch` không xuyên được
    sang process con (worker sẽ import module gốc, không thấy bản đã mock).
    Chạy hàm trực tiếp trong process test thay vì gửi sang pool thật, giữ
    nguyên hành vi mock ở từng test (`monkeypatch.setattr(module, "func", ...)`
    vẫn có tác dụng vì hàm được resolve tại thời điểm gọi, cùng process)."""
    from app.core import worker_pool

    monkeypatch.setattr(
        worker_pool,
        "submit",
        lambda func, *args, **kwargs: _ImmediateFuture(func(*args, **kwargs)),
    )
