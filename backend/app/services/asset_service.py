"""Kho file dùng chung cho dựng video: logo, watermark, intro/outro, nhạc nền.

Khác với file của từng video (nằm trong `storage/<video_id>/`), asset được dùng
lại cho NHIỀU video — một logo kênh dùng cho mọi video — nên để riêng ở
`storage/assets/` và không bị xoá khi dọn file của một video.
"""

import logging
import re
import shutil
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.core.config import _storage_dir

logger = logging.getLogger(__name__)

# Phân loại theo công dụng trên timeline, không theo đuôi file: cùng là .mp4
# nhưng intro nối vào track video còn logo thì không.
KIND_IMAGE = "image"
KIND_VIDEO = "video"
KIND_AUDIO = "audio"

_EXTENSIONS: dict[str, set[str]] = {
    KIND_IMAGE: {".png", ".jpg", ".jpeg", ".webp"},
    KIND_VIDEO: {".mp4", ".mov", ".mkv", ".webm"},
    KIND_AUDIO: {".mp3", ".wav", ".m4a", ".aac", ".flac"},
}

# Giới hạn để một file lỡ tay không lấp đầy ổ đĩa. Video rộng tay hơn vì intro
# 1080p vài giây đã có thể vượt 50 MB.
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
    path = _storage_dir() / "assets"
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
    """Giữ tên gốc để người dùng nhận ra file, nhưng bỏ ký tự có thể thoát khỏi
    thư mục assets hoặc phá cú pháp filter của ffmpeg."""
    stem = Path(filename).name
    # Bỏ dấu tiếng Việt: ffmpeg filter_complex xử lý đường dẫn non-ASCII không ổn định.
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
    # Tiền tố id để 2 file trùng tên không đè lên nhau — người dùng hay có nhiều
    # phiên bản "logo.png".
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
    """Nhập file đã có sẵn trên máy — bản desktop dùng đường này thay vì upload
    qua HTTP (người dùng chọn file bằng hộp thoại của hệ điều hành)."""
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
    # copy2 giữ mtime — hữu ích khi đối chiếu với file gốc.
    shutil.copy2(path, target)
    return Asset(id=asset_id, name=_safe_name(path.name), kind=kind, path=str(target), size=size)
