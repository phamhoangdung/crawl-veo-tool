"""Douyin: check the cookie configuration, probe share links, download videos, and search
by keyword (Phase 3).

`probe_share_url()` makes 2 public steps (resolve the short link → fetch detail) then reports
the JSON shape received — useful for a quick cookie/connection check without
downloading the whole video. `download_video()` delegates extraction/download to yt-dlp (see the docstring of
`app.adapters.douyin.client`) instead of guessing JSON fields.

`search_videos()` **needs a REAL logged-in account cookie**, unlike
`probe_share_url()`/`download_video()` which only need an anonymous cookie — verified with a
real request (see the docstring of `app.adapters.douyin.search`). `DOUYIN_COOKIE` is shared
by all 3 functions; if only an anonymous cookie is configured then `search_videos()` will raise
`DouyinLoginRequiredError` even though `is_configured()` returns `True`.
"""

import asyncio
import logging
from pathlib import Path

from app.adapters.douyin.client import DouyinClient
from app.adapters.douyin.search import probe_search
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DouyinNotConfiguredError(RuntimeError):
    """No Douyin cookie in the configuration."""

    def __init__(self) -> None:
        super().__init__(
            "Chưa cấu hình cookie Douyin. Đăng nhập Douyin trên trình duyệt, mở "
            "DevTools → Network → copy header Cookie, rồi dán vào DOUYIN_COOKIE "
            "trong backend/.env và khởi động lại backend."
        )


def is_configured() -> bool:
    return bool(get_settings().douyin_cookie.strip())


async def probe_share_url(share_url: str) -> dict:
    """Try to resolve the share link and fetch metadata, reporting the JSON structure received.

    Raises `DouyinNotConfiguredError` when there is no cookie, `DouyinCookieExpiredError`
    when Douyin returns 401/403 (cookie expired) — two very different situations so the
    UI must tell them apart: one is "go get a cookie", the other is "the old cookie
    expired, get it again".
    """
    if not is_configured():
        raise DouyinNotConfiguredError()

    cookie = get_settings().douyin_cookie.strip()
    async with DouyinClient(cookie=cookie) as client:
        aweme_id = await client.resolve_share_url(share_url)
        detail = await client.get_video_detail(aweme_id)

    logger.info("Douyin probe thành công: aweme_id=%s", aweme_id)
    return {
        "aweme_id": aweme_id,
        # The top-level keys and those inside `aweme_detail` — enough to know where to
        # read when writing the no-watermark link extraction.
        "top_level_keys": sorted(detail.keys()),
        "detail_keys": sorted(_detail_node(detail).keys()),
    }


async def download_video(share_url: str, dest_path: Path) -> dict:
    """Resolve the share link then download the video without watermark to `dest_path` (.mp4).

    Raises `DouyinNotConfiguredError` when there is no cookie, `DouyinCookieExpiredError`
    when the cookie is missing/expired (yt-dlp reports "fresh cookies needed", or HTTP 401/403
    during resolve) — the same 2 errors as `probe_share_url` so the UI handles them consistently.
    """
    if not is_configured():
        raise DouyinNotConfiguredError()

    cookie = get_settings().douyin_cookie.strip()
    async with DouyinClient(cookie=cookie) as client:
        aweme_id = await client.resolve_share_url(share_url)
        info = await asyncio.to_thread(
            client.download_no_watermark, aweme_id, dest_path, cookie=cookie
        )

    logger.info("Douyin tải thành công: aweme_id=%s -> %s", aweme_id, dest_path)
    return info


async def search_videos(keyword: str, *, offset: int = 0, count: int = 15) -> dict:
    """Search videos by keyword. Returns the raw JSON from Douyin (on success) — the JSON
    shape on success is NOT known yet (see the docstring of `app.adapters.douyin.search`),
    used for probing until a real login cookie is available.

    Raises `DouyinNotConfiguredError` (no cookie configured at all),
    `DouyinLoginRequiredError` (a cookie exists but is not a login cookie —
    the most common one you will hit until you log into Douyin for real),
    `DouyinSearchError` (other business errors from Douyin).
    """
    if not is_configured():
        raise DouyinNotConfiguredError()

    cookie = get_settings().douyin_cookie.strip()
    result = await probe_search(keyword, cookie, offset=offset, count=count)
    logger.info("Douyin search thành công: keyword=%s", keyword)
    return result


def _detail_node(payload: dict) -> dict:
    """The node holding the video metadata. Douyin used to put it at `aweme_detail`, and sometimes at
    `aweme_list[0]` — try both instead of assuming one and failing silently."""
    node = payload.get("aweme_detail")
    if isinstance(node, dict):
        return node
    items = payload.get("aweme_list")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return {}
