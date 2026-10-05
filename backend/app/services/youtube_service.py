"""Watch YouTube trends — watch ONLY, no video download (see the docstring of
`app.adapters.youtube.client`). Shares the API key pool with the other providers
(Phase 8) to get rotation/failover if more YouTube keys are added later.
"""

from sqlalchemy.orm import Session

from app.adapters.youtube.client import (
    YouTubeApiError,
    YouTubeClient,
    YouTubeInvalidKeyError,
    YouTubeNotConfiguredError,
    YouTubeQuotaExceededError,
)
from app.schemas.youtube import (
    YoutubeCategoryRead,
    YoutubeTrendingPageRead,
    YoutubeVideoRead,
)
from app.services import api_key_service


async def run_with_key(db: Session, user_id: int, action):
    """Take 1 YouTube key from the pool, run `action(client)`, record
    success/failure so the pool knows which key needs a rest (like translate_service)."""
    picked = api_key_service.pick_decrypted_key(db, user_id, "youtube")
    if picked is None:
        raise YouTubeNotConfiguredError()
    key_id, api_key = picked

    async with YouTubeClient(api_key) as client:
        try:
            result = await action(client)
        except (YouTubeQuotaExceededError, YouTubeInvalidKeyError):
            api_key_service.mark_key_result(db, key_id, success=False)
            raise
        api_key_service.mark_key_result(db, key_id, success=True)
        return result


def is_configured(db: Session, user_id: int) -> bool:
    return api_key_service.get_decrypted_key(db, user_id, "youtube") is not None


def _from_video_item(item: dict) -> YoutubeVideoRead:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    thumbnails = snippet.get("thumbnails", {})
    thumb = thumbnails.get("medium") or thumbnails.get("default") or {}
    return YoutubeVideoRead(
        video_id=item["id"] if isinstance(item["id"], str) else item["id"]["videoId"],
        title=snippet.get("title", ""),
        channel_title=snippet.get("channelTitle", ""),
        thumbnail_url=thumb.get("url"),
        view_count=int(stats["viewCount"]) if "viewCount" in stats else None,
        like_count=int(stats["likeCount"]) if "likeCount" in stats else None,
        comment_count=int(stats["commentCount"]) if "commentCount" in stats else None,
        published_at=snippet.get("publishedAt"),
    )


async def list_categories(db: Session, user_id: int, region_code: str) -> list[YoutubeCategoryRead]:
    async def action(client: YouTubeClient) -> list[YoutubeCategoryRead]:
        items = await client.list_video_categories(region_code)
        return [
            YoutubeCategoryRead(id=item["id"], name=item["snippet"]["title"])
            for item in items
        ]

    return await run_with_key(db, user_id, action)


async def get_trending_page(
    db: Session,
    user_id: int,
    *,
    region_code: str,
    category_id: str | None,
    page_token: str | None,
) -> YoutubeTrendingPageRead:
    async def action(client: YouTubeClient) -> YoutubeTrendingPageRead:
        payload = await client.list_most_popular(
            region_code, category_id=category_id, page_token=page_token
        )
        videos = [_from_video_item(item) for item in payload.get("items", [])]
        next_token = payload.get("nextPageToken")
        return YoutubeTrendingPageRead(
            videos=videos, next_page_token=next_token, has_more=bool(next_token)
        )

    return await run_with_key(db, user_id, action)


__all__ = [
    "YouTubeApiError",
    "get_trending_page",
    "is_configured",
    "list_categories",
]
