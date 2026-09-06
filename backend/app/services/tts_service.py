import asyncio
import logging
from pathlib import Path

import edge_tts
import httpx
from sqlalchemy.orm import Session

from app.adapters.tts import edge as edge_tts_adapter
from app.adapters.tts import elevenlabs as elevenlabs_adapter
from app.services import api_key_service

logger = logging.getLogger(__name__)

_EDGE_TTS_MAX_ATTEMPTS = 3


class TtsFailedError(RuntimeError):
    pass


async def _synthesize_with_edge_retry(text: str, output_path: Path) -> None:
    """edge-tts thỉnh thoảng lỗi tạm thời `NoAudioReceived` (vấn đề đã biết của thư viện,
    không phải do input sai) — retry vài lần trước khi coi là lỗi thật."""
    last_error: Exception | None = None
    for attempt in range(1, _EDGE_TTS_MAX_ATTEMPTS + 1):
        try:
            await edge_tts_adapter.synthesize(text, output_path)
            return
        except edge_tts.exceptions.NoAudioReceived as exc:
            last_error = exc
            logger.warning("Edge-TTS attempt %d/%d failed: %s", attempt, _EDGE_TTS_MAX_ATTEMPTS, exc)
            await asyncio.sleep(1)
    raise TtsFailedError(f"Edge-TTS failed after {_EDGE_TTS_MAX_ATTEMPTS} attempts") from last_error


async def synthesize_speech(db: Session, user_id: int, text: str, output_path: Path) -> None:
    """Ưu tiên ElevenLabs nếu đã cấu hình key và gọi được; fallback Edge-TTS (free) nếu không."""
    api_key = api_key_service.get_decrypted_key(db, user_id, "elevenlabs")
    if api_key:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                await elevenlabs_adapter.synthesize(client, api_key, text, output_path)
            return
        except httpx.HTTPError as exc:
            logger.warning("ElevenLabs TTS failed (%s), falling back to Edge-TTS", exc)
    await _synthesize_with_edge_retry(text, output_path)
