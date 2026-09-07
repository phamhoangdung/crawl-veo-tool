"""Cắt clip ngắn dọc 9:16 từ video dài — tái dùng render_timeline() của Phase 13,
không viết logic render riêng. Xem docs/phases/phase-11-shorts-crosspost.md."""

from pathlib import Path

from app.adapters import ffmpeg


def build_clip_timeline(
    video_source: str,
    caption_segments: list[dict],
    *,
    start: float,
    end: float,
    crop: dict | None = None,
    cta_text: str | None = None,
) -> dict:
    """Dựng "edit operations" (Phase 13) cho 1 clip cắt từ `start` tới `end` của
    video gốc — mốc thời gian trong caption/CTA được dịch về hệ quy chiếu MỚI của
    clip (trừ đi `start`), vì clip là 1 video độc lập bắt đầu từ 0."""
    if end <= start:
        raise ValueError("'end' phải lớn hơn 'start'")

    video_clip: dict = {"source": video_source, "start": start, "end": end}
    if crop:
        video_clip["crop"] = crop

    tracks: list[dict] = [{"type": "video", "clips": [video_clip]}]

    overlay_clips = []
    for seg in caption_segments:
        if seg["start"] >= end or seg["end"] <= start:
            continue
        text = seg.get("translated_text") or seg.get("text")
        if not text:
            continue
        overlay_clips.append(
            {
                "text": text,
                "start": max(0.0, seg["start"] - start),
                "end": min(end - start, seg["end"] - start),
                "x": 0.5,
                "y": 0.85,
            }
        )
    if cta_text:
        overlay_clips.append(
            {"text": cta_text, "start": 0, "end": end - start, "x": 0.5, "y": 0.95, "font_size": 24}
        )
    if overlay_clips:
        tracks.append({"type": "overlay", "clips": overlay_clips})

    return {"tracks": tracks}


def render_clip(
    video_source: str,
    caption_segments: list[dict],
    output_path: Path,
    *,
    start: float,
    end: float,
    crop: dict | None = None,
    cta_text: str | None = None,
) -> Path:
    operations = build_clip_timeline(
        video_source, caption_segments, start=start, end=end, crop=crop, cta_text=cta_text
    )
    ffmpeg.render_timeline(operations, output_path)
    return output_path
