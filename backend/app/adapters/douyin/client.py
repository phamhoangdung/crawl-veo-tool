"""Douyin: resolve share links + download videos without watermark.

Resolve mechanism (per Douyin's public behavior, not official documentation):
1. A share link like `https://v.douyin.com/xxxxx/` redirects to a URL containing the aweme_id.
2. `get_video_detail()` calls the detail endpoint directly — used for "probing" (see
   `douyin_service.probe_share_url`), no longer used to extract the download link ourselves.

The download part (`download_no_watermark`) is **delegated to yt-dlp** instead of parsing JSON ourselves —
see the 2026-09-15 research in docs/phases/phase-3-multiprovider-douyin.md:
yt-dlp already has a Douyin extractor (`DouyinIE`, sharing code with TikTok, calling the same
endpoint `aweme/v1/web/aweme/detail/` as `get_video_detail()` below), maintained by the
community whenever Douyin changes its anti-bot mechanism — saves re-probing the endpoint ourselves.

**Verified with a real call (2026-09-15, yt-dlp 2026.8.19, no cookie):**
the error returned is exactly "Fresh cookies (not necessarily logged in) are needed" — i.e.
yt-dlp does NOT avoid the need for a cookie, it only saves writing the JSON parsing code. The important
point: this cookie does not require logging into an account (`s_v_web_id` is an anonymous
anti-bot cookie, generated when the browser runs the JS challenge while opening the page) — unlike
the initial misunderstanding that a Douyin login cookie is required.
"""

import re
from pathlib import Path
from typing import Any

import httpx
import yt_dlp

_MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
    ),
}
_AWEME_ID_RE = re.compile(r"/(?:video|note)/(\d+)")


class DouyinCookieExpiredError(RuntimeError):
    """Cookie missing/expired — repeated 401/403, or yt-dlp reports "fresh cookies needed"."""


class DouyinClient:
    def __init__(self, cookie: str | None = None) -> None:
        headers = dict(_MOBILE_HEADERS)
        if cookie:
            headers["Cookie"] = cookie
        self._client = httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=True)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "DouyinClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def resolve_share_url(self, share_url: str) -> str:
        """Follow the redirect of a short share link (v.douyin.com/...) to get the aweme_id."""
        response = await self._client.get(share_url)
        match = _AWEME_ID_RE.search(str(response.url))
        if not match:
            raise ValueError(f"Không tìm thấy aweme_id trong URL đã resolve: {response.url}")
        return match.group(1)

    async def get_video_detail(self, aweme_id: str) -> dict:
        response = await self._client.get(
            "https://www.iesdouyin.com/aweme/v1/web/aweme/detail/",
            params={"aweme_id": aweme_id},
        )
        if response.status_code in (401, 403):
            raise DouyinCookieExpiredError(f"HTTP {response.status_code} khi gọi video detail")
        response.raise_for_status()
        return response.json()

    def download_no_watermark(self, aweme_id: str, dest_path: Path, *, cookie: str) -> dict[str, Any]:
        """Download the video without watermark using yt-dlp. Synchronous (blocking) — call it via
        `asyncio.to_thread` at the service layer, not directly in async code.

        `dest_path` should already end in `.mp4` — Douyin returns an already-muxed stream, so there is no
        need to merge video/audio separately like Bilibili (DASH).
        """
        video_url = f"https://www.douyin.com/video/{aweme_id}"
        ydl_opts: dict[str, Any] = {
            "outtmpl": str(dest_path),
            "http_headers": {"Cookie": cookie} if cookie else {},
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "merge_output_format": "mp4",
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            if "fresh cookies" in str(exc).lower() or "cookies" in str(exc).lower():
                raise DouyinCookieExpiredError(str(exc)) from exc
            raise
        return info or {}
