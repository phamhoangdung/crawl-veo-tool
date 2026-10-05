import pytest

from app.schemas.job import SelectedVideo
from app.services import crawl_service


class TestLooksChinese:
    """A keyword that is already Chinese is not translated again — avoids a spare API call."""

    @pytest.mark.parametrize("text", ["美食", "美食 vlog", "中国菜"])
    def test_detects_chinese(self, text: str) -> None:
        assert crawl_service._looks_chinese(text) is True

    @pytest.mark.parametrize("text", ["ẩm thực", "food", "", "vlog 2024"])
    def test_rejects_non_chinese(self, text: str) -> None:
        assert crawl_service._looks_chinese(text) is False


class TestNormalizeCoverUrl:
    """The search API returns an image missing the scheme ('//i2.hdslb.com/...') — it must be forced to https."""

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
        """The cache is a module-level dict (see crawl_service) — clear it between tests so nothing leaks."""
        crawl_service._keyword_translation_cache.clear()

    @pytest.fixture
    def real_db(self):
        """The keyword cache now lives in the DB (durable across restarts) so a real session is needed."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        import app.models  # noqa: F401
        from app.core.db import Base
        from app.models.user import User

        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        session.add(User(id=1))
        session.commit()
        yield session
        session.close()

    @pytest.mark.anyio
    async def test_caches_successful_translation(
        self, real_db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Once translated, later calls use the cache without calling the API again — saves quota & avoids the rate limit."""
        call_count = 0

        async def fake_translate(*args: object, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            return "美食"

        monkeypatch.setattr(crawl_service.translate_service, "translate_text", fake_translate)

        first = await crawl_service.translate_keyword_to_chinese(real_db, 1, "ẩm thực")
        second = await crawl_service.translate_keyword_to_chinese(real_db, 1, "ẩm thực")

        assert first == ("美食", True)
        assert second == ("美食", True)
        assert call_count == 1

    @pytest.mark.anyio
    async def test_translation_survives_restart(
        self, real_db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A translated keyword must survive a restart — the RAM cache is lost, the DB cache is not."""
        call_count = 0

        async def fake_translate(*args: object, **kwargs: object) -> str:
            nonlocal call_count
            call_count += 1
            return "美食"

        monkeypatch.setattr(crawl_service.translate_service, "translate_text", fake_translate)

        await crawl_service.translate_keyword_to_chinese(real_db, 1, "ẩm thực")
        # Simulate a restart: the in-RAM cache disappears.
        crawl_service._keyword_translation_cache.clear()
        result = await crawl_service.translate_keyword_to_chinese(real_db, 1, "ẩm thực")

        assert result == ("美食", True)
        assert call_count == 1, "phải lấy từ cache DB, không gọi lại API"

        from app.models.translation_cache import TranslationCache

        assert real_db.query(TranslationCache).count() == 1

    @pytest.mark.anyio
    async def test_skips_translation_when_already_chinese(self, dummy_session: object) -> None:
        assert await crawl_service.translate_keyword_to_chinese(dummy_session, 1, "美食") == ("美食", True)

    @pytest.mark.anyio
    async def test_falls_back_to_original_on_failure(
        self, dummy_session: object, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed translation must not kill the job — searching verbatim beats not searching."""

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


class TestSearchReturnsFullResults:
    """The search result must be EXACTLY what Bilibili returned — videos already in the
    library still show, only marked so they are not downloaded again."""

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
        # The video needs a NOT NULL job_id — the old job represents the previous crawl.
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

        # 2 of the 3 videos are already in the library.
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
            return TestSearchReturnsFullResults._fake_results(["BV1", "BV2", "BV3"])

        monkeypatch.setattr(BilibiliClient, "search_videos", fake_search)

        job = await crawl_service.create_bilibili_crawl_job(db, 1, "匹克球")

        assert job.total_found == 3
        assert job.already_in_library == 2
        # All 3 show, none filtered out.
        assert len(job.result_videos) == 3
        marked = [v.platform_video_id for v in job.result_videos if v.already_in_library]
        assert sorted(marked) == ["BV1", "BV2"]

    @pytest.mark.anyio
    async def test_all_existing_still_shows_every_video(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The case users hit: previously it found 20 videos but showed 0."""
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
            return TestSearchReturnsFullResults._fake_results(bvids)

        monkeypatch.setattr(BilibiliClient, "search_videos", fake_search)

        job = await crawl_service.create_bilibili_crawl_job(db, 1, "匹克球")

        # All 20 videos show, no more coming out as 0.
        assert len(job.result_videos) == 20
        assert job.total_found == 20
        assert job.already_in_library == 20
        assert all(v.already_in_library for v in job.result_videos)
        # No duplicate record added (the table has a UniqueConstraint).
        from app.models.video import Video

        assert db.query(Video).count() == 20

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
        assert job.already_in_library == 0
        assert job.result_videos == []


class TestCreateJobFromSelection:
    """Phase 20 — bulk selection on the Discovery screen. Previously an existing video
    was skipped with `continue` and dropped from the returned result; now it must return the FULL
    selected list (like `create_bilibili_crawl_job`) so the router knows exactly which
    videos need a background download."""

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
        session.add(
            Job(id=99, user_id=1, platform=Platform.BILIBILI, keyword="lần trước", status=JobStatus.COMPLETED)
        )
        session.commit()
        yield session
        session.close()

    @staticmethod
    def _selected(bvids: list[str]) -> list[SelectedVideo]:
        return [
            SelectedVideo(bvid=b, title=f"video {b}", author_name="tác giả", duration_seconds=60)
            for b in bvids
        ]

    @pytest.mark.anyio
    async def test_returns_new_and_existing_videos_in_order(self, db) -> None:
        from app.models.job import Platform
        from app.models.video import Video, VideoStatus

        db.add(
            Video(
                user_id=1,
                job_id=99,
                platform=Platform.BILIBILI,
                platform_video_id="BV1",
                title="đã có",
                source_url="https://e.com",
                status=VideoStatus.DOWNLOADED,
            )
        )
        db.commit()

        job = await crawl_service.create_job_from_selection(
            db, 1, self._selected(["BV1", "BV2", "BV3"])
        )

        # All 3 are present, including BV1 which already existed — previously it was skipped.
        assert [v.platform_video_id for v in job.result_videos] == ["BV1", "BV2", "BV3"]
        assert job.result_videos[0].already_in_library is True
        assert job.result_videos[1].already_in_library is False
        assert job.result_videos[2].already_in_library is False
        # No duplicate for an existing video (UniqueConstraint platform+platform_video_id).
        assert db.query(Video).filter(Video.platform_video_id == "BV1").count() == 1

    @pytest.mark.anyio
    async def test_new_videos_start_as_queued(self, db) -> None:
        from app.models.video import VideoStatus

        job = await crawl_service.create_job_from_selection(db, 1, self._selected(["BV9"]))

        assert job.result_videos[0].status == VideoStatus.QUEUED
        assert job.result_videos[0].local_path is None
