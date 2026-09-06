import pytest


@pytest.fixture
def dummy_session():
    """Session giả cho test không thực sự chạm DB (chỉ cần truyền qua các hàm bị mock)."""
    return object()
