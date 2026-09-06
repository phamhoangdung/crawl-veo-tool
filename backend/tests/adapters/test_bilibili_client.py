import httpx
import pytest

from app.adapters.bilibili import wbi
from app.adapters.bilibili.client import BilibiliApiError, BilibiliClient

_NAV_RESPONSE = {
    "code": 0,
    "data": {
        "wbi_img": {
            "img_url": "https://i0.hdslb.com/bfs/wbi/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png",
            "sub_url": "https://i0.hdslb.com/bfs/wbi/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png",
        }
    },
}


@pytest.fixture(autouse=True)
def _reset_wbi_cache():
    """Mixin key được cache module-level (xem wbi.py) — reset để mỗi test độc lập."""
    wbi._cached_mixin_key = None
    wbi._cached_at = 0.0
    yield


def _mock_transport(routes: dict[str, dict]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/x/web-interface/nav":
            return httpx.Response(200, json=_NAV_RESPONSE)
        payload = routes.get(request.url.path)
        assert payload is not None, f"unexpected request to {request.url}"
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handle)


@pytest.mark.asyncio
async def test_search_videos_strips_highlight_tags():
    routes = {
        "/x/web-interface/wbi/search/all/v2": {
            "code": 0,
            "data": {
                "result": [
                    {
                        "result_type": "video",
                        "data": [
                            {
                                "bvid": "BV1xxxxxxxx",
                                "title": '<em class="keyword">demo</em> video',
                                "author": "someone",
                                "duration": "12:34",
                            }
                        ],
                    }
                ]
            },
        }
    }
    async with httpx.AsyncClient(transport=_mock_transport(routes)) as http:
        results = await BilibiliClient(http_client=http).search_videos("demo")

    assert results == [
        {"bvid": "BV1xxxxxxxx", "title": "demo video", "author": "someone", "duration": "12:34"}
    ]


@pytest.mark.asyncio
async def test_search_videos_raises_on_api_error():
    routes = {"/x/web-interface/wbi/search/all/v2": {"code": -412, "message": "risk control"}}
    async with httpx.AsyncClient(transport=_mock_transport(routes)) as http:
        with pytest.raises(BilibiliApiError):
            await BilibiliClient(http_client=http).search_videos("demo")


@pytest.mark.asyncio
async def test_get_popular_returns_list():
    routes = {"/x/web-interface/popular": {"code": 0, "data": {"list": [{"bvid": "BV1yyyyyyyy"}]}}}
    async with httpx.AsyncClient(transport=_mock_transport(routes)) as http:
        items = await BilibiliClient(http_client=http).get_popular()

    assert items == [{"bvid": "BV1yyyyyyyy"}]


@pytest.mark.asyncio
async def test_get_ranking_returns_list():
    routes = {"/x/web-interface/ranking/region": {"code": 0, "data": [{"bvid": "BV1zzzzzzzz"}]}}
    async with httpx.AsyncClient(transport=_mock_transport(routes)) as http:
        items = await BilibiliClient(http_client=http).get_ranking(rid=1)

    assert items == [{"bvid": "BV1zzzzzzzz"}]


@pytest.mark.asyncio
async def test_get_play_streams_returns_dash_payload():
    routes = {
        "/x/player/wbi/playurl": {
            "code": 0,
            "data": {"dash": {"video": [{"baseUrl": "https://example.invalid/v.m4s"}], "audio": []}},
        }
    }
    async with httpx.AsyncClient(transport=_mock_transport(routes)) as http:
        dash = await BilibiliClient(http_client=http).get_play_streams("BV1xxxxxxxx", 123)

    assert dash["video"][0]["baseUrl"] == "https://example.invalid/v.m4s"
