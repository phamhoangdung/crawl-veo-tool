from app.services.clip_candidate_service import suggest_clip_candidates


def _segments(*, count: int, seg_duration: float = 3.0, text: str = "một câu nói bình thường") -> list[dict]:
    return [
        {
            "start": i * seg_duration,
            "end": (i + 1) * seg_duration,
            "text": text,
            "translated_text": text,
        }
        for i in range(count)
    ]


def test_returns_empty_for_no_segments() -> None:
    assert suggest_clip_candidates([]) == []


def test_produces_at_least_one_candidate_for_long_enough_transcript() -> None:
    segments = _segments(count=20, seg_duration=3.0)  # 60s tổng
    candidates = suggest_clip_candidates(segments, target_duration=45.0)
    assert len(candidates) >= 1
    assert candidates[0].start == 0


def test_excludes_windows_shorter_than_half_target_duration() -> None:
    """1 segment 5s, target 45s -> cửa sổ thực tế chỉ có 5s (<50% của 45s) -> loại."""
    segments = _segments(count=1, seg_duration=5.0)
    assert suggest_clip_candidates(segments, target_duration=45.0) == []

def test_prefers_segments_with_emphasis_punctuation() -> None:
    """2 cửa sổ không chồng lấn, 1 cái có dấu chấm than -> phải được chọn (cả 2 đủ
    ngắn để max_candidates=1 chỉ giữ lại 1)."""
    plain = _segments(count=10, seg_duration=5.0, text="một câu nói rất bình thường không có gì đặc biệt")
    exciting = [
        {**s, "start": s["start"] + 100, "end": s["end"] + 100, "text": "Không thể tin được! Thật sao?!", "translated_text": "Không thể tin được! Thật sao?!"}
        for s in _segments(count=10, seg_duration=5.0)
    ]
    segments = plain + exciting

    candidates = suggest_clip_candidates(segments, target_duration=45.0, max_candidates=1)

    assert len(candidates) == 1
    assert candidates[0].start >= 100  # cửa sổ "exciting" được chọn, không phải "plain"


def test_filters_overlapping_lower_score_windows() -> None:
    segments = _segments(count=30, seg_duration=3.0)  # 90s liên tục, nhiều cửa sổ chồng lấn
    candidates = suggest_clip_candidates(segments, target_duration=45.0, max_candidates=10)

    for a in candidates:
        for b in candidates:
            if a is b:
                continue
            overlap = max(0.0, min(a.end, b.end) - max(a.start, b.start))
            shorter = min(a.end - a.start, b.end - b.start)
            assert (overlap / shorter if shorter > 0 else 0) <= 0.5


def test_respects_max_candidates() -> None:
    segments = _segments(count=60, seg_duration=3.0)  # 180s
    candidates = suggest_clip_candidates(segments, target_duration=20.0, max_candidates=3)
    assert len(candidates) <= 3


def test_result_sorted_by_start_time_not_score() -> None:
    segments = _segments(count=60, seg_duration=3.0)
    candidates = suggest_clip_candidates(segments, target_duration=20.0, max_candidates=5)
    starts = [c.start for c in candidates]
    assert starts == sorted(starts)


def test_skips_segments_with_empty_text() -> None:
    segments = _segments(count=20, seg_duration=3.0, text="")
    for s in segments:
        s["translated_text"] = ""
        s["text"] = ""
    assert suggest_clip_candidates(segments, target_duration=45.0) == []
