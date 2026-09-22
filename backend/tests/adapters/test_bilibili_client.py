import httpx
import pytest

from app.adapters.bilibili import wbi
from app.adapters.bilibili.client import (
    BilibiliApiError,
    BilibiliClient,
    BilibiliRiskControlError,
)

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


@pytest.mark.asyncio
async def test_get_related_returns_list():
    """Phase 22 — endpoint công khai, không cần WBI (không mock /nav route riêng)."""
    routes = {
        "/x/web-interface/archive/related": {
            "code": 0,
            "data": [{"bvid": "BV1related1", "owner": {"mid": 42, "name": "ai đó"}}],
        }
    }
    async with httpx.AsyncClient(transport=_mock_transport(routes)) as http:
        items = await BilibiliClient(http_client=http).get_related("BV1xxxxxxxx")

    assert items == [{"bvid": "BV1related1", "owner": {"mid": 42, "name": "ai đó"}}]


@pytest.mark.asyncio
async def test_get_space_videos_returns_vlist():
    routes = {
        "/x/space/wbi/arc/search": {
            "code": 0,
            "data": {"list": {"vlist": [{"bvid": "BV1space1", "mid": 42}]}},
        }
    }
    async with httpx.AsyncClient(transport=_mock_transport(routes)) as http:
        items = await BilibiliClient(http_client=http).get_space_videos("42")

    assert items == [{"bvid": "BV1space1", "mid": 42}]


@pytest.mark.asyncio
async def test_get_space_videos_raises_risk_control_on_http_412():
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/x/web-interface/nav":
            return httpx.Response(200, json=_NAV_RESPONSE)
        return httpx.Response(412, json={"code": -412, "message": "risk control"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        with pytest.raises(BilibiliRiskControlError):
            await BilibiliClient(http_client=http).get_space_videos("42")


@pytest.mark.asyncio
async def test_get_space_videos_raises_risk_control_on_code_352():
    """`风控校验失败` (đo thật 2026-09-22: mã lỗi phổ biến nhất khi bị chặn) —
    HTTP 200 nhưng payload `code=-352`, khác hẳn nhánh HTTP 412 ở test trên."""
    routes = {"/x/space/wbi/arc/search": {"code": -352, "message": "风控校验失败"}}
    async with httpx.AsyncClient(transport=_mock_transport(routes)) as http:
        with pytest.raises(BilibiliRiskControlError):
            await BilibiliClient(http_client=http).get_space_videos("42")


@pytest.mark.asyncio
async def test_get_space_videos_other_api_errors_not_wrapped_as_risk_control():
    """Lỗi khác (vd -404 kênh không tồn tại) không nên bị gộp chung thành
    risk-control — caller cần phân biệt được để không hiện nhầm thông báo."""
    routes = {"/x/space/wbi/arc/search": {"code": -404, "message": "not found"}}
    async with httpx.AsyncClient(transport=_mock_transport(routes)) as http:
        with pytest.raises(BilibiliApiError) as exc_info:
            await BilibiliClient(http_client=http).get_space_videos("42")
    assert not isinstance(exc_info.value, BilibiliRiskControlError)
