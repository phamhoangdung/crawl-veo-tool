from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Category(Base):
    """Chuyên mục Bilibili, phát hiện tự động từ field `tid`/`tname` của API.

    Không hardcode danh sách: chuyên mục mới xuất hiện trong kết quả API sẽ được
    thêm vào đây, nên tool tự bắt kịp khi Bilibili đổi phân loại.
    """

    __tablename__ = "categories"

    # tid do Bilibili cấp — dùng luôn làm khoá chính để upsert cho gọn.
    rid: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_zh: Mapped[str] = mapped_column(String)
    # Tên tiếng Việt dịch sẵn; None nghĩa là chưa dịch, UI hiển thị name_zh.
    name_vi: Mapped[str | None] = mapped_column(String, default=None)
    group_name: Mapped[str | None] = mapped_column(String, default=None)
    # Người dùng có theo dõi chuyên mục này ở trang Trending không.
    is_followed: Mapped[bool] = mapped_column(default=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CategorySnapshot(Base):
    """Số liệu 1 chuyên mục tại 1 thời điểm.

    Bilibili chỉ trả số hiện tại, không có lịch sử — muốn vẽ đường xu hướng thì
    phải tự tích luỹ. Mỗi lần mở trang Trending sẽ ghi thêm 1 điểm.
    """

    __tablename__ = "category_snapshots"
    __table_args__ = (Index("ix_snapshot_rid_time", "rid", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    rid: Mapped[int] = mapped_column(ForeignKey("categories.rid"))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    video_count: Mapped[int] = mapped_column(Integer, default=0)
    total_plays: Mapped[int] = mapped_column(Integer, default=0)
    avg_plays: Mapped[int] = mapped_column(Integer, default=0)
    max_plays: Mapped[int] = mapped_column(Integer, default=0)
    total_likes: Mapped[int] = mapped_column(Integer, default=0)
    # Lượt xem trung bình chia cho số ngày kể từ khi video đăng — xấp xỉ "độ nóng".
    heat_score: Mapped[float] = mapped_column(Float, default=0.0)
