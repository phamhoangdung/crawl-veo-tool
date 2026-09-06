from sqlalchemy.orm import Session

from app.services import api_key_service

# Giá ước tính (USD) — chỉ để cảnh báo trước khi chạy batch lớn, KHÔNG chính xác
# 100% so với hoá đơn thật (giá provider có thể đổi, không tính discount/tier).
_OPENAI_TRANSLATE_USD_PER_1K_CHARS = 0.002
_ELEVENLABS_TTS_USD_PER_1K_CHARS = 0.30

# Ước tính thô: tốc độ nói trung bình quy ra số ký tự/giây, áp dụng chung cho nhiều ngôn ngữ.
_AVG_CHARS_PER_SECOND_SPEECH = 3.0

_WARNING_THRESHOLD_USD = 1.0


def estimate_batch_cost(db: Session, user_id: int, total_duration_seconds: float) -> dict:
    estimated_chars = total_duration_seconds * _AVG_CHARS_PER_SECOND_SPEECH

    uses_openai = api_key_service.get_decrypted_key(db, user_id, "openai") is not None
    uses_elevenlabs = api_key_service.get_decrypted_key(db, user_id, "elevenlabs") is not None

    translate_cost = (estimated_chars / 1000) * _OPENAI_TRANSLATE_USD_PER_1K_CHARS if uses_openai else 0.0
    tts_cost = (estimated_chars / 1000) * _ELEVENLABS_TTS_USD_PER_1K_CHARS if uses_elevenlabs else 0.0
    total_cost = translate_cost + tts_cost

    return {
        "estimated_chars": round(estimated_chars),
        "translate_provider": "openai" if uses_openai else "google (free)",
        "tts_provider": "elevenlabs" if uses_elevenlabs else "edge-tts (free)",
        "translate_cost_usd": round(translate_cost, 4),
        "tts_cost_usd": round(tts_cost, 4),
        "total_cost_usd": round(total_cost, 4),
        "warning": (
            f"Chi phí ước tính ${total_cost:.2f} — kiểm tra lại trước khi chạy batch lớn."
            if total_cost > _WARNING_THRESHOLD_USD
            else None
        ),
    }
