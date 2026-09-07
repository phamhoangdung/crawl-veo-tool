from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models.api_key import ApiKey, ApiKeyStatus

# Thời gian "nghỉ" 1 key sau khi gặp lỗi 429/quota — đơn giản hoá theo quyết định ở
# docs/phases/phase-8-ai-account-pool.md: chỉ dựa lỗi provider trả về, không cho user
# tự khai báo hạn mức. Sau thời gian này key tự về `active` để thử lại.
_COOLDOWN_MINUTES = 60


def add_key(db: Session, user_id: int, provider: str, plain_key: str, label: str | None = None) -> ApiKey:
    """Thêm 1 key mới vào pool của provider — KHÔNG upsert như bản 1-key/provider cũ.
    Mỗi lần gọi tạo 1 row riêng để rotation có nhiều key cùng provider mà chọn."""
    record = ApiKey(
        user_id=user_id,
        provider=provider,
        encrypted_key=encrypt_secret(plain_key),
        label=label,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_keys(db: Session, user_id: int) -> list[ApiKey]:
    return (
        db.query(ApiKey)
        .filter(ApiKey.user_id == user_id)
        .order_by(ApiKey.provider, ApiKey.id)
        .all()
    )


def get_key(db: Session, user_id: int, key_id: int) -> ApiKey | None:
    return (
        db.query(ApiKey)
        .filter(ApiKey.id == key_id, ApiKey.user_id == user_id)
        .first()
    )


def update_key(
    db: Session, user_id: int, key_id: int, *, label: str | None = None, status: ApiKeyStatus | None = None
) -> ApiKey | None:
    """Sửa label và/hoặc đặt status thủ công (vd đánh dấu `invalid`/`exhausted` khi biết
    chắc 1 key đã chết hẳn, không cần đợi lỗi 429 tự phát hiện)."""
    record = get_key(db, user_id, key_id)
    if record is None:
        return None
    if label is not None:
        record.label = label
    if status is not None:
        record.status = status
        if status == ApiKeyStatus.ACTIVE:
            record.cooldown_until = None
    db.commit()
    db.refresh(record)
    return record


def delete_key(db: Session, user_id: int, key_id: int) -> bool:
    record = get_key(db, user_id, key_id)
    if record is None:
        return False
    db.delete(record)
    db.commit()
    return True


def _reactivate_expired_cooldowns(db: Session, user_id: int, provider: str) -> None:
    now = datetime.now(timezone.utc)
    expired = (
        db.query(ApiKey)
        .filter(
            ApiKey.user_id == user_id,
            ApiKey.provider == provider,
            ApiKey.status == ApiKeyStatus.COOLDOWN,
            ApiKey.cooldown_until.isnot(None),
            ApiKey.cooldown_until <= now,
        )
        .all()
    )
    for key in expired:
        key.status = ApiKeyStatus.ACTIVE
        key.cooldown_until = None
    if expired:
        db.commit()


def pick_key_for_task(db: Session, user_id: int, provider: str) -> ApiKey | None:
    """Chọn 1 key `active` trong pool theo least-recently-used (key chưa dùng lần nào
    được ưu tiên trước). Không hoàn toàn atomic qua nhiều process (SQLite không có
    SELECT...FOR UPDATE như Postgres) — đủ dùng cho quy mô cá nhân 1 process hiện tại;
    ghi chú lại nếu sau này chuyển sang Celery đa worker cần transaction chặt hơn.
    """
    _reactivate_expired_cooldowns(db, user_id, provider)

    candidate = (
        db.query(ApiKey)
        .filter(
            ApiKey.user_id == user_id,
            ApiKey.provider == provider,
            ApiKey.status == ApiKeyStatus.ACTIVE,
        )
        .order_by(ApiKey.last_used_at.is_(None).desc(), ApiKey.last_used_at.asc())
        .first()
    )
    if candidate is None:
        return None

    candidate.last_used_at = datetime.now(timezone.utc)
    candidate.request_count += 1
    db.commit()
    db.refresh(candidate)
    return candidate


def pick_decrypted_key(db: Session, user_id: int, provider: str) -> tuple[int, str] | None:
    """Tiện ích cho translate_service/tts_service: chọn key trong pool và giải mã luôn,
    trả (key_id, plain_key) hoặc None nếu pool rỗng/không còn key active."""
    record = pick_key_for_task(db, user_id, provider)
    if record is None:
        return None
    return record.id, decrypt_secret(record.encrypted_key)


def mark_key_result(db: Session, key_id: int, *, success: bool) -> None:
    """Gọi sau mỗi lần dùng key: thành công thì không làm gì thêm (đã cập nhật
    last_used_at/request_count lúc pick); thất bại vì hết quota thì cho key nghỉ
    (status=cooldown) để lần chọn tiếp theo bỏ qua nó."""
    if success:
        return
    key = db.get(ApiKey, key_id)
    if key is None:
        return
    key.error_count += 1
    key.status = ApiKeyStatus.COOLDOWN
    key.cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=_COOLDOWN_MINUTES)
    db.commit()


def get_decrypted_key(db: Session, user_id: int, provider: str) -> str | None:
    """Chỉ "peek" xem có key active nào cấu hình không — KHÔNG cập nhật
    last_used_at/request_count. Dùng cho chỗ chỉ cần biết "có key hay không" mà
    không thực sự gọi API (vd cost_service ước tính chi phí trước khi chạy batch).

    translate_service/tts_service dùng `pick_decrypted_key` + `mark_key_result` thay
    vì hàm này, để có rotation/failover thật (xem docs/phases/phase-8-ai-account-pool.md).
    """
    record = (
        db.query(ApiKey)
        .filter(
            ApiKey.user_id == user_id,
            ApiKey.provider == provider,
            ApiKey.status == ApiKeyStatus.ACTIVE,
        )
        .first()
    )
    return decrypt_secret(record.encrypted_key) if record else None


def to_masked_key(record: ApiKey) -> str:
    return mask_secret(decrypt_secret(record.encrypted_key))
