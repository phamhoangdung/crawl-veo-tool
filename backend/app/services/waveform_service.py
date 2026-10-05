"""Compute the waveform (peak amplitude per time window) for the frontend to draw on canvas — see
docs/phases/phase-13-timeline-editor.md. Computed in the backend (using the existing ffmpeg/pydub)
instead of the Web Audio API in the browser, simpler for the MVP."""

from pathlib import Path

from pydub import AudioSegment

_DEFAULT_BUCKET_COUNT = 200


def compute_waveform(audio_path: Path, *, bucket_count: int = _DEFAULT_BUCKET_COUNT) -> list[float]:
    """Return `bucket_count` peak amplitude values normalized to [0, 1].

    For multichannel audio (stereo), take the peak over the interleaved sample array — accurate
    enough for visual waveform display, no need to separate channels.
    """
    audio = AudioSegment.from_file(audio_path)
    samples = audio.get_array_of_samples()
    if len(samples) == 0 or bucket_count <= 0:
        return [0.0] * bucket_count

    max_possible = float(2 ** (8 * audio.sample_width - 1))
    bucket_size = max(1, len(samples) // bucket_count)

    peaks: list[float] = []
    for start in range(0, len(samples), bucket_size):
        chunk = samples[start : start + bucket_size]
        if not chunk:
            continue
        peak = max(abs(s) for s in chunk)
        peaks.append(round(min(peak / max_possible, 1.0), 4))

    peaks = peaks[:bucket_count]
    peaks.extend([0.0] * (bucket_count - len(peaks)))
    return peaks
