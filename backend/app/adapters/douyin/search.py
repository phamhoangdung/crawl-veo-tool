"""Search Douyin videos by keyword (Phase 3, researched + verified 2026-09-15).

**Important finding, very different from the video-download part:** the search endpoint
(`aweme/v1/web/general/search/single/`) requires:
1. The `a_bogus` anti-bot signature on EVERY query param (see `_vendor_abogus.py`).
2. **A real logged-in account cookie** — not an anonymous cookie like video download.
   Verified with a real request (2026-09-15, no cookie): the server returns HTTP 200 with
   `{"status_code": 2483, "status_msg": "请先登录，再继续搜索吧"}` ("please log in
   before searching"). The a_bogus signature is syntactically correct (not blocked at the
   anti-bot layer), but blocked at the business layer for lack of a login session.

So this is a "probe" like `douyin_service.probe_share_url()`: it builds the correctly signed request,
classifies the "login required" error separately from other errors, while the JSON shape
of a **successful search** (with a real login cookie) is still UNKNOWN — we do not guess,
leaving the result-reading part to a later session that has a real login cookie.
"""

import base64
import random

import httpx

from app.adapters.douyin._vendor_abogus import ABogus, BrowserFingerprintGenerator

_SEARCH_URL = "https://www.douyin.com/aweme/v1/web/general/search/single/"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
)

# Matches `BaseRequestModel` in f2/apps/douyin/model.py (checked against the real source,
# not guessed) — the browser/version values are static strings imitating a specific
# Edge/Windows browser, with no need to update to the machine's real browser version.
_BASE_PARAMS: dict[str, str | int] = {
    "device_platform": "webapp",
    "aid": "6383",
    "channel": "channel_pc_web",
    "pc_client_type": 1,
    "publish_video_strategy_type": 2,
    "pc_libra_divert": "Windows",
    "version_code": "290100",
    "version_name": "29.1.0",
    "cookie_enabled": "true",
    "screen_width": 1920,
    "screen_height": 1080,
    "browser_language": "zh-CN",
    "browser_platform": "Win32",
    "browser_name": "Edge",
    "browser_version": "130.0.0.0",
    "browser_online": "true",
    "engine_name": "Blink",
    "engine_version": "130.0.0.0",
    "os_name": "Windows",
    "os_version": "10",
    "cpu_core_num": 12,
    "device_memory": 8,
    "platform": "PC",
    "downlink": 10,
    "effective_type": "4g",
    "round_trip_time": 100,
}

# Matches `PostSearch` in f2/apps/douyin/model.py.
_SEARCH_DEFAULTS: dict[str, str | int] = {
    "search_channel": "aweme_general",
    "filter_selected": "{}",
    "search_source": "normal_search",
    "search_id": "",
    "query_correct_type": 1,
    "is_filter_search": 0,
    "from_group_id": "",
    "need_filter_settings": 1,
}


class DouyinLoginRequiredError(RuntimeError):
    """Douyin refuses the search for lack of a real logged-in ACCOUNT session — unlike
    `DouyinCookieExpiredError` (anonymous cookie missing/expired) in that the
    required action is to really log in, not just open the page and copy a cookie."""


class DouyinSearchError(RuntimeError):
    """Douyin returned a non-zero `status_code` that is not the known "login required" error."""


def _gen_fake_ms_token(length: int = 107) -> str:
    """A fake msToken (the real Douyin msToken-issuing endpoint is not called) — verified
    with a real request (2026-09-15): a self-generated fake msToken got the same response as
    a real msToken fetched via mssdk, i.e. the server does not check it strictly at this step. Generating it
    locally avoids calling yet another network endpoint just to get a token."""
    raw = bytes(random.getrandbits(8) for _ in range(length))
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _sign(params: dict[str, str | int]) -> str:
    """Append `a_bogus` to the end of the query string, returning the full signed URL."""
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    browser_fp = BrowserFingerprintGenerator.generate_fingerprint("Edge")
    signed_params, _ab_value, _ua = ABogus(fp=browser_fp, user_agent=_USER_AGENT).generate_abogus(
        param_str, "GET"
    )
    return f"{_SEARCH_URL}?{signed_params}"


async def probe_search(keyword: str, cookie: str, *, offset: int = 0, count: int = 15) -> dict:
    """Really call the search endpoint, returning raw JSON or raising a classified error.

    Raises `DouyinLoginRequiredError` when Douyin says login is required (status_code
    2483 — a code verified for real, not guessed), and `DouyinSearchError` for the remaining
    non-zero `status_code` values (never seen for real; Douyin's message is kept as is
    to ease lookup when encountered).
    """
    params = {
        **_BASE_PARAMS,
        "msToken": _gen_fake_ms_token(),
        **_SEARCH_DEFAULTS,
        "keyword": keyword,
        "offset": offset,
        "count": count,
    }
    url = _sign(params)
    headers = {
        "User-Agent": _USER_AGENT,
        "Referer": "https://www.douyin.com/",
    }
    if cookie:
        headers["Cookie"] = cookie

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()

    status_code = data.get("status_code")
    if status_code == 2483:
        raise DouyinLoginRequiredError(data.get("status_msg", "Cần đăng nhập Douyin"))
    if status_code not in (0, None):
        raise DouyinSearchError(f"status_code={status_code}: {data.get('status_msg')}")

    return data
