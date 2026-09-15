"""Test `topic_service` — CRUD + thuật toán tính điểm cơ hội (Phase 17).

Mock ở mức `run_with_key` (đã chọn key + gọi YouTubeClient xong xuôi) để test
tập trung vào logic tính điểm (trung vị tỉ lệ view/sub) và các quy tắc nghiệp
vụ (cooldown, quyền sở hữu topic) — không gọi API YouTube thật (cần key thật,
xem docs/phases/phase-17-content-opportunity.md).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.topic import Topic
from app.models.user import User
from app.schemas.youtube import TopicCreateRequest
from app.services import topic_service


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(User(id=1))
        db.add(User(id=2))
        db.commit()
    return factory


class TestCrud:
    def test_create_topic_defaults_query_to_name(self, session_factory) -> None:
        with session_factory() as db:
            topic = topic_service.create_topic(
                db, 1, TopicCreateRequest(name="Truyện ma")
            )
            assert topic.query == "Truyện ma"

    def test_create_topic_uses_explicit_query_when_given(self, session_factory) -> None:
        with session_factory() as db:
            topic = topic_service.create_topic(
                db, 1, TopicCreateRequest(name="Truyện ma", query="ghost story animation")
            )
            assert topic.query == "ghost story animation"

    def test_list_topics_sorts_scored_first_by_score_desc(self, session_factory) -> None:
        with session_factory() as db:
            db.add_all(
                [
                    Topic(id=1, user_id=1, name="A", query="a", score=None),
                    Topic(id=2, user_id=1, name="B", query="b", score=5.0),
                    Topic(id=3, user_id=1, name="C", query="c", score=50.0),
                ]
            )
            db.commit()

            topics = topic_service.list_topics(db, 1)

            assert [t.id for t in topics] == [3, 2, 1]

    def test_list_topics_scoped_to_user(self, session_factory) -> None:
        with session_factory() as db:
            db.add_all(
                [
                    Topic(id=1, user_id=1, name="mine", query="a"),
                    Topic(id=2, user_id=2, name="other", query="b"),
                ]
            )
            db.commit()

            topics = topic_service.list_topics(db, 1)

            assert [t.id for t in topics] == [1]

    def test_delete_topic_rejects_other_users_topic(self, session_factory) -> None:
        with session_factory() as db:
            db.add(Topic(id=1, user_id=2, name="other", query="b"))
            db.commit()

            deleted = topic_service.delete_topic(db, 1, 1)

            assert deleted is False
            assert db.get(Topic, 1) is not None

    def test_delete_topic_succeeds_for_owner(self, session_factory) -> None:
        with session_factory() as db:
            db.add(Topic(id=1, user_id=1, name="mine", query="a"))
            db.commit()

            deleted = topic_service.delete_topic(db, 1, 1)

            assert deleted is True
            assert db.get(Topic, 1) is None


class TestComputeScore:
    async def _score_video(self, view: int, subs: int, channel_id: str, video_id: str, title: str):
        return {
            "id": video_id,
            "snippet": {"channelId": channel_id, "title": title},
            "statistics": {"viewCount": str(view)},
        }, {"id": channel_id, "statistics": {"subscriberCount": str(subs)}}

    @pytest.mark.asyncio
    async def test_score_is_median_of_view_to_sub_ratio(self, session_factory) -> None:
        with session_factory() as db:
            db.add(Topic(id=1, user_id=1, name="t", query="t query"))
            db.commit()

            v1, c1 = await self._score_video(1000, 100, "ch1", "v1", "video 1")  # ratio 10
            v2, c2 = await self._score_video(5000, 100, "ch2", "v2", "video 2 hit")  # ratio 50
            v3, c3 = await self._score_video(100, 1000, "ch3", "v3", "video 3")  # ratio 0.1

            async def fake_run_with_key(db_arg, user_id, action):
                client = AsyncMock()
                client.search_videos.return_value = {
                    "items": [
                        {"id": {"videoId": "v1"}},
                        {"id": {"videoId": "v2"}},
                        {"id": {"videoId": "v3"}},
                    ],
                    "pageInfo": {"totalResults": 340},
                }
                client.list_videos_stats.return_value = [v1, v2, v3]
                client.list_channels_stats.return_value = [c1, c2, c3]
                return await action(client)

            with patch.object(topic_service, "run_with_key", fake_run_with_key):
                topic = await topic_service.compute_score(db, 1, 1)

            assert topic.score == 10.0  # trung vị của [10, 50, 0.1]
            assert topic.sample_video_count == 3
            assert topic.competition_count == 340
            assert topic.top_video_title == "video 2 hit"
            assert topic.top_video_url == "https://www.youtube.com/watch?v=v2"
            assert topic.scored_at is not None

    @pytest.mark.asyncio
    async def test_no_matching_videos_scores_zero_without_crashing(self, session_factory) -> None:
        with session_factory() as db:
            db.add(Topic(id=1, user_id=1, name="t", query="obscure query"))
            db.commit()

            async def fake_run_with_key(db_arg, user_id, action):
                client = AsyncMock()
                client.search_videos.return_value = {"items": [], "pageInfo": {"totalResults": 0}}
                client.list_videos_stats.return_value = []
                return await action(client)

            with patch.object(topic_service, "run_with_key", fake_run_with_key):
                topic = await topic_service.compute_score(db, 1, 1)

            assert topic.score == 0.0
            assert topic.sample_video_count == 0
            assert topic.top_video_title is None

    @pytest.mark.asyncio
    async def test_recompute_within_cooldown_raises(self, session_factory) -> None:
        with session_factory() as db:
            db.add(
                Topic(
                    id=1,
                    user_id=1,
                    name="t",
                    query="t",
                    scored_at=datetime.now(timezone.utc) - timedelta(minutes=2),
                )
            )
            db.commit()

            with pytest.raises(topic_service.TopicScoreCooldownError):
                await topic_service.compute_score(db, 1, 1)

    @pytest.mark.asyncio
    async def test_other_users_topic_raises_value_error(self, session_factory) -> None:
        with session_factory() as db:
            db.add(Topic(id=1, user_id=2, name="t", query="t"))
            db.commit()

            with pytest.raises(ValueError):
                await topic_service.compute_score(db, 1, 1)
