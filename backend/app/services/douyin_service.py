"""Douyin: kiểm tra cấu hình cookie và thăm dò một link chia sẻ (Phase 3).

**Phạm vi có chủ đích:** module này KHÔNG bóc tách link video không watermark.
Lý do: API detail của Douyin không có tài liệu công khai, hình dạng JSON chỉ biết
được khi gọi thật bằng cookie hợp lệ. Viết code bóc tách theo phỏng đoán sẽ tạo ra
thứ trông như chạy được nhưng sai ở chỗ không ai kiểm ra cho tới khi thử thật.

Thay vào đó, `probe_share_url()` gọi đúng hai bước đã có (resolve link ngắn → lấy
detail) rồi **báo cáo lại hình dạng JSON nhận được**. Khi bạn có cookie thật, chạy
một lần là biết chính xác cần đọc trường nào — lúc đó viết phần bóc tách mới có căn cứ.
"""

import logging

from app.adapters.douyin.client import DouyinClient, DouyinCookieExpiredError
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
