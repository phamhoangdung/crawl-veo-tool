"""MCP server for external agents (Claude Code/Codex) to drive AI Studio — Phase 14.

Runs over stdio, spawned by the agent itself (`python -m app.mcp_server`), NOT a separate background
service. Each tool only calls the local REST API that is running — no business logic embedded,
so the UI and the agent always go through the same path (see research Part 6.2).

Configuration via environment variables:
  MCP_TOKEN     — the `sk_local_...` token created on the API Keys page (required)
  MCP_API_BASE  — defaults to http://127.0.0.1:8000

Quick try:  MCP_TOKEN=sk_local_xxx python -m app.mcp_server
"""

import logging
import os
import sys

import httpx
from mcp.server.mcpserver import MCPServer

logger = logging.getLogger(__name__)

# Log to stderr: stdout is the MCP protocol channel, printing anything there breaks the session.
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

server = MCPServer("crawl-veo-ai-studio")

_TIMEOUT_SECONDS = 600.0  # video generation can take a few minutes


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
    """List the existing character/scene reference image sets.

    The name (`name`) of each set is used as a mention in prompts: `@set_name`.
    """
    return await _request("GET", "/character-references")


@server.tool()
async def estimate_generation_cost(
    asset_type: str, model: str | None = None, duration_seconds: float = 5.0
) -> dict:
    """Estimate the cost (USD) before generating. Call this tool BEFORE generating a video.

    asset_type: "image" or "video".
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
    """Generate 1 keyframe image from a prompt (~50-100x cheaper than generating video).

    Use `@set_name` in the prompt to attach reference images, for example:
    "@hero @prop_bag medium shot, 50mm, standing at the bank counter".

    Returns `from_cache=true` if the identical request was generated before (no cost).
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
    """Generate a video clip from an existing keyframe image. EXPENSIVE — estimate the cost before calling.

    Pass `keyframe_end_asset_id` to interpolate motion between 2 images (better
    control, matching the previous/next scene). If the scene needs no real motion, use
    `make_ken_burns_clip` (free) instead of this tool.
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
    """Create a FREE clip from 1 still image using slow camera motion (ffmpeg).

    Use it for scenes that need no real motion (a talking head, a background scene) — this is the biggest way
    to cut cost compared with AI video generation.
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
    """List generated images/video. asset_type: "image" | "video" | empty = all."""
    params = {"asset_type": asset_type} if asset_type else {}
    return await _request("GET", "/assets", params=params)


@server.tool()
async def get_budget_status() -> dict:
    """See how much was spent this month and how much remains of the budget."""
    return await _request("GET", "/budget")


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
