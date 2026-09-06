import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.job import Platform


class VideoStatus(str, enum.Enum):
    """State machine theo docs/overview/plan.md — mỗi bước có failed_* riêng để biết chính xác lỗi ở đâu khi resume."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    SEPARATING_AUDIO = "separating_audio"
    TRANSCRIBING = "transcribing"
    TRANSLATING = "translating"
    DUBBING = "dubbing"
    MUXING = "muxing"
    DONE = "done"
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
    duration_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    source_url: Mapped[str] = mapped_column()
    local_path: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[VideoStatus] = mapped_column(Enum(VideoStatus), default=VideoStatus.QUEUED)
    error_message: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
