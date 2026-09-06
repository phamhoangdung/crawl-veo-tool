from fastapi import APIRouter

from app.schemas.trending import TrendingVideoRead
from app.services import trending_service

router = APIRouter(prefix="/api/trending/bilibili", tags=["trending"])


@router.get("/popular", response_model=list[TrendingVideoRead])
async def popular(page: int = 1, page_size: int = 20) -> list[TrendingVideoRead]:
    return await trending_service.get_bilibili_popular(page=page, page_size=page_size)


@router.get("/ranking", response_model=list[TrendingVideoRead])
async def ranking(rid: int = 1, day: int = 3) -> list[TrendingVideoRead]:
    return await trending_service.get_bilibili_ranking(rid=rid, day=day)
