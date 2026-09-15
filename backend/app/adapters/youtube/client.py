"""YouTube Data API v3 — CHỈ dùng để xem xu hướng/đo cơ hội chủ đề, KHÔNG tải
video (khác Bilibili/Douyin). Theo yêu cầu người dùng: "ytb chỉ là để xem xu
hướng thôi, chứ ko lấy video về".

API chính thức, tài liệu công khai đầy đủ (developers.google.com/youtube/v3) —
khác Bilibili/Douyin không cần đoán field. Miễn phí, giới hạn theo quota (mặc
định 10.000 unit/ngày/project): `videos.list` = 1 unit, `search.list` = 100
unit, `channels.list`/`videoCategories.list` = 1 unit (verify qua tài liệu
chính thức 2026-09-16, xem docs/phases/phase-17-content-opportunity.md).
"""

import httpx

_BASE_URL = "https://www.googleapis.com/youtube/v3"


class YouTubeNotConfiguredError(RuntimeError):
    """Chưa có API key YouTube Data API trong pool."""

    def __init__(self) -> None:
        super().__init__(
            "Chưa cấu hình API key YouTube Data API. Tạo key tại "
            "console.cloud.google.com (bật 'YouTube Data API v3'), rồi thêm "
            "vào trang API Keys với provider 'youtube'."
        )


class YouTubeQuotaExceededError(RuntimeError):
    """Hết quota trong ngày (10.000 unit mặc định) — reset theo giờ Thái Bình
    Dương (múi giờ Google dùng để tính quota), không phải theo ngày VN."""


class YouTubeInvalidKeyError(RuntimeError):
    """Key sai, bị xoá, hoặc chưa bật YouTube Data API v3 cho project đó."""


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
        """Ánh xạ lỗi Google trả về sang lỗi cụ thể — dạng lỗi tài liệu chính
        thức: `{"error": {"code": ..., "message": ..., "errors": [{"reason": ...}]}}`."""
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
        # Chỉ giữ category còn cho phép duyệt (assignable) — category cũ/đã
        # ngừng dùng vẫn có thể xuất hiện trong response nhưng vô nghĩa để chọn.
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
        """Chi phí 100 unit/lần — chỉ gọi khi người dùng chủ động bấm tính điểm
        chủ đề, không gọi tự động/định kỳ."""
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
        """`videos.list` theo id — 1 unit/lần dù nhiều id (tối đa 50 id/lần
        theo tài liệu chính thức), dùng lấy view/like sau khi có id từ search."""
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
