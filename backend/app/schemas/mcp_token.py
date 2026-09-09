from datetime import datetime

from pydantic import BaseModel, Field


class McpTokenCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    scopes: list[str]


class McpTokenRead(BaseModel):
    id: int
    name: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class McpTokenCreateResponse(BaseModel):
    token: McpTokenRead
    plain_token: str
    mcp_config: dict
    warning: str


class McpScopesResponse(BaseModel):
    scopes: list[str]
