from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.job import JobStatus, Platform
from app.models.video import VideoStatus


class JobCreateRequest(BaseModel):
    platform: Platform
    keyword: str
    # Bilibili là nền tảng Trung Quốc: search nguyên văn tiếng Việt gần như
    # không ra kết quả, nên cho phép dịch từ khoá sang tiếng Trung giản thể.
    translate_keyword: bool = False


class SelectedVideo(BaseModel):
    """1 video người dùng chọn ở trang Trending — metadata lấy sẵn từ danh sách."""

    bvid: str
    title: str
    author_name: str | None = None
    duration_seconds: int | None = None
    cover_url: str | None = None


class JobFromSelectionRequest(BaseModel):
    videos: list[SelectedVideo]


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    platform_video_id: str
    title: str
    author_name: str | None
    duration_seconds: int | None
    cover_url: str | None
    source_url: str
    status: VideoStatus
    created_at: datetime


class JobPageRead(BaseModel):
    """1 trang video tải thêm vào job — dùng cho infinite scroll trang Crawl."""

    videos: list[VideoRead]
    page: int
    has_more: bool


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: Platform
    keyword: str
    status: JobStatus
    created_at: datetime


class JobWithVideosRead(JobRead):
    videos: list[VideoRead]
