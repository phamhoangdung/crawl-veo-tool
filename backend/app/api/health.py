from fastapi import APIRouter

from app.services import health_check_service

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/downloader")
async def downloader_health() -> dict:
    """Really call the 3 most-used Bilibili endpoints — run periodically (e.g. an external cron) to learn
    early when Bilibili changes its API, instead of only finding out when a real crawl job fails."""
    return await health_check_service.check_bilibili_downloader()
