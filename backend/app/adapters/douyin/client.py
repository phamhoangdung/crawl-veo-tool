"""Douyin: resolve link share + tải video không watermark.

Cơ chế resolve (theo cơ chế công khai của Douyin, không phải tài liệu chính thức):
1. Link share dạng `https://v.douyin.com/xxxxx/` redirect sang URL chứa aweme_id.
2. `get_video_detail()` gọi thẳng endpoint detail — dùng cho "Thăm dò" (xem
   `douyin_service.probe_share_url`), không dùng để tự bóc tách link tải nữa.

Phần tải (`download_no_watermark`) **giao cho yt-dlp** thay vì tự bóc tách JSON —
xem nghiên cứu 2026-09-15 trong docs/phases/phase-3-multiprovider-douyin.md:
yt-dlp có sẵn extractor Douyin (`DouyinIE`, dùng chung code với TikTok, gọi đúng
endpoint `aweme/v1/web/aweme/detail/` như `get_video_detail()` ở dưới), do cộng
đồng bảo trì mỗi khi Douyin đổi cơ chế chống bot — đỡ việc tự dò lại endpoint.

**Đã verify bằng lệnh gọi thật (2026-09-15, yt-dlp 2026.8.19, không cookie):**
lỗi trả về đúng "Fresh cookies (not necessarily logged in) are needed" — tức
yt-dlp KHÔNG né được việc cần cookie, chỉ đỡ việc tự viết code bóc JSON. Điểm
quan trọng: cookie này không cần đăng nhập tài khoản (`s_v_web_id` là cookie ẩn
danh chống bot, sinh ra khi trình duyệt chạy JS challenge lúc mở trang) — khác
với hiểu nhầm ban đầu là "cần cookie đăng nhập Douyin".
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
    """Cookie thiếu/hết hạn — 401/403 lặp lại, hoặc yt-dlp báo "fresh cookies needed"."""


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
        """Theo redirect của link share ngắn (v.douyin.com/...) để lấy aweme_id."""
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
        """Tải video không watermark bằng yt-dlp. Đồng bộ (blocking) — gọi qua
        `asyncio.to_thread` ở tầng service, không gọi trực tiếp trong code async.

        `dest_path` nên có sẵn đuôi `.mp4` — Douyin trả sẵn 1 luồng đã mux, không
        cần ghép video/audio riêng như Bilibili (DASH).
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
