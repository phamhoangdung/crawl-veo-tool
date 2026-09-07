"""Tính waveform (biên độ đỉnh theo cửa sổ thời gian) để frontend vẽ canvas — xem
docs/phases/phase-13-timeline-editor.md. Tính ở backend (dùng ffmpeg/pydub có sẵn)
thay vì Web Audio API phía trình duyệt, đơn giản hơn cho MVP."""

from pathlib import Path

from pydub import AudioSegment

_DEFAULT_BUCKET_COUNT = 200


def compute_waveform(audio_path: Path, *, bucket_count: int = _DEFAULT_BUCKET_COUNT) -> list[float]:
    """Trả về `bucket_count` giá trị biên độ đỉnh đã chuẩn hoá về [0, 1].

    Với audio nhiều kênh (stereo), lấy peak trên mảng sample đã interleave — đủ
    chính xác cho mục đích hiển thị waveform trực quan, không cần tách kênh.
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
