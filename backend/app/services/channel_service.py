"""Bilibili channel/author — Phase 22. Mirrors `category_service.py` with 1 deliberate
difference: categories are a small set replaced entirely on each set
(`set_followed`), channels are a potentially large set, followed/unfollowed ONE AT A TIME
(`follow`/`unfollow`) — see the `models/channel.py` docstring.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.adapters.bilibili.client import BilibiliClient, BilibiliRiskControlError
from app.models.channel import Channel
from app.models.job import Platform

logger = logging.getLogger(__name__)


def upsert_seen_batch(
    db: Session, platform: Platform, channels: list[tuple[str, str]]
) -> None:
    """Record channels seen through scanned data (no separate scan job needed
    like categories — every video already carries a channel).

    1 query for the whole list + 1 commit — the same N+1-avoidance pattern used in
    Phase 20 (`trending_service._attach_library_status`). `channels` is
    `[(channel_id, name), ...]`, and may repeat channel_id (many videos of the same
    channel on 1 page) — dedupe before querying.
    """
    if not channels:
        return

    dedup: dict[str, str] = {}
    for channel_id, name in channels:
        if channel_id:
            dedup[channel_id] = name

    if not dedup:
        return

    existing = {
        c.channel_id: c
        for c in db.query(Channel)
        .filter(Channel.platform == platform, Channel.channel_id.in_(dedup.keys()))
        .all()
    }

    now = datetime.now(timezone.utc)
    for channel_id, name in dedup.items():
        channel = existing.get(channel_id)
        if channel is None:
            db.add(
                Channel(
                    platform=platform,
                    channel_id=channel_id,
                    name=name,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        else:
            channel.name = name
            channel.last_seen_at = now

    db.commit()


def follow(db: Session, platform: Platform, channel_id: str, name: str) -> Channel:
    """Follow 1 channel — create it if never seen (e.g. the user follows
    straight from the popup before any `upsert_seen_batch` call touched that channel)."""
    channel = (
        db.query(Channel)
        .filter(Channel.platform == platform, Channel.channel_id == channel_id)
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if channel is None:
        channel = Channel(
            platform=platform,
            channel_id=channel_id,
            name=name,
            is_followed=True,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(channel)
    else:
        channel.is_followed = True
        channel.last_seen_at = now
    db.commit()
    db.refresh(channel)
    return channel


def unfollow(db: Session, platform: Platform, channel_id: str, name: str) -> Channel:
    """Symmetric to `follow()` — takes `name` to create a new channel if never
    seen (rare but possible: unfollowing a channel the backend never
    recorded, e.g. from old FE data). Returns a `Channel` (instead of `None`) so the API
    returns the latest state, the same return type as `follow()`."""
    channel = (
        db.query(Channel)
        .filter(Channel.platform == platform, Channel.channel_id == channel_id)
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if channel is None:
        channel = Channel(
            platform=platform,
            channel_id=channel_id,
            name=name,
            is_followed=False,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(channel)
    else:
        channel.is_followed = False
        channel.last_seen_at = now
    db.commit()
    db.refresh(channel)
    return channel


def get_followed(db: Session, platform: Platform) -> list[Channel]:
    return (
        db.query(Channel)
        .filter(Channel.platform == platform, Channel.is_followed.is_(True))
        .order_by(Channel.name)
        .all()
    )


class ChannelVideosResult:
    """Result of the channel API call — `degraded=True` when hit by risk control (very different from
    "this channel truly has no videos"), so the caller shows the right message instead of
    silently treating it as an empty list.

    Measured 2026-09-22 (10 popular channels, 1 request/channel, no cookie): **all
    10/10 were blocked** — far worse than the initial "heavy risk control" prediction, almost
    CERTAINLY degraded=True for every user in v1 (no
    `bilibili_cookie` yet, see docs/phases/phase-22-channel-follow.md, section "Quyết
    định đã chốt" #5 — the decision NOT to add a cookie in v1 was made before this
    measurement, now there is a real measurement for a later session to weigh reversing it)."""

    def __init__(self, videos: list[dict], degraded: bool) -> None:
        self.videos = videos
        self.degraded = degraded


async def list_channel_videos(
    mid: str, page: int = 1, page_size: int = 25
) -> ChannelVideosResult:
    """Call `get_space_videos` — wraps `BilibiliRiskControlError` into an empty
    result + a `degraded` flag, does NOT raise up to the router (1 failing auxiliary API must not
    break the whole preview popup, see docs/phases/phase-22-channel-follow.md).
    """
    try:
        async with BilibiliClient() as client:
            videos = await client.get_space_videos(mid, page=page, page_size=page_size)
        return ChannelVideosResult(videos=videos, degraded=False)
    except BilibiliRiskControlError as exc:
        logger.info("Kênh %s bị risk-control khi lấy danh sách video: %s", mid, exc)
        return ChannelVideosResult(videos=[], degraded=True)
