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


class TtsFailedError(RuntimeError):
    pass


def _has_speakable_content(text: str) -> bool:
    """Có chữ/số để đọc không — chỉ dấu câu thì Edge-TTS không trả về audio nào."""
    return bool(re.search(r"[^\W_]", text, flags=re.UNICODE))


async def _synthesize_with_edge_retry(text: str, output_path: Path) -> None:
    """Gọi Edge-TTS, retry khi lỗi mạng tạm thời.

    `NoAudioReceived` có hai nguyên nhân rất khác nhau:
    - Văn bản không đọc được (chỉ dấu câu, hoặc chữ không thuộc ngôn ngữ của
      giọng — ví dụ giọng tiếng Việt gặp chữ Hán). Đây là lỗi input, **retry vô
      ích**, nên báo lỗi ngay kèm nội dung để dễ truy nguyên.
    - Trục trặc tạm thời phía dịch vụ. Trường hợp này retry mới có tác dụng.
    """
    if not _has_speakable_content(text):
        raise TtsFailedError(
            f"Văn bản không có nội dung đọc được: {text!r}"
        )

    last_error: Exception | None = None
    for attempt in range(1, _EDGE_TTS_MAX_ATTEMPTS + 1):
        try:
            await edge_tts_adapter.synthesize(text, output_path)
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
