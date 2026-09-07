import pytest

from app.services import crawl_service


class TestLooksChinese:
    """Từ khoá đã là tiếng Trung thì không dịch lại — tránh gọi API thừa."""

    @pytest.mark.parametrize("text", ["美食", "美食 vlog", "中国菜"])
    def test_detects_chinese(self, text: str) -> None:
        assert crawl_service._looks_chinese(text) is True

    @pytest.mark.parametrize("text", ["ẩm thực", "food", "", "vlog 2024"])
    def test_rejects_non_chinese(self, text: str) -> None:
        assert crawl_service._looks_chinese(text) is False


class TestNormalizeCoverUrl:
    """Search API trả ảnh thiếu scheme ('//i2.hdslb.com/...') — phải ép về https."""

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
        assert crawl_service._normalize_cover_url(raw) == expected


class TestTranslateKeywordToChinese:
    @pytest.mark.anyio
    async def test_skips_translation_when_already_chinese(self, dummy_session: object) -> None:
        assert await crawl_service.translate_keyword_to_chinese(dummy_session, 1, "美食") == "美食"

    @pytest.mark.anyio
    async def test_falls_back_to_original_on_failure(
        self, dummy_session: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dịch hỏng không được làm chết cả job — search nguyên văn còn hơn không search."""

        async def boom(*args: object, **kwargs: object) -> str:
            raise RuntimeError("provider down")

        monkeypatch.setattr(crawl_service.translate_service, "translate_text", boom)
        result = await crawl_service.translate_keyword_to_chinese(dummy_session, 1, "ẩm thực")
        assert result == "ẩm thực"

    @pytest.mark.anyio
    async def test_falls_back_when_translation_is_blank(
        self, dummy_session: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def blank(*args: object, **kwargs: object) -> str:
            return "   "

        monkeypatch.setattr(crawl_service.translate_service, "translate_text", blank)
        result = await crawl_service.translate_keyword_to_chinese(dummy_session, 1, "ẩm thực")
        assert result == "ẩm thực"
