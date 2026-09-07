"""Gợi ý ứng viên clip ngắn từ transcript — xem docs/phases/phase-11-shorts-crosspost.md.

Chấm điểm ĐƠN GIẢN (mật độ từ + dấu câu nhấn mạnh), KHÔNG phải mô hình dự đoán viral
thật. Review thị trường 2026 cho thấy điểm virality của các tool tương tự (Opus
Clip...) không đáng tin cậy — hàm này chỉ dùng để XẾP THỨ TỰ gợi ý cho người dùng
tự chọn/kéo-chỉnh trên timeline (Phase 13), không tự động chọn/loại bỏ thay người
dùng.
"""

from dataclasses import dataclass

_DEFAULT_TARGET_DURATION = 45.0
_MIN_DURATION_RATIO = 0.5
_MAX_OVERLAP_RATIO = 0.5


@dataclass
class ClipCandidate:
    start: float
    end: float
    text: str
    score: float


def _segment_score(text: str, duration: float) -> float:
    """Điểm càng cao càng "ưu tiên gợi ý trước" — không phải điểm viral tuyệt đối."""
    if duration <= 0:
        return 0.0
    word_count = len(text.split())
    density = word_count / duration
    emphasis_bonus = 0.5 * (text.count("!") + text.count("?"))
    return density + emphasis_bonus


def _overlap_ratio(a: ClipCandidate, b: ClipCandidate) -> float:
    overlap = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    shorter = min(a.end - a.start, b.end - b.start)
    return overlap / shorter if shorter > 0 else 0.0


def suggest_clip_candidates(
    segments: list[dict],
    *,
    target_duration: float = _DEFAULT_TARGET_DURATION,
    max_candidates: int = 5,
) -> list[ClipCandidate]:
    """Trượt cửa sổ ~`target_duration` giây qua transcript (mỗi segment làm 1 mốc
    bắt đầu ứng viên), chấm điểm, loại ứng viên chồng lấn quá `_MAX_OVERLAP_RATIO`
    với ứng viên điểm cao hơn đã chọn, trả về tối đa `max_candidates` theo thứ tự
    thời gian (không phải thứ tự điểm — để hiển thị tự nhiên trên timeline)."""
    if not segments:
        return []

    windows: list[ClipCandidate] = []
    for i, seg in enumerate(segments):
        window_start = seg["start"]
        window_end = window_start + target_duration
        included = [s for s in segments[i:] if s["start"] < window_end]
        if not included:
            continue
        actual_end = min(included[-1]["end"], window_end)
        duration = actual_end - window_start
        if duration < target_duration * _MIN_DURATION_RATIO:
            continue
        text = " ".join(
            (s.get("translated_text") or s.get("text") or "") for s in included
        ).strip()
        if not text:
            continue
        windows.append(
            ClipCandidate(
                start=window_start,
                end=actual_end,
                text=text,
                score=_segment_score(text, duration),
            )
        )

    windows.sort(key=lambda w: w.score, reverse=True)

    selected: list[ClipCandidate] = []
    for window in windows:
        if len(selected) >= max_candidates:
            break
        if any(_overlap_ratio(window, chosen) > _MAX_OVERLAP_RATIO for chosen in selected):
            continue
        selected.append(window)

    selected.sort(key=lambda w: w.start)
    return selected
