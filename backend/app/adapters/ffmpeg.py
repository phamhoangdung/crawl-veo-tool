import shutil
import subprocess
from pathlib import Path


class FfmpegNotFoundError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("ffmpeg không có trong PATH — cài ffmpeg trước khi tải/merge video.")


def ensure_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None:
        raise FfmpegNotFoundError()


def merge_video_audio(video_path: Path, audio_path: Path, output_path: Path) -> None:
    """Ghép video-only + audio-only stream (DASH) thành 1 file mp4, copy codec (không re-encode)."""
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c", "copy",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
