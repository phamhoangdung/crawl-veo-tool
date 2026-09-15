from datetime import datetime

from pydantic import BaseModel


class YoutubeCategoryRead(BaseModel):
    id: str
    name: str


class YoutubeVideoRead(BaseModel):
    video_id: str
    title: str
    channel_title: str
    thumbnail_url: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    published_at: str | None = None


class YoutubeTrendingPageRead(BaseModel):
    videos: list[YoutubeVideoRead]
    next_page_token: str | None = None
    has_more: bool = False


class TopicCreateRequest(BaseModel):
    name: str
    query: str | None = None
    note: str | None = None


class TopicRead(BaseModel):
    id: int
    name: str
    query: str
    note: str | None = None
    created_at: datetime
    score: float | None = None
    sample_video_count: int | None = None
    competition_count: int | None = None
    top_video_title: str | None = None
    top_video_url: str | None = None
    scored_at: datetime | None = None
