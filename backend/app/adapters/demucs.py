import subprocess
import sys
from pathlib import Path


def separate_vocals(audio_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """Tách audio thành 2 track: vocals.wav (giọng nói) và no_vocals.wav (nhạc nền/hiệu ứng).

    Dùng `python -m demucs` qua subprocess thay vì gọi thẳng API nội bộ của demucs —
    ổn định hơn giữa các phiên bản, không cần theo dõi thay đổi internal API.
    Lần chạy đầu sẽ tải model (~80MB), hơi chậm.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable, "-m", "demucs",
            "--two-stems=vocals",
            "-o", str(output_dir),
            str(audio_path),
        ],
        check=True,
        capture_output=True,
    )
    stem_dir = output_dir / "htdemucs" / audio_path.stem
    return stem_dir / "vocals.wav", stem_dir / "no_vocals.wav"
