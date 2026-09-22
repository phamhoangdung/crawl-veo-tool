"""Kênh/tác giả Bilibili — Phase 22. Mirror `category_service.py` với 1 khác
biệt cố ý: chuyên mục là tập nhỏ thay thế toàn bộ mỗi lần set
(`set_followed`), kênh là tập có thể lớn, theo/bỏ theo TỪNG kênh một
(`follow`/`unfollow`) — xem docstring `models/channel.py`.
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
    """Ghi nhận kênh đã thấy qua dữ liệu quét được (không cần job quét riêng
    như chuyên mục — mỗi video kéo theo 1 kênh sẵn).

    1 query cho cả danh sách + 1 commit — cùng pattern chống N+1 đã dùng ở
    Phase 20 (`trending_service._attach_library_status`). `channels` là
    `[(channel_id, name), ...]`, có thể trùng channel_id (nhiều video cùng 1
    kênh trong 1 trang) — dedup trước khi query.
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
    """Theo dõi 1 kênh — tạo mới nếu chưa từng thấy (vd người dùng theo dõi
    thẳng từ popup mà chưa có lượt `upsert_seen_batch` nào chạm tới kênh đó)."""
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
    """Đối xứng với `follow()` — nhận `name` để tạo kênh mới nếu chưa từng
    thấy (hiếm nhưng có thể xảy ra: bỏ theo dõi 1 kênh mà backend chưa từng
    ghi nhận, vd do dữ liệu FE cũ). Trả về `Channel` (thay vì `None`) để API
    trả lại đúng trạng thái mới nhất, cùng kiểu trả với `follow()`."""
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
    """Kết quả gọi API kênh — `degraded=True` khi bị risk-control (khác hẳn
    "kênh này thật sự không có video"), để caller hiện đúng thông báo thay vì
    coi là danh sách rỗng im lặng.

    Đo thật 2026-09-22 (10 kênh phổ biến, 1 request/kênh, không cookie): **cả
    10/10 đều bị chặn** — tệ hơn hẳn dự đoán "risk-control nặng" ban đầu, gần
    như CHẮC CHẮN degraded=True với mọi người dùng ở v1 (chưa có
    `bilibili_cookie`, xem docs/phases/phase-22-channel-follow.md mục "Quyết
    định đã chốt" #5 — quyết định KHÔNG thêm cookie v1 đã chốt trước khi có số
    đo này, nay có số đo thật để phiên sau cân nhắc có nên đảo quyết định)."""

    def __init__(self, videos: list[dict], degraded: bool) -> None:
        self.videos = videos
        self.degraded = degraded


async def list_channel_videos(
    mid: str, page: int = 1, page_size: int = 25
) -> ChannelVideosResult:
    """Gọi `get_space_videos` — bọc `BilibiliRiskControlError` thành kết quả
    rỗng + cờ `degraded`, KHÔNG raise lên router (1 API phụ lỗi không được làm
    vỡ cả popup xem trước, xem docs/phases/phase-22-channel-follow.md).
    """
    try:
        async with BilibiliClient() as client:
            videos = await client.get_space_videos(mid, page=page, page_size=page_size)
        return ChannelVideosResult(videos=videos, degraded=False)
    except BilibiliRiskControlError as exc:
        logger.info("Kênh %s bị risk-control khi lấy danh sách video: %s", mid, exc)
        return ChannelVideosResult(videos=[], degraded=True)
