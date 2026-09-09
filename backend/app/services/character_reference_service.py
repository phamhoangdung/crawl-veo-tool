"""Bộ ảnh tham chiếu nhân vật/cảnh (Phase 14).

Ảnh tham chiếu được đính kèm vào MỌI lần sinh ảnh/video để nhân vật giữ đặc điểm
xuyên nhiều cảnh — mỗi lần gọi model là một lần sinh độc lập, model không "nhớ"
lần trước. Xem docs/ai-video-generation/research.md Phần 3.
"""

import logging
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import _storage_dir
from app.models.character_reference import CharacterReference

logger = logging.getLogger(__name__)

_SLUG_PATTERN = re.compile(r"^[a-z0-9_]+$")
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024


class CharacterReferenceError(ValueError):
    pass


def references_dir() -> Path:
    path = _storage_dir() / "character_refs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_name(name: str) -> str:
    """`name` được dùng làm mention token `@ten` trong prompt nên phải là slug —
    khoảng trắng hay dấu tiếng Việt sẽ làm việc parse `@ten` không xác định."""
    cleaned = name.strip().lower()
    if not _SLUG_PATTERN.match(cleaned):
        raise CharacterReferenceError(
            f"Tên '{name}' không hợp lệ — chỉ dùng chữ thường không dấu, số và _ "
            "(vì tên này được gọi trong prompt dạng @ten)."
        )
    return cleaned


def create_reference(
    db: Session,
    user_id: int,
    name: str,
    images: list[tuple[str, bytes]],
    description: str | None = None,
) -> CharacterReference:
    slug = validate_name(name)

    existing = db.execute(
        select(CharacterReference).where(
            CharacterReference.user_id == user_id, CharacterReference.name == slug
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise CharacterReferenceError(f"Đã có bộ ảnh tên '{slug}' — chọn tên khác.")

    if not images:
        raise CharacterReferenceError("Cần ít nhất 1 ảnh tham chiếu.")

    saved_paths: list[str] = []
    target_dir = references_dir() / f"{slug}_{uuid.uuid4().hex[:8]}"
    target_dir.mkdir(parents=True, exist_ok=True)

    for filename, data in images:
        suffix = Path(filename).suffix.lower()
        if suffix not in _ALLOWED_SUFFIXES:
            raise CharacterReferenceError(
                f"Định dạng {suffix or '(không có đuôi)'} không hỗ trợ — "
                f"dùng {', '.join(sorted(_ALLOWED_SUFFIXES))}."
            )
        if not data:
            raise CharacterReferenceError(f"File {filename} rỗng.")
        if len(data) > _MAX_IMAGE_BYTES:
            raise CharacterReferenceError(
                f"Ảnh {filename} nặng {len(data) / 1024 / 1024:.1f} MB, "
                f"vượt giới hạn {_MAX_IMAGE_BYTES // 1024 // 1024} MB."
            )
        target = target_dir / f"{len(saved_paths):02d}{suffix}"
        target.write_bytes(data)
        saved_paths.append(str(target))

    record = CharacterReference(
        user_id=user_id, name=slug, description=description, file_paths=saved_paths
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.info("Đã tạo bộ ảnh tham chiếu '%s' (%d ảnh)", slug, len(saved_paths))
    return record


def list_references(db: Session, user_id: int) -> list[CharacterReference]:
    return list(
        db.execute(
            select(CharacterReference)
            .where(CharacterReference.user_id == user_id)
            .order_by(CharacterReference.created_at.desc())
        ).scalars()
    )


def get_reference(db: Session, user_id: int, reference_id: int) -> CharacterReference | None:
    return db.execute(
        select(CharacterReference).where(
            CharacterReference.id == reference_id, CharacterReference.user_id == user_id
        )
    ).scalar_one_or_none()


def get_by_name(db: Session, user_id: int, name: str) -> CharacterReference | None:
    return db.execute(
        select(CharacterReference).where(
            CharacterReference.name == name, CharacterReference.user_id == user_id
        )
    ).scalar_one_or_none()


def delete_reference(db: Session, user_id: int, reference_id: int) -> bool:
    record = get_reference(db, user_id, reference_id)
    if record is None:
        return False

    for path_str in record.file_paths:
        Path(path_str).unlink(missing_ok=True)
    parent = Path(record.file_paths[0]).parent if record.file_paths else None
    if parent is not None and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()

    db.delete(record)
    db.commit()
    return True


def resolve_mentions(db: Session, user_id: int, prompt: str) -> tuple[list[CharacterReference], list[str]]:
    """Tìm các token `@ten` trong prompt, trả (bộ ảnh khớp, tên không tồn tại).

    Quy ước học từ GOHA Flow Studio: người dùng gõ `@char_hero @prop_bag` ở đầu
    prompt, tool tự đính kèm đúng ảnh — không phải chọn tay từng cặp ảnh-prompt.
    """
    mentioned = re.findall(r"@([a-z0-9_]+)", prompt.lower())
    found: list[CharacterReference] = []
    missing: list[str] = []

    for name in dict.fromkeys(mentioned):
        record = get_by_name(db, user_id, name)
        if record is None:
            missing.append(name)
        else:
            found.append(record)
    return found, missing
