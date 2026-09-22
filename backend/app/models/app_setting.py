from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AppSetting(Base):
    """Cài đặt người dùng tự chỉnh, lưu bền qua restart — Phase 21 (tốc độ
    tải). Đây là bảng cài đặt ĐẦU TIÊN của dự án; trước đây mọi cấu hình runtime
    chỉ đọc được từ env (`core/config.py::Settings`), không sửa được từ UI.

    Dạng khoá-giá trị theo `user_id` thay vì mỗi cài đặt 1 cột riêng — thêm cài
    đặt mới không cần migration, và khớp sẵn với multi-tenant ở Phase 18 (mỗi
    user có bộ cài đặt riêng ngay từ đầu, không phải sửa lại schema).

    `value` luôn lưu dạng chuỗi (số/bool tự ép ở `settings_service`) — đơn giản
    hơn JSON column cho một bảng chỉ vài chục dòng, dễ đọc thẳng trong DB khi
    debug.
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
