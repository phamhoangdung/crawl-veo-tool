import pytest

from app.services import trending_service


class TestParseDuration:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("7:10", 430),
            ("1:02:03", 3723),
            (600, 600),
            ("600", 600),
            (None, None),
            ("không phải số", None),
        ],
    )
    def test_parses(self, raw: object, expected: int | None) -> None:
        assert trending_service._parse_duration_to_seconds(raw) == expected


class TestNormalizeCoverUrl:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("//i2.hdslb.com/a.jpg", "https://i2.hdslb.com/a.jpg"),
            ("http://i2.hdslb.com/a.jpg", "https://i2.hdslb.com/a.jpg"),
            ("https://i2.hdslb.com/a.jpg", "https://i2.hdslb.com/a.jpg"),
            (None, None),
            ("", None),
        ],
    )
    def test_normalizes(self, raw: str | None, expected: str | None) -> None:
        assert trending_service._normalize_cover_url(raw) == expected
