from datetime import datetime, timezone

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.job import Platform


class Channel(Base):
    """Kênh/tác giả Bilibili (Douyin để sau, xem `Platform`) — mirror
    `models/category.py::Category` (phát hiện tự động qua dữ liệu quét được,
    không hardcode danh sách), khác ở chỗ theo dõi TỪNG kênh một
    (`follow`/`unfollow`) thay vì thay thế cả danh sách một lần như chuyên mục
    (`set_followed`) — tập kênh có thể lớn hơn nhiều tập chuyên mục.

    Phase 22 — xem docs/phases/phase-22-channel-follow.md.
    """

    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("platform", "channel_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[Platform] = mapped_column()
    # Bilibili: str(mid). Lưu dạng string để không giả định định dạng id của
    # nền tảng khác khi Douyin dùng lại bảng này sau (Phase 3 hết blocked).
    channel_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    avatar_url: Mapped[str | None] = mapped_column(String, default=None)
    is_followed: Mapped[bool] = mapped_column(default=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
