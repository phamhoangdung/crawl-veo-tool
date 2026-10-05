"""User settings stored durably in the DB — Phase 21 (download thread count) + Phase 20
(number of videos downloading at once). See the `models/app_setting.py` docstring.

Only 2 keys exist in this phase (`download_connections`, `download_max_videos`)
— deliberately not generalized into a big registry for "every future setting";
3 repeated lines beat a premature abstraction, and for a new key adding 1 field to
`AppSettingsRead`/`AppSettingsUpdate` is enough.
"""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.app_setting import AppSetting

DOWNLOAD_CONNECTIONS_KEY = "download_connections"
DOWNLOAD_MAX_VIDEOS_KEY = "download_max_videos"

SPEAKER_DIARIZATION_KEY = "speaker_diarization_enabled"

DOWNLOAD_CONNECTIONS_MIN = 1
DOWNLOAD_CONNECTIONS_MAX = 8
DOWNLOAD_MAX_VIDEOS_MIN = 1
DOWNLOAD_MAX_VIDEOS_MAX = 10


def _get_int(db: Session, user_id: int, key: str, default: int) -> int:
    row = (
        db.query(AppSetting)
        .filter(AppSetting.user_id == user_id, AppSetting.key == key)
        .one_or_none()
    )
    if row is None:
        return default
    try:
        return int(row.value)
    except ValueError:
        # A corrupt value in the DB (hand-edited, failed migration...) — fall back to the default
        # instead of crashing the whole app every time a download starts.
        return default


def get_download_connections(db: Session, user_id: int) -> int:
    """Read AT THE START OF EVERY DOWNLOAD (not cached at import time) — changing settings
    must take effect right away for the next download, without requiring a
    backend restart (see Definition of Done in phase-21)."""
    return _get_int(
        db, user_id, DOWNLOAD_CONNECTIONS_KEY, get_settings().download_connections
    )


def get_download_max_videos(db: Session, user_id: int) -> int:
    return _get_int(
        db, user_id, DOWNLOAD_MAX_VIDEOS_KEY, get_settings().download_max_videos
    )


def get_speaker_diarization_enabled(db: Session, user_id: int) -> bool:
    """Speaker separation (Phase 19) — OFF by default: results are not stable yet (a video
    with 1 host can still come out as dozens of "speakers"), so it is only enabled when the user
    actively wants to try it. Stored as 0/1 like the other numeric keys."""
    return bool(_get_int(db, user_id, SPEAKER_DIARIZATION_KEY, 0))


def get_all(db: Session, user_id: int) -> dict[str, int]:
    return {
        DOWNLOAD_CONNECTIONS_KEY: get_download_connections(db, user_id),
        DOWNLOAD_MAX_VIDEOS_KEY: get_download_max_videos(db, user_id),
        SPEAKER_DIARIZATION_KEY: int(get_speaker_diarization_enabled(db, user_id)),
    }


def _set_int(db: Session, user_id: int, key: str, value: int) -> None:
    row = (
        db.query(AppSetting)
        .filter(AppSetting.user_id == user_id, AppSetting.key == key)
        .one_or_none()
    )
    if row is None:
        db.add(AppSetting(user_id=user_id, key=key, value=str(value)))
    else:
        row.value = str(value)


def update(
    db: Session,
    user_id: int,
    *,
    download_connections: int | None = None,
    download_max_videos: int | None = None,
    speaker_diarization_enabled: bool | None = None,
) -> dict[str, int]:
    """Only write the keys passed in (not None) — calling `PUT` with 1 field
    must not accidentally erase the other fields."""
    if speaker_diarization_enabled is not None:
        _set_int(db, user_id, SPEAKER_DIARIZATION_KEY, int(speaker_diarization_enabled))
    if download_connections is not None:
        _set_int(db, user_id, DOWNLOAD_CONNECTIONS_KEY, download_connections)
    if download_max_videos is not None:
        _set_int(db, user_id, DOWNLOAD_MAX_VIDEOS_KEY, download_max_videos)
    db.commit()
    return get_all(db, user_id)
