from datetime import datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

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
    # Phase 22: id kênh thật — điền song song với author_name khi tạo Video.
    channel_id: str | None = None


class JobFromSelectionRequest(BaseModel):
    videos: list[SelectedVideo]
    # Phase 20: màn Khám phá tải thẳng khi bấm "Tải video đã chọn" — trước đây
    # chỉ tạo job rồi im lặng, không màn hình nào hiển thị lại được (xem
    # docs/phases/phase-20-discovery-workspace.md mục "Khảo sát" điểm 1). Vẫn
    # để cờ tắt được (mặc định True) cho các lối gọi khác trong tương lai muốn
    # chỉ tạo job mà chưa tải ngay.
    download: bool = True


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
    # Chỉ set ở luồng search: video này đã có trong thư viện từ trước (không phải
    # vừa thêm bởi job này). Mặc định False cho các luồng khác.
    already_in_library: bool = False


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
    # Đọc từ `result_videos` (toàn bộ kết quả Bilibili, gồm cả video đã có trong
    # thư viện) khi service set thuộc tính đó; nếu không thì về `videos` như cũ —
    # các luồng khác (from-selection) không set `result_videos`.
    videos: list[VideoRead] = Field(validation_alias=AliasChoices("result_videos", "videos"))
    # Không lưu DB — chỉ set tạm ở create_bilibili_crawl_job để frontend cảnh
    # báo khi dịch từ khoá thất bại (search bằng nguyên văn gần như 0 kết quả).
    translation_failed: bool = False
    # Số video trong kết quả đã có sẵn trong thư viện — vẫn hiện đầy đủ, chỉ để
    # UI đánh dấu "đã tải" thay vì ẩn đi.
    already_in_library: int = 0
    total_found: int = 0
