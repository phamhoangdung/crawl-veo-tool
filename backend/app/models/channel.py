from datetime import datetime, timezone

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.job import Platform


class Channel(Base):
    """Bilibili channel/author (Douyin later, see `Platform`) — mirrors
    `models/category.py::Category` (auto-discovered from scanned data,
    no hardcoded list), except that channels are followed ONE AT A TIME
    (`follow`/`unfollow`) instead of replacing the whole list at once like categories
    (`set_followed`) — the set of channels can be much larger than the set of categories.

    Phase 22 — see docs/phases/phase-22-channel-follow.md.
    """

    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("platform", "channel_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[Platform] = mapped_column()
    # Bilibili: str(mid). Stored as a string so we do not assume the id format of
    # other platforms when Douyin reuses this table later (once Phase 3 is unblocked).
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
