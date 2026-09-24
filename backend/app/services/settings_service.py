"""Cài đặt người dùng lưu bền trong DB — Phase 21 (số luồng tải) + Phase 20
(số video tải cùng lúc). Xem docstring `models/app_setting.py`.

Chỉ 2 khoá tồn tại ở phase này (`download_connections`, `download_max_videos`)
— cố tình không tổng quát hoá thành registry lớn cho "mọi cài đặt tương lai";
3 dòng lặp còn hơn 1 abstraction sớm, thêm khoá mới thì thêm 1 field vào
`AppSettingsRead`/`AppSettingsUpdate` là đủ.
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
        # Giá trị hỏng trong DB (chỉnh tay, migration lỗi...) — về mặc định
        # thay vì crash cả app mỗi lần khởi động download.
        return default


def get_download_connections(db: Session, user_id: int) -> int:
    """Đọc lúc BẮT ĐẦU MỖI LƯỢT TẢI (không cache ở import-time) — đổi cài đặt
    phải có tác dụng ngay với lượt tải tiếp theo, không bắt khởi động lại
    backend (xem Definition of Done ở phase-21)."""
    return _get_int(
        db, user_id, DOWNLOAD_CONNECTIONS_KEY, get_settings().download_connections
    )


def get_download_max_videos(db: Session, user_id: int) -> int:
    return _get_int(
        db, user_id, DOWNLOAD_MAX_VIDEOS_KEY, get_settings().download_max_videos
    )


def get_speaker_diarization_enabled(db: Session, user_id: int) -> bool:
    """Phân vai người nói (Phase 19) — mặc định TẮT: kết quả chưa ổn định (video
    1 người dẫn vẫn có thể ra hàng chục "người nói"), nên chỉ bật khi người dùng
    chủ động muốn thử. Lưu dạng 0/1 như các khoá số khác."""
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
    """Chỉ ghi các khoá được truyền vào (không None) — gọi `PUT` với 1 field
    không được vô tình xoá field còn lại."""
    if speaker_diarization_enabled is not None:
        _set_int(db, user_id, SPEAKER_DIARIZATION_KEY, int(speaker_diarization_enabled))
    if download_connections is not None:
        _set_int(db, user_id, DOWNLOAD_CONNECTIONS_KEY, download_connections)
    if download_max_videos is not None:
        _set_int(db, user_id, DOWNLOAD_MAX_VIDEOS_KEY, download_max_videos)
    db.commit()
    return get_all(db, user_id)
