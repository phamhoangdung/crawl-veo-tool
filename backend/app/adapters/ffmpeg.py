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


def extract_audio(video_path: Path, output_path: Path) -> None:
    """Tách audio track thành file wav riêng (đầu vào cho Demucs)."""
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "pcm_s16le", str(output_path)],
        check=True,
        capture_output=True,
    )


def time_stretch(input_path: Path, output_path: Path, factor: float) -> None:
    """Co giãn thời lượng audio theo `factor` (giữ cao độ) bằng filter `atempo` của ffmpeg.

    `atempo` chỉ nhận factor trong [0.5, 2.0] mỗi lần — factor ngoài khoảng này cần chain
    nhiều lần `atempo`, ít gặp với 1 câu thoại nên clamp về biên thay vì chain cho đơn giản.
    """
    ensure_ffmpeg_available()
    clamped = max(0.5, min(2.0, factor))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path), "-filter:a", f"atempo={clamped}", str(output_path)],
        check=True,
        capture_output=True,
    )


def mix_audio_tracks(track_a: Path, track_b: Path, output_path: Path) -> None:
    """Trộn 2 track audio (vd giọng đọc mới + nhạc nền đã tách) thành 1 track."""
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(track_a),
            "-i", str(track_b),
            "-filter_complex", "amix=inputs=2:duration=longest",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def replace_audio_track(video_path: Path, new_audio_path: Path, output_path: Path) -> None:
    """Thay toàn bộ audio track của video bằng file audio mới (Phase 2: chưa giữ nhạc nền gốc).

    Re-encode audio sang AAC vì track mới thường khác codec input (mp3 từ TTS);
    giữ nguyên video stream (copy) để không tốn thời gian re-encode video.
    `-shortest` để cắt theo track ngắn hơn nếu audio/video lệch thời lượng.
    """
    ensure_ffmpeg_available()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(new_audio_path),
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )
