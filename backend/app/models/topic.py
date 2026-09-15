from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Topic(Base):
    """1 chủ đề nội dung người dùng muốn theo dõi/khai thác (vd "review điện
    thoại", "truyện ma") — Phase 17. `query` dùng để tìm video mẫu trên YouTube
    khi tính điểm cơ hội, tách riêng khỏi `name` để sửa từ khoá tìm mà không
    đổi tên hiển thị (vd name="Truyện ma" nhưng query="ghost story animation").

    Không lưu lịch sử điểm theo thời gian (khác `CategorySnapshot` của
    Bilibili) — mỗi topic chỉ giữ lần tính gần nhất, vì mục đích là quyết định
    "có nên khai thác chủ đề này không" tại thời điểm xem, không phải theo dõi
    xu hướng dài hạn.
    """

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String)
    query: Mapped[str] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Điểm cơ hội — xem `topic_service.compute_score()`. None nghĩa là chưa
    # tính lần nào.
    score: Mapped[float | None] = mapped_column(Float, default=None)
    sample_video_count: Mapped[int | None] = mapped_column(Integer, default=None)
    competition_count: Mapped[int | None] = mapped_column(Integer, default=None)
    top_video_title: Mapped[str | None] = mapped_column(String, default=None)
    top_video_url: Mapped[str | None] = mapped_column(String, default=None)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
