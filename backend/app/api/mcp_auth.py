"""Kiểm tra scope cho request đến từ agent ngoài qua MCP — Phase 14.

Hai loại client dùng chung endpoint `/api/ai-studio`:

- **Web UI cục bộ**: không gửi token (chỉ chạy trên máy người dùng, sau này lên
  multi-tenant sẽ có auth riêng — xem docs/overview/plan.md). Cho qua.
- **Agent ngoài qua MCP**: gửi `Authorization: Bearer sk_local_...`. Có token thì
  BẮT BUỘC token còn hiệu lực và có đúng scope, nếu không thì từ chối.

Nhờ vậy scope thực sự có tác dụng với agent mà không phải bắt UI cục bộ tự sinh
token — nhưng token sai/đã thu hồi thì không bao giờ được lọt qua như "không có
token".
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services import mcp_token_service


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return value.strip() or None


def require_scope(scope: str):
    """Tạo dependency kiểm tra 1 scope cụ thể."""

    def dependency(request: Request, db: Session = Depends(get_db)) -> None:
        token = _bearer_token(request)
        if token is None:
            return  # web UI cục bộ

        record = mcp_token_service.authenticate(db, token)
        if record is None:
            raise HTTPException(status_code=401, detail="Token MCP không hợp lệ hoặc đã bị thu hồi")

        try:
            mcp_token_service.require_scope(record, scope)
        except mcp_token_service.McpTokenError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return dependency
