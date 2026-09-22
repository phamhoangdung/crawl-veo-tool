"""Cài đặt người dùng — Phase 21 (số luồng tải) + Phase 20 (số video tải cùng
lúc). Xem docstring `services/settings_service.py`."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])

_DEFAULT_USER_ID = 1  # MVP: 1 user cố định, xem app/api/crawl.py.


class AppSettingsRead(BaseModel):
    download_connections: int
    download_max_videos: int


class AppSettingsUpdate(BaseModel):
    # `Field(ge=1, le=8)` chặn CỨNG ở schema — số đo thật cho thấy 16 luồng
    # chậm hơn 8, cho nhập cao hơn chỉ hại người dùng (xem phase-21).
    download_connections: int | None = Field(default=None, ge=1, le=8)
    download_max_videos: int | None = Field(default=None, ge=1, le=10)


@router.get("", response_model=AppSettingsRead)
def get_app_settings(db: Session = Depends(get_db)) -> AppSettingsRead:
    return AppSettingsRead(**settings_service.get_all(db, _DEFAULT_USER_ID))


@router.put("", response_model=AppSettingsRead)
def update_app_settings(
    payload: AppSettingsUpdate, db: Session = Depends(get_db)
) -> AppSettingsRead:
    result = settings_service.update(
        db,
        _DEFAULT_USER_ID,
        download_connections=payload.download_connections,
        download_max_videos=payload.download_max_videos,
    )
    return AppSettingsRead(**result)
