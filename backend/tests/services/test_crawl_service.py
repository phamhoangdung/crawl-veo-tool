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
    @pytest.fixture(autouse=True)
    def _clear_keyword_cache(self) -> None:
        """Cache là dict module-level (xem crawl_service) — dọn giữa các test để không rò rỉ."""
        crawl_service._keyword_translation_cache.clear()

    @pytest.mark.anyio
    async def test_caches_successful_translation(
        self, dummy_session: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dịch xong 1 lần thì lần sau dùng cache, không gọi lại API — đỡ tốn quota & đỡ rate limit."""
        call_count = 0

        async def fake_translate(*args: object, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            return "美食"

        monkeypatch.setattr(crawl_service.translate_service, "translate_text", fake_translate)

        first = await crawl_service.translate_keyword_to_chinese(dummy_session, 1, "ẩm thực")
        second = await crawl_service.translate_keyword_to_chinese(dummy_session, 1, "ẩm thực")

        assert first == ("美食", True)
        assert second == ("美食", True)
        assert call_count == 1

    @pytest.mark.anyio
    async def test_skips_translation_when_already_chinese(self, dummy_session: object) -> None:
        assert await crawl_service.translate_keyword_to_chinese(dummy_session, 1, "美食") == ("美食", True)

    @pytest.mark.anyio
    async def test_falls_back_to_original_on_failure(
        self, dummy_session: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dịch hỏng không được làm chết cả job — search nguyên văn còn hơn không search."""

        async def boom(*args: object, **kwargs: object) -> str:
            raise RuntimeError("provider down")

        monkeypatch.setattr(crawl_service.translate_service, "translate_text", boom)
        result = await crawl_service.translate_keyword_to_chinese(dummy_session, 1, "ẩm thực")
        assert result == ("ẩm thực", False)

    @pytest.mark.anyio
    async def test_falls_back_when_translation_is_blank(
        self, dummy_session: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def blank(*args: object, **kwargs: object) -> str:
            return "   "

        monkeypatch.setattr(crawl_service.translate_service, "translate_text", blank)
        result = await crawl_service.translate_keyword_to_chinese(dummy_session, 1, "ẩm thực")
        assert result == ("ẩm thực", False)


class TestSkippedExistingCount:
    """Bilibili trả gần như cùng một tập video mỗi lần tìm. Khi đã tải hết,
    job mới ra 0 video — không đếm số bị lọc thì UI báo "0 video" y như bị chặn."""

    @pytest.fixture
    def db(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        import app.models  # noqa: F401
        from app.core.db import Base
        from app.models.job import Job, JobStatus, Platform
        from app.models.user import User

        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        session.add(User(id=1))
        session.commit()
        # Video cần job_id NOT NULL — job cũ đại diện cho lần crawl trước.
        session.add(
            Job(
                id=99,
                user_id=1,
                platform=Platform.BILIBILI,
                keyword="lần trước",
                status=JobStatus.COMPLETED,
            )
        )
        session.commit()
        yield session
        session.close()

    @staticmethod
    def _fake_results(bvids: list[str]) -> list[dict]:
        return [
            {"bvid": b, "title": f"video {b}", "author": "tác giả", "duration": "1:00", "pic": ""}
            for b in bvids
        ]

    @pytest.mark.anyio
    async def test_counts_videos_already_in_db(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.adapters.bilibili.client import BilibiliClient
        from app.models.job import Platform
        from app.models.video import Video, VideoStatus

        # 2 trong 3 video đã có sẵn trong thư viện.
        for bvid in ("BV1", "BV2"):
            db.add(
                Video(
                    user_id=1,
                    job_id=99,
                    platform=Platform.BILIBILI,
                    platform_video_id=bvid,
                    title="đã có",
                    source_url="https://e.com",
                    status=VideoStatus.DONE,
                )
            )
        db.commit()

        async def fake_search(self, keyword: str, page: int = 1) -> list[dict]:
            return TestSkippedExistingCount._fake_results(["BV1", "BV2", "BV3"])

        monkeypatch.setattr(BilibiliClient, "search_videos", fake_search)

        job = await crawl_service.create_bilibili_crawl_job(db, 1, "匹克球")

        assert job.total_found == 3
        assert job.skipped_existing == 2
        assert len(job.videos) == 1

    @pytest.mark.anyio
    async def test_all_existing_gives_zero_new_but_reports_total(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Đây đúng là ca người dùng gặp: tìm ra 20 video mà hiện 0."""
        from app.adapters.bilibili.client import BilibiliClient
        from app.models.job import Platform
        from app.models.video import Video, VideoStatus

        bvids = [f"BV{i}" for i in range(20)]
        for bvid in bvids:
            db.add(
                Video(
                    user_id=1,
                    job_id=99,
                    platform=Platform.BILIBILI,
                    platform_video_id=bvid,
                    title="đã có",
                    source_url="https://e.com",
                    status=VideoStatus.DONE,
                )
            )
        db.commit()

        async def fake_search(self, keyword: str, page: int = 1) -> list[dict]:
            return TestSkippedExistingCount._fake_results(bvids)

        monkeypatch.setattr(BilibiliClient, "search_videos", fake_search)

        job = await crawl_service.create_bilibili_crawl_job(db, 1, "匹克球")

        assert len(job.videos) == 0
        # Hai số này là thứ phân biệt "đã tải hết" với "không tìm thấy gì".
        assert job.total_found == 20
        assert job.skipped_existing == 20

    @pytest.mark.anyio
    async def test_genuinely_empty_search_reports_zero_skipped(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.adapters.bilibili.client import BilibiliClient

        async def fake_search(self, keyword: str, page: int = 1) -> list[dict]:
            return []

        monkeypatch.setattr(BilibiliClient, "search_videos", fake_search)

        job = await crawl_service.create_bilibili_crawl_job(db, 1, "từ khoá vô nghĩa")

        assert job.total_found == 0
        assert job.skipped_existing == 0
