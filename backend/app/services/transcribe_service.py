from functools import lru_cache
from pathlib import Path

from app.core import packs


@lru_cache
def _get_model():
    """Load once and reuse for every request (the first model download is slow)."""
    packs.require_ai()
    from faster_whisper import WhisperModel

    return WhisperModel("small", device="cpu", compute_type="int8")


def transcribe(video_path: Path, language: str = "zh") -> list[dict]:
    """faster-whisper decodes the audio from the video file itself via PyAV, no ffmpeg pre-extraction needed."""
    model = _get_model()
    segments, _info = model.transcribe(str(video_path), language=language, vad_filter=True)
    return [
        {"start": segment.start, "end": segment.end, "text": segment.text.strip(), "translated_text": ""}
        for segment in segments
    ]
