import subprocess
import sys
from pathlib import Path

from app.core.config import is_frozen

# Trùng `DEMUCS_FLAG` ở app/entrypoint.py (không import từ đó: file đó chạy như script).
_FROZEN_DEMUCS_FLAG = "--run-demucs"


def _demucs_command() -> list[str]:
    if is_frozen():
        # Bản đóng gói không có `python -m`; `sys.executable` là chính viedub-backend.exe.
        return [sys.executable, _FROZEN_DEMUCS_FLAG]
    return [sys.executable, "-m", "demucs"]


def separate_vocals(audio_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """Tách audio thành 2 track: vocals.wav (giọng nói) và no_vocals.wav (nhạc nền/hiệu ứng).

    Chạy Demucs ở subprocess riêng thay vì gọi thẳng API nội bộ — ổn định hơn giữa
    các phiên bản, và nếu Demucs hết RAM/crash thì không kéo sập cả server.
    Lần chạy đầu sẽ tải model (~80MB), hơi chậm.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            *_demucs_command(),
            "--two-stems=vocals",
            "-o", str(output_dir),
            str(audio_path),
        ],
        check=True,
        capture_output=True,
    )
    stem_dir = output_dir / "htdemucs" / audio_path.stem
    return stem_dir / "vocals.wav", stem_dir / "no_vocals.wav"
