import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.mcp_access_token import MCP_SCOPES, McpAccessToken
from app.schemas.mcp_token import (
    McpScopesResponse,
    McpTokenCreateRequest,
    McpTokenCreateResponse,
    McpTokenRead,
)
from app.services import mcp_token_service

router = APIRouter(prefix="/api/mcp-tokens", tags=["mcp-tokens"])

_DEFAULT_USER_ID = 1
_API_BASE = "http://127.0.0.1:8000"


def _to_read(record: McpAccessToken) -> McpTokenRead:
    return McpTokenRead(
        id=record.id,
        name=record.name,
        scopes=record.scopes,
        created_at=record.created_at,
        last_used_at=record.last_used_at,
        revoked_at=record.revoked_at,
    )


def _mcp_config(plain_token: str) -> dict:
    """Config dán thẳng vào Claude Code/Codex.

    Tự sinh kèm đường dẫn Python thật đang chạy — viết tay chỗ này rất dễ sai
    (đó cũng là lý do GOHA hiện sẵn khối config để copy, xem research Phần 6.2).
    """
    backend_dir = Path(__file__).resolve().parent.parent.parent
    return {
        "mcpServers": {
            "crawl-veo": {
                "command": sys.executable,
                "args": ["-m", "app.mcp_server"],
                "env": {
                    "MCP_TOKEN": plain_token,
                    "MCP_API_BASE": _API_BASE,
                    "PYTHONPATH": str(backend_dir),
                },
            }
        }
    }


@router.get("/scopes", response_model=McpScopesResponse)
def list_scopes() -> McpScopesResponse:
    return McpScopesResponse(scopes=list(MCP_SCOPES))


@router.get("", response_model=list[McpTokenRead])
def list_tokens(db: Session = Depends(get_db)) -> list[McpTokenRead]:
    return [_to_read(r) for r in mcp_token_service.list_tokens(db, _DEFAULT_USER_ID)]


@router.post("", response_model=McpTokenCreateResponse)
def create_token(
    payload: McpTokenCreateRequest, db: Session = Depends(get_db)
) -> McpTokenCreateResponse:
    try:
        issued = mcp_token_service.create_token(
            db, _DEFAULT_USER_ID, payload.name, payload.scopes
        )
    except mcp_token_service.McpTokenError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return McpTokenCreateResponse(
        token=_to_read(issued.record),
        plain_token=issued.plain_token,
        mcp_config=_mcp_config(issued.plain_token),
        warning="Token chỉ hiện 1 lần — copy và lưu ngay, rời trang là không lấy lại được.",
    )


@router.delete("/{token_id}", status_code=204)
def revoke_token(token_id: int, db: Session = Depends(get_db)) -> None:
    revoked = mcp_token_service.revoke_token(db, _DEFAULT_USER_ID, token_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Không tìm thấy token còn hiệu lực")
