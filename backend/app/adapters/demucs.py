import subprocess
import sys
from pathlib import Path

from app.core.config import is_frozen

# Same as `DEMUCS_FLAG` in app/entrypoint.py (not imported from there: that file runs as a script).
_FROZEN_DEMUCS_FLAG = "--run-demucs"


def _demucs_command() -> list[str]:
    if is_frozen():
        # The packaged build has no `python -m`; `sys.executable` is viedub-backend.exe itself.
        return [sys.executable, _FROZEN_DEMUCS_FLAG]
    return [sys.executable, "-m", "demucs"]


def separate_vocals(audio_path: Path, output_dir: Path) -> tuple[Path, Path]:
    """Split audio into 2 tracks: vocals.wav (speech) and no_vocals.wav (background music/effects).

    Runs Demucs in its own subprocess instead of calling the internal API directly — more stable across
    versions, and if Demucs runs out of RAM/crashes it does not bring the whole server down.
    The first run downloads the model (~80MB), which is a bit slow.
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
