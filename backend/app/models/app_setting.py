from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AppSetting(Base):
    """User-adjustable settings, persisted across restarts — Phase 21 (download
    speed). This is the project's FIRST settings table; previously all runtime config
    could only be read from env (`core/config.py::Settings`) and not edited from the UI.

    Key-value per `user_id` instead of one column per setting — a new setting
    needs no migration, and it already fits multi-tenant in Phase 18 (each
    user has their own settings from the start, no schema rework).

    `value` is always stored as a string (numbers/bools are coerced in `settings_service`) — simpler
    than a JSON column for a table of a few dozen rows, and easy to read straight in the DB when
    debugging.
    """

    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    key: Mapped[str] = mapped_column()
    value: Mapped[str] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
