from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Category(Base):
    """Bilibili category, auto-discovered from the API's `tid`/`tname` fields.

    The list is not hardcoded: a new category appearing in API results gets
    added here, so the tool keeps up when Bilibili changes its taxonomy.
    """

    __tablename__ = "categories"

    # tid is issued by Bilibili — used directly as the primary key to keep upserts simple.
    rid: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_zh: Mapped[str] = mapped_column(String)
    # Pre-translated Vietnamese name; None means not translated yet, the UI shows name_zh.
    name_vi: Mapped[str | None] = mapped_column(String, default=None)
    group_name: Mapped[str | None] = mapped_column(String, default=None)
    # Whether the user follows this category on the Trending page.
    is_followed: Mapped[bool] = mapped_column(default=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CategorySnapshot(Base):
    """Metrics of one category at one point in time.

    Bilibili only returns the current numbers, no history — to draw a trend line we
    have to accumulate them ourselves. Every time the Trending page opens, one point is added.
    """

    __tablename__ = "category_snapshots"
    __table_args__ = (Index("ix_snapshot_rid_time", "rid", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rid: Mapped[int] = mapped_column(ForeignKey("categories.rid"))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    video_count: Mapped[int] = mapped_column(Integer, default=0)
    total_plays: Mapped[int] = mapped_column(Integer, default=0)
    avg_plays: Mapped[int] = mapped_column(Integer, default=0)
    max_plays: Mapped[int] = mapped_column(Integer, default=0)
    total_likes: Mapped[int] = mapped_column(Integer, default=0)
    # Total `pts` — the real ranking score Bilibili computes itself, more reliable than total_plays
    # for comparing "hotness" across time points/categories (see schemas/trending.py).
    total_pts: Mapped[int] = mapped_column(Integer, default=0)
    # Average views divided by days since the video was posted — approximates "heat".
    heat_score: Mapped[float] = mapped_column(Float, default=0.0)
