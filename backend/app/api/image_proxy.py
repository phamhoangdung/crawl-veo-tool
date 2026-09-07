from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Response

router = APIRouter(prefix="/api/image", tags=["image"])

# Bilibili chặn hotlink theo Referer: request từ localhost bị 403. Proxy này gọi
# hộ với Referer hợp lệ. Hiện frontend dùng referrerPolicy="no-referrer" là đủ,
# giữ endpoint này làm phương án dự phòng nếu CDN siết chặt hơn.
_BILIBILI_REFERER = "https://www.bilibili.com"

# Chỉ proxy đúng CDN ảnh của Bilibili — nếu nhận URL tuỳ ý, endpoint này trở
# thành lỗ hổng SSRF (bắt backend gọi tới địa chỉ nội bộ).
_ALLOWED_HOST_SUFFIXES = (".hdslb.com", ".bilibili.com")

_MAX_BYTES = 10 * 1024 * 1024


def _is_allowed(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in _ALLOWED_HOST_SUFFIXES)


@router.get("")
async def proxy_image(url: str = Query(..., description="URL ảnh trên CDN Bilibili")) -> Response:
    if not _is_allowed(url):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ ảnh từ CDN Bilibili.")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            upstream = await client.get(url, headers={"Referer": _BILIBILI_REFERER})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Không tải được ảnh: {exc}") from exc

    if upstream.status_code != 200:
        raise HTTPException(status_code=502, detail=f"CDN trả về {upstream.status_code}.")

    content_type = upstream.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=502, detail="URL không trỏ tới ảnh.")

    if len(upstream.content) > _MAX_BYTES:
        raise HTTPException(status_code=502, detail="Ảnh quá lớn.")

    return Response(
        content=upstream.content,
        media_type=content_type,
        # Ảnh cover không đổi nên cache thoải mái, đỡ gọi lại CDN mỗi lần render.
        headers={"Cache-Control": "public, max-age=86400"},
    )
