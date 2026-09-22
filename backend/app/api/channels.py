"""Theo dõi kênh (Phase 22) — tách riêng khỏi `api/trending.py` vì
`Channel.platform` thiết kế đa nền tảng ngay từ đầu (Douyin dùng lại sau khi
hết blocked, xem docs/phases/phase-22-channel-follow.md), trong khi
`api/trending.py` hiện chỉ có route Bilibili thuần tuý
(`prefix="/api/trending/bilibili"`)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.job import Platform
from app.schemas.trending import ChannelRead, SetChannelFollowedRequest
from app.services import channel_service

router = APIRouter(prefix="/api/channels", tags=["channels"])


def _to_read(channel) -> ChannelRead:  # noqa: ANN001 — Channel model, tránh import vòng cho type hint
    return ChannelRead(
        platform=channel.platform.value,
        channel_id=channel.channel_id,
        name=channel.name,
        avatar_url=channel.avatar_url,
        is_followed=channel.is_followed,
    )


@router.get("/followed", response_model=list[ChannelRead])
def get_followed(
    platform: str = Query("bilibili"), db: Session = Depends(get_db)
) -> list[ChannelRead]:
    channels = channel_service.get_followed(db, Platform(platform))
    return [_to_read(c) for c in channels]


@router.put("/{platform}/{channel_id}/followed", response_model=ChannelRead)
def set_followed(
    platform: str,
    channel_id: str,
    payload: SetChannelFollowedRequest,
    name: str = Query(..., description="Tên kênh — cần khi tạo mới kênh chưa từng thấy"),
    db: Session = Depends(get_db),
) -> ChannelRead:
    """Theo/bỏ theo dõi 1 kênh. `name` truyền qua query vì có thể là lần đầu
    tool biết tới kênh này (bấm Theo dõi thẳng từ popup trước khi kênh từng
    được `upsert_seen_batch` ghi nhận qua lượt duyệt nào)."""
    platform_enum = Platform(platform)
    if payload.followed:
        channel = channel_service.follow(db, platform_enum, channel_id, name)
    else:
        channel = channel_service.unfollow(db, platform_enum, channel_id, name)
    return _to_read(channel)
