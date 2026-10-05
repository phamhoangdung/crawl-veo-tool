import hashlib
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TranslationCache(Base):
    """Existing translation, keyed by the text CONTENT rather than by video.

    Reason: the title-translation tooltip fires on every hover; without a cache a few passes of the
    mouse over a 40-row table would exhaust the quota. Keyed by content, so many
    videos with the same title (very common with re-uploads) cost a single translation, and the
    cache can be reused for text outside the crawl table.
    """

    __tablename__ = "translation_cache"

    # Hash of (text, language pair) as the primary key: text can exceed SQLite's
    # index size limit, while a hash is always a fixed 64 characters.
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_text: Mapped[str] = mapped_column(Text)
    translated_text: Mapped[str] = mapped_column(Text)
    source_lang: Mapped[str] = mapped_column(String(16))
    target_lang: Mapped[str] = mapped_column(String(16))
    hit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


def make_key(text: str, source_lang: str, target_lang: str) -> str:
    """Normalize whitespace before hashing — the same title that differs only by extra
    spaces should not count as 2 translations."""
    normalized = " ".join(text.split())
    raw = f"{source_lang}|{target_lang}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
