"""Token cho agent ngoài (Claude Code/Codex) gọi vào qua MCP — Phase 14.

Khác key của provider AI (`api_key_service`, mã hoá 2 chiều bằng Fernet vì phải
giải mã ra để gửi cho provider): token này chỉ cần so sánh, không bao giờ cần đọc
lại, nên lưu hash một chiều — rò DB cũng không dùng lại được token.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mcp_access_token import MCP_SCOPES, McpAccessToken

logger = logging.getLogger(__name__)

_TOKEN_PREFIX = "sk_local_"


class McpTokenError(ValueError):
    pass


@dataclass
class IssuedToken:
    record: McpAccessToken
    plain_token: str


def _hash_token(plain_token: str) -> str:
    return hashlib.sha256(plain_token.encode("utf-8")).hexdigest()


def validate_scopes(scopes: list[str]) -> list[str]:
    unknown = [s for s in scopes if s not in MCP_SCOPES]
    if unknown:
        raise McpTokenError(
            f"Scope không hợp lệ: {', '.join(unknown)}. Cho phép: {', '.join(MCP_SCOPES)}"
        )
    if not scopes:
        raise McpTokenError("Cần ít nhất 1 scope.")
    return list(dict.fromkeys(scopes))


def create_token(
    db: Session, user_id: int, name: str, scopes: list[str]
) -> IssuedToken:
    """Trả về plaintext DUY NHẤT lần này — về sau chỉ còn hash trong DB."""
    cleaned_name = name.strip()
    if not cleaned_name:
        raise McpTokenError("Cần đặt tên cho token (vd claude-code).")

    checked_scopes = validate_scopes(scopes)
    plain_token = _TOKEN_PREFIX + secrets.token_urlsafe(32)

    record = McpAccessToken(
        user_id=user_id,
        name=cleaned_name,
        token_hash=_hash_token(plain_token),
        scopes=checked_scopes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # Không log giá trị token, chỉ log việc đã tạo (cùng nguyên tắc với API key).
    logger.info("Đã tạo MCP token '%s' với %d scope", cleaned_name, len(checked_scopes))
    return IssuedToken(record=record, plain_token=plain_token)


def list_tokens(db: Session, user_id: int) -> list[McpAccessToken]:
    return list(
        db.execute(
            select(McpAccessToken)
            .where(McpAccessToken.user_id == user_id)
            .order_by(McpAccessToken.created_at.desc())
        ).scalars()
    )


def revoke_token(db: Session, user_id: int, token_id: int) -> bool:
    record = db.execute(
        select(McpAccessToken).where(
            McpAccessToken.id == token_id, McpAccessToken.user_id == user_id
        )
    ).scalar_one_or_none()
    if record is None or record.revoked_at is not None:
        return False

    record.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return True


def authenticate(db: Session, plain_token: str) -> McpAccessToken | None:
    """Trả token record nếu hợp lệ và chưa thu hồi, ngược lại None."""
    if not plain_token:
        return None

    record = db.execute(
        select(McpAccessToken).where(McpAccessToken.token_hash == _hash_token(plain_token))
    ).scalar_one_or_none()
    if record is None or record.revoked_at is not None:
        return None

    record.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return record


def require_scope(record: McpAccessToken, scope: str) -> None:
    if scope not in record.scopes:
        raise McpTokenError(
            f"Token '{record.name}' không có scope '{scope}' — tạo token mới với scope này."
        )
