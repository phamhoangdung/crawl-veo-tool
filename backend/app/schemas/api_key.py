from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApiKeySaveRequest(BaseModel):
    provider: str
    api_key: str


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    masked_key: str
    updated_at: datetime
