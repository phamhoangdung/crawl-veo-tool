"""Test `YouTubeClient` — dựng theo tài liệu chính thức developers.google.com/
youtube/v3 (khác Bilibili/Douyin, không cần đoán field). Mock ở mức
`httpx.MockTransport`, không gọi API thật (cần key thật, xem
docs/phases/phase-17-content-opportunity.md)."""

import httpx
import pytest

from app.adapters.youtube.client import (
    YouTubeApiError,
    YouTubeClient,
    YouTubeInvalidKeyError,
    YouTubeQuotaExceededError,
)


def _mock_transport(routes: dict[str, dict]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        payload = routes.get(request.url.path)
        assert payload is not None, f"unexpected request to {request.url}"
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handle)


@pytest.mark.asyncio
async def test_list_video_categories_filters_non_assignable():
    routes = {
        "/youtube/v3/videoCategories": {
            "items": [
                {"id": "1", "snippet": {"title": "Phim & Hoạt hình", "assignable": True}},
                {"id": "2", "snippet": {"title": "Cũ (ngừng dùng)", "assignable": False}},
            ]
        }
    }
    async with httpx.AsyncClient(transport=_mock_transport(routes)) as http:
        items = await YouTubeClient("fake-key", http_client=http).list_video_categories("VN")

    assert [i["id"] for i in items] == ["1"]


@pytest.mark.asyncio
async def test_list_most_popular_passes_params_and_returns_payload():
    captured = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": [{"id": "abc"}], "nextPageToken": "n1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await YouTubeClient("fake-key", http_client=http).list_most_popular(
            "VN", category_id="10"
        )

    assert captured["params"]["chart"] == "mostPopular"
    assert captured["params"]["regionCode"] == "VN"
    assert captured["params"]["videoCategoryId"] == "10"
    assert captured["params"]["key"] == "fake-key"
    assert result["items"] == [{"id": "abc"}]


@pytest.mark.asyncio
async def test_quota_exceeded_maps_to_specific_error():
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "code": 403,
                    "message": "The request cannot be completed because you have exceeded your quota.",
                    "errors": [{"reason": "quotaExceeded"}],
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(YouTubeQuotaExceededError):
            await YouTubeClient("fake-key", http_client=http).list_most_popular("VN")


@pytest.mark.asyncio
async def test_invalid_key_maps_to_specific_error():
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": 400,
                    "message": "API key not valid. Please pass a valid API key.",
                    "errors": [{"reason": "badRequest"}],
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(YouTubeInvalidKeyError):
            await YouTubeClient("bad-key", http_client=http).list_most_popular("VN")


@pytest.mark.asyncio
async def test_unknown_error_falls_back_to_generic_api_error():
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "internal error", "errors": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(YouTubeApiError):
            await YouTubeClient("fake-key", http_client=http).list_most_popular("VN")


@pytest.mark.asyncio
async def test_list_videos_stats_empty_ids_skips_request():
    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not call API with empty id list")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        result = await YouTubeClient("fake-key", http_client=http).list_videos_stats([])

    assert result == []


@pytest.mark.asyncio
async def test_search_videos_includes_published_after_when_given():
    captured = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"items": [], "pageInfo": {"totalResults": 0}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        await YouTubeClient("fake-key", http_client=http).search_videos(
            "review dien thoai", published_after="2026-08-01T00:00:00Z"
        )

    assert captured["params"]["publishedAfter"] == "2026-08-01T00:00:00Z"
    assert captured["params"]["order"] == "viewCount"
