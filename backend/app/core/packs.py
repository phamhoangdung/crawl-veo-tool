"""Optional download packs for the packaged (frozen) app.

The installer stays small by NOT bundling the heavy parts. They are downloaded on
first use into the user data directory instead:

- ``ffmpeg``: ffmpeg + ffprobe (~210MB unpacked on Windows, ~110MB on macOS).
- ``ai``: torch (CPU), demucs, speechbrain, faster-whisper, scikit-learn and their
  dependencies, as a zip of a ``pip install --target`` directory (see
  ``scripts/build-ai-pack.mjs``). It is added to ``sys.path`` at runtime, so it must
  be built with the same Python minor version as the PyInstaller backend (3.11).

When running from source (dev) nothing is downloaded: the packages come from the
venv and ffmpeg from PATH, and ``status()`` simply reports them as installed.

This module must only import the standard library and ``app.core.config``: it runs
before any heavy import (also in the ``--run-demucs`` subprocess).
"""

import importlib.util
import logging
import os
import platform
import shutil
import stat
import sys
import tarfile
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from app.core.config import app_data_dir, is_frozen

logger = logging.getLogger(__name__)

# Bump when the pack layout/contents change incompatibly: the old directory is then
# ignored and the new pack is offered for download again.
AI_PACK_VERSION = "1"
FFMPEG_VERSION = "9.0.2"

_RELEASE_BASE = "https://github.com/phamhoangdung/crawl-veo-tool/releases/download"
_IS_WINDOWS = sys.platform == "win32"
# One AI pack per platform, all attached to the same `ai-pack-v<n>` release. The macOS
# pack is a tar.gz because zip loses symlinks and permission bits.
_MAC_ARM = platform.machine().lower() in ("arm64", "aarch64")
_AI_ASSET = (
    "ai-pack-win64.zip"
    if _IS_WINDOWS
    else "ai-pack-macos-arm64.tar.gz" if _MAC_ARM else "ai-pack-macos-x64.tar.gz"
)
_AI_URL = os.environ.get("AI_PACK_URL", f"{_RELEASE_BASE}/ai-pack-v{AI_PACK_VERSION}/{_AI_ASSET}")
# macOS: static builds, one zip per binary (osxexperts for arm64, evermeet for Intel).
_MAC_FFMPEG_URLS = (
    (
        "https://www.osxexperts.net/ffmpeg81arm.zip",
        "https://www.osxexperts.net/ffprobe81arm.zip",
    )
    if _MAC_ARM
    else (
        "https://evermeet.cx/ffmpeg/get/zip",
        "https://evermeet.cx/ffmpeg/get/ffprobe/zip",
    )
)
_FFMPEG_URLS = (
    (
        os.environ.get(
            "FFMPEG_PACK_URL",
            f"https://github.com/GyanD/codexffmpeg/releases/download/{FFMPEG_VERSION}"
            f"/ffmpeg-{FFMPEG_VERSION}-essentials_build.zip",
        ),
    )
    if _IS_WINDOWS
    else _MAC_FFMPEG_URLS
)

_MARKER = ".complete"
_CHUNK = 1024 * 256


class PackMissingError(RuntimeError):
    """Raised when a feature needs a pack that has not been downloaded yet."""

    def __init__(self, pack_id: str) -> None:
        self.pack_id = pack_id
        super().__init__(
            f"Thiếu gói '{pack_id}'. Mở trang Cài đặt → Gói bổ sung để tải về (chỉ cần 1 lần)."
        )


@dataclass
class _State:
    state: str = "idle"  # idle | downloading | extracting | done | error
    downloaded: int = 0
    total: int | None = None
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_states: dict[str, _State] = {"ffmpeg": _State(), "ai": _State()}
_activated = False


def packs_dir() -> Path:
    return app_data_dir() / "packs"


def _ai_dir() -> Path:
    return packs_dir() / f"ai-v{AI_PACK_VERSION}"


def ffmpeg_bin_dir() -> Path:
    # Same directory ffmpeg_locator already searches (`<app data>/bin`).
    return app_data_dir() / "bin"


def is_installed(pack_id: str) -> bool:
    if pack_id == "ai":
        if not is_frozen():
            return importlib.util.find_spec("torch") is not None
        return (_ai_dir() / _MARKER).is_file()
    if pack_id == "ffmpeg":
        # Imported lazily: ffmpeg_locator imports this package's config only.
        from app.core.ffmpeg_locator import ensure_ffmpeg_on_path

        return ensure_ffmpeg_on_path()
    raise KeyError(pack_id)


def activate() -> bool:
    """Make an installed AI pack importable. Safe to call many times; returns whether
    the pack is active. No-op outside the frozen app (dev imports from the venv)."""
    global _activated
    if not is_frozen():
        return is_installed("ai")
    if _activated:
        return True
    root = _ai_dir()
    if not (root / _MARKER).is_file():
        return False
    sys.path.insert(0, str(root))
    # Native libs (torch, ctranslate2, av, onnxruntime, ...) live in package dirs and
    # in `*.libs` folders; Windows needs them registered explicitly.
    dll_dirs = [root, *root.glob("*.libs"), root / "torch" / "lib", root / "ctranslate2"]
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    for directory in dll_dirs:
        if directory.is_dir():
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(directory))
            if str(directory) not in path_parts:
                path_parts.insert(0, str(directory))
    os.environ["PATH"] = os.pathsep.join(path_parts)
    _activated = True
    logger.info("AI pack activated from %s", root)
    return True


def require_ai() -> None:
    """Call right before importing torch/demucs/speechbrain/faster_whisper."""
    if not activate():
        raise PackMissingError("ai")


def status() -> list[dict]:
    result = []
    for pack_id, label, size_mb in (
        ("ffmpeg", "ffmpeg (xử lý video/âm thanh)", 110 if _IS_WINDOWS else 50),
        ("ai", "Gói AI (Whisper, Demucs, phân vai)", 600),
    ):
        st = _states[pack_id]
        installed = is_installed(pack_id)
        result.append(
            {
                "id": pack_id,
                "label": label,
                "approx_size_mb": size_mb,
                "installed": installed,
                "state": "done" if installed and st.state != "error" else st.state,
                "downloaded": st.downloaded,
                "total": st.total,
                "error": st.error,
            }
        )
    return result


def start_install(pack_id: str) -> None:
    """Start downloading a pack in a background thread. No-op if already running."""
    if pack_id not in _states:
        raise KeyError(pack_id)
    st = _states[pack_id]
    with st.lock:
        if st.state in ("downloading", "extracting"):
            return
        st.state, st.downloaded, st.total, st.error = "downloading", 0, None, None
    threading.Thread(target=_run_install, args=(pack_id,), daemon=True).start()


def _download(url: str, dest: Path, st: _State) -> None:
    with httpx.stream("GET", url, follow_redirects=True, timeout=60) as response:
        response.raise_for_status()
        raw_total = response.headers.get("content-length")
        file_total = int(raw_total) if raw_total and raw_total.isdigit() else None
        # Several archives (macOS ffmpeg) share one progress bar: the total grows per file.
        st.total = None if file_total is None else (st.total or 0) + file_total
        with open(dest, "wb") as f:
            for chunk in response.iter_bytes(_CHUNK):
                f.write(chunk)
                st.downloaded += len(chunk)


def _run_install(pack_id: str) -> None:
    st = _states[pack_id]
    work = packs_dir() / f"_{pack_id}-download"
    try:
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        if pack_id == "ai":
            archive = work / _AI_ASSET
            _download(_AI_URL, archive, st)
            st.state = "extracting"
            _extract_ai(archive)
        else:
            archives = []
            for index, url in enumerate(_FFMPEG_URLS):
                archive = work / f"ffmpeg-{index}.zip"
                _download(url, archive, st)
                archives.append(archive)
            st.state = "extracting"
            for archive in archives:
                _extract_ffmpeg(archive)
        st.state = "done"
        logger.info("Pack %s installed", pack_id)
    except Exception as exc:  # surfaced to the UI through status()
        logger.exception("Pack %s install failed", pack_id)
        st.state, st.error = "error", str(exc)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _extract_ai(archive: Path) -> None:
    final = _ai_dir()
    partial = final.with_name(final.name + ".part")
    shutil.rmtree(partial, ignore_errors=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(partial)
    else:
        with tarfile.open(archive) as tf:
            if hasattr(tarfile, "fully_trusted_filter"):  # our own archive: keep symlinks
                tf.extractall(partial, filter="fully_trusted")
            else:
                tf.extractall(partial)
    shutil.rmtree(final, ignore_errors=True)
    partial.rename(final)
    (final / _MARKER).write_text(AI_PACK_VERSION, encoding="utf-8")
    # Drop older pack versions to reclaim disk space.
    for old in packs_dir().glob("ai-v*"):
        if old != final:
            shutil.rmtree(old, ignore_errors=True)


def _extract_ffmpeg(archive: Path) -> None:
    target = ffmpeg_bin_dir()
    target.mkdir(parents=True, exist_ok=True)
    wanted = {"ffmpeg.exe", "ffprobe.exe"} if _IS_WINDOWS else {"ffmpeg", "ffprobe"}
    with zipfile.ZipFile(archive) as zf:
        for member in zf.namelist():
            name = member.rsplit("/", 1)[-1]
            # Windows build: binaries sit under bin/; macOS zips hold the binary at the top.
            if name in wanted and ("/bin/" in member or not _IS_WINDOWS):
                with zf.open(member) as src, open(target / name, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                path = target / name
                path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
