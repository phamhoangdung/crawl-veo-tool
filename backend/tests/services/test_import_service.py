import io
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.job import Platform
from app.models.user import User
from app.models.video import Video, VideoStatus
from app.services import import_service


@pytest.fixture
def db(tmp_path: Path, monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(import_service, "storage_dir", lambda: tmp_path)
    with sessionmaker(bind=engine)() as session:
        session.add(User(id=1))
        session.commit()
        yield session


@pytest.fixture
def fake_ffmpeg(monkeypatch):
    monkeypatch.setattr(import_service.ffmpeg, "probe_duration_seconds", lambda p: 12.6)

    def thumb(video, out, **kw):
        out.write_bytes(b"jpg")

    monkeypatch.setattr(import_service.ffmpeg, "extract_thumbnail", thumb)


def test_imports_file_as_downloaded_local_video(db, tmp_path, fake_ffmpeg) -> None:
    video = import_service.import_local_video(
        db, 1, "Chuyến đi Đà Lạt.MP4", io.BytesIO(b"fake-video-bytes")
    )

    assert video.platform == Platform.LOCAL
    assert video.status == VideoStatus.DOWNLOADED
    assert video.title == "Chuyến đi Đà Lạt"
    assert video.duration_seconds == 13
    assert video.cover_url == f"/api/videos/{video.id}/cover"
    stored = Path(video.local_path)
    assert stored.read_bytes() == b"fake-video-bytes"
    assert stored.name == "original.mp4"
    assert tmp_path in stored.parents


def test_rejects_unsupported_extension_without_creating_rows(db, fake_ffmpeg) -> None:
    with pytest.raises(import_service.UnsupportedVideoFormatError):
        import_service.import_local_video(db, 1, "virus.exe", io.BytesIO(b"x"))
    assert db.query(Video).count() == 0


def test_filename_cannot_escape_storage_dir(db, tmp_path, fake_ffmpeg) -> None:
    video = import_service.import_local_video(
        db, 1, "../../../evil.mkv", io.BytesIO(b"x")
    )
    assert tmp_path in Path(video.local_path).parents
    assert video.title == "evil"


def test_importing_same_file_twice_makes_two_videos(db, fake_ffmpeg) -> None:
    a = import_service.import_local_video(db, 1, "a.mp4", io.BytesIO(b"x"))
    b = import_service.import_local_video(db, 1, "a.mp4", io.BytesIO(b"x"))
    assert a.id != b.id


def test_missing_ffmpeg_does_not_block_import(db, monkeypatch) -> None:
    monkeypatch.setattr(import_service.ffmpeg, "probe_duration_seconds", lambda p: None)

    def boom(*a, **k):
        raise RuntimeError("no ffmpeg")

    monkeypatch.setattr(import_service.ffmpeg, "extract_thumbnail", boom)
    video = import_service.import_local_video(db, 1, "a.mp4", io.BytesIO(b"x"))
    assert video.status == VideoStatus.DOWNLOADED
    assert video.duration_seconds is None
    assert video.cover_url is None


def test_copy_failure_rolls_back_and_cleans_up(db, tmp_path, fake_ffmpeg) -> None:
    class Broken(io.BytesIO):
        def read(self, *a):
            raise OSError("disk gone")

    with pytest.raises(OSError):
        import_service.import_local_video(db, 1, "a.mp4", Broken(b"x"))
    assert db.query(Video).count() == 0
    assert not any(tmp_path.iterdir())
