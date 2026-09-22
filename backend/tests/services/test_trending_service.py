import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.job import Job, JobStatus, Platform
from app.models.user import User
from app.models.video import Video, VideoStatus
from app.services import trending_service


@pytest.fixture
def db_session():
    """Session DB thật (SQLite in-memory) — `_attach_library_status` (Phase 20)
    chạy query thật nên `dummy_session` (chỉ là `object()`) không còn đủ cho
    các test gọi `search_bilibili`/`get_category_page`/`get_bilibili_popular_page`."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


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
        self, db_session, monkeypatch: pytest.MonkeyPatch
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
            db_session, 1, "ẩm thực", translate_keyword=True
        )

        assert seen_keyword == "美食"
        assert result.translation_failed is False

    @pytest.mark.anyio
    async def test_translate_off_searches_verbatim(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.adapters.bilibili.client import BilibiliClient

        seen_keyword = None

        async def fake_search(self, keyword: str, page: int = 1) -> list[dict]:
            nonlocal seen_keyword
            seen_keyword = keyword
            return TestSearchBilibiliTranslate._fake_results(["BV1"])

        monkeypatch.setattr(BilibiliClient, "search_videos", fake_search)

        result = await trending_service.search_bilibili(db_session, 1, "ẩm thực")

        assert seen_keyword == "ẩm thực"
        assert result.translation_failed is False

    @pytest.mark.anyio
    async def test_reports_translation_failure(
        self, db_session, monkeypatch: pytest.MonkeyPatch
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
            db_session, 1, "ẩm thực", translate_keyword=True
        )

        assert result.translation_failed is True


class TestAttachLibraryStatus:
    """Phase 20 — màn Khám phá cần biết video nào đã tải để hiện badge/link
    'Video của tôi' ngay trên thẻ, không phải đoán qua bvid ở frontend."""

    def test_marks_existing_video_and_leaves_others_untouched(self, db_session) -> None:
        db_session.add(User(id=1))
        db_session.flush()
        job = Job(
            user_id=1, platform=Platform.BILIBILI, keyword="test", status=JobStatus.COMPLETED
        )
        db_session.add(job)
        db_session.flush()
        db_session.add(
            Video(
                user_id=1,
                job_id=job.id,
                platform=Platform.BILIBILI,
                platform_video_id="BV1",
                title="đã có trong thư viện",
                source_url="https://www.bilibili.com/video/BV1",
                status=VideoStatus.DOWNLOADED,
            )
        )
        db_session.commit()

        videos = [
            trending_service.TrendingVideoRead(bvid="BV1", title="video 1"),
            trending_service.TrendingVideoRead(bvid="BV2", title="video 2"),
        ]
        trending_service._attach_library_status(db_session, videos)

        assert videos[0].already_in_library is True
        assert videos[0].video_id is not None
        assert videos[1].already_in_library is False
        assert videos[1].video_id is None

    def test_empty_list_does_not_query(self, db_session) -> None:
        # Không raise dù chưa có gì trong DB — bảo vệ nhánh rỗng (search 0 kết quả).
        trending_service._attach_library_status(db_session, [])


class TestAttachChannelInfo:
    """Phase 22 — ghi nhận kênh vừa thấy + gắn `channel_is_followed`."""

    def test_upserts_channel_and_marks_followed(self, db_session) -> None:
        from app.models.channel import Channel
        from app.services import channel_service

        channel_service.follow(db_session, Platform.BILIBILI, "42", "Kênh đã theo dõi")

        videos = [
            trending_service.TrendingVideoRead(
                bvid="BV1", title="v1", author_name="Kênh đã theo dõi", channel_id="42"
            ),
            trending_service.TrendingVideoRead(
                bvid="BV2", title="v2", author_name="Kênh chưa từng thấy", channel_id="99"
            ),
        ]
        trending_service._attach_channel_info(db_session, videos)

        assert videos[0].channel_is_followed is True
        assert videos[1].channel_is_followed is False
        # Kênh 99 chưa từng thấy trước đó phải được ghi nhận mới (upsert_seen_batch).
        assert db_session.query(Channel).filter(Channel.channel_id == "99").count() == 1

    def test_videos_without_channel_id_are_skipped(self, db_session) -> None:
        videos = [trending_service.TrendingVideoRead(bvid="BV1", title="v1", channel_id=None)]
        # Không raise dù không có channel_id nào để upsert.
        trending_service._attach_channel_info(db_session, videos)
        assert videos[0].channel_is_followed is False


class TestRunPeriodicSnapshot:
    """Phase 20 — ghi snapshot chuyên mục đều đặn, tách khỏi việc ai đó có mở
    trang Báo cáo xu hướng hay không (trước đây lịch sử chỉ dày lên khi có
    người mở `GET /stats`)."""

    @pytest.mark.anyio
    async def test_writes_snapshot_for_followed_categories_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.models.category import Category

        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        with session_factory() as db:
            db.add(Category(rid=21, name_zh="日常", is_followed=True))
            db.add(Category(rid=99, name_zh="不追踪", is_followed=False))
            db.commit()

        calls: list[list[int]] = []

        async def fake_get_categories_stats(db, rids, day=3, save_history=True):
            calls.append(rids)
            assert save_history is True
            return []

        monkeypatch.setattr(
            trending_service, "get_categories_stats", fake_get_categories_stats
        )

        # Vòng lặp chạy vô hạn — raise CancelledError ngay ở lần ngủ đầu tiên
        # để dừng sau đúng 1 vòng (checkpoint thật, không phụ thuộc lịch chạy
        # của event loop như gọi `task.cancel()` từ trong 1 coroutine không
        # await gì — coroutine đó không bao giờ nhường lại quyền điều khiển).
        async def raise_cancelled(*a, **k):
            raise asyncio.CancelledError

        monkeypatch.setattr(trending_service.asyncio, "sleep", raise_cancelled)

        with pytest.raises(asyncio.CancelledError):
            await trending_service.run_periodic_snapshot(session_factory, interval_seconds=999)

        assert calls == [[21]]

    @pytest.mark.anyio
    async def test_survives_exception_in_one_cycle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """1 chu kỳ lỗi (Bilibili trục trặc, mất mạng...) không được giết vòng lặp."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.models.category import Category

        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        with session_factory() as db:
            db.add(Category(rid=21, name_zh="日常", is_followed=True))
            db.commit()

        call_count = 0

        async def failing_get_categories_stats(db, rids, day=3, save_history=True):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Bilibili lỗi tạm thời")

        monkeypatch.setattr(
            trending_service, "get_categories_stats", failing_get_categories_stats
        )

        sleep_calls = 0

        async def fake_sleep(seconds):
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                raise asyncio.CancelledError

        monkeypatch.setattr(trending_service.asyncio, "sleep", fake_sleep)

        with pytest.raises(asyncio.CancelledError):
            await trending_service.run_periodic_snapshot(session_factory, interval_seconds=999)

        # Vòng lặp không chết ở lần lỗi đầu — vẫn chạy tiếp tới lần 2 (ngủ 2 lần).
        assert call_count == 2


class TestGetRelated:
    @pytest.mark.anyio
    async def test_converts_related_items(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.adapters.bilibili.client import BilibiliClient

        async def fake_get_related(self, bvid):
            return [
                {
                    "bvid": "BV1related",
                    "title": "video liên quan",
                    "owner": {"mid": 7, "name": "tác giả"},
                    "stat": {"view": 100, "like": 10},
                    "duration": 60,
                    "pic": "//i0.hdslb.com/a.jpg",
                }
            ]

        monkeypatch.setattr(BilibiliClient, "get_related", fake_get_related)

        page = await trending_service.get_related(db_session, "BV1source")

        assert page.videos[0].bvid == "BV1related"
        assert page.videos[0].channel_id == "7"
        assert page.videos[0].cover_url == "https://i0.hdslb.com/a.jpg"
        assert page.has_more is False


class TestGetChannelVideos:
    @pytest.mark.anyio
    async def test_degraded_when_risk_controlled(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.adapters.bilibili.client import BilibiliClient, BilibiliRiskControlError

        async def fake_get_space_videos(self, mid, page=1, page_size=25):
            raise BilibiliRiskControlError(412, "blocked")

        monkeypatch.setattr(BilibiliClient, "get_space_videos", fake_get_space_videos)

        page = await trending_service.get_channel_videos(db_session, "42")

        assert page.degraded is True
        assert page.videos == []
        assert page.has_more is False  # degraded không được hứa còn trang sau

    @pytest.mark.anyio
    async def test_converts_space_video_items(
        self, db_session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.adapters.bilibili.client import BilibiliClient

        async def fake_get_space_videos(self, mid, page=1, page_size=25):
            return [{"bvid": "BV1space", "title": "t", "mid": 42, "length": "3:05"}]

        monkeypatch.setattr(BilibiliClient, "get_space_videos", fake_get_space_videos)

        page = await trending_service.get_channel_videos(db_session, "42")

        assert page.degraded is False
        assert page.videos[0].bvid == "BV1space"
        assert page.videos[0].duration_seconds == 185
        assert page.videos[0].channel_id == "42"


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
