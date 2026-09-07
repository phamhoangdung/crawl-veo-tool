from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.api_key import ApiKey
from app.schemas.api_key import ApiKeyAddRequest, ApiKeyRead, ApiKeyUpdateRequest
from app.services import api_key_service

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])

# MVP: 1 user cố định — xem docs/overview/plan.md phần multi-tenant.
_DEFAULT_USER_ID = 1


def _to_read(record: ApiKey) -> ApiKeyRead:
    return ApiKeyRead(
        id=record.id,
        provider=record.provider,
        label=record.label,
        masked_key=api_key_service.to_masked_key(record),
        status=record.status,
        request_count=record.request_count,
        error_count=record.error_count,
        last_used_at=record.last_used_at,
        cooldown_until=record.cooldown_until,
        updated_at=record.updated_at,
    )


@router.get("", response_model=list[ApiKeyRead])
def list_api_keys(db: Session = Depends(get_db)) -> list[ApiKeyRead]:
    return [_to_read(record) for record in api_key_service.list_keys(db, _DEFAULT_USER_ID)]


@router.post("", response_model=ApiKeyRead)
def add_api_key(payload: ApiKeyAddRequest, db: Session = Depends(get_db)) -> ApiKeyRead:
    """Thêm 1 key mới vào pool của provider (Phase 8) — không upsert, mỗi lần gọi là
    1 key riêng để rotation có nhiều key cùng provider mà chọn."""
    record = api_key_service.add_key(
        db, _DEFAULT_USER_ID, payload.provider, payload.api_key, payload.label
    )
    return _to_read(record)


@router.patch("/{key_id}", response_model=ApiKeyRead)
def update_api_key(
    key_id: int, payload: ApiKeyUpdateRequest, db: Session = Depends(get_db)
) -> ApiKeyRead:
    record = api_key_service.update_key(
        db, _DEFAULT_USER_ID, key_id, label=payload.label, status=payload.status
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy key")
    return _to_read(record)


@router.delete("/{key_id}", status_code=204)
def delete_api_key(key_id: int, db: Session = Depends(get_db)) -> None:
    deleted = api_key_service.delete_key(db, _DEFAULT_USER_ID, key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy key")
