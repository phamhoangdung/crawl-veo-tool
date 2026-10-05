"""Scope checking for requests coming from external agents through MCP — Phase 14.

Two kinds of clients share the `/api/ai-studio` endpoint:

- **Local web UI**: sends no token (it only runs on the user's machine; once multi-tenant
  arrives it will have its own auth — see docs/overview/plan.md). Let it through.
- **External agent via MCP**: sends `Authorization: Bearer sk_local_...`. With a token, the token
  MUST be valid and have the right scope, otherwise it is rejected.

This way scope really takes effect for agents without forcing the local UI to generate
a token itself — but a wrong/revoked token never slips through as "no
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
    """Create a dependency that checks 1 specific scope."""

    def dependency(request: Request, db: Session = Depends(get_db)) -> None:
        token = _bearer_token(request)
        if token is None:
            return  # local web UI

        record = mcp_token_service.authenticate(db, token)
        if record is None:
            raise HTTPException(status_code=401, detail="Token MCP không hợp lệ hoặc đã bị thu hồi")

        try:
            mcp_token_service.require_scope(record, scope)
        except mcp_token_service.McpTokenError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    return dependency
