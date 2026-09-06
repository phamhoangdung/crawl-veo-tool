"""CHƯA TEST được với video/cookie thật — xem docs/phases/phase-3-multiprovider-douyin.md.

Cơ chế (theo cơ chế công khai của Douyin, không phải tài liệu chính thức):
1. Link share dạng `https://v.douyin.com/xxxxx/` redirect sang URL chứa aweme_id.
2. Gọi `aweme_id` qua endpoint detail để lấy metadata + `play_addr` (không watermark)
   khác với `play_addr_lowbr`/link share công khai (có watermark do app chèn khi share).
3. Một số endpoint cần cookie hợp lệ (đăng nhập) mới trả đủ dữ liệu — cần cookie thật
   để xác nhận endpoint nào đủ dùng ở thời điểm implement.
"""

import re

import httpx

_MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
    ),
}
_AWEME_ID_RE = re.compile(r"/(?:video|note)/(\d+)")


class DouyinCookieExpiredError(RuntimeError):
    """401/403 lặp lại nhiều lần liên tiếp — cần refresh cookie."""


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
