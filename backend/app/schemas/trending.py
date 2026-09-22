from datetime import datetime
from typing import Literal

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
    # Tổng điểm `pts` — điểm xếp hạng THẬT do Bilibili tự tính (tổng hợp
    # view+like+coin+share+lưu+thời gian), verify bằng request thật 2026-09-16:
    # thứ tự pts giảm dần khớp đúng thứ hạng trả về, kể cả khi lượt xem thô thì
    # không (video xem nhiều hơn nhưng mới/ít tương tác hơn vẫn xếp sau). Đáng
    # tin hơn `total_plays` để đo "độ hot thật" của 1 chuyên mục.
    total_pts: int
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
    # 4 field dưới verify field-mapping bằng request thật tới `x/web-interface/view`
    # (2026-09-16) — tên field thô của Bilibili (`review`/`video_review`) không tự
    # giải thích, đối chiếu với `stat.reply`/`stat.danmaku` mới biết chắc ý nghĩa.
    comment_count: int | None = None  # bình luận (ranking/search: `review`)
    danmaku_count: int | None = None  # chú thích trôi (ranking: `video_review`; search: `danmaku`)
    coin_count: int | None = None  # lượt tặng xu — chỉ ranking mới có, search không trả field này
    # Điểm xếp hạng thật của Bilibili (`pts`) — chỉ ranking mới có (search không
    # trả field này). None nghĩa là video này đến từ search, không phải đang
    # xếp hạng thật — frontend dùng để phân biệt, không phải video nào cũng "hot".
    heat_score: float | None = None
    published_at: str | None = None  # ISO 8601 UTC


class TrendingPageRead(BaseModel):
    """1 trang video. `has_more` cho frontend biết còn gì để lướt tiếp không."""

    videos: list[TrendingVideoRead]
    page: int
    has_more: bool
    # "ranking" = bảng xếp hạng thật theo chuyên mục (đúng nghĩa "đang xu hướng");
    # "popular" = danh sách phổ biến toàn trang Bilibili (tab "Tất cả", có phân
    # trang thật, không gắn 1 chuyên mục); "search" = tìm theo từ khoá (tên
    # chuyên mục khi lướt quá trang 1, hoặc ô tìm kiếm tự do) — rộng hơn nhưng
    # lẫn cả video không liên quan, KHÔNG phải "đang xu hướng". Frontend hiển
    # thị khác nhau theo từng nguồn, không nối liền như cùng 1 danh sách.
    source: Literal["ranking", "popular", "search"] = "ranking"
    # Chỉ có ý nghĩa khi source="search" và caller bật translate_keyword — báo
    # dịch từ khoá thất bại (đã tự rơi về tìm nguyên văn) để UI cảnh báo, giống
    # `translation_failed` của job crawl (xem crawl_service).
    translation_failed: bool = False


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
    # Tổng `pts` (điểm xếp hạng thật Bilibili) của các video đang rank trong
    # chuyên mục — dùng làm chỉ số chính để so sánh "độ hot" giữa chuyên mục,
    # thay cho `total_plays` (dễ bị lệch bởi 1 video cũ có view khủng nhưng
    # không còn ai quan tâm thật sự, xem docstring `SnapshotPoint.total_pts`).
    total_pts: int
    top_video_title: str | None = None
