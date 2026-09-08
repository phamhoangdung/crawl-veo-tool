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
    # Không lưu DB — chỉ set tạm ở create_bilibili_crawl_job để frontend cảnh
    # báo khi dịch từ khoá thất bại (search bằng nguyên văn gần như 0 kết quả).
    translation_failed: bool = False
    # Số video Bilibili trả về nhưng bị lọc vì đã có trong DB, và tổng số tìm
    # được. Không có 2 số này thì "0 video" trông giống hệt "không tìm thấy gì".
    skipped_existing: int = 0
    total_found: int = 0
