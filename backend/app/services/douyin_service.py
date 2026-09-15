"""Douyin: kiểm tra cấu hình cookie, thăm dò link chia sẻ, tải video, và tìm kiếm
theo từ khoá (Phase 3).

`probe_share_url()` gọi 2 bước công khai (resolve link ngắn → lấy detail) rồi báo
lại hình dạng JSON nhận được — hữu ích để kiểm tra cookie/kết nối nhanh mà không
tải cả video. `download_video()` giao việc bóc tách/tải cho yt-dlp (xem docstring
`app.adapters.douyin.client`) thay vì tự đoán field JSON.

`search_videos()` **cần cookie ĐĂNG NHẬP tài khoản thật**, khác với
`probe_share_url()`/`download_video()` chỉ cần cookie ẩn danh — đã verify bằng
request thật (xem docstring `app.adapters.douyin.search`). `DOUYIN_COOKIE` dùng
chung cho cả 3 hàm; nếu chỉ cấu hình cookie ẩn danh thì `search_videos()` sẽ ném
`DouyinLoginRequiredError` dù `is_configured()` trả `True`.
"""

import asyncio
import logging
from pathlib import Path

from app.adapters.douyin.client import DouyinClient
from app.adapters.douyin.search import probe_search
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class DouyinNotConfiguredError(RuntimeError):
    """Chưa có cookie Douyin trong cấu hình."""

    def __init__(self) -> None:
        super().__init__(
            "Chưa cấu hình cookie Douyin. Đăng nhập Douyin trên trình duyệt, mở "
            "DevTools → Network → copy header Cookie, rồi dán vào DOUYIN_COOKIE "
            "trong backend/.env và khởi động lại backend."
        )


def is_configured() -> bool:
    return bool(get_settings().douyin_cookie.strip())


async def probe_share_url(share_url: str) -> dict:
    """Thử resolve link chia sẻ và lấy metadata, báo lại cấu trúc JSON nhận được.

    Ném `DouyinNotConfiguredError` khi chưa có cookie, `DouyinCookieExpiredError`
    khi Douyin trả 401/403 (cookie hết hạn) — hai tình huống khác hẳn nhau nên
    UI phải phân biệt được: một bên là "đi lấy cookie đi", bên kia là "cookie cũ
    hết hạn rồi, lấy lại".
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
        # Các khoá ở tầng ngoài cùng và trong `aweme_detail` — đủ để biết phải
        # đọc vào đâu khi viết phần bóc tách link không watermark.
        "top_level_keys": sorted(detail.keys()),
        "detail_keys": sorted(_detail_node(detail).keys()),
    }


async def download_video(share_url: str, dest_path: Path) -> dict:
    """Resolve link chia sẻ rồi tải video không watermark về `dest_path` (.mp4).

    Ném `DouyinNotConfiguredError` khi chưa có cookie, `DouyinCookieExpiredError`
    khi cookie thiếu/hết hạn (yt-dlp báo "fresh cookies needed", hoặc HTTP 401/403
    lúc resolve) — cùng 2 lỗi như `probe_share_url` để UI xử lý nhất quán.
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
    """Tìm kiếm video theo từ khoá. Trả JSON thô từ Douyin (thành công) — hình
    dạng JSON lúc thành công CHƯA biết (xem docstring `app.adapters.douyin.search`),
    dùng để thăm dò cho tới khi có cookie đăng nhập thật.

    Ném `DouyinNotConfiguredError` (chưa cấu hình cookie gì cả),
    `DouyinLoginRequiredError` (có cookie nhưng không phải cookie đăng nhập —
    cái phổ biến nhất sẽ gặp cho tới khi bạn tự đăng nhập Douyin thật),
    `DouyinSearchError` (lỗi nghiệp vụ khác từ Douyin).
    """
    if not is_configured():
        raise DouyinNotConfiguredError()

    cookie = get_settings().douyin_cookie.strip()
    result = await probe_search(keyword, cookie, offset=offset, count=count)
    logger.info("Douyin search thành công: keyword=%s", keyword)
    return result


def _detail_node(payload: dict) -> dict:
    """Node chứa metadata video. Douyin từng đặt ở `aweme_detail`, cũng có khi ở
    `aweme_list[0]` — thử cả hai thay vì giả định một cái rồi hỏng lặng lẽ."""
    node = payload.get("aweme_detail")
    if isinstance(node, dict):
        return node
    items = payload.get("aweme_list")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return {}
