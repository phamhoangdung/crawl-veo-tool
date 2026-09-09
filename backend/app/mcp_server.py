"""MCP server cho agent ngoài (Claude Code/Codex) điều khiển AI Studio — Phase 14.

Chạy qua stdio, do agent tự spawn (`python -m app.mcp_server`), KHÔNG phải service
nền riêng. Mỗi tool chỉ gọi REST API cục bộ đang chạy — không nhúng business logic,
để UI và agent luôn đi qua cùng một đường (xem research Phần 6.2).

Cấu hình qua biến môi trường:
  MCP_TOKEN     — token `sk_local_...` tạo ở trang API Keys (bắt buộc)
  MCP_API_BASE  — mặc định http://127.0.0.1:8000

Chạy thử:  MCP_TOKEN=sk_local_xxx python -m app.mcp_server
"""

import logging
import os
import sys

import httpx
from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)

# Log ra stderr: stdout là kênh truyền protocol MCP, in gì vào đó là làm hỏng phiên.
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

server = MCPServer("crawl-veo-ai-studio")

_TIMEOUT_SECONDS = 600.0  # sinh video có thể mất vài phút


def _api_base() -> str:
    return os.environ.get("MCP_API_BASE", "http://127.0.0.1:8000").rstrip("/")


def _headers() -> dict[str, str]:
    token = os.environ.get("MCP_TOKEN", "")
    if not token:
        raise RuntimeError(
            "Thiếu MCP_TOKEN — tạo token ở trang API Keys rồi dán vào config MCP."
        )
    return {"Authorization": f"Bearer {token}"}


async def _request(method: str, path: str, **kwargs) -> dict | list:
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.request(
            method, f"{_api_base()}/api/ai-studio{path}", headers=_headers(), **kwargs
        )
    if response.status_code >= 400:
        detail = _extract_detail(response)
        raise RuntimeError(f"[HTTP {response.status_code}] {detail}")
    return response.json()


def _extract_detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text


@server.tool()
async def list_character_references() -> list:
    """Liệt kê các bộ ảnh tham chiếu nhân vật/cảnh đã có.

    Tên (`name`) của mỗi bộ dùng làm mention trong prompt: `@ten_bo_anh`.
    """
    return await _request("GET", "/character-references")


@server.tool()
async def estimate_generation_cost(
    asset_type: str, model: str | None = None, duration_seconds: float = 5.0
) -> dict:
    """Ước tính chi phí (USD) trước khi sinh. Gọi tool này TRƯỚC khi sinh video.

    asset_type: "image" hoặc "video".
    """
    params: dict[str, object] = {"asset_type": asset_type, "duration_seconds": duration_seconds}
    if model:
        params["model"] = model
    return await _request("GET", "/cost-estimate", params=params)


@server.tool()
async def generate_keyframe(
    prompt: str,
    model: str | None = None,
    character_ref_id: int | None = None,
    output_prefix: str | None = None,
    confirm_expensive: bool = False,
) -> dict:
    """Sinh 1 ảnh keyframe từ prompt (rẻ hơn sinh video ~50-100 lần).

    Gọi `@ten_bo_anh` trong prompt để đính kèm ảnh tham chiếu, ví dụ:
    "@hero @prop_bag medium shot, 50mm, standing at the bank counter".

    Trả về `from_cache=true` nếu yêu cầu y hệt đã sinh trước đó (không tốn phí).
    """
    payload = {
        "prompt": prompt,
        "model": model,
        "character_ref_id": character_ref_id,
        "output_prefix": output_prefix,
        "confirm_expensive": confirm_expensive,
    }
    return await _request("POST", "/generate/keyframe", json=payload)


@server.tool()
async def generate_video_clip(
    prompt: str,
    keyframe_start_asset_id: int,
    keyframe_end_asset_id: int | None = None,
    model: str | None = None,
    duration_seconds: float = 5.0,
    output_prefix: str | None = None,
    confirm_expensive: bool = False,
) -> dict:
    """Sinh video clip từ ảnh keyframe đã có. ĐẮT — ước tính chi phí trước khi gọi.

    Truyền `keyframe_end_asset_id` để nội suy chuyển động giữa 2 ảnh (kiểm soát
    tốt hơn, khớp cảnh trước/sau). Nếu cảnh không cần chuyển động thật, dùng
    `make_ken_burns_clip` (miễn phí) thay cho tool này.
    """
    payload = {
        "prompt": prompt,
        "keyframe_start_asset_id": keyframe_start_asset_id,
        "keyframe_end_asset_id": keyframe_end_asset_id,
        "model": model,
        "duration_seconds": duration_seconds,
        "output_prefix": output_prefix,
        "confirm_expensive": confirm_expensive,
    }
    return await _request("POST", "/generate/video-clip", json=payload)


@server.tool()
async def make_ken_burns_clip(
    keyframe_asset_id: int,
    duration_seconds: float = 5.0,
    motion: str = "zoom_in",
    output_prefix: str | None = None,
) -> dict:
    """Tạo clip MIỄN PHÍ từ 1 ảnh tĩnh bằng chuyển động camera chậm (ffmpeg).

    Dùng cho cảnh không cần chuyển động thật (người nói, cảnh nền) — đây là cách
    giảm chi phí lớn nhất so với sinh video AI.
    motion: "zoom_in" | "zoom_out" | "pan_right".
    """
    payload = {
        "keyframe_asset_id": keyframe_asset_id,
        "duration_seconds": duration_seconds,
        "motion": motion,
        "output_prefix": output_prefix,
    }
    return await _request("POST", "/generate/ken-burns", json=payload)


@server.tool()
async def list_generated_assets(asset_type: str | None = None) -> list:
    """Liệt kê ảnh/video đã sinh. asset_type: "image" | "video" | bỏ trống = tất cả."""
    params = {"asset_type": asset_type} if asset_type else {}
    return await _request("GET", "/assets", params=params)


@server.tool()
async def get_budget_status() -> dict:
    """Xem đã chi bao nhiêu trong tháng và còn lại bao nhiêu trong hạn mức."""
    return await _request("GET", "/budget")


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
