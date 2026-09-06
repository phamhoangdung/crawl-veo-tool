from fastapi import APIRouter

from app.schemas.trending import CategoryRead, TrendingVideoRead
from app.services import trending_service

router = APIRouter(prefix="/api/trending/bilibili", tags=["trending"])

# rid xác nhận qua request thật tới ranking/region (đối chiếu field `typename`) —
# xem docs/phases/phase-1-crawl-bilibili.md mục Ghi chú. Category do người dùng chọn theo dõi trước.
DEFAULT_CATEGORIES = [
    CategoryRead(rid=71, name="Giải trí"),
    CategoryRead(rid=211, name="Ẩm thực"),
    CategoryRead(rid=21, name="Đời sống"),
]


@router.get("/categories", response_model=list[CategoryRead])
async def categories() -> list[CategoryRead]:
    return DEFAULT_CATEGORIES


@router.get("/popular", response_model=list[TrendingVideoRead])
async def popular(page: int = 1, page_size: int = 20) -> list[TrendingVideoRead]:
    return await trending_service.get_bilibili_popular(page=page, page_size=page_size)


@router.get("/ranking", response_model=list[TrendingVideoRead])
async def ranking(rid: int = 1, day: int = 3) -> list[TrendingVideoRead]:
    return await trending_service.get_bilibili_ranking(rid=rid, day=day)
