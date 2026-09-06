from pathlib import Path


def _format_timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    hours, rem_ms = divmod(total_ms, 3_600_000)
    minutes, rem_ms = divmod(rem_ms, 60_000)
    secs, ms = divmod(rem_ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_bilingual_srt(segments: list[dict]) -> str:
    """Mỗi cue gồm 2 dòng: bản gốc rồi tới bản dịch — dạng phụ đề song ngữ phổ biến."""
    lines: list[str] = []
    for i, segment in enumerate(segments, start=1):
        original = (segment.get("text") or "").strip()
        translated = (segment.get("translated_text") or "").strip()
        if not original and not translated:
            continue
        lines.append(str(i))
        lines.append(f"{_format_timestamp(segment['start'])} --> {_format_timestamp(segment['end'])}")
        if original:
            lines.append(original)
        if translated:
            lines.append(translated)
        lines.append("")
    return "\n".join(lines)


def write_srt(segments: list[dict], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_bilingual_srt(segments), encoding="utf-8")
    return output_path


def pick_font_size_for(width: int, height: int) -> int:
    """Video dọc (9:16 kiểu Douyin) cần cỡ chữ tương đối lớn hơn vì khung hẹp hơn khung
    ngang (16:9 kiểu Bilibili) — quy đổi theo % chiều rộng thay vì số cố định.

    Đã verify template ngang (16:9) bằng burn-in thật; chưa có video mẫu 9:16 để verify
    thật template dọc — xem docs/phases/phase-5-subtitles-library.md phần Ghi chú.
    """
    is_portrait = height > width
    reference_dimension = height if is_portrait else width
    percentage = 0.045 if is_portrait else 0.03
    return round(reference_dimension * percentage)
