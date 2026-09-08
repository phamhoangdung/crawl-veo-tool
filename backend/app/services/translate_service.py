import asyncio
import logging
import random
from typing import Awaitable, Callable

import httpx
from sqlalchemy.orm import Session

from app.adapters.provider_errors import AllProvidersExhaustedError, ProviderQuotaExceededError
from app.adapters.translate import google as google_translate
from app.adapters.translate import openai as openai_translate
from app.services import api_key_service

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY_SECONDS = 1.0


async def _call_with_retry(label: str, call: Callable[[], Awaitable[str]]) -> str:
    """Retry khi bị rate limit (429) — cả OpenAI lẫn Google free đều có thể trả lỗi
    này khi dịch nhiều đoạn phụ đề liên tiếp (mỗi đoạn phụ đề là 1 request riêng).
    Tôn trọng header Retry-After nếu server trả về, không thì backoff tăng dần + jitter.

    Nếu vẫn 429 sau khi hết lượt retry, ném `ProviderQuotaExceededError` (thay vì
    `httpx.HTTPStatusError` thô) để caller (translate_text) biết đây là tín hiệu
    "key này cần nghỉ" và chuyển sang key khác trong pool — xem Phase 8.
    """
    for attempt in range(_MAX_RETRIES):
        try:
            return await call()
        except httpx.HTTPStatusError as exc:
            is_last_attempt = attempt == _MAX_RETRIES - 1
            if exc.response.status_code != 429:
                raise
            if is_last_attempt:
                raise ProviderQuotaExceededError(label, exc) from exc
            retry_after = exc.response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else _BASE_DELAY_SECONDS * (2**attempt)
            delay += random.uniform(0, 0.5)
            logger.warning(
                "%s bị rate limit (429), thử lại sau %.1fs (lần %d/%d)",
                label, delay, attempt + 1, _MAX_RETRIES,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")  # vòng for luôn return hoặc raise trước khi hết vòng


async def translate_text(db: Session, user_id: int, text: str, source_lang: str, target_lang: str) -> str:
    """Xoay vòng key OpenAI trong pool (Phase 8) khi bị hết quota/rate-limit; hết cả
    pool thì fallback Google Translate (free) như trước. Nếu Google free cũng lỗi
    (hết quota/rate-limit của chính endpoint free, hoặc lỗi mạng khác), ném
    `AllProvidersExhaustedError` để dubbing_service chuyển video sang PAUSED_QUOTA
    thay vì fail hẳn.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        tried_key_ids: set[int] = set()
        while True:
            picked = api_key_service.pick_decrypted_key(db, user_id, "openai")
            if picked is None or picked[0] in tried_key_ids:
                break
            key_id, api_key = picked
            tried_key_ids.add(key_id)
            try:
                result = await _call_with_retry(
                    "OpenAI translate",
                    lambda: openai_translate.translate(client, api_key, text, source_lang, target_lang),
                )
                api_key_service.mark_key_result(db, key_id, success=True)
                return result
            except ProviderQuotaExceededError:
                api_key_service.mark_key_result(db, key_id, success=False)
                logger.warning("OpenAI key #%d hết quota, thử key khác trong pool", key_id)
                continue
            except httpx.HTTPError as exc:
                logger.warning("OpenAI translate failed (%s), falling back to Google Translate", exc)
                break

        try:
            return await _call_with_retry(
                "Google translate",
                lambda: google_translate.translate(client, text, source_lang, target_lang),
            )
        except (ProviderQuotaExceededError, httpx.HTTPError) as exc:
            raise AllProvidersExhaustedError(
                "Dịch thất bại: hết quota toàn bộ key OpenAI trong pool "
                "và Google Translate (free) cũng lỗi"
            ) from exc


async def complete_text(db: Session, user_id: int, prompt: str) -> str:
    """Gọi LLM với prompt tự do (sinh metadata...), dùng chung pool key với dịch.

    Khác `translate_text`: KHÔNG fallback sang Google Translate — endpoint dịch
    free không nhận prompt tự do. Hết key thì báo lỗi để người dùng biết cần cấu
    hình API key, thay vì trả rác.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        tried_key_ids: set[int] = set()
        while True:
            picked = api_key_service.pick_decrypted_key(db, user_id, "openai")
            if picked is None or picked[0] in tried_key_ids:
                break
            key_id, api_key = picked
            tried_key_ids.add(key_id)
            try:
                result = await _call_with_retry(
                    "OpenAI complete",
                    lambda: openai_translate.complete(client, api_key, prompt),
                )
                api_key_service.mark_key_result(db, key_id, success=True)
                return result
            except ProviderQuotaExceededError:
                api_key_service.mark_key_result(db, key_id, success=False)
                logger.warning("OpenAI key #%d hết quota, thử key khác trong pool", key_id)
                continue
            except httpx.HTTPError as exc:
                api_key_service.mark_key_result(db, key_id, success=False)
                logger.warning("OpenAI complete lỗi với key #%d: %s", key_id, exc)
                continue

    raise AllProvidersExhaustedError(
        "Cần API key OpenAI để sinh metadata — thêm ở trang API Keys."
    )
