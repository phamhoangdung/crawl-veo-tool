"""Phase 21 — bảng cài đặt đầu tiên của dự án (trước đây chỉ đọc từ env)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import Base
from app.models.user import User
from app.services import settings_service


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1))
    session.commit()
    yield session
    session.close()


class TestDefaults:
    def test_reads_config_default_when_no_row(self, db) -> None:
        assert settings_service.get_download_connections(db, 1) == (
            get_settings().download_connections
        )
        assert settings_service.get_download_max_videos(db, 1) == (
            get_settings().download_max_videos
        )

    def test_default_is_1_connection(self, db) -> None:
        """Mặc định phải KHỚP hành vi cũ (1 luồng) — người dùng chưa đụng vào
        Cài đặt thì không được tự nhiên đổi tốc độ/hành vi tải."""
        assert settings_service.get_download_connections(db, 1) == 1


class TestUpdate:
    def test_persists_across_reads(self, db) -> None:
        settings_service.update(db, 1, download_connections=8)
        assert settings_service.get_download_connections(db, 1) == 8

    def test_updating_one_key_does_not_touch_the_other(self, db) -> None:
        settings_service.update(db, 1, download_connections=4, download_max_videos=5)
        settings_service.update(db, 1, download_connections=8)

        assert settings_service.get_download_connections(db, 1) == 8
        assert settings_service.get_download_max_videos(db, 1) == 5

    def test_update_overwrites_existing_row_not_duplicates(self, db) -> None:
        settings_service.update(db, 1, download_connections=2)
        settings_service.update(db, 1, download_connections=6)

        from app.models.app_setting import AppSetting

        rows = (
            db.query(AppSetting)
            .filter(AppSetting.user_id == 1, AppSetting.key == "download_connections")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].value == "6"

    def test_settings_are_per_user(self, db) -> None:
        db.add(User(id=2))
        db.commit()

        settings_service.update(db, 1, download_connections=8)

        assert settings_service.get_download_connections(db, 1) == 8
        assert settings_service.get_download_connections(db, 2) == 1


class TestGetAll:
    def test_returns_both_keys(self, db) -> None:
        result = settings_service.get_all(db, 1)
        assert set(result.keys()) == {"download_connections", "download_max_videos"}
