from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CharacterReference(Base):
    """Bộ ảnh tham chiếu nhân vật/cảnh (character sheet) — nhiều góc của cùng 1
    nhân vật, đính kèm vào mọi lần sinh ảnh/video để giữ đặc điểm nhất quán.

    `name` là slug (không dấu, không khoảng trắng) vì được dùng làm mention token
    `@ten` trong prompt — xem docs/ai-video-generation/research.md Phần 6.1.
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
