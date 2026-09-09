from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Scope hẹp có chủ đích: agent chỉ được sinh nội dung và đọc chi phí, KHÔNG được
# đụng vào API key provider hay cấu hình hệ thống.
MCP_SCOPES = (
    "assets:read",
    "assets:write",
    "gen:write",
    "jobs:read",
    "cost:read",
)


class McpAccessToken(Base):
    """Token cho agent ngoài (Claude Code/Codex) gọi vào qua MCP.

    Chỉ lưu hash — plaintext hiện đúng 1 lần lúc tạo rồi không lấy lại được.
    Đây là token nội bộ của app, không liên quan tới key của provider AI.
    """

    __tablename__ = "mcp_access_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column()
    token_hash: Mapped[str] = mapped_column(index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
