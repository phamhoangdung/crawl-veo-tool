import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ApiKeyStatus(str, enum.Enum):
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    EXHAUSTED = "exhausted"
    INVALID = "invalid"


class ApiKey(Base):
    """Phase 8: nhiều key/provider (pool) — không còn unique(user_id, provider) như
    trước. Xem docs/phases/phase-8-ai-account-pool.md và migration bảng cũ ở
    app/core/db.py::_migrate_api_keys_pool()."""

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column()
    encrypted_key: Mapped[str] = mapped_column()
    label: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[ApiKeyStatus] = mapped_column(Enum(ApiKeyStatus), default=ApiKeyStatus.ACTIVE)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
