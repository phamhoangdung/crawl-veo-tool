from pydantic import BaseModel


class TrendingVideoRead(BaseModel):
    bvid: str
    title: str
    author_name: str | None = None
    play_count: int | None = None
    duration_seconds: int | None = None
    cover_url: str | None = None
