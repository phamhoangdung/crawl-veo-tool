from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.api_key import ApiKeyRead, ApiKeySaveRequest
from app.services import api_key_service

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])

# MVP: 1 user cố định — xem docs/overview/plan.md phần multi-tenant.
_DEFAULT_USER_ID = 1


@router.get("", response_model=list[ApiKeyRead])
def list_api_keys(db: Session = Depends(get_db)) -> list[ApiKeyRead]:
    records = api_key_service.list_keys(db, _DEFAULT_USER_ID)
    return [
        ApiKeyRead(
            provider=record.provider,
            masked_key=api_key_service.to_masked_key(record),
            updated_at=record.updated_at,
        )
        for record in records
    ]


@router.put("", response_model=ApiKeyRead)
def save_api_key(payload: ApiKeySaveRequest, db: Session = Depends(get_db)) -> ApiKeyRead:
    record = api_key_service.save_key(db, _DEFAULT_USER_ID, payload.provider, payload.api_key)
    return ApiKeyRead(
        provider=record.provider,
        masked_key=api_key_service.to_masked_key(record),
        updated_at=record.updated_at,
    )
