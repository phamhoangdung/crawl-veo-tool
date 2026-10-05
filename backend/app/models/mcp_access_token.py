from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Deliberately narrow scope: an agent may only generate content and read costs, and may NOT
# touch provider API keys or system configuration.
MCP_SCOPES = (
    "assets:read",
    "assets:write",
    "gen:write",
    "jobs:read",
    "cost:read",
)


class McpAccessToken(Base):
    """Token for external agents (Claude Code/Codex) calling in through MCP.

    Only the hash is stored — the plaintext is shown exactly once at creation and cannot be retrieved again.
    This is the app's own internal token, unrelated to AI provider keys.
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
