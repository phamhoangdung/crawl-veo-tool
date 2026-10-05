"""Shared file library for video assembly: logos, watermarks, intro/outro, background music.

Unlike the files of an individual video (in `storage/<video_id>/`), an asset is reused
by MANY videos — one channel logo used for every video — so it is kept separately in
`storage/assets/` and not deleted when cleaning up one video's files.
"""

import logging
import re
import shutil
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import storage_dir

logger = logging.getLogger(__name__)

# Classified by use on the timeline, not by file extension: both are .mp4
# but an intro joins the video track while a logo does not.
KIND_IMAGE = "image"
KIND_VIDEO = "video"
KIND_AUDIO = "audio"

_EXTENSIONS: dict[str, set[str]] = {
    KIND_IMAGE: {".png", ".jpg", ".jpeg", ".webp"},
    KIND_VIDEO: {".mp4", ".mov", ".mkv", ".webm"},
    KIND_AUDIO: {".mp3", ".wav", ".m4a", ".aac", ".flac"},
}

# Limit so a careless file does not fill the disk. Video is more generous because an intro
# of a few seconds at 1080p can already exceed 50 MB.
MAX_BYTES: dict[str, int] = {
    KIND_IMAGE: 10 * 1024 * 1024,
    KIND_AUDIO: 50 * 1024 * 1024,
    KIND_VIDEO: 500 * 1024 * 1024,
}


class AssetError(ValueError):
    pass


@dataclass
class Asset:
    id: str
    name: str
    kind: str
    path: str
    size: int


def assets_dir() -> Path:
    path = storage_dir() / "assets"
    path.mkdir(parents=True, exist_ok=True)
    return path


def detect_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    for kind, extensions in _EXTENSIONS.items():
        if suffix in extensions:
            return kind
    allowed = sorted(e for exts in _EXTENSIONS.values() for e in exts)
    raise AssetError(f"Định dạng {suffix or '(không có đuôi)'} không hỗ trợ. Nhận: {', '.join(allowed)}")


def _safe_name(filename: str) -> str:
    """Keep the original name so the user recognizes the file, but strip characters that could escape the
    assets directory or break the ffmpeg filter syntax."""
    stem = Path(filename).name
    # Strip Vietnamese diacritics: ffmpeg filter_complex handles non-ASCII paths unreliably.
    stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return stem or "asset"


def save_asset(filename: str, data: bytes) -> Asset:
    kind = detect_kind(filename)

    limit = MAX_BYTES[kind]
    if len(data) > limit:
        raise AssetError(
            f"File {len(data) / 1024 / 1024:.1f} MB vượt giới hạn {limit // 1024 // 1024} MB cho loại '{kind}'"
        )
    if not data:
        raise AssetError("File rỗng")

    safe = _safe_name(filename)
    # Id prefix so 2 files with the same name do not overwrite each other — users often have several
    # versions of "logo.png".
    asset_id = uuid.uuid4().hex[:12]
    target = assets_dir() / f"{asset_id}__{safe}"
    target.write_bytes(data)

    logger.info("Đã lưu asset %s (%s, %d bytes)", target.name, kind, len(data))
    return Asset(id=asset_id, name=safe, kind=kind, path=str(target), size=len(data))


def _parse(path: Path) -> Asset | None:
    name = path.name
    if "__" not in name:
        return None
    asset_id, _, original = name.partition("__")
    try:
        kind = detect_kind(original)
    except AssetError:
        return None
    return Asset(id=asset_id, name=original, kind=kind, path=str(path), size=path.stat().st_size)


def list_assets(kind: str | None = None) -> list[Asset]:
    assets = [a for p in sorted(assets_dir().iterdir()) if p.is_file() and (a := _parse(p))]
    return [a for a in assets if kind is None or a.kind == kind]


def get_asset(asset_id: str) -> Asset | None:
    return next((a for a in list_assets() if a.id == asset_id), None)


def delete_asset(asset_id: str) -> bool:
    asset = get_asset(asset_id)
    if asset is None:
        return False
    Path(asset.path).unlink(missing_ok=True)
    return True


def import_from_path(source: str) -> Asset:
    """Import a file already on the machine — the desktop build uses this path instead of uploading
    over HTTP (the user picks the file with the operating system's dialog)."""
    path = Path(source).expanduser()
    if not path.is_file():
        raise AssetError(f"Không tìm thấy file: {source}")

    kind = detect_kind(path.name)
    size = path.stat().st_size
    if size > MAX_BYTES[kind]:
        raise AssetError(
            f"File {size / 1024 / 1024:.1f} MB vượt giới hạn {MAX_BYTES[kind] // 1024 // 1024} MB"
        )

    asset_id = uuid.uuid4().hex[:12]
    target = assets_dir() / f"{asset_id}__{_safe_name(path.name)}"
    # copy2 keeps mtime — useful when comparing with the source file.
    shutil.copy2(path, target)
    return Asset(id=asset_id, name=_safe_name(path.name), kind=kind, path=str(target), size=size)
