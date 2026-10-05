from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models.api_key import ApiKey, ApiKeyStatus

# How long a key "rests" after a 429/quota error — simplified per the decision in
# docs/phases/phase-8-ai-account-pool.md: relies only on the error the provider returns, does not let the user
# declare their own quota. After this time the key returns to `active` by itself to be retried.
_COOLDOWN_MINUTES = 60


def add_key(db: Session, user_id: int, provider: str, plain_key: str, label: str | None = None) -> ApiKey:
    """Add 1 new key to the provider's pool — NOT an upsert like the old 1-key/provider version.
    Every call creates a separate row so rotation has several keys of the same provider to choose from."""
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
    """Edit the label and/or set the status manually (e.g. mark `invalid`/`exhausted` when it is known
    for sure that a key is dead for good, without waiting for a 429 error to detect it)."""
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
    """Pick 1 `active` key in the pool by least-recently-used (a key never used
    is preferred first). Not fully atomic across multiple processes (SQLite has no
    SELECT...FOR UPDATE like Postgres) — enough for the current personal single-process scale;
    note it down in case a later move to multi-worker Celery needs tighter transactions.
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
    """Helper for translate_service/tts_service: pick a key in the pool and decrypt it right away,
    returning (key_id, plain_key) or None if the pool is empty/has no active key left."""
    record = pick_key_for_task(db, user_id, provider)
    if record is None:
        return None
    return record.id, decrypt_secret(record.encrypted_key)


def mark_key_result(db: Session, key_id: int, *, success: bool) -> None:
    """Call after each use of a key: on success do nothing more (last_used_at/request_count
    were already updated at pick time); on failure due to quota put the key to rest
    (status=cooldown) so the next pick skips it."""
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
    """Only "peek" whether any active key is configured — does NOT update
    last_used_at/request_count. For places that only need to know "is there a key" without
    actually calling the API (e.g. cost_service estimating cost before running a batch).

    translate_service/tts_service use `pick_decrypted_key` + `mark_key_result` instead
    of this function, to get real rotation/failover (see docs/phases/phase-8-ai-account-pool.md).
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
