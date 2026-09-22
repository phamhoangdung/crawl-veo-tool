"""Phase 21 — chặn cứng khoảng hợp lệ NGAY Ở SCHEMA (`Field(ge, le)`), không
phụ thuộc UI chặn. Test ở tầng schema (không dùng TestClient — codebase này
chưa có pattern đó, xem docs/conventions.md) vẫn xác nhận đúng validation sẽ
chạy trước khi payload chạm tới service."""

import pytest
from pydantic import ValidationError

from app.api.settings import AppSettingsUpdate


class TestDownloadConnectionsBounds:
    @pytest.mark.parametrize("value", [1, 4, 8])
    def test_accepts_valid_range(self, value: int) -> None:
        AppSettingsUpdate(download_connections=value)

    @pytest.mark.parametrize("value", [0, -1, 9, 100])
    def test_rejects_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError):
            AppSettingsUpdate(download_connections=value)


class TestDownloadMaxVideosBounds:
    @pytest.mark.parametrize("value", [1, 5, 10])
    def test_accepts_valid_range(self, value: int) -> None:
        AppSettingsUpdate(download_max_videos=value)

    @pytest.mark.parametrize("value", [0, -1, 11, 100])
    def test_rejects_out_of_range(self, value: int) -> None:
        with pytest.raises(ValidationError):
            AppSettingsUpdate(download_max_videos=value)


def test_both_fields_optional_none_is_valid() -> None:
    """`PUT` chỉ đổi 1 field vẫn hợp lệ — không bắt buộc gửi cả 2."""
    AppSettingsUpdate()
