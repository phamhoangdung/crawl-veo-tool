from sqlalchemy.orm import Session

from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.models.api_key import ApiKey


def save_key(db: Session, user_id: int, provider: str, plain_key: str) -> ApiKey:
    existing = (
        db.query(ApiKey)
        .filter(ApiKey.user_id == user_id, ApiKey.provider == provider)
        .first()
    )
    encrypted = encrypt_secret(plain_key)
    if existing:
        existing.encrypted_key = encrypted
        db.commit()
        db.refresh(existing)
        return existing

    record = ApiKey(user_id=user_id, provider=provider, encrypted_key=encrypted)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_keys(db: Session, user_id: int) -> list[ApiKey]:
    return db.query(ApiKey).filter(ApiKey.user_id == user_id).all()


def get_decrypted_key(db: Session, user_id: int, provider: str) -> str | None:
    record = (
        db.query(ApiKey)
        .filter(ApiKey.user_id == user_id, ApiKey.provider == provider)
        .first()
    )
    if record is None:
        return None
    return decrypt_secret(record.encrypted_key)


def to_masked_key(record: ApiKey) -> str:
    return mask_secret(decrypt_secret(record.encrypted_key))
