import hashlib
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TranslationCache(Base):
    """Bản dịch đã có, khoá theo NỘI DUNG text thay vì theo video.

    Lý do: tooltip dịch tiêu đề gọi mỗi lần hover, không cache thì chỉ cần rê
    chuột qua bảng 40 dòng vài lượt là hết quota. Khoá theo nội dung nên nhiều
    video trùng tiêu đề (rất hay gặp với video re-up) chỉ tốn 1 lần dịch, và
    cache dùng lại được cho text ngoài bảng crawl.
    """

    __tablename__ = "translation_cache"

    # Hash của (text, cặp ngôn ngữ) làm khoá chính: text có thể dài hơn giới hạn
    # index của SQLite, còn hash thì luôn cố định 64 ký tự.
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
    """Chuẩn hoá khoảng trắng trước khi hash — cùng một tiêu đề chỉ khác thừa
    dấu cách thì không nên tính là 2 lần dịch."""
    normalized = " ".join(text.split())
    raw = f"{source_lang}|{target_lang}|{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
