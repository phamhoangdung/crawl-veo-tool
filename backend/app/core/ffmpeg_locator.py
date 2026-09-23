"""Tìm ffmpeg/ffprobe ngoài PATH của tiến trình hiện tại.

Bản cài desktop có thể được mở từ trình cài đặt (chạy dưới quyền hệ thống chỉ có
PATH của máy) hoặc từ shell cũ, trong khi WinGet/Scoop đặt ffmpeg vào PATH của
NGƯỜI DÙNG. Tiến trình khi đó không thấy ffmpeg dù máy đã cài. Ở đây đọc lại PATH
mới từ registry + thử các thư mục cài phổ biến, rồi thêm thư mục tìm được vào
`os.environ["PATH"]` để mọi lệnh gọi `ffmpeg`/`ffprobe` trong backend đều chạy được.
"""

import logging
import os
import shutil
import sys
from pathlib import Path

from app.core.config import app_data_dir

logger = logging.getLogger(__name__)

_EXE = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def _registry_path_dirs() -> list[Path]:
    """PATH mới nhất của người dùng + máy, đọc thẳng từ registry (Windows)."""
    if sys.platform != "win32":
        return []
    import winreg  # chỉ có trên Windows

    sources = (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    )
    dirs: list[Path] = []
    for hive, subkey in sources:
        try:
            with winreg.OpenKey(hive, subkey) as key:
                raw, _type = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        dirs.extend(
            Path(os.path.expandvars(part)) for part in str(raw).split(os.pathsep) if part
        )
    return dirs


def _known_install_dirs() -> list[Path]:
    dirs: list[Path] = [app_data_dir() / "bin"]
    if sys.platform != "win32":
        return dirs
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    winget = local / "Microsoft" / "WinGet"
    dirs.append(winget / "Links")
    dirs.extend(sorted((winget / "Packages").glob("Gyan.FFmpeg*/ffmpeg-*/bin")))
    dirs.extend(
        [
            Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "chocolatey" / "bin",
            Path.home() / "scoop" / "shims",
            Path(r"C:\ffmpeg\bin"),
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ffmpeg" / "bin",
        ]
    )
    return dirs


def find_ffmpeg_dir() -> Path | None:
    """Thư mục đầu tiên chứa ffmpeg (ưu tiên PATH hiện có, rồi registry, rồi nơi cài phổ biến)."""
    current = [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    for directory in (*current, *_registry_path_dirs(), *_known_install_dirs()):
        try:
            if (directory / _EXE).is_file():
                return directory
        except OSError:
            continue
    return None


def ensure_ffmpeg_on_path() -> bool:
    """True nếu gọi được `ffmpeg` sau hàm này. Gọi lại nhiều lần vẫn an toàn."""
    if shutil.which("ffmpeg") is not None:
        return True
    directory = find_ffmpeg_dir()
    if directory is None:
        return False
    os.environ["PATH"] = f"{directory}{os.pathsep}{os.environ.get('PATH', '')}"
    logger.info("Đã thêm %s vào PATH của backend (tìm thấy ffmpeg ngoài PATH gốc).", directory)
    return shutil.which("ffmpeg") is not None
