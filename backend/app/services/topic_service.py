"""Chủ đề nội dung người dùng theo dõi + điểm "cơ hội khai thác" (Phase 17).

Thuật toán tính điểm — cố ý đơn giản, dùng số liệu THẬT, không đoán:
1. `search.list` tìm ~25 video có view cao nhất trong 30 ngày khớp từ khoá chủ
   đề (100 unit — tốn nhất, chỉ gọi khi người dùng chủ động bấm "Tính điểm").
2. `videos.list` theo id lấy view count thật của các video đó (1 unit).
3. `channels.list` lấy số sub của các kênh đăng — để tính tỉ lệ view/sub.
4. Điểm = TRUNG VỊ tỉ lệ view/sub của các video mẫu. Tỉ lệ cao (vd 1 video có
   view gấp 50-100 lần số sub kênh) là dấu hiệu quen thuộc trong giới phân
   tích YouTube: nội dung/định dạng đó được thuật toán đẩy mạnh bất kể kênh
   nhỏ hay lớn — tức "dễ khai thác" hơn kiểu nội dung phụ thuộc độ nổi tiếng
   sẵn có của kênh. Đây là 1 tín hiệu tham khảo, KHÔNG phải điểm số khoa học
   chính xác — hiển thị kèm số liệu thô để người dùng tự đánh giá thêm.
"""

import statistics
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.topic import Topic
from app.schemas.youtube import TopicCreateRequest
from app.services.youtube_service import run_with_key

_MIN_RECOMPUTE_INTERVAL_MINUTES = 10
_LOOKBACK_DAYS = 30


class TopicScoreCooldownError(RuntimeError):
    """Vừa tính điểm gần đây — chặn bấm liên tục làm tốn quota (100 unit/lần)."""


def create_topic(db: Session, user_id: int, payload: TopicCreateRequest) -> Topic:
    topic = Topic(
        user_id=user_id,
        name=payload.name,
        query=(payload.query or payload.name).strip(),
        note=payload.note,
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


def list_topics(db: Session, user_id: int) -> list[Topic]:
    return (
        db.query(Topic)
        .filter(Topic.user_id == user_id)
        .order_by(Topic.score.is_(None), Topic.score.desc())
        .all()
    )


def delete_topic(db: Session, user_id: int, topic_id: int) -> bool:
    topic = db.get(Topic, topic_id)
    if topic is None or topic.user_id != user_id:
        return False
    db.delete(topic)
    db.commit()
    return True


async def compute_score(db: Session, user_id: int, topic_id: int) -> Topic:
    topic = db.get(Topic, topic_id)
    if topic is None or topic.user_id != user_id:
        raise ValueError("Topic not found")

    now = datetime.now(timezone.utc)
    if topic.scored_at is not None:
        scored_at = topic.scored_at
        if scored_at.tzinfo is None:
            scored_at = scored_at.replace(tzinfo=timezone.utc)
        if now - scored_at < timedelta(minutes=_MIN_RECOMPUTE_INTERVAL_MINUTES):
            raise TopicScoreCooldownError(
                f"Vừa tính điểm cách đây chưa tới {_MIN_RECOMPUTE_INTERVAL_MINUTES} phút."
            )

    published_after = (now - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")

    async def action(client) -> tuple[float, int, int, str | None, str | None]:
        search_result = await client.search_videos(
            topic.query, max_results=25, order="viewCount", published_after=published_after
        )
        search_items = search_result.get("items", [])
        total_results = search_result.get("pageInfo", {}).get("totalResults", 0)
        video_ids = [item["id"]["videoId"] for item in search_items if "videoId" in item.get("id", {})]

        videos = await client.list_videos_stats(video_ids)
        if not videos:
            return (0.0, 0, total_results, None, None)

        channel_ids = list({v["snippet"]["channelId"] for v in videos})
        channels = await client.list_channels_stats(channel_ids)
        subs_by_channel = {
            c["id"]: int(c.get("statistics", {}).get("subscriberCount", 0)) for c in channels
        }

        ratios: list[float] = []
        top_video = max(videos, key=lambda v: int(v.get("statistics", {}).get("viewCount", 0)))
        for v in videos:
            view = int(v.get("statistics", {}).get("viewCount", 0))
            subs = subs_by_channel.get(v["snippet"]["channelId"], 0)
            ratios.append(view / max(subs, 1))

        score = statistics.median(ratios) if ratios else 0.0
        top_title = top_video["snippet"]["title"]
        top_url = f"https://www.youtube.com/watch?v={top_video['id']}"
        return (score, len(videos), total_results, top_title, top_url)

    score, sample_count, competition, top_title, top_url = await run_with_key(
        db, user_id, action
    )

    topic.score = score
    topic.sample_video_count = sample_count
    topic.competition_count = competition
    topic.top_video_title = top_title
    topic.top_video_url = top_url
    topic.scored_at = now
    db.commit()
    db.refresh(topic)
    return topic
