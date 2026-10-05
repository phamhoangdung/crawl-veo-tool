import asyncio
import logging
import re
from pathlib import Path

import edge_tts
import httpx
from sqlalchemy.orm import Session

from app.adapters.tts import edge as edge_tts_adapter
from app.adapters.tts import elevenlabs as elevenlabs_adapter
from app.services import api_key_service

logger = logging.getLogger(__name__)

_EDGE_TTS_MAX_ATTEMPTS = 3

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """1 client shared for the whole process lifetime instead of opening a new one on every
    ElevenLabs call — avoids repeated TLS handshakes/connection-pool setup when many
    TTS segments run in parallel (see docs/performance-optimization/plan.md, section P1).
    Not explicitly closed, same reason as `translate_service._get_client`.
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=60)
    return _client


class TtsFailedError(RuntimeError):
    pass


def _has_speakable_content(text: str) -> bool:
    """Whether there is any letter/digit to read — with only punctuation Edge-TTS returns no audio."""
    return bool(re.search(r"[^\W_]", text, flags=re.UNICODE))


async def _synthesize_with_edge_retry(
    text: str, output_path: Path, voice: str = edge_tts_adapter.DEFAULT_VOICE
) -> None:
    """Call Edge-TTS, retrying on transient network errors.

    `NoAudioReceived` has two very different causes:
    - Text that cannot be read (only punctuation, or characters not in the voice's
      language — e.g. a Vietnamese voice meeting Han characters). This is an input error, **retrying is
      useless**, so raise right away with the content for easy tracing.
    - A transient problem on the service side. Retrying only helps in this case.
    """
    if not _has_speakable_content(text):
        raise TtsFailedError(f"Văn bản không có nội dung đọc được: {text!r}")

    last_error: Exception | None = None
    for attempt in range(1, _EDGE_TTS_MAX_ATTEMPTS + 1):
        try:
            await edge_tts_adapter.synthesize(text, output_path, voice=voice)
            return
        except edge_tts.exceptions.NoAudioReceived as exc:
            last_error = exc
            logger.warning(
                "Edge-TTS lần %d/%d thất bại (%s) — text: %r",
                attempt,
                _EDGE_TTS_MAX_ATTEMPTS,
                exc,
                text[:60],
            )
            await asyncio.sleep(1)
    raise TtsFailedError(
        f"Edge-TTS thất bại sau {_EDGE_TTS_MAX_ATTEMPTS} lần thử. "
        f"Nếu lặp lại, kiểm tra xem văn bản có đúng tiếng Việt không: {text[:60]!r}"
    ) from last_error


async def synthesize_speech(
    db: Session,
    user_id: int,
    text: str,
    output_path: Path,
    voice: dict[str, str] | None = None,
) -> None:
    """Rotate ElevenLabs keys in the pool (Phase 8) when 1 key is out of quota (HTTP 429);
    when the whole pool is exhausted (or no key is configured) fall back to Edge-TTS (free) as before.

    `voice`: {"provider": "edge"|"elevenlabs", "voice_id": "..."} — assigned by the user
    to one speaker (Phase 19, multi-voice dubbing). None uses the default
    as before (ElevenLabs pool then Edge fallback), not breaking the old behavior.

    Does not raise AllProvidersExhaustedError here (unlike translate_service): free Edge-TTS
    has no notion of "out of quota", and its error (TtsFailedError) is already handled
    separately by dubbing_service by skipping the segment — turning it into a "total out-of-quota"
    error would be wrong in nature and stop the job unfairly when really only 1 sentence could not be read.
    """
    edge_voice = edge_tts_adapter.DEFAULT_VOICE
    if voice and voice.get("provider") == "edge":
        edge_voice = voice["voice_id"]
        await _synthesize_with_edge_retry(text, output_path, voice=edge_voice)
        return

    elevenlabs_voice_id = (
        voice["voice_id"]
        if voice and voice.get("provider") == "elevenlabs"
        else elevenlabs_adapter.DEFAULT_VOICE_ID
    )

    client = _get_client()
    tried_key_ids: set[int] = set()
    while True:
        picked = api_key_service.pick_decrypted_key(db, user_id, "elevenlabs")
        if picked is None or picked[0] in tried_key_ids:
            break
        key_id, api_key = picked
        tried_key_ids.add(key_id)
        try:
            await elevenlabs_adapter.synthesize(
                client, api_key, text, output_path, voice_id=elevenlabs_voice_id
            )
            api_key_service.mark_key_result(db, key_id, success=True)
            return
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                api_key_service.mark_key_result(db, key_id, success=False)
                logger.warning(
                    "ElevenLabs key #%d hết quota, thử key khác trong pool", key_id
                )
                continue
            logger.warning("ElevenLabs TTS failed (%s), falling back to Edge-TTS", exc)
            break
        except httpx.HTTPError as exc:
            logger.warning("ElevenLabs TTS failed (%s), falling back to Edge-TTS", exc)
            break
    await _synthesize_with_edge_retry(text, output_path, voice=edge_voice)
