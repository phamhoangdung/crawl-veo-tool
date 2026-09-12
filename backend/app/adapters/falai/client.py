"""Adapter fal.ai thật (Phase 14) — dùng khi `FALAI_MODE=real`.

⚠️ **CHƯA CHẠY LẦN NÀO VỚI KEY THẬT.** Phần cơ chế hàng đợi (submit → poll →
tải file) theo đúng giao thức queue công khai của fal.ai và có test bằng HTTP giả;
còn hai thứ dưới đây là **suy đoán có căn cứ chứ không phải sự thật đã kiểm chứng**,
và là chỗ đầu tiên cần xem lại khi có key:

1. `_MODEL_ENDPOINTS` — đường dẫn model trên fal.ai. Tên model đổi theo thời gian
   (kling-2.1 → 3.0...), nên để ở một bảng duy nhất, sửa một chỗ là xong.
2. `_image_input()` / `_video_input()` — tên trường đầu vào của từng model. Mỗi
   họ model đặt tên khác nhau (`image_url` vs `start_image_url`...).

Thiết kế để hỏng thì hỏng TO: gặp response không đúng hình dạng mong đợi thì ném
`GenerationError` nói rõ thiếu trường nào, chứ không lặng lẽ ghi ra file rỗng rồi
để người dùng phát hiện sau khi đã trả tiền.

Adapter chỉ là HTTP client mỏng: key do service chọn từ pool rồi truyền vào, và
429 ném `ProviderQuotaExceededError` để service xoay key (cùng quy ước với
`app/adapters/translate/openai.py`, xem Phase 8).
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

# Tên model nội bộ (dùng trong cost_service, UI, DB) -> đường dẫn model fal.ai.
# CHƯA KIỂM CHỨNG — xem cảnh báo đầu file.
_MODEL_ENDPOINTS: dict[str, str] = {
    # Ảnh
    "nano-banana": "fal-ai/nano-banana",
    "flux-schnell": "fal-ai/flux/schnell",
    "flux-dev": "fal-ai/flux/dev",
    # Video
    "kling-3.0": "fal-ai/kling-video/v2/master/image-to-video",
    "luma-ray2": "fal-ai/luma-dream-machine/ray-2/image-to-video",
    "veo-3.1": "fal-ai/veo3/image-to-video",
}

# Mỗi bao lâu hỏi lại trạng thái job. fal.ai tính tiền theo lần sinh chứ không
# theo lần hỏi trạng thái, nhưng hỏi quá dày vẫn có thể bị rate-limit.
_POLL_INTERVAL_SECONDS = 2.0
# Trần thời gian chờ: sinh video 8s ở model chậm nhất hiếm khi quá 5 phút. Quá
# mốc này thì nhiều khả năng job kẹt, chờ tiếp cũng vô ích.
_POLL_TIMEOUT_SECONDS = 600.0

# Các chuỗi cho biết provider từ chối vì chính sách nội dung, không phải lỗi kỹ
# thuật. Thử lại hay đổi key đều vô ích — phải sửa prompt.
_POLICY_MARKERS = (
    "content policy",
    "safety",
    "nsfw",
    "prohibited",
    "blocked",
)


class GenerationError(RuntimeError):
    """Lỗi không thể tự khắc phục bằng cách đổi key hay thử lại."""


def resolve_endpoint(model: str) -> str:
    endpoint = _MODEL_ENDPOINTS.get(model)
    if endpoint is None:
        raise GenerationError(
            f"Chưa biết đường dẫn fal.ai cho model {model!r}. "
            f"Thêm vào _MODEL_ENDPOINTS (đang có: {sorted(_MODEL_ENDPOINTS)})."
        )
    return endpoint


def _auth_headers(api_key: str) -> dict[str, str]:
    # fal.ai dùng tiền tố "Key", không phải "Bearer".
    return {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}


def _to_data_uri(path: Path) -> str:
    """Nhúng ảnh tham chiếu thẳng vào request thay vì upload trước.

    Bớt được một vòng gọi API (và một chỗ có thể hỏng riêng); đổi lại request nặng
    hơn, chấp nhận được với vài ảnh tham chiếu.
    """
    if not path.exists():
        raise GenerationError(f"Không tìm thấy ảnh tham chiếu: {path}")
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _raise_for_status(response: httpx.Response) -> None:
    """Chuẩn hoá lỗi HTTP thành đúng loại mà tầng trên biết cách xử lý."""
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
    """Chờ job xong rồi lấy kết quả. Ném lỗi rõ ràng khi job hỏng hoặc quá hạn chờ."""
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
    """Lấy URL file từ kết quả. Hình dạng khác nhau giữa model ảnh và model video.

    Không đoán mò: không tìm thấy thì ném lỗi kèm nguyên các khoá có trong response
    để người sửa biết phải nhìn vào đâu.
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
    """Tải file kết quả về. Ghi ra file tạm rồi mới đổi tên: tải dở mà đứt mạng sẽ
    để lại file hỏng ở đúng đường dẫn mà cache coi là "đã có", tức là mất tiền sinh
    lại cũng không sửa được."""
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
    """CHƯA KIỂM CHỨNG — xem cảnh báo đầu file."""
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
    """CHƯA KIỂM CHỨNG — xem cảnh báo đầu file."""
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
    """Toàn bộ luồng thật, nhận sẵn `client` để test tiêm được `MockTransport`.

    Hai hàm public bên dưới chỉ lo mở/đóng client — tách ra để không phải thêm
    tham số chỉ-dùng-cho-test vào API công khai.
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
    del width, height  # model video nhận tỉ lệ theo ảnh keyframe, không theo số pixel
    endpoint = resolve_endpoint(model)
    payload = _video_input(prompt, keyframe_start, keyframe_end, duration_seconds)
    async with httpx.AsyncClient(timeout=60) as client:
        await _run(client, api_key, endpoint, payload, output_path, kind="video")
