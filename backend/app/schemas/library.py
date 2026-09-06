from datetime import datetime

from pydantic import BaseModel


class LibraryItemRead(BaseModel):
    id: int
    title: str
    platform: str
    status: str
    has_dubbed: bool
    has_burned: bool
    created_at: datetime
