from collections import defaultdict
from typing import Literal

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

# MVP: 1 fixed user — see app/api/crawl.py.
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
    """Translate category names in the BACKGROUND, without blocking the response — only queue when there
    really are untranslated entries, avoiding 1 count query + a spare task spawn on every page
    load. Safe to share the request's `db`: FastAPI guarantees the cleanup of the `yield`
    dependency (closing the session) runs AFTER the background task finishes."""
    if category_service.count_pending_translations(db) > 0:
        background_tasks.add_task(
            category_service.translate_missing_names, db, _DEFAULT_USER_ID
        )


@router.get("/categories", response_model=list[CategoryRead])
async def categories(
    background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> list[CategoryRead]:
    """Categories already discovered, from the DB (not hardcoded — see category_service).

    Every call also translates any missing names in the background — the user does not need to
    click "Scan new categories" many times just to wait for the whole backlog to finish.
    """
    _queue_translation_if_pending(background_tasks, db)
    rows = db.query(Category).order_by(Category.rid).all()
    return [_to_read(c) for c in rows]


@router.post("/categories/refresh", response_model=list[CategoryRead])
async def refresh_categories(
    background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> list[CategoryRead]:
    """Scan the Bilibili API for new categories; translate names in the background (see the
    `_queue_translation_if_pending` docstring) — the response returns right away, without waiting for translation."""
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
    """Site-wide popular list of Bilibili — used for the "All" tab (not
    limited by category), with real pagination."""
    return await trending_service.get_bilibili_popular_page(db, page=page, page_size=page_size)


@router.get("/search", response_model=TrendingPageRead)
async def search(
    keyword: str,
    page: int = 1,
    translate_keyword: bool = False,
    db: Session = Depends(get_db),
) -> TrendingPageRead:
    """Free search by any keyword — not limited to 1 category.

    `translate_keyword` is identical to the option of the same name on the Crawl page (`POST
    /api/jobs`) — previously the Trending page lacked this option despite using the same
    Bilibili source, and Vietnamese search almost always returned 0 results.
    """
    return await trending_service.search_bilibili(
        db, _DEFAULT_USER_ID, keyword, page=page, translate_keyword=translate_keyword
    )


@router.get("/related", response_model=TrendingPageRead)
async def related(bvid: str, db: Session = Depends(get_db)) -> TrendingPageRead:
    """Related videos (Phase 22) — used for the "Similar videos" strip in the preview
    popup. Public endpoint, no WBI needed, low risk-control exposure."""
    return await trending_service.get_related(db, bvid)


@router.get("/channel/{channel_id}/videos", response_model=TrendingPageRead)
async def channel_videos(
    channel_id: str, page: int = 1, db: Session = Depends(get_db)
) -> TrendingPageRead:
    """Other videos of 1 channel (Phase 22) — may return `degraded=True` when blocked by
    Bilibili risk control (measured 2026-09-22: this risk is VERY high, see the
    `channel_service.ChannelVideosResult` docstring). The frontend must show the proper
    degraded-state message, not treat it as an empty list."""
    return await trending_service.get_channel_videos(db, channel_id, page=page)


# Bilibili only has 3-day and 7-day rankings — measured: day=1/30/90/365
# all return error -400. Block here to return a clear 422 instead of a confusing 500.
RankingDays = Literal[3, 7]


@router.get("/ranking", response_model=list[TrendingVideoRead])
async def ranking(
    rid: int = 1, day: RankingDays = 3
) -> list[TrendingVideoRead]:
    return await trending_service.get_bilibili_ranking(rid=rid, day=day)


@router.get("/category-page", response_model=TrendingPageRead)
async def category_page(
    rid: int, page: int = 1, day: RankingDays = 3, db: Session = Depends(get_db)
) -> TrendingPageRead:
    """1 page of videos of a category — used for infinite scroll on the Trending page."""
    return await trending_service.get_category_page(db, rid=rid, page=page, day=day)


@router.get("/stats", response_model=list[CategoryStatsRead])
async def stats(
    rids: str = Query(..., description="Danh sách rid, phân tách bằng dấu phẩy"),
    day: int = 3,
    db: Session = Depends(get_db),
) -> list[CategoryStatsRead]:
    """Current numbers of each category; every call records 1 more history point."""
    parsed = [int(part) for part in rids.split(",") if part.strip().isdigit()]
    return await trending_service.get_categories_stats(db, parsed, day=day)


@router.get("/history", response_model=list[CategoryHistoryRead])
async def history(
    rids: str = Query(..., description="Danh sách rid, phân tách bằng dấu phẩy"),
    days: int = 30,
    db: Session = Depends(get_db),
) -> list[CategoryHistoryRead]:
    """Accumulated history of the numbers, used to draw the trend line over time."""
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
