from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.adapters.youtube.client import (
    YouTubeApiError,
    YouTubeInvalidKeyError,
    YouTubeNotConfiguredError,
    YouTubeQuotaExceededError,
)
from app.core.db import get_db
from app.schemas.youtube import YoutubeCategoryRead, YoutubeTrendingPageRead
from app.services import youtube_service

router = APIRouter(prefix="/api/trending/youtube", tags=["youtube"])

# MVP: 1 user cố định — xem app/api/crawl.py.
_DEFAULT_USER_ID = 1


def _handle_youtube_errors(exc: Exception):
    if isinstance(exc, YouTubeNotConfiguredError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, YouTubeQuotaExceededError):
        raise HTTPException(
            status_code=429,
            detail=f"YouTube Data API hết quota trong ngày (reset theo giờ Mỹ): {exc}",
        ) from exc
    if isinstance(exc, YouTubeInvalidKeyError):
        raise HTTPException(status_code=401, detail=f"API key YouTube không hợp lệ: {exc}") from exc
    if isinstance(exc, YouTubeApiError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    raise exc


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    return {"configured": youtube_service.is_configured(db, _DEFAULT_USER_ID)}


@router.get("/categories", response_model=list[YoutubeCategoryRead])
async def categories(
    region_code: str = "VN", db: Session = Depends(get_db)
) -> list[YoutubeCategoryRead]:
    try:
        return await youtube_service.list_categories(db, _DEFAULT_USER_ID, region_code)
    except Exception as exc:
        _handle_youtube_errors(exc)
        raise


@router.get("/trending", response_model=YoutubeTrendingPageRead)
async def trending(
    region_code: str = "VN",
    category_id: str | None = None,
    page_token: str | None = None,
    db: Session = Depends(get_db),
) -> YoutubeTrendingPageRead:
    try:
        return await youtube_service.get_trending_page(
            db,
            _DEFAULT_USER_ID,
            region_code=region_code,
            category_id=category_id,
            page_token=page_token,
        )
    except Exception as exc:
        _handle_youtube_errors(exc)
        raise
