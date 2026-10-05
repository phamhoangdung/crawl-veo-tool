from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Topic(Base):
    """1 content topic the user wants to track/exploit (e.g. "phone reviews",
    "ghost stories") — Phase 17. `query` is used to find sample videos on YouTube
    when computing the opportunity score, kept apart from `name` so the search keyword can be edited without
    changing the display name (e.g. name="Truyện ma" but query="ghost story animation").

    Score history over time is not stored (unlike Bilibili's `CategorySnapshot`) —
    each topic keeps only its latest computation, because the purpose is to decide
    "should we exploit this topic" at the time of viewing, not to track
    long-term trends.
    """

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String)
    query: Mapped[str] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Opportunity score — see `topic_service.compute_score()`. None means it has not
    # been computed yet.
    score: Mapped[float | None] = mapped_column(Float, default=None)
    sample_video_count: Mapped[int | None] = mapped_column(Integer, default=None)
    competition_count: Mapped[int | None] = mapped_column(Integer, default=None)
    top_video_title: Mapped[str | None] = mapped_column(String, default=None)
    top_video_url: Mapped[str | None] = mapped_column(String, default=None)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
