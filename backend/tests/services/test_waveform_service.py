import subprocess
from pathlib import Path

import pytest

from app.services import waveform_service


@pytest.fixture
def sine_clip(tmp_path: Path) -> Path:
    path = tmp_path / "sine.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(path)],
        check=True,
        capture_output=True,
    )
    return path


@pytest.fixture
def silent_clip(tmp_path: Path) -> Path:
    path = tmp_path / "silence.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=duration=2", str(path)],
        check=True,
        capture_output=True,
    )
    return path


def test_returns_requested_bucket_count(sine_clip: Path) -> None:
    result = waveform_service.compute_waveform(sine_clip, bucket_count=50)
    assert len(result) == 50


def test_values_normalized_between_0_and_1(sine_clip: Path) -> None:
    result = waveform_service.compute_waveform(sine_clip, bucket_count=100)
    assert all(0.0 <= v <= 1.0 for v in result)


def test_sine_wave_has_nonzero_peaks(sine_clip: Path) -> None:
    result = waveform_service.compute_waveform(sine_clip, bucket_count=100)
    assert max(result) > 0.1


def test_silence_has_near_zero_peaks(silent_clip: Path) -> None:
    result = waveform_service.compute_waveform(silent_clip, bucket_count=100)
    assert max(result) < 0.01


def test_default_bucket_count(sine_clip: Path) -> None:
    result = waveform_service.compute_waveform(sine_clip)
    assert len(result) == 200
