from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.models.job import Job, JobStatus, Platform
from app.models.user import User
from app.models.video import Video, VideoStatus
from app.services import file_manager_service


@pytest.fixture
def db() -> Session:
    """DB in-memory riêng cho mỗi test — xoá file là thao tác phá huỷ, phải cách ly."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    # Commit user trước: pragma foreign_keys=ON (đăng ký toàn cục ở core/db.py)
    # áp dụng cả ở đây, nên Job không thể chèn cùng lượt với User nó tham chiếu.
    session.add(User(id=1))
    session.commit()
    session.add(
        Job(id=1, user_id=1, platform=Platform.BILIBILI, keyword="test", status=JobStatus.COMPLETED)
    )
    session.commit()
    yield session
    session.close()


def _make_video(db: Session, tmp_path: Path, *, with_dubbed: bool = False) -> Video:
    video_dir = tmp_path / "1" / "1"
    video_dir.mkdir(parents=True)

    original = video_dir / "original.mp4"
    original.write_bytes(b"x" * 1000)

    dubbed_path = None
    if with_dubbed:
        dubbed = video_dir / "dubbed.mp4"
        dubbed.write_bytes(b"y" * 500)
        dubbed_path = str(dubbed)

    video = Video(
        id=1,
        user_id=1,
        job_id=1,
        platform=Platform.BILIBILI,
        platform_video_id="BV1",
        title="Video thử",
        source_url="https://example.com",
        local_path=str(original),
        dubbed_path=dubbed_path,
        status=VideoStatus.DOWNLOADED,
    )
    db.add(video)
    db.commit()
    return video


class TestListVideoFiles:
    def test_reports_real_sizes(self, db: Session, tmp_path: Path) -> None:
        _make_video(db, tmp_path, with_dubbed=True)

        entries = file_manager_service.list_video_files(db, 1)

        assert len(entries) == 1
        assert entries[0].total_bytes == 1500
        assert {f.variant for f in entries[0].files} == {"original", "dubbed"}

    def test_marks_missing_file_as_not_exists(self, db: Session, tmp_path: Path) -> None:
        """DB trỏ tới file người dùng đã xoá tay — phải báo thiếu, không nổ."""
        video = _make_video(db, tmp_path)
        Path(video.local_path).unlink()

        entry = file_manager_service.list_video_files(db, 1)[0]

        assert entry.files[0].exists is False
        assert entry.total_bytes == 0


class TestDeleteVariant:
    def test_deletes_file_and_clears_path(self, db: Session, tmp_path: Path) -> None:
        video = _make_video(db, tmp_path, with_dubbed=True)
        dubbed = Path(video.dubbed_path)

        assert file_manager_service.delete_variant(db, 1, "dubbed") is True
        assert not dubbed.exists()
        assert video.dubbed_path is None

    def test_deleting_original_resets_status(self, db: Session, tmp_path: Path) -> None:
        """Mất file gốc thì các bước sau không chạy được — phải về lại queued."""
        video = _make_video(db, tmp_path)

        file_manager_service.delete_variant(db, 1, "original")

        assert video.local_path is None
        assert video.status == VideoStatus.QUEUED

    def test_rejects_unknown_variant(self, db: Session, tmp_path: Path) -> None:
        _make_video(db, tmp_path)

        with pytest.raises(ValueError, match="không hợp lệ"):
            file_manager_service.delete_variant(db, 1, "khong-ton-tai")

    def test_returns_false_when_no_path(self, db: Session, tmp_path: Path) -> None:
        _make_video(db, tmp_path)

        assert file_manager_service.delete_variant(db, 1, "burned") is False


class TestDeleteVideoFiles:
    def test_removes_directory_and_reports_freed(self, db: Session, tmp_path: Path) -> None:
        video = _make_video(db, tmp_path, with_dubbed=True)
        video_dir = Path(video.local_path).parent

        freed = file_manager_service.delete_video_files(db, 1)

        assert freed == 1500
        assert not video_dir.exists()
        assert video.local_path is None
        assert video.dubbed_path is None
        assert video.status == VideoStatus.QUEUED

    def test_raises_for_unknown_video(self, db: Session) -> None:
        with pytest.raises(ValueError, match="không tồn tại"):
            file_manager_service.delete_video_files(db, 999)
