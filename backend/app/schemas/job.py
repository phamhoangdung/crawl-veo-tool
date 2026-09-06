from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.job import JobStatus, Platform
from app.models.video import VideoStatus


class JobCreateRequest(BaseModel):
    platform: Platform
    keyword: str


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    platform_video_id: str
    title: str
    author_name: str | None
    duration_seconds: int | None
    source_url: str
    status: VideoStatus
    created_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    keyword: str
    status: JobStatus
    created_at: datetime


class JobWithVideosRead(JobRead):
    videos: list[VideoRead]
