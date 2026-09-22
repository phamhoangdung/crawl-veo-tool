import pytest

from app.services import trending_service


class TestSearchBilibiliTranslate:
    """`translate_keyword` tái dùng `crawl_service.translate_keyword_to_chinese`
    — trước đây trang Trending không có tuỳ chọn này dù trang Crawl có."""

    @staticmethod
    def _fake_results(bvids: list[str]) -> list[dict]:
        return [
            {"bvid": b, "title": f"video {b}", "author": "tác giả", "duration": "1:00", "pic": ""}
            for b in bvids
        ]

    @pytest.mark.anyio
    async def test_translates_keyword_before_searching(
        self, dummy_session: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.adapters.bilibili.client import BilibiliClient

        seen_keyword = None

        async def fake_search(self, keyword: str, page: int = 1) -> list[dict]:
            nonlocal seen_keyword
            seen_keyword = keyword
            return TestSearchBilibiliTranslate._fake_results(["BV1"])

        async def fake_translate(db: object, user_id: int, keyword: str) -> tuple[str, bool]:
            assert keyword == "ẩm thực"
            return "美食", True

        monkeypatch.setattr(BilibiliClient, "search_videos", fake_search)
        monkeypatch.setattr(
            trending_service.crawl_service, "translate_keyword_to_chinese", fake_translate
        )

        result = await trending_service.search_bilibili(
            dummy_session, 1, "ẩm thực", translate_keyword=True
        )

        assert seen_keyword == "美食"
        assert result.translation_failed is False

    @pytest.mark.anyio
    async def test_translate_off_searches_verbatim(
        self, dummy_session: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.adapters.bilibili.client import BilibiliClient

        seen_keyword = None

        async def fake_search(self, keyword: str, page: int = 1) -> list[dict]:
            nonlocal seen_keyword
            seen_keyword = keyword
            return TestSearchBilibiliTranslate._fake_results(["BV1"])

        monkeypatch.setattr(BilibiliClient, "search_videos", fake_search)

        result = await trending_service.search_bilibili(dummy_session, 1, "ẩm thực")

        assert seen_keyword == "ẩm thực"
        assert result.translation_failed is False

    @pytest.mark.anyio
    async def test_reports_translation_failure(
        self, dummy_session: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.adapters.bilibili.client import BilibiliClient

        async def fake_search(self, keyword: str, page: int = 1) -> list[dict]:
            return TestSearchBilibiliTranslate._fake_results([])

        async def fake_translate(db: object, user_id: int, keyword: str) -> tuple[str, bool]:
            return keyword, False

        monkeypatch.setattr(BilibiliClient, "search_videos", fake_search)
        monkeypatch.setattr(
            trending_service.crawl_service, "translate_keyword_to_chinese", fake_translate
        )

        result = await trending_service.search_bilibili(
            dummy_session, 1, "ẩm thực", translate_keyword=True
        )

        assert result.translation_failed is True


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
