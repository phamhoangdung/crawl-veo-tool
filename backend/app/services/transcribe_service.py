from functools import lru_cache
from pathlib import Path

from faster_whisper import WhisperModel


@lru_cache
def _get_model() -> WhisperModel:
    """Load 1 lần, tái dùng cho mọi request — tải model lần đầu khá chậm."""
    return WhisperModel("small", device="cpu", compute_type="int8")


def transcribe(video_path: Path, language: str = "zh") -> list[dict]:
    """faster-whisper tự giải mã audio từ file video qua PyAV, không cần tách audio trước bằng ffmpeg."""
    model = _get_model()
    segments, _info = model.transcribe(str(video_path), language=language, vad_filter=True)
    return [
        {"start": segment.start, "end": segment.end, "text": segment.text.strip(), "translated_text": ""}
        for segment in segments
    ]
