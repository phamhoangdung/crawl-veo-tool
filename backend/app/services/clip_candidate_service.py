"""Suggest short clip candidates from the transcript — see docs/phases/phase-11-shorts-crosspost.md.

SIMPLE scoring (word density + emphasis punctuation), NOT a real viral prediction
model. 2026 market reviews show the virality scores of similar tools (Opus
Clip...) are unreliable — this function is only used to ORDER suggestions for the user
to pick/drag-adjust on the timeline (Phase 13), never automatically choosing/discarding on the
user's behalf.
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
    """The higher the score, the more it is "suggested first" — not an absolute viral score."""
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
    """Slide a ~`target_duration` second window over the transcript (each segment serves as a
    candidate start point), score, drop candidates overlapping more than `_MAX_OVERLAP_RATIO`
    with an already chosen higher-scoring candidate, return at most `max_candidates` in
    time order (not score order — to display naturally on the timeline)."""
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
