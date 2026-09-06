import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Platform(str, enum.Enum):
    BILIBILI = "bilibili"
    DOUYIN = "douyin"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Job(Base):
    """1 job = 1 lần crawl theo từ khoá; chứa nhiều Video bên trong."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    platform: Mapped[Platform] = mapped_column(Enum(Platform))
    keyword: Mapped[str] = mapped_column()
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
