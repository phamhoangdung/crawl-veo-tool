"""Real fal.ai adapter (Phase 14) — used when `FALAI_MODE=real`.

⚠️ **HAS NEVER BEEN RUN WITH A REAL KEY.** The queue mechanism (submit → poll →
download file) follows fal.ai's public queue protocol and is tested with fake HTTP;
the two items below are **educated guesses, not verified facts**,
and are the first place to revisit once a key is available:

1. `_MODEL_ENDPOINTS` — model paths on fal.ai. Model names change over time
   (kling-2.1 → 3.0...), so they live in a single table: fix one place and done.
2. `_image_input()` / `_video_input()` — the input field names of each model. Each
   model family names them differently (`image_url` vs `start_image_url`...).

Designed to fail LOUDLY: on a response not shaped as expected it raises
`GenerationError` saying which field is missing, instead of silently writing an empty file and
letting the user find out after having paid.

The adapter is only a thin HTTP client: the key is chosen from the pool by the service and passed in, and
429 raises `ProviderQuotaExceededError` so the service rotates keys (same convention as
`app/adapters/translate/openai.py`, see Phase 8).
"""

import asyncio
import base64
import logging
import mimetypes
from pathlib import Path

import httpx

from app.adapters.falai.errors import PromptBlockedError
from app.adapters.provider_errors import ProviderQuotaExceededError

logger = logging.getLogger(__name__)

PROVIDER_NAME = "falai"

_QUEUE_BASE = "https://queue.fal.run"

# Internal model name (used in cost_service, UI, DB) -> fal.ai model path.
# UNVERIFIED — see the warning at the top of the file.
_MODEL_ENDPOINTS: dict[str, str] = {
    # Images
    "nano-banana": "fal-ai/nano-banana",
    "flux-schnell": "fal-ai/flux/schnell",
    "flux-dev": "fal-ai/flux/dev",
    # Video
    "kling-3.0": "fal-ai/kling-video/v2/master/image-to-video",
    "luma-ray2": "fal-ai/luma-dream-machine/ray-2/image-to-video",
    "veo-3.1": "fal-ai/veo3/image-to-video",
}

# How often to re-ask the job status. fal.ai bills per generation, not
# per status poll, but polling too often can still hit rate limits.
_POLL_INTERVAL_SECONDS = 2.0
# Waiting cap: an 8s video on the slowest model rarely exceeds 5 minutes. Past
# this mark the job is most likely stuck, and waiting more is pointless.
_POLL_TIMEOUT_SECONDS = 600.0

# Strings indicating the provider refused for content policy, not a
# technical error. Retrying or changing keys is useless — the prompt must be fixed.
_POLICY_MARKERS = (
    "content policy",
    "safety",
    "nsfw",
    "prohibited",
    "blocked",
)


class GenerationError(RuntimeError):
    """An error that cannot be fixed by changing keys or retrying."""


def resolve_endpoint(model: str) -> str:
    endpoint = _MODEL_ENDPOINTS.get(model)
    if endpoint is None:
        raise GenerationError(
            f"Chưa biết đường dẫn fal.ai cho model {model!r}. "
            f"Thêm vào _MODEL_ENDPOINTS (đang có: {sorted(_MODEL_ENDPOINTS)})."
        )
    return endpoint


def _auth_headers(api_key: str) -> dict[str, str]:
    # fal.ai uses the "Key" prefix, not "Bearer".
    return {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}


def _to_data_uri(path: Path) -> str:
    """Embed reference images straight into the request instead of uploading first.

    Saves one API round trip (and one separate place that can fail); in exchange the request is
    heavier, acceptable with a few reference images.
    """
    if not path.exists():
        raise GenerationError(f"Không tìm thấy ảnh tham chiếu: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _raise_for_status(response: httpx.Response) -> None:
    """Normalize an HTTP error into the exact kind the upper layer knows how to handle."""
    if response.status_code == 429:
        exc = httpx.HTTPStatusError(
            "429 Too Many Requests", request=response.request, response=response
        )
        raise ProviderQuotaExceededError(PROVIDER_NAME, exc) from exc

    if response.status_code in (400, 422):
        detail = _error_detail(response)
        if any(marker in detail.lower() for marker in _POLICY_MARKERS):
            raise PromptBlockedError(PROVIDER_NAME, detail)
        raise GenerationError(f"fal.ai từ chối request ({response.status_code}): {detail}")

    response.raise_for_status()


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    if isinstance(body, dict):
        detail = body.get("detail") or body.get("error") or body
        return str(detail)[:300]
    return str(body)[:300]


async def _submit(
    client: httpx.AsyncClient, api_key: str, endpoint: str, payload: dict
) -> dict:
    response = await client.post(
        f"{_QUEUE_BASE}/{endpoint}", json=payload, headers=_auth_headers(api_key)
    )
    _raise_for_status(response)
    body = response.json()
    if "status_url" not in body or "response_url" not in body:
        raise GenerationError(
            "Response nhận job của fal.ai thiếu status_url/response_url — "
            f"giao thức có thể đã đổi. Nhận được: {str(body)[:200]}"
        )
    return body


async def _wait_for_result(
    client: httpx.AsyncClient, api_key: str, submitted: dict
) -> dict:
    """Wait for the job to finish, then fetch the result. Raises a clear error when the job fails or the wait times out."""
    headers = _auth_headers(api_key)
    deadline = asyncio.get_running_loop().time() + _POLL_TIMEOUT_SECONDS

    while True:
        response = await client.get(submitted["status_url"], headers=headers)
        _raise_for_status(response)
        status = response.json().get("status")

        if status == "COMPLETED":
            break
        if status in ("FAILED", "ERROR"):
            raise GenerationError(
                f"fal.ai báo job thất bại: {_error_detail(response)}"
            )
        if asyncio.get_running_loop().time() > deadline:
            raise GenerationError(
                f"Quá {_POLL_TIMEOUT_SECONDS:.0f}s mà job fal.ai vẫn ở trạng thái "
                f"{status!r} — nhiều khả năng job kẹt."
            )
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    result = await client.get(submitted["response_url"], headers=headers)
    _raise_for_status(result)
    return result.json()


def _extract_media_url(result: dict, *, kind: str) -> str:
    """Get the file URL from the result. The shape differs between image and video models.

    No guessing: if nothing is found, raise an error with all the keys present in the response
    so the fixer knows where to look.
    """
    if kind == "image":
        images = result.get("images") or result.get("image")
        if isinstance(images, list) and images:
            first = images[0]
            url = first.get("url") if isinstance(first, dict) else first
            if url:
                return url
        if isinstance(images, dict) and images.get("url"):
            return images["url"]
    else:
        video = result.get("video") or result.get("videos")
        if isinstance(video, dict) and video.get("url"):
            return video["url"]
        if isinstance(video, list) and video:
            first = video[0]
            url = first.get("url") if isinstance(first, dict) else first
            if url:
                return url

    raise GenerationError(
        f"Không tìm thấy URL {kind} trong kết quả fal.ai. "
        f"Các khoá nhận được: {sorted(result)}"
    )


async def _download(client: httpx.AsyncClient, url: str, output_path: Path) -> None:
    """Download the result file. Writes to a temp file before renaming: a download cut off by a network drop would
    leave a broken file at the exact path the cache treats as "already there", meaning that even paying to
    regenerate could not fix it."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_suffix(output_path.suffix + ".part")

    response = await client.get(url)
    response.raise_for_status()
    partial.write_bytes(response.content)

    if partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise GenerationError("fal.ai trả file rỗng")

    partial.replace(output_path)


def _image_input(
    prompt: str, reference_images: list[Path], width: int, height: int
) -> dict:
    """UNVERIFIED — see the warning at the top of the file."""
    payload: dict = {"prompt": prompt, "image_size": {"width": width, "height": height}}
    if reference_images:
        payload["image_urls"] = [_to_data_uri(p) for p in reference_images]
    return payload


def _video_input(
    prompt: str,
    keyframe_start: Path | None,
    keyframe_end: Path | None,
    duration_seconds: float,
) -> dict:
    """UNVERIFIED — see the warning at the top of the file."""
    payload: dict = {"prompt": prompt, "duration": str(int(duration_seconds))}
    if keyframe_start is not None:
        payload["image_url"] = _to_data_uri(keyframe_start)
    if keyframe_end is not None:
        payload["tail_image_url"] = _to_data_uri(keyframe_end)
    return payload


async def _run(
    client: httpx.AsyncClient,
    api_key: str,
    endpoint: str,
    payload: dict,
    output_path: Path,
    *,
    kind: str,
) -> None:
    """The whole real flow, taking a ready `client` so tests can inject a `MockTransport`.

    The two public functions below only open/close the client — split out so no
    test-only parameter has to be added to the public API.
    """
    submitted = await _submit(client, api_key, endpoint, payload)
    logger.info("fal.ai nhận job %s: %s", kind, submitted.get("request_id"))
    result = await _wait_for_result(client, api_key, submitted)
    await _download(client, _extract_media_url(result, kind=kind), output_path)


async def generate_image(
    api_key: str,
    prompt: str,
    output_path: Path,
    *,
    reference_images: list[Path] | None = None,
    model: str = "nano-banana",
    width: int = 1280,
    height: int = 720,
) -> None:
    endpoint = resolve_endpoint(model)
    payload = _image_input(prompt, reference_images or [], width, height)
    async with httpx.AsyncClient(timeout=60) as client:
        await _run(client, api_key, endpoint, payload, output_path, kind="image")


async def generate_video(
    api_key: str,
    prompt: str,
    output_path: Path,
    *,
    keyframe_start: Path | None = None,
    keyframe_end: Path | None = None,
    model: str = "kling-3.0",
    duration_seconds: float = 5.0,
    width: int = 1280,
    height: int = 720,
) -> None:
    del width, height  # video models take the ratio from the keyframe image, not from pixel counts
    endpoint = resolve_endpoint(model)
    payload = _video_input(prompt, keyframe_start, keyframe_end, duration_seconds)
    async with httpx.AsyncClient(timeout=60) as client:
        await _run(client, api_key, endpoint, payload, output_path, kind="video")
