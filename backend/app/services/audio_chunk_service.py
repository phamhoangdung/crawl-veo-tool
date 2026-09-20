"""Cắt audio dài thành từng khúc tại chỗ im lặng trước khi chạy Demucs.

Vì sao cần: Demucs nạp nguyên track vào RAM rồi chạy model PyTorch trên đó —
video 30-60 phút sẽ ngốn nhiều GB và dễ bị giết giữa chừng trên máy cá nhân.
Cắt thành khúc ~5 phút thì lượng RAM đỉnh gần như không đổi dù video dài bao nhiêu.

Vì sao cắt tại chỗ IM LẶNG chứ không cắt đều 5 phút một: Demucs xử lý từng khúc
độc lập, cắt ngang một câu hát/câu thoại sẽ nghe rõ tiếng "khục" ở chỗ nối khi
ghép lại. Cắt vào khoảng lặng thì chỗ nối rơi vào đúng chỗ vốn đã không có tiếng.
"""

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from app.adapters import demucs, ffmpeg

logger = logging.getLogger(__name__)

# Khúc dài quá thì mất tác dụng tiết kiệm RAM, ngắn quá thì số lần khởi động
# Demucs (mỗi lần đều phải nạp model) lấn át thời gian xử lý thật.
DEFAULT_TARGET_SECONDS = 300.0
DEFAULT_MAX_SECONDS = 420.0
# Dưới ngưỡng này thì chạy thẳng, không cắt — thêm bước cắt/ghép chỉ tổ chậm.
CHUNKING_THRESHOLD_SECONDS = 600.0


def plan_chunks(
    duration: float,
    silences: list[tuple[float, float]],
    *,
    target_seconds: float = DEFAULT_TARGET_SECONDS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> list[tuple[float, float]]:
    """Chia [0, duration] thành các khúc, ưu tiên cắt giữa khoảng lặng.

    Hàm thuần (không chạm đĩa) để test được mọi trường hợp biên mà không cần
    dựng file audio thật.

    Quy tắc chọn điểm cắt cho mỗi khúc: nhắm tới `target_seconds`, chấp nhận mọi
    khoảng lặng nằm trong `[nửa target, max]` tính từ đầu khúc, chọn cái GẦN
    target nhất. Không có khoảng lặng nào hợp lệ thì cắt cứng tại `max_seconds` —
    thà có một mối nối nghe được còn hơn để một khúc dài vô hạn làm tràn RAM.
    """
    if duration <= 0:
        return []
    if duration <= max_seconds:
        return [(0.0, duration)]

    midpoints = sorted((start + end) / 2 for start, end in silences)

    chunks: list[tuple[float, float]] = []
    cursor = 0.0
    while duration - cursor > max_seconds:
        ideal = cursor + target_seconds
        earliest = cursor + target_seconds / 2
        latest = cursor + max_seconds
        candidates = [m for m in midpoints if earliest <= m <= latest]
        cut = min(candidates, key=lambda m: abs(m - ideal)) if candidates else latest
        chunks.append((cursor, cut))
        cursor = cut

    chunks.append((cursor, duration))
    return chunks


def separate_vocals(
    audio_path: Path,
    output_dir: Path,
    *,
    duration: float | None = None,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> tuple[Path, Path]:
    """Tách giọng khỏi nhạc nền, tự cắt khúc khi audio quá dài.

    Trả về đúng cặp `(vocals, no_vocals)` như `demucs.separate_vocals` và ghi ra
    ĐÚNG đường dẫn quy ước `<output_dir>/htdemucs/<tên file>/` — phía sau
    (`timeline_service.get_audio_stems`) đọc theo đường dẫn đó, đổi chỗ ghi sẽ
    làm mất track nhạc nền trong editor mà không báo lỗi gì.
    """
    if duration is None:
        duration = ffmpeg.probe_duration_seconds(audio_path) or 0.0

    if duration <= CHUNKING_THRESHOLD_SECONDS:
        return demucs.separate_vocals(audio_path, output_dir)

    silences = ffmpeg.detect_silences(audio_path)
    chunks = plan_chunks(duration, silences)
    logger.info(
        "Audio dài %.0fs -> cắt thành %d khúc tại %d khoảng lặng phát hiện được",
        duration,
        len(chunks),
        len(silences),
    )

    work_dir = output_dir / "_chunks"
    work_dir.mkdir(parents=True, exist_ok=True)
    vocal_parts: list[Path] = []
    background_parts: list[Path] = []

    for index, (start, end) in enumerate(chunks):
        part_path = work_dir / f"part{index:03d}.wav"
        ffmpeg.slice_audio(audio_path, part_path, start, end)
        vocals, background = demucs.separate_vocals(
            part_path, work_dir / f"out{index:03d}"
        )
        vocal_parts.append(vocals)
        background_parts.append(background)
        if on_chunk_done is not None:
            on_chunk_done(index + 1, len(chunks))

    stem_dir = output_dir / "htdemucs" / audio_path.stem
    stem_dir.mkdir(parents=True, exist_ok=True)
    vocals_out = stem_dir / "vocals.wav"
    background_out = stem_dir / "no_vocals.wav"
    ffmpeg.concat_audio(vocal_parts, vocals_out)
    ffmpeg.concat_audio(background_parts, background_out)

    # File khúc trung gian (part*.wav, out*/htdemucs/...) không còn cần sau khi
    # đã nối xong — dọn ngay thay vì để tích luỹ tới lần cleanup 30 ngày
    # (storage_cleanup_service), quan trọng hơn khi host nhiều user dùng chung
    # ổ đĩa (xem docs/performance-optimization/plan.md mục P1).
    shutil.rmtree(work_dir, ignore_errors=True)

    return vocals_out, background_out
