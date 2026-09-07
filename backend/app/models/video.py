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
    """State machine theo docs/overview/plan.md — mỗi bước có failed_* riêng để biết chính xác lỗi ở đâu khi resume."""

    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    SEPARATING_AUDIO = "separating_audio"
    TRANSCRIBING = "transcribing"
    # Mỗi bước cần trạng thái "đã xong" riêng, nếu không video kẹt mãi ở trạng
    # thái "đang làm" và UI không biết bước nào đã hoàn tất.
    TRANSCRIBED = "transcribed"
    TRANSLATING = "translating"
    TRANSLATED = "translated"
    DUBBING = "dubbing"
    MUXING = "muxing"
    DONE = "done"
    # Phase 8: hết quota toàn bộ key trong pool CỘNG provider fallback free — khác
    # FAILED_* (lỗi thật, cần sửa gì đó), đây là "tạm dừng chờ", tự thử lại được khi
    # có key mới hoặc cooldown hết hạn (docs/phases/phase-8-ai-account-pool.md).
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
    duration_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    cover_url: Mapped[str | None] = mapped_column(default=None)
    source_url: Mapped[str] = mapped_column()
    local_path: Mapped[str | None] = mapped_column(default=None)
    dubbed_path: Mapped[str | None] = mapped_column(default=None)
    burned_path: Mapped[str | None] = mapped_column(default=None)
    timeline_rendered_path: Mapped[str | None] = mapped_column(default=None)
    transcript_json: Mapped[list[dict] | None] = mapped_column(JSON, default=None)
    # Phase 13: draft timeline (edit operations) — chưa render, cho sửa nhiều lần
    # trước khi bấm nút render riêng (nguyên tắc "AI gợi ý, người quyết định").
    timeline_json: Mapped[dict | None] = mapped_column(JSON, default=None)
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

    job: Mapped["Job"] = relationship(back_populates="videos")
