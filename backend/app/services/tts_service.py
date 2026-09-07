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
    """Xoay vòng key ElevenLabs trong pool (Phase 8) khi 1 key hết quota (HTTP 429);
    hết cả pool (hoặc chưa cấu hình key nào) thì fallback Edge-TTS (free) như trước.

    Không ném AllProvidersExhaustedError ở đây (khác translate_service): Edge-TTS
    free không có khái niệm "hết quota", lỗi của nó (TtsFailedError) đã được
    dubbing_service xử lý riêng bằng cách bỏ qua đoạn — biến nó thành lỗi "hết quota
    toàn phần" sẽ sai bản chất và làm job dừng oan khi thực ra chỉ 1 câu không đọc được.
    """
    tried_key_ids: set[int] = set()
    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            picked = api_key_service.pick_decrypted_key(db, user_id, "elevenlabs")
            if picked is None or picked[0] in tried_key_ids:
                break
            key_id, api_key = picked
            tried_key_ids.add(key_id)
            try:
                await elevenlabs_adapter.synthesize(client, api_key, text, output_path)
                api_key_service.mark_key_result(db, key_id, success=True)
                return
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    api_key_service.mark_key_result(db, key_id, success=False)
                    logger.warning("ElevenLabs key #%d hết quota, thử key khác trong pool", key_id)
                    continue
                logger.warning("ElevenLabs TTS failed (%s), falling back to Edge-TTS", exc)
                break
            except httpx.HTTPError as exc:
                logger.warning("ElevenLabs TTS failed (%s), falling back to Edge-TTS", exc)
                break
    await _synthesize_with_edge_retry(text, output_path)
