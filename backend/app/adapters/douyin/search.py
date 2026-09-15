"""Tìm kiếm video Douyin theo từ khoá (Phase 3, nghiên cứu + verify 2026-09-15).

**Phát hiện quan trọng khác hẳn phần tải video:** endpoint tìm kiếm
(`aweme/v1/web/general/search/single/`) đòi hỏi:
1. Chữ ký chống bot `a_bogus` trên MỌI query param (xem `_vendor_abogus.py`).
2. **Cookie đăng nhập tài khoản thật** — không phải cookie ẩn danh như tải video.
   Đã verify bằng request thật (2026-09-15, không cookie): server trả HTTP 200 với
   `{"status_code": 2483, "status_msg": "请先登录，再继续搜索吧"}` ("vui lòng đăng
   nhập trước khi tìm kiếm"). Chữ ký a_bogus đúng cú pháp (không bị chặn ở tầng
   chống bot), nhưng bị chặn ở tầng nghiệp vụ vì thiếu phiên đăng nhập.

Vì vậy đây là "probe" giống `douyin_service.probe_share_url()`: xây đúng request
đã ký, phân loại lỗi "cần đăng nhập" tách biệt với lỗi khác, còn hình dạng JSON
lúc **tìm kiếm thành công** (có cookie đăng nhập thật) vẫn CHƯA biết — không đoán,
để phiên sau có cookie đăng nhập thật mới viết phần đọc kết quả.
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

# Khớp `BaseRequestModel` trong f2/apps/douyin/model.py (đối chiếu source thật,
# không đoán) — các giá trị browser/version là chuỗi tĩnh mô phỏng 1 trình duyệt
# Edge/Windows cụ thể, không cần cập nhật theo phiên bản trình duyệt thật của máy.
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

# Khớp `PostSearch` trong f2/apps/douyin/model.py.
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
    """Douyin từ chối tìm kiếm vì thiếu phiên ĐĂNG NHẬP tài khoản thật — khác
    với `DouyinCookieExpiredError` (cookie ẩn danh thiếu/hết hạn) ở chỗ hành
    động cần làm là đăng nhập thật, không chỉ mở trang rồi copy cookie."""


class DouyinSearchError(RuntimeError):
    """Douyin trả `status_code` khác 0 và không phải lỗi "cần đăng nhập" đã biết."""


def _gen_fake_ms_token(length: int = 107) -> str:
    """msToken giả (không gọi endpoint sinh msToken thật của Douyin) — đã verify
    bằng request thật (2026-09-15): msToken giả tự sinh nhận cùng phản hồi với
    msToken thật lấy qua mssdk, tức bước này server không kiểm tra chặt. Tự sinh
    tại chỗ tránh phải gọi thêm 1 endpoint mạng khác chỉ để lấy token."""
    raw = bytes(random.getrandbits(8) for _ in range(length))
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _sign(params: dict[str, str | int]) -> str:
    """Gắn `a_bogus` vào cuối chuỗi query, trả về URL đầy đủ đã ký."""
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    browser_fp = BrowserFingerprintGenerator.generate_fingerprint("Edge")
    signed_params, _ab_value, _ua = ABogus(fp=browser_fp, user_agent=_USER_AGENT).generate_abogus(
        param_str, "GET"
    )
    return f"{_SEARCH_URL}?{signed_params}"


async def probe_search(keyword: str, cookie: str, *, offset: int = 0, count: int = 15) -> dict:
    """Gọi thật endpoint tìm kiếm, trả về JSON thô hoặc ném lỗi đã phân loại.

    Ném `DouyinLoginRequiredError` khi Douyin báo cần đăng nhập (status_code
    2483 — mã đã verify thật, không đoán), `DouyinSearchError` cho các
    `status_code` khác 0 còn lại (chưa gặp thật, giữ nguyên message Douyin trả
    về để dễ tra cứu khi gặp).
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
