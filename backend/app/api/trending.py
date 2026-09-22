from collections import defaultdict

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.category import Category
from app.schemas.trending import (
    CategoryHistoryRead,
    CategoryRead,
    CategoryStatsRead,
    FollowCategoriesRequest,
    SnapshotPoint,
    TrendingPageRead,
    TrendingVideoRead,
)
from app.services import category_service, trending_service

router = APIRouter(prefix="/api/trending/bilibili", tags=["trending"])

# MVP: 1 user cố định — xem app/api/crawl.py.
_DEFAULT_USER_ID = 1


def _to_read(category: Category) -> CategoryRead:
    return CategoryRead(
        rid=category.rid,
        name=category.name_vi or category.name_zh,
        name_zh=category.name_zh,
        group=category.group_name,
        is_followed=category.is_followed,
    )


def _queue_translation_if_pending(background_tasks: BackgroundTasks, db: Session) -> None:
    """Dịch tên chuyên mục chạy NỀN, không chặn response — chỉ xếp hàng khi thật
    sự còn mục chưa dịch, tránh tốn 1 query đếm + spawn task thừa mỗi lần load
    trang. An toàn dùng chung `db` của request: FastAPI đảm bảo cleanup của
    dependency `yield` (đóng session) chạy SAU khi background task xong."""
    if category_service.count_pending_translations(db) > 0:
        background_tasks.add_task(
            category_service.translate_missing_names, db, _DEFAULT_USER_ID
        )


@router.get("/categories", response_model=list[CategoryRead])
async def categories(
    background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> list[CategoryRead]:
    """Chuyên mục đã phát hiện, lấy từ DB (không hardcode — xem category_service).

    Mỗi lần gọi cũng tự động dịch nốt tên còn thiếu ở nền — người dùng không cần
    bấm "Quét chuyên mục mới" nhiều lần chỉ để chờ dịch xong hết backlog.
    """
    _queue_translation_if_pending(background_tasks, db)
    rows = db.query(Category).order_by(Category.rid).all()
    return [_to_read(c) for c in rows]


@router.post("/categories/refresh", response_model=list[CategoryRead])
async def refresh_categories(
    background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> list[CategoryRead]:
    """Quét API Bilibili tìm chuyên mục mới; dịch tên chạy nền (xem docstring
    `_queue_translation_if_pending`) — response trả về ngay, không chờ dịch."""
    await category_service.discover_categories(db)
    _queue_translation_if_pending(background_tasks, db)
    rows = db.query(Category).order_by(Category.rid).all()
    return [_to_read(c) for c in rows]


@router.put("/categories/followed", response_model=list[int])
async def set_followed(
    payload: FollowCategoriesRequest, db: Session = Depends(get_db)
) -> list[int]:
    category_service.set_followed(db, payload.rids)
    return category_service.get_followed_rids(db)


@router.get("/categories/followed", response_model=list[int])
async def get_followed(db: Session = Depends(get_db)) -> list[int]:
    return category_service.get_followed_rids(db)


@router.get("/popular", response_model=TrendingPageRead)
async def popular(
    page: int = 1, page_size: int = 20, db: Session = Depends(get_db)
) -> TrendingPageRead:
    """Danh sách phổ biến toàn trang Bilibili — dùng cho tab "Tất cả" (không
    giới hạn theo chuyên mục), có phân trang thật."""
    return await trending_service.get_bilibili_popular_page(db, page=page, page_size=page_size)


@router.get("/search", response_model=TrendingPageRead)
async def search(
    keyword: str,
    page: int = 1,
    translate_keyword: bool = False,
    db: Session = Depends(get_db),
) -> TrendingPageRead:
    """Tìm kiếm tự do theo từ khoá bất kỳ — không giới hạn trong 1 chuyên mục.

    `translate_keyword` giống hệt tuỳ chọn cùng tên ở trang Crawl (`POST
    /api/jobs`) — trước đây trang Trending thiếu tuỳ chọn này dù dùng cùng
    nguồn Bilibili, search tiếng Việt gần như luôn ra 0 kết quả.
    """
    return await trending_service.search_bilibili(
        db, _DEFAULT_USER_ID, keyword, page=page, translate_keyword=translate_keyword
    )


@router.get("/related", response_model=TrendingPageRead)
async def related(bvid: str, db: Session = Depends(get_db)) -> TrendingPageRead:
    """Video liên quan (Phase 22) — dùng cho dải "Video tương tự" trong popup
    xem trước. Endpoint công khai, không cần WBI, rủi ro risk-control thấp."""
    return await trending_service.get_related(db, bvid)


@router.get("/channel/{channel_id}/videos", response_model=TrendingPageRead)
async def channel_videos(
    channel_id: str, page: int = 1, db: Session = Depends(get_db)
) -> TrendingPageRead:
    """Video khác trong 1 kênh (Phase 22) — có thể trả `degraded=True` khi bị
    Bilibili risk-control chặn (đo thật 2026-09-22: rủi ro này RẤT cao, xem
    docstring `channel_service.ChannelVideosResult`). Frontend phải hiện đúng
    thông báo suy giảm, không coi là danh sách rỗng."""
    return await trending_service.get_channel_videos(db, channel_id, page=page)


@router.get("/ranking", response_model=list[TrendingVideoRead])
async def ranking(rid: int = 1, day: int = 3) -> list[TrendingVideoRead]:
    return await trending_service.get_bilibili_ranking(rid=rid, day=day)


@router.get("/category-page", response_model=TrendingPageRead)
async def category_page(
    rid: int, page: int = 1, day: int = 3, db: Session = Depends(get_db)
) -> TrendingPageRead:
    """1 trang video của chuyên mục — dùng cho infinite scroll ở trang Trending."""
    return await trending_service.get_category_page(db, rid=rid, page=page, day=day)


@router.get("/stats", response_model=list[CategoryStatsRead])
async def stats(
    rids: str = Query(..., description="Danh sách rid, phân tách bằng dấu phẩy"),
    day: int = 3,
    db: Session = Depends(get_db),
) -> list[CategoryStatsRead]:
    """Số liệu hiện tại của từng chuyên mục; mỗi lần gọi ghi thêm 1 điểm lịch sử."""
    parsed = [int(part) for part in rids.split(",") if part.strip().isdigit()]
    return await trending_service.get_categories_stats(db, parsed, day=day)


@router.get("/history", response_model=list[CategoryHistoryRead])
async def history(
    rids: str = Query(..., description="Danh sách rid, phân tách bằng dấu phẩy"),
    days: int = 30,
    db: Session = Depends(get_db),
) -> list[CategoryHistoryRead]:
    """Lịch sử số liệu đã tích luỹ, dùng vẽ đường xu hướng theo thời gian."""
    parsed = [int(part) for part in rids.split(",") if part.strip().isdigit()]
    snapshots = category_service.get_history(db, parsed, days=days)

    by_rid: dict[int, list[SnapshotPoint]] = defaultdict(list)
    for snapshot in snapshots:
        by_rid[snapshot.rid].append(
            SnapshotPoint(
                rid=snapshot.rid,
                captured_at=snapshot.captured_at,
                total_plays=snapshot.total_plays,
                avg_plays=snapshot.avg_plays,
                total_pts=snapshot.total_pts,
                heat_score=snapshot.heat_score,
            )
        )

    result: list[CategoryHistoryRead] = []
    for rid in parsed:
        category = db.get(Category, rid)
        if category is None:
            continue
        result.append(
            CategoryHistoryRead(
                rid=rid,
                name=category.name_vi or category.name_zh,
                points=by_rid.get(rid, []),
            )
        )
    return result
