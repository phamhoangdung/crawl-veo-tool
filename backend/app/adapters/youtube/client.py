"""YouTube Data API v3 — ONLY used to watch trends/measure topic opportunity, NOT to download
videos (unlike Bilibili/Douyin). Per the user's request: "YouTube is only for watching
trends, not for taking videos".

Official API with full public documentation (developers.google.com/youtube/v3) —
unlike Bilibili/Douyin there is no need to guess fields. Free, limited by quota (default
10,000 units/day/project): `videos.list` = 1 unit, `search.list` = 100
units, `channels.list`/`videoCategories.list` = 1 unit (verified against the
official docs 2026-09-16, see docs/phases/phase-17-content-opportunity.md).
"""

import httpx

_BASE_URL = "https://www.googleapis.com/youtube/v3"


class YouTubeNotConfiguredError(RuntimeError):
    """No YouTube Data API key in the pool yet."""

    def __init__(self) -> None:
        super().__init__(
            "Chưa cấu hình API key YouTube Data API. Tạo key tại "
            "console.cloud.google.com (bật 'YouTube Data API v3'), rồi thêm "
            "vào trang API Keys với provider 'youtube'."
        )


class YouTubeQuotaExceededError(RuntimeError):
    """Out of quota for the day (10,000 units by default) — resets on Pacific
    Time (the timezone Google uses to compute quota), not on the Vietnam day."""


class YouTubeInvalidKeyError(RuntimeError):
    """Wrong key, deleted, or YouTube Data API v3 not enabled for that project."""


class YouTubeApiError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"YouTube API error {status_code}: {message}")
        self.status_code = status_code


class YouTubeClient:
    def __init__(self, api_key: str, http_client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._client = http_client or httpx.AsyncClient(timeout=15)
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "YouTubeClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _get(self, path: str, params: dict) -> dict:
        response = await self._client.get(
            f"{_BASE_URL}/{path}", params={**params, "key": self._api_key}
        )
        if response.status_code >= 400:
            self._raise_for_error(response)
        return response.json()

    def _raise_for_error(self, response: httpx.Response) -> None:
        """Map errors returned by Google to specific errors — the official documented
        error shape: `{"error": {"code": ..., "message": ..., "errors": [{"reason": ...}]}}`."""
        try:
            payload = response.json()
            error = payload.get("error", {})
            reason = (error.get("errors") or [{}])[0].get("reason", "")
            message = error.get("message", response.text)
        except ValueError:
            reason, message = "", response.text

        if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise YouTubeQuotaExceededError(message)
        if reason in ("keyInvalid", "badRequest") and response.status_code in (400, 403):
            raise YouTubeInvalidKeyError(message)
        raise YouTubeApiError(response.status_code, message)

    async def list_video_categories(self, region_code: str) -> list[dict]:
        payload = await self._get(
            "videoCategories", {"part": "snippet", "regionCode": region_code}
        )
        # Keep only categories still assignable — old/deprecated categories
        # may still appear in the response but are meaningless to pick.
        return [
            item
            for item in payload.get("items", [])
            if item.get("snippet", {}).get("assignable", True)
        ]

    async def list_most_popular(
        self,
        region_code: str,
        category_id: str | None = None,
        page_token: str | None = None,
        max_results: int = 24,
    ) -> dict:
        params: dict = {
            "part": "snippet,statistics,contentDetails",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": max_results,
        }
        if category_id:
            params["videoCategoryId"] = category_id
        if page_token:
            params["pageToken"] = page_token
        return await self._get("videos", params)

    async def search_videos(
        self,
        query: str,
        *,
        max_results: int = 25,
        order: str = "viewCount",
        published_after: str | None = None,
    ) -> dict:
        """Costs 100 units per call — only call when the user explicitly clicks to compute the
        topic score, never automatically/periodically."""
        params: dict = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": order,
            "maxResults": max_results,
        }
        if published_after:
            params["publishedAfter"] = published_after
        return await self._get("search", params)

    async def list_videos_stats(self, video_ids: list[str]) -> list[dict]:
        """`videos.list` by id — 1 unit per call regardless of many ids (up to 50 ids per call
        per the official docs), used to get views/likes after getting ids from search."""
        if not video_ids:
            return []
        payload = await self._get(
            "videos",
            {"part": "snippet,statistics", "id": ",".join(video_ids[:50])},
        )
        return payload.get("items", [])

    async def list_channels_stats(self, channel_ids: list[str]) -> list[dict]:
        if not channel_ids:
            return []
        payload = await self._get(
            "channels",
            {"part": "statistics", "id": ",".join(channel_ids[:50])},
        )
        return payload.get("items", [])
