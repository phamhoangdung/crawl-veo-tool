import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.provider_errors import (
    AllProvidersExhaustedError,
    ProviderQuotaExceededError,
)
from app.adapters.translate import google as google_translate
from app.adapters.translate import openai as openai_translate
from app.services import api_key_service

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY_SECONDS = 1.0

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """1 client shared for the whole process lifetime instead of opening a new one per translation —
    avoids repeated TLS handshakes/connection-pool setup when many segments are translated in
    parallel (see docs/performance-optimization/plan.md, section P1). Not explicitly
    closed: this is a long-running single-process app, the OS cleans up sockets when the process
    exits, not worth adding a lifecycle/shutdown handler just for this.

    Timeout 60s (instead of the 30s of the original `translate_text`) to be sufficient when shared with
    `complete_text` — it is only an upper bound, not slowing down normal requests.
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=60)
    return _client


async def _call_with_retry(label: str, call: Callable[[], Awaitable[str]]) -> str:
    """Retry on rate limit (429) — both OpenAI and free Google can return this error
    when translating many subtitle segments in a row (each subtitle segment is its own request).
    Respects the Retry-After header if the server returns one, otherwise increasing backoff + jitter.

    If it is still 429 after the retries run out, raises `ProviderQuotaExceededError` (instead of the raw
    `httpx.HTTPStatusError`) so the caller (translate_text) knows this is the signal
    "this key needs a rest" and switches to another key in the pool — see Phase 8.
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
            delay = (
                float(retry_after)
                if retry_after
                else _BASE_DELAY_SECONDS * (2**attempt)
            )
            delay += random.uniform(0, 0.5)
            logger.warning(
                "%s bị rate limit (429), thử lại sau %.1fs (lần %d/%d)",
                label,
                delay,
                attempt + 1,
                _MAX_RETRIES,
            )
            await asyncio.sleep(delay)
    raise AssertionError(
        "unreachable"
    )  # the for loop always returns or raises before it ends


async def translate_text(
    db: Session, user_id: int, text: str, source_lang: str, target_lang: str
) -> str:
    """Rotate OpenAI keys in the pool (Phase 8) when out of quota/rate-limited; when the whole
    pool is exhausted fall back to Google Translate (free) as before. If free Google also fails
    (out of quota/rate limit of the free endpoint itself, or another network error), raises
    `AllProvidersExhaustedError` so dubbing_service moves the video to PAUSED_QUOTA
    instead of failing outright.
    """
    client = _get_client()
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
                lambda: openai_translate.translate(
                    client, api_key, text, source_lang, target_lang
                ),
            )
            api_key_service.mark_key_result(db, key_id, success=True)
            return result
        except ProviderQuotaExceededError:
            api_key_service.mark_key_result(db, key_id, success=False)
            logger.warning("OpenAI key #%d hết quota, thử key khác trong pool", key_id)
            continue
        except httpx.HTTPError as exc:
            logger.warning(
                "OpenAI translate failed (%s), falling back to Google Translate", exc
            )
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
    """Call the LLM with a free-form prompt (metadata generation...), sharing the key pool with translation.

    Unlike `translate_text`: NO fallback to Google Translate — the free translation endpoint
    does not accept free-form prompts. When keys run out, report an error so the user knows an API key
    must be configured, instead of returning garbage.
    """
    client = _get_client()
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


async def translate_cached(
    db: Session,
    user_id: int,
    text: str,
    source_lang: str = "zh",
    target_lang: str = "vi",
) -> tuple[str, bool]:
    """Translate with a cache in the DB. Returns `(translation, from_cache)`.

    For the title-translation tooltip: every hover is a request, without a cache a few passes of the
    mouse over a 40-row table is enough to exhaust the quota. The cache lives in the DB so it
    survives a restart, unlike an in-memory cache.
    """
    from app.models.translation_cache import TranslationCache, make_key

    key = make_key(text, source_lang, target_lang)

    cached = db.get(TranslationCache, key)
    if cached is not None:
        # Count reuses to know whether the cache is really effective.
        cached.hit_count += 1
        db.commit()
        return cached.translated_text, True

    translated = await translate_text(db, user_id, text, source_lang, target_lang)

    db.add(
        TranslationCache(
            key=key,
            source_text=text,
            translated_text=translated,
            source_lang=source_lang,
            target_lang=target_lang,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Two hover requests for the same title at the same time — the other record got in first,
        # not an error. The translation is still correct so just return it.
        db.rollback()

    return translated, False
