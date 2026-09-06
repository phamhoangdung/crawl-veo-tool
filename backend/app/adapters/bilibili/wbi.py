"""Ký WBI cho các API cần chữ ký của Bilibili (search, playurl...).

Cơ chế: Bilibili trộn 2 khoá (img_key, sub_key) lấy từ endpoint `nav` qua 1 bảng
hoán vị cố định (mixin_key_table) thành 1 mixin_key 32 ký tự, dùng để md5-sign
query string của mỗi request kèm timestamp (wts). Khoá đổi theo ngày nên cache
vài giờ là đủ, không cần fetch lại mỗi request.
"""

import hashlib
import time
from urllib.parse import urlencode

import httpx

_MIXIN_KEY_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

_CACHE_TTL_SECONDS = 6 * 60 * 60
_cached_mixin_key: str | None = None
_cached_at: float = 0.0


def _build_mixin_key(img_key: str, sub_key: str) -> str:
    raw = img_key + sub_key
    return "".join(raw[i] for i in _MIXIN_KEY_TABLE)[:32]


async def _fetch_mixin_key(client: httpx.AsyncClient) -> str:
    response = await client.get("https://api.bilibili.com/x/web-interface/nav")
    response.raise_for_status()
    wbi_img = response.json()["data"]["wbi_img"]
    img_key = wbi_img["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sub_key = wbi_img["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    return _build_mixin_key(img_key, sub_key)


async def _get_mixin_key(client: httpx.AsyncClient) -> str:
    global _cached_mixin_key, _cached_at
    if _cached_mixin_key is None or time.time() - _cached_at > _CACHE_TTL_SECONDS:
        _cached_mixin_key = await _fetch_mixin_key(client)
        _cached_at = time.time()
    return _cached_mixin_key


async def sign_params(client: httpx.AsyncClient, params: dict) -> dict:
    mixin_key = await _get_mixin_key(client)
    signed = {**params, "wts": int(time.time())}
    sorted_query = urlencode(sorted(signed.items()))
    signed["w_rid"] = hashlib.md5((sorted_query + mixin_key).encode()).hexdigest()
    return signed
