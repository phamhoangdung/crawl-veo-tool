"""Fake adapter for image/video generation — used when FALAI_MODE=fake (the default when there is
no real key yet). Generates files with ffmpeg instead of calling the API, so development costs nothing.

Deliberately simulates bad behavior too (delay, 429, blocked prompt, out of quota): these
situations are nearly impossible to reproduce on demand with the real API, so the fake adapter
can test more, not just cost less. See "Chế độ phát triển không tốn phí"
in docs/phases/phase-14-ai-video-generation.md.
"""

import asyncio
import logging
import random
from pathlib import Path

import httpx

from app.adapters import ffmpeg
from app.adapters.falai.errors import PromptBlockedError
from app.adapters.provider_errors import ProviderQuotaExceededError
from app.core.config import get_settings

logger = logging.getLogger(__name__)

PROVIDER_NAME = "falai-fake"


def _maybe_fail(prompt: str) -> None:
    settings = get_settings()

    if settings.falai_fake_force_error == "quota":
        raise ProviderQuotaExceededError(PROVIDER_NAME, _fake_429())
    if settings.falai_fake_force_error == "policy":
        raise PromptBlockedError(PROVIDER_NAME, "bị chặn theo cấu hình fake")

    if random.random() < settings.falai_fake_quota_error_rate:
        logger.info("fake adapter: mô phỏng lỗi 429")
        raise ProviderQuotaExceededError(PROVIDER_NAME, _fake_429())
    if random.random() < settings.falai_fake_policy_error_rate:
        logger.info("fake adapter: mô phỏng prompt bị chặn")
        raise PromptBlockedError(PROVIDER_NAME, "nội dung mô phỏng bị chặn")


def _fake_429() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://fake.local/generate")
    response = httpx.Response(429, request=request)
    return httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)


async def _simulate_latency(seconds: float) -> None:
    if seconds > 0:
        await asyncio.sleep(seconds)


def _label(prompt: str, extra: str) -> str:
    """Text overlay on the frame to tell clips apart when concatenating many clips."""
    head = prompt.strip().replace("\n", " ")[:60]
    return f"FAKE | {extra} | {head}"


async def generate_image(
    prompt: str,
    output_path: Path,
    *,
    reference_images: list[Path] | None = None,
    model: str = "fake-image",
    width: int = 1280,
    height: int = 720,
) -> None:
    _maybe_fail(prompt)
    await _simulate_latency(get_settings().falai_fake_image_delay_seconds)

    ref_count = len(reference_images or [])
    ffmpeg.make_placeholder_image(
        output_path,
        label=_label(prompt, f"{model} | refs={ref_count}"),
        width=width,
        height=height,
    )


async def generate_video(
    prompt: str,
    output_path: Path,
    *,
    keyframe_start: Path | None = None,
    keyframe_end: Path | None = None,
    model: str = "fake-video",
    duration_seconds: float = 5.0,
    width: int = 1280,
    height: int = 720,
) -> None:
    _maybe_fail(prompt)
    await _simulate_latency(get_settings().falai_fake_video_delay_seconds)

    frames = "start+end" if keyframe_end else ("start" if keyframe_start else "text-only")
    ffmpeg.make_placeholder_video(
        output_path,
        label=_label(prompt, f"{model} | {duration_seconds}s | {frames}"),
        duration_seconds=duration_seconds,
        width=width,
        height=height,
    )
