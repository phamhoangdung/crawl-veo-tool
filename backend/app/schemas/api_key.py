from datetime import datetime

from pydantic import BaseModel

from app.models.api_key import ApiKeyStatus


class ApiKeyAddRequest(BaseModel):
    provider: str
    api_key: str
    label: str | None = None


class ApiKeyUpdateRequest(BaseModel):
    label: str | None = None
    status: ApiKeyStatus | None = None


class ApiKeyRead(BaseModel):
    id: int
    provider: str
    label: str | None
    masked_key: str
    status: ApiKeyStatus
    request_count: int
    error_count: int
    last_used_at: datetime | None
    cooldown_until: datetime | None
    updated_at: datetime
