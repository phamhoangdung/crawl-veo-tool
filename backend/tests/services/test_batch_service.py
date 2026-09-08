import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.models.job import Job, JobStatus, Platform
from app.models.user import User
from app.models.video import Video, VideoStatus
from app.services import batch_service


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    # Pragma foreign_keys=ON là toàn cục (core/db.py) nên User phải commit trước Job.
    with factory() as db:
        db.add(User(id=1))
        db.commit()
        db.add(
            Job(id=1, user_id=1, platform=Platform.BILIBILI, keyword="t", status=JobStatus.COMPLETED)
        )
        db.commit()
    return factory


def _add_video(factory, video_id: int, **kwargs) -> None:
    with factory() as db:
        db.add(
            Video(
                id=video_id,
                user_id=1,
                job_id=1,
                platform=Platform.BILIBILI,
                platform_video_id=f"BV{video_id}",
                title=f"Video {video_id}",
                source_url="https://example.com",
                status=kwargs.pop("status", VideoStatus.QUEUED),
                **kwargs,
            )
        )
        db.commit()


@pytest.fixture(autouse=True)
def _reset_current():
    yield
    batch_service._current = None


class TestPickPendingSteps:
    """Chạy lại batch không được làm lại bước đã có kết quả."""

    def test_skips_completed_steps(self) -> None:
        video = Video(
            local_path="/x/original.mp4",
            transcript_json=[{"text": "a", "translated_text": "b"}],
            dubbed_path=None,
        )
        pending = batch_service._pick_pending_steps(video, batch_service.DEFAULT_STEPS)

        assert pending == ["dub"]

    def test_all_steps_when_nothing_done(self) -> None:
        video = Video(local_path=None, transcript_json=None, dubbed_path=None)
        pending = batch_service._pick_pending_steps(video, batch_service.DEFAULT_STEPS)

        assert pending == batch_service.DEFAULT_STEPS

    def test_transcript_without_translation_still_needs_translate(self) -> None:
        video = Video(
            local_path="/x.mp4",
            transcript_json=[{"text": "a", "translated_text": ""}],
        )
        pending = batch_service._pick_pending_steps(video, batch_service.DEFAULT_STEPS)

        assert "translate" in pending
        assert "transcribe" not in pending


class TestPrepareBatch:
    @pytest.mark.anyio
    async def test_marks_missing_videos_as_failed(self, session_factory) -> None:
        """Id không tồn tại phải báo lại, nếu không người gọi tưởng đã chạy."""
        _add_video(session_factory, 1)
        job = await batch_service.prepare_batch(session_factory, [1, 999])

        by_id = {i.video_id: i for i in job.items}
        assert by_id[1].status == "pending"
        assert by_id[999].status == "failed"
        assert "không tồn tại" in (by_id[999].error or "")

    @pytest.mark.anyio
    async def test_rejects_second_batch_while_running(self, session_factory) -> None:
        _add_video(session_factory, 1)
        await batch_service.prepare_batch(session_factory, [1])

        with pytest.raises(RuntimeError, match="Đang có batch chạy"):
            await batch_service.prepare_batch(session_factory, [1])


class TestExecuteBatch:
    @pytest.mark.anyio
    async def test_one_failure_does_not_block_others(
        self, session_factory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_video(session_factory, 1)
        _add_video(session_factory, 2)

        async def fake_run_step(step: str, video_id: int) -> None:
            if video_id == 1:
                raise RuntimeError("hỏng")

        from app.api import pipeline as pipeline_api

        monkeypatch.setattr(pipeline_api, "run_step", fake_run_step)

        job = await batch_service.prepare_batch(session_factory, [1, 2], steps=["download"])
        await batch_service.execute_batch(session_factory, job)

        by_id = {i.video_id: i for i in job.items}
        assert by_id[1].status == "failed"
        assert "hỏng" in (by_id[1].error or "")
        assert by_id[2].status == "done"

    @pytest.mark.anyio
    async def test_cancel_skips_remaining(
        self, session_factory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_video(session_factory, 1)
        _add_video(session_factory, 2)

        async def fake_run_step(step: str, video_id: int) -> None:
            batch_service.cancel_current()

        from app.api import pipeline as pipeline_api

        monkeypatch.setattr(pipeline_api, "run_step", fake_run_step)

        job = await batch_service.prepare_batch(
            session_factory, [1, 2], steps=["download"], concurrency=1
        )
        await batch_service.execute_batch(session_factory, job)

        statuses = [i.status for i in job.items]
        assert "skipped" in statuses

    @pytest.mark.anyio
    async def test_video_already_complete_is_done_without_work(
        self, session_factory, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _add_video(
            session_factory,
            1,
            local_path="/x/original.mp4",
            transcript_json=[{"text": "a", "translated_text": "b"}],
            dubbed_path="/x/dubbed.mp4",
        )

        called = {"count": 0}

        async def fake_run_step(step: str, video_id: int) -> None:
            called["count"] += 1

        from app.api import pipeline as pipeline_api

        monkeypatch.setattr(pipeline_api, "run_step", fake_run_step)

        job = await batch_service.prepare_batch(session_factory, [1])
        await batch_service.execute_batch(session_factory, job)

        assert job.items[0].status == "done"
        assert called["count"] == 0


class TestListPending:
    def test_returns_videos_without_dub(self, session_factory) -> None:
        _add_video(session_factory, 1, dubbed_path="/x/dubbed.mp4")
        _add_video(session_factory, 2)

        assert batch_service.list_pending_video_ids(session_factory) == [2]
