from pydantic import BaseModel


class ImportedVideoRead(BaseModel):
    id: int
    title: str
    status: str
    duration_seconds: int | None
    cover_url: str | None
