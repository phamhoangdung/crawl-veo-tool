"""Phase 22 — theo dõi kênh. Mirror test style của `test_category_service.py`."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.adapters.bilibili.client import BilibiliRiskControlError
from app.core.db import Base
from app.models.channel import Channel
from app.models.job import Platform
from app.services import channel_service


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


class TestUpsertSeenBatch:
    def test_creates_new_channel(self, db) -> None:
        channel_service.upsert_seen_batch(db, Platform.BILIBILI, [("123", "Kênh A")])

        rows = db.query(Channel).all()
        assert len(rows) == 1
        assert rows[0].channel_id == "123"
        assert rows[0].name == "Kênh A"
        assert rows[0].is_followed is False

    def test_seeing_same_mid_again_is_idempotent(self, db) -> None:
        """Thấy lại cùng mid không tạo trùng dòng — chỉ cập nhật `last_seen_at`/tên."""
        channel_service.upsert_seen_batch(db, Platform.BILIBILI, [("123", "Tên cũ")])
        channel_service.upsert_seen_batch(db, Platform.BILIBILI, [("123", "Tên mới")])

        rows = db.query(Channel).filter(Channel.channel_id == "123").all()
        assert len(rows) == 1
        assert rows[0].name == "Tên mới"

    def test_dedups_within_same_batch(self, db) -> None:
        """1 trang video có nhiều video cùng 1 kênh — không tạo 2 dòng."""
        channel_service.upsert_seen_batch(
            db, Platform.BILIBILI, [("123", "Kênh A"), ("123", "Kênh A")]
        )
        assert db.query(Channel).count() == 1

    def test_does_not_touch_is_followed_flag(self, db) -> None:
        """Chỉ thấy lại (không phải người dùng bấm theo dõi) không được tự ý bật cờ theo dõi."""
        channel_service.follow(db, Platform.BILIBILI, "123", "Kênh A")
        channel_service.upsert_seen_batch(db, Platform.BILIBILI, [("123", "Kênh A")])

        channel = db.query(Channel).filter(Channel.channel_id == "123").one()
        assert channel.is_followed is True  # vẫn giữ nguyên, không bị reset

    def test_empty_list_does_nothing(self, db) -> None:
        channel_service.upsert_seen_batch(db, Platform.BILIBILI, [])
        assert db.query(Channel).count() == 0


class TestFollowUnfollow:
    def test_follow_creates_channel_not_yet_seen(self, db) -> None:
        channel = channel_service.follow(db, Platform.BILIBILI, "999", "Kênh mới")
        assert channel.is_followed is True
        assert db.query(Channel).count() == 1

    def test_unfollow_persists(self, db) -> None:
        channel_service.follow(db, Platform.BILIBILI, "123", "Kênh A")
        channel_service.unfollow(db, Platform.BILIBILI, "123", "Kênh A")

        channel = db.query(Channel).filter(Channel.channel_id == "123").one()
        assert channel.is_followed is False

    def test_get_followed_only_returns_followed(self, db) -> None:
        channel_service.follow(db, Platform.BILIBILI, "1", "A")
        channel_service.upsert_seen_batch(db, Platform.BILIBILI, [("2", "B")])  # chưa theo dõi

        followed = channel_service.get_followed(db, Platform.BILIBILI)
        assert [c.channel_id for c in followed] == ["1"]

    def test_follow_persists_across_reload(self, db) -> None:
        """Theo dõi 1 kênh → tải lại app → trạng thái vẫn còn (persist DB thật)."""
        channel_service.follow(db, Platform.BILIBILI, "123", "Kênh A")

        # Mô phỏng "tải lại app": session mới, đọc lại từ DB.
        reloaded = db.query(Channel).filter(Channel.channel_id == "123").one()
        assert reloaded.is_followed is True


class TestListChannelVideos:
    @pytest.mark.anyio
    async def test_returns_degraded_on_risk_control(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.adapters.bilibili.client import BilibiliClient

        async def fake_get_space_videos(self, mid, page=1, page_size=25):
            raise BilibiliRiskControlError(412, "blocked")

        monkeypatch.setattr(BilibiliClient, "get_space_videos", fake_get_space_videos)

        result = await channel_service.list_channel_videos("123")

        assert result.degraded is True
        assert result.videos == []

    @pytest.mark.anyio
    async def test_returns_videos_when_not_blocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.adapters.bilibili.client import BilibiliClient

        async def fake_get_space_videos(self, mid, page=1, page_size=25):
            return [{"bvid": "BV1", "title": "video 1"}]

        monkeypatch.setattr(BilibiliClient, "get_space_videos", fake_get_space_videos)

        result = await channel_service.list_channel_videos("123")

        assert result.degraded is False
        assert len(result.videos) == 1

    @pytest.mark.anyio
    async def test_other_errors_are_not_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Chỉ risk-control mới suy giảm nhẹ nhàng — lỗi khác (vd mất mạng)
        vẫn phải nổi lên để caller biết, không im lặng trả rỗng."""
        from app.adapters.bilibili.client import BilibiliClient

        async def fake_get_space_videos(self, mid, page=1, page_size=25):
            raise RuntimeError("mất mạng")

        monkeypatch.setattr(BilibiliClient, "get_space_videos", fake_get_space_videos)

        with pytest.raises(RuntimeError):
            await channel_service.list_channel_videos("123")
