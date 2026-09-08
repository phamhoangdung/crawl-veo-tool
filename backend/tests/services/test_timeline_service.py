from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.models.job import Job, JobStatus, Platform
from app.models.user import User
from app.models.video import Video
from app.services import timeline_service


@pytest.fixture
def db(tmp_path: Path) -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1))
    session.commit()
    session.add(
        Job(id=1, user_id=1, platform=Platform.BILIBILI, keyword="test", status=JobStatus.COMPLETED)
    )
    session.commit()
    video_dir = tmp_path / "1" / "1"
    video_dir.mkdir(parents=True)
    session.add(
        Video(
            id=1,
            user_id=1,
            job_id=1,
            platform=Platform.BILIBILI,
            platform_video_id="BV1",
            title="test video",
            source_url="https://example.com",
            local_path=str(video_dir / "original.mp4"),
        )
    )
    session.commit()
    yield session
    session.close()


_VALID_OPERATIONS = {
    "tracks": [
        {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 2}]},
    ]
}


class TestSaveTimeline:
    def test_saves_and_returns_operations(self, db: Session) -> None:
        result = timeline_service.save_timeline(db, 1, _VALID_OPERATIONS)
        assert result == _VALID_OPERATIONS
        assert timeline_service.get_timeline(db, 1) == _VALID_OPERATIONS

    def test_overwrites_previous_draft(self, db: Session) -> None:
        timeline_service.save_timeline(db, 1, _VALID_OPERATIONS)
        second = {
            "tracks": [{"type": "video", "clips": [{"source": "b.mp4", "start": 0, "end": 5}]}]
        }
        timeline_service.save_timeline(db, 1, second)
        assert timeline_service.get_timeline(db, 1) == second

    def test_raises_for_missing_video(self, db: Session) -> None:
        with pytest.raises(timeline_service.VideoNotFoundError):
            timeline_service.save_timeline(db, 999, _VALID_OPERATIONS)

    def test_rejects_missing_tracks(self, db: Session) -> None:
        with pytest.raises(timeline_service.TimelineValidationError):
            timeline_service.save_timeline(db, 1, {})

    def test_rejects_no_video_track(self, db: Session) -> None:
        with pytest.raises(timeline_service.TimelineValidationError, match="video"):
            timeline_service.save_timeline(
                db, 1, {"tracks": [{"type": "overlay", "clips": [{"text": "hi", "start": 0, "end": 1}]}]}
            )

    def test_rejects_invalid_track_type(self, db: Session) -> None:
        with pytest.raises(timeline_service.TimelineValidationError, match="Loại track"):
            timeline_service.save_timeline(db, 1, {"tracks": [{"type": "bogus", "clips": []}]})

    def test_rejects_clip_end_before_start(self, db: Session) -> None:
        bad = {"tracks": [{"type": "video", "clips": [{"source": "a.mp4", "start": 5, "end": 2}]}]}
        with pytest.raises(timeline_service.TimelineValidationError, match="end"):
            timeline_service.save_timeline(db, 1, bad)

    def test_rejects_video_clip_missing_source(self, db: Session) -> None:
        bad = {"tracks": [{"type": "video", "clips": [{"start": 0, "end": 2}]}]}
        with pytest.raises(timeline_service.TimelineValidationError):
            timeline_service.save_timeline(db, 1, bad)


class TestGetTimeline:
    def test_returns_none_when_no_draft_saved(self, db: Session) -> None:
        assert timeline_service.get_timeline(db, 1) is None

    def test_raises_for_missing_video(self, db: Session) -> None:
        with pytest.raises(timeline_service.VideoNotFoundError):
            timeline_service.get_timeline(db, 999)


class TestRenderTimelineForVideo:
    def test_raises_when_no_draft_saved(self, db: Session) -> None:
        with pytest.raises(timeline_service.TimelineValidationError, match="Chưa có timeline"):
            timeline_service.render_timeline_for_video(db, 1)

    def test_calls_ffmpeg_and_persists_output_path(self, db: Session, tmp_path: Path) -> None:
        timeline_service.save_timeline(db, 1, _VALID_OPERATIONS)

        with patch("app.services.timeline_service.ffmpeg.render_timeline") as mock_render:
            output_path = timeline_service.render_timeline_for_video(db, 1)

        mock_render.assert_called_once()
        called_operations, called_output = mock_render.call_args[0]
        assert called_operations == _VALID_OPERATIONS
        assert called_output == output_path

        video = db.get(Video, 1)
        assert video.timeline_rendered_path == str(output_path)

    def test_does_not_render_automatically_on_save(self, db: Session) -> None:
        """Nguyên tắc cốt lõi Phase 13: save KHÔNG kích hoạt render."""
        with patch("app.services.timeline_service.ffmpeg.render_timeline") as mock_render:
            timeline_service.save_timeline(db, 1, _VALID_OPERATIONS)

        mock_render.assert_not_called()


class TestImageTrackValidation:
    """Track ảnh (logo/watermark, Phase 9) — renderer đã hỗ trợ từ trước nhưng
    validator lại chặn, khiến không lưu nổi timeline có logo."""

    def test_accepts_image_track_without_time_range(self, db: Session) -> None:
        """Không có start/end nghĩa là logo hiện suốt video — mặc định hợp lý."""
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 2}]},
                {
                    "type": "image",
                    "clips": [{"source": "logo.png", "x": 0.9, "y": 0.1, "width": 0.15}],
                },
            ]
        }
        assert timeline_service.save_timeline(db, 1, operations) == operations

    def test_accepts_image_track_with_time_range(self, db: Session) -> None:
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 5}]},
                {"type": "image", "clips": [{"source": "logo.png", "start": 1, "end": 4}]},
            ]
        }
        assert timeline_service.save_timeline(db, 1, operations) == operations

    def test_rejects_image_clip_without_source(self, db: Session) -> None:
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 2}]},
                {"type": "image", "clips": [{"x": 0.5}]},
            ]
        }
        with pytest.raises(timeline_service.TimelineValidationError, match="'source'"):
            timeline_service.save_timeline(db, 1, operations)

    def test_rejects_half_specified_time_range(self, db: Session) -> None:
        """Chỉ có start mà thiếu end thường là lỗi gõ nhầm, không phải chủ ý."""
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 2}]},
                {"type": "image", "clips": [{"source": "logo.png", "start": 1}]},
            ]
        }
        with pytest.raises(timeline_service.TimelineValidationError, match="cả 'start' và 'end'"):
            timeline_service.save_timeline(db, 1, operations)

    def test_rejects_end_before_start(self, db: Session) -> None:
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 5}]},
                {"type": "image", "clips": [{"source": "logo.png", "start": 4, "end": 2}]},
            ]
        }
        with pytest.raises(timeline_service.TimelineValidationError):
            timeline_service.save_timeline(db, 1, operations)


class TestBlurTrackValidation:
    """Vùng che logo/phụ đề gốc — validator phải chặn hình dạng sai trước khi
    tới ffmpeg, vì lỗi filter của ffmpeg rất khó đọc."""

    def test_accepts_blur_region(self, db: Session) -> None:
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 5}]},
                {
                    "type": "blur",
                    "clips": [{"x": 0.7, "y": 0.05, "width": 0.25, "height": 0.15}],
                },
            ]
        }
        assert timeline_service.save_timeline(db, 1, operations) == operations

    def test_accepts_pixelate_mode(self, db: Session) -> None:
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 5}]},
                {
                    "type": "blur",
                    "clips": [
                        {"x": 0, "y": 0, "width": 0.2, "height": 0.2, "mode": "pixelate"}
                    ],
                },
            ]
        }
        assert timeline_service.save_timeline(db, 1, operations) == operations

    def test_rejects_missing_dimensions(self, db: Session) -> None:
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 5}]},
                {"type": "blur", "clips": [{"x": 0, "y": 0, "height": 0.2}]},
            ]
        }
        with pytest.raises(timeline_service.TimelineValidationError, match="width"):
            timeline_service.save_timeline(db, 1, operations)

    def test_rejects_zero_size(self, db: Session) -> None:
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 5}]},
                {"type": "blur", "clips": [{"x": 0, "y": 0, "width": 0, "height": 0.2}]},
            ]
        }
        with pytest.raises(timeline_service.TimelineValidationError, match="kích thước dương"):
            timeline_service.save_timeline(db, 1, operations)

    def test_rejects_unknown_mode(self, db: Session) -> None:
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 5}]},
                {
                    "type": "blur",
                    "clips": [{"x": 0, "y": 0, "width": 0.2, "height": 0.2, "mode": "xyz"}],
                },
            ]
        }
        with pytest.raises(timeline_service.TimelineValidationError, match="không hợp lệ"):
            timeline_service.save_timeline(db, 1, operations)

    def test_rejects_half_specified_time_range(self, db: Session) -> None:
        operations = {
            "tracks": [
                {"type": "video", "clips": [{"source": "a.mp4", "start": 0, "end": 5}]},
                {
                    "type": "blur",
                    "clips": [{"x": 0, "y": 0, "width": 0.2, "height": 0.2, "start": 1}],
                },
            ]
        }
        with pytest.raises(timeline_service.TimelineValidationError, match="cả 'start' và 'end'"):
            timeline_service.save_timeline(db, 1, operations)
