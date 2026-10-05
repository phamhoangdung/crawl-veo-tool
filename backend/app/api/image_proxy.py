from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Response

router = APIRouter(prefix="/api/image", tags=["image"])

# Bilibili blocks hotlinking by Referer: requests from localhost get 403. This proxy calls
# on our behalf with a valid Referer. Currently the frontend uses referrerPolicy="no-referrer" which is enough,
# and this endpoint is kept as a fallback in case the CDN tightens up.
_BILIBILI_REFERER = "https://www.bilibili.com"

# Only proxy Bilibili's own image CDN — if it accepted arbitrary URLs, this endpoint would
# become an SSRF hole (making the backend call internal addresses).
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
        # Cover images do not change so cache freely, avoiding calling the CDN again on every render.
        headers={"Cache-Control": "public, max-age=86400"},
    )
