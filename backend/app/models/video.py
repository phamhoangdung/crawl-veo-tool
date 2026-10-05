import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.job import Platform

if TYPE_CHECKING:
    from app.models.job import Job


class VideoStatus(str, enum.Enum):
    """State machine per docs/overview/plan.md — each step has its own failed_* so we know exactly where it failed when resuming."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    SEPARATING_AUDIO = "separating_audio"
    TRANSCRIBING = "transcribing"
    # Each step needs its own "done" state, otherwise a video gets stuck forever in the
    # "in progress" state and the UI cannot tell which step has completed.
    TRANSCRIBED = "transcribed"
    TRANSLATING = "translating"
    TRANSLATED = "translated"
    DUBBING = "dubbing"
    MUXING = "muxing"
    DONE = "done"
    # Phase 8: every key in the pool is out of quota AND the free fallback provider too — unlike
    # FAILED_* (a real error that needs fixing), this is "paused, waiting", retried automatically when
    # a new key arrives or the cooldown expires (docs/phases/phase-8-ai-account-pool.md).
    PAUSED_QUOTA = "paused_quota"
    FAILED_DOWNLOAD = "failed_download"
    FAILED_SEPARATING_AUDIO = "failed_separating_audio"
    FAILED_TRANSCRIBING = "failed_transcribing"
    FAILED_TRANSLATING = "failed_translating"
    FAILED_DUBBING = "failed_dubbing"
    FAILED_MUXING = "failed_muxing"


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("platform", "platform_video_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    platform: Mapped[Platform] = mapped_column(Enum(Platform))
    platform_video_id: Mapped[str] = mapped_column()
    title: Mapped[str] = mapped_column()
    author_name: Mapped[str | None] = mapped_column(default=None)
    # Phase 22: real channel id (Bilibili: str(mid)) — filled alongside
    # `author_name` (display name, may collide across different channels) everywhere
    # author_name is set. `author_name` keeps its old behavior; this column
    # only adds channel lookup/following (`models/channel.py`).
    channel_id: Mapped[str | None] = mapped_column(default=None)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    cover_url: Mapped[str | None] = mapped_column(default=None)
    source_url: Mapped[str] = mapped_column()
    local_path: Mapped[str | None] = mapped_column(default=None)
    dubbed_path: Mapped[str | None] = mapped_column(default=None)
    burned_path: Mapped[str | None] = mapped_column(default=None)
    timeline_rendered_path: Mapped[str | None] = mapped_column(default=None)
    transcript_json: Mapped[list[dict] | None] = mapped_column(JSON, default=None)
    # Phase 13: draft timeline (edit operations) — not rendered yet, allows many edits
    # before the separate render button is pressed (the "AI suggests, human decides" principle).
    timeline_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    # Phase 19: map speaker_label -> {"provider", "voice_id"} — a speaker with none
    # assigned uses the shared default voice as before (speaker separation is not mandatory).
    speaker_voices_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    status: Mapped[VideoStatus] = mapped_column(
        Enum(VideoStatus), default=VideoStatus.QUEUED
    )
    error_message: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    job: Mapped["Job"] = relationship(back_populates="videos")
