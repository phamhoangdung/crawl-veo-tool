from datetime import datetime

from pydantic import BaseModel


class CategoryRead(BaseModel):
    rid: int
    name: str
    # Tên tiếng Trung vừa để hiển thị, vừa làm từ khoá search khi lướt quá
    # 11 video mà ranking/region trả về.
    name_zh: str | None = None
    group: str | None = None
    is_followed: bool = False


class FollowCategoriesRequest(BaseModel):
    rids: list[int]


class SnapshotPoint(BaseModel):
    """1 điểm trên đường xu hướng của 1 chuyên mục."""

    rid: int
    captured_at: datetime
    total_plays: int
    avg_plays: int
    heat_score: float


class CategoryHistoryRead(BaseModel):
    rid: int
    name: str
    points: list[SnapshotPoint]


class TrendingVideoRead(BaseModel):
    bvid: str
    title: str
    author_name: str | None = None
    play_count: int | None = None
    like_count: int | None = None
    duration_seconds: int | None = None
    cover_url: str | None = None


class TrendingPageRead(BaseModel):
    """1 trang video. `has_more` cho frontend biết còn gì để lướt tiếp không."""

    videos: list[TrendingVideoRead]
    page: int
    has_more: bool


class CategoryStatsRead(BaseModel):
    """Thống kê 1 category, dùng vẽ chart so sánh mức độ quan tâm."""

    rid: int
    name: str
    group: str | None = None
    video_count: int
    total_plays: int
    avg_plays: int
    max_plays: int
    total_likes: int
    top_video_title: str | None = None
