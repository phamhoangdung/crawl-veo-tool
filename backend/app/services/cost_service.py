from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.generated_asset import GeneratedAsset
from app.services import api_key_service

# Giá ước tính (USD) — chỉ để cảnh báo trước khi chạy batch lớn, KHÔNG chính xác
# 100% so với hoá đơn thật (giá provider có thể đổi, không tính discount/tier).
_OPENAI_TRANSLATE_USD_PER_1K_CHARS = 0.002
_ELEVENLABS_TTS_USD_PER_1K_CHARS = 0.30

# Ước tính thô: tốc độ nói trung bình quy ra số ký tự/giây, áp dụng chung cho nhiều ngôn ngữ.
_AVG_CHARS_PER_SECOND_SPEECH = 3.0

_WARNING_THRESHOLD_USD = 1.0


# Phase 14 — giá ước tính sinh ảnh/video (USD). Chênh nhau tới ~10x giữa model
# rẻ nhất và Veo, nên chọn model theo từng cảnh là đòn giảm chi phí lớn nhất sau
# việc dùng ảnh tĩnh + Ken Burns. Giá thay đổi theo thời gian — chỉ để cảnh báo.
_IMAGE_MODEL_USD: dict[str, float] = {
    "fake-image": 0.0,
    "nano-banana": 0.01,
    "flux-schnell": 0.003,
    "flux-dev": 0.025,
}

_VIDEO_MODEL_USD_PER_SECOND: dict[str, float] = {
    "fake-video": 0.0,
    "luma-ray2": 0.04,
    "kling-3.0": 0.10,
    "veo-3.1": 0.40,
}

_KEN_BURNS_MODEL = "ffmpeg-ken-burns"


class MonthlyBudgetExceededError(RuntimeError):
    """Đã chi hết hạn mức tháng — chặn trước khi gọi API thay vì để đốt tiếp.

    Quan trọng nhất ở đường MCP: agent chạy tự động qua đêm là lúc không ai ngồi
    xem, nên hạn mức là chốt an toàn cuối cùng.
    """

    def __init__(self, spent_usd: float, budget_usd: float) -> None:
        super().__init__(
            f"Đã chi ${spent_usd:.2f}/${budget_usd:.2f} trong tháng này — "
            "tăng FALAI_MONTHLY_BUDGET_USD hoặc chờ sang tháng."
        )
        self.spent_usd = spent_usd
        self.budget_usd = budget_usd


def estimate_image_cost(model: str, count: int = 1) -> float:
    return round(_IMAGE_MODEL_USD.get(model, 0.02) * count, 4)


def estimate_video_cost(model: str, duration_seconds: float) -> float:
    if model == _KEN_BURNS_MODEL:
        return 0.0
    return round(_VIDEO_MODEL_USD_PER_SECOND.get(model, 0.10) * duration_seconds, 4)


def spent_this_month_usd(db: Session, user_id: int) -> float:
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = db.execute(
        select(func.sum(GeneratedAsset.cost_estimate_usd)).where(
            GeneratedAsset.user_id == user_id, GeneratedAsset.created_at >= month_start
        )
    ).scalar()
    return round(total or 0.0, 4)


def check_monthly_budget(db: Session, user_id: int, upcoming_cost_usd: float) -> None:
    budget = get_settings().falai_monthly_budget_usd
    if budget <= 0:
        return
    spent = spent_this_month_usd(db, user_id)
    if spent + upcoming_cost_usd > budget:
        raise MonthlyBudgetExceededError(spent, budget)


def budget_status(db: Session, user_id: int) -> dict:
    budget = get_settings().falai_monthly_budget_usd
    spent = spent_this_month_usd(db, user_id)
    return {
        "spent_this_month_usd": spent,
        "monthly_budget_usd": budget,
        "remaining_usd": round(max(0.0, budget - spent), 4),
    }


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
