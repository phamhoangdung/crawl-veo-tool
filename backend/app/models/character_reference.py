from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CharacterReference(Base):
    """Character/scene reference set (character sheet) — several angles of the same
    character, attached to every image/video generation to keep features consistent.

    `name` is a slug (no diacritics, no spaces) because it is used as the mention token
    `@name` in prompts — see docs/ai-video-generation/research.md Part 6.1.
    """

    __tablename__ = "character_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column()
    description: Mapped[str | None] = mapped_column(default=None)
    file_paths: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
