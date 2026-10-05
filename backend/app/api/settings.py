"""User settings — Phase 21 (download thread count) + Phase 20 (number of videos downloading at
once). See the `services/settings_service.py` docstring."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])

_DEFAULT_USER_ID = 1  # MVP: 1 fixed user, see app/api/crawl.py.


class AppSettingsRead(BaseModel):
    download_connections: int
    download_max_videos: int
    speaker_diarization_enabled: bool


class AppSettingsUpdate(BaseModel):
    # `Field(ge=1, le=8)` is a HARD cap at the schema — measurements show 16 threads
    # is slower than 8, letting users enter more only hurts them (see phase-21).
    download_connections: int | None = Field(default=None, ge=1, le=8)
    download_max_videos: int | None = Field(default=None, ge=1, le=10)
    speaker_diarization_enabled: bool | None = None


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
        speaker_diarization_enabled=payload.speaker_diarization_enabled,
    )
    return AppSettingsRead(**result)
