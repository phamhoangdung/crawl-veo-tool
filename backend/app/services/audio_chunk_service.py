"""Cut long audio into chunks at silent points before running Demucs.

Why it is needed: Demucs loads the whole track into RAM then runs the PyTorch model on it —
a 30-60 minute video would eat many GB and is easily killed midway on a personal machine.
Cutting into ~5 minute chunks keeps the peak RAM almost unchanged however long the video is.

Why cut at SILENT points rather than evenly every 5 minutes: Demucs processes each chunk
independently, cutting through a sung/spoken sentence would make a clear "click" audible at the seam when
joined again. Cutting in a silence puts the seam exactly where there was no sound anyway.
"""

import logging
import shutil
from collections.abc import Callable
from pathlib import Path

from app.adapters import demucs, ffmpeg

logger = logging.getLogger(__name__)

# Chunks that are too long defeat the RAM savings, too short and the number of Demucs
# launches (each must load the model) overwhelms the real processing time.
DEFAULT_TARGET_SECONDS = 300.0
DEFAULT_MAX_SECONDS = 420.0
# Below this threshold run straight through without cutting — adding cut/join steps only slows things down.
CHUNKING_THRESHOLD_SECONDS = 600.0


def plan_chunks(
    duration: float,
    silences: list[tuple[float, float]],
    *,
    target_seconds: float = DEFAULT_TARGET_SECONDS,
    max_seconds: float = DEFAULT_MAX_SECONDS,
) -> list[tuple[float, float]]:
    """Split [0, duration] into chunks, preferring to cut in the middle of a silence.

    A pure function (touching no disk) so every edge case can be tested without needing to
    build a real audio file.

    Rule for choosing the cut point of each chunk: aim for `target_seconds`, accept any
    silence within `[half target, max]` counted from the chunk start, picking the one CLOSEST to
    target. If no silence is valid, hard-cut at `max_seconds` —
    better one audible seam than letting an endless chunk overflow RAM.
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
    """Separate the voice from the background music, automatically chunking when the audio is too long.

    Returns exactly the pair `(vocals, no_vocals)` like `demucs.separate_vocals` and writes to
    EXACTLY the conventional path `<output_dir>/htdemucs/<file name>/` — downstream
    (`timeline_service.get_audio_stems`) reads from that path, changing where it writes would
    lose the background music track in the editor without any error.
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

    # Intermediate chunk files (part*.wav, out*/htdemucs/...) are no longer needed once
    # joining is done — clean up right away instead of letting them accumulate until the 30-day cleanup
    # (storage_cleanup_service), more important when hosting many users sharing one
    # disk (see docs/performance-optimization/plan.md, section P1).
    shutil.rmtree(work_dir, ignore_errors=True)

    return vocals_out, background_out
