"""Phase 21 — hard-limit the valid range RIGHT AT THE SCHEMA (`Field(ge, le)`), not
depending on the UI limiting it. Tested at the schema layer (no TestClient — this codebase
has no such pattern yet, see docs/conventions.md) it still confirms that exactly the validation
runs before the payload reaches the service."""

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
    """`PUT` changing only 1 field is still valid — sending both is not required."""
    AppSettingsUpdate()
