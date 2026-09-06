from fastapi import APIRouter

from app.services import health_check_service

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/downloader")
async def downloader_health() -> dict:
    """Gọi thật 3 endpoint Bilibili hay dùng nhất — chạy định kỳ (vd cron ngoài) để biết
    sớm khi Bilibili đổi API, thay vì chỉ phát hiện khi 1 job crawl thật bị fail."""
    return await health_check_service.check_bilibili_downloader()
