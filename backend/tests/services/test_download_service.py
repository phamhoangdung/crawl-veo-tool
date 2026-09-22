"""Phase 20 — màn Khám phá tải hàng loạt: giới hạn SỐ VIDEO tải song song qua
semaphore (`download_max_videos`), khác hẳn số kết nối cho MỖI video của
Phase 21 (chưa code). Test `run_download_task` — hàm orchestration dùng
chung cho cả nút tải đơn lẻ (trang Video của tôi) lẫn tải hàng loạt (màn
Khám phá), trước đây nằm riêng trong `api/pipeline.py`."""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.db import Base
from app.core.config import get_settings
from app.models.job import Job, JobStatus, Platform
from app.models.user import User
from app.models.video import Video, VideoStatus
from app.services import download_service, progress_service


@pytest.fixture(autouse=True)
def _reset_download_slots(monkeypatch: pytest.MonkeyPatch):
    """Semaphore module-level: xoá giữa các test để không rò rỉ giới hạn/khoá
    của test trước (mỗi test set `download_max_videos` khác nhau)."""
    monkeypatch.setattr(download_service, "_download_slots", None)
    get_settings.cache_clear()
    yield
    monkeypatch.setattr(download_service, "_download_slots", None)
    get_settings.cache_clear()


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1))
    session.commit()
    session.add(
        Job(id=1, user_id=1, platform=Platform.BILIBILI, keyword="k", status=JobStatus.COMPLETED)
    )
    session.commit()
    yield session
    session.close()


class TestDownloadSlotsLimit:
    """`download_bilibili_video` phải xếp hàng qua semaphore, không chạy quá
    `download_max_videos` lượt thật cùng lúc."""

    @pytest.mark.anyio
    async def test_limits_concurrent_slot_runs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOWNLOAD_MAX_VIDEOS", "2")

        concurrent = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def fake_slot(job_id, video_id, bvid, cid, *, connections):
            nonlocal concurrent, max_concurrent
            async with lock:
                concurrent += 1
                max_concurrent = max(max_concurrent, concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                concurrent -= 1
            return f"/tmp/{video_id}.mp4"

        monkeypatch.setattr(download_service, "_download_bilibili_video_slot", fake_slot)

        await asyncio.gather(
            *(
                download_service.download_bilibili_video(1, vid, f"BV{vid}", 1)
                for vid in range(5)
            )
        )

        assert max_concurrent == 2

    @pytest.mark.anyio
    async def test_reports_queued_stage_while_waiting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DOWNLOAD_MAX_VIDEOS", "1")
        progress_service.clear(1)
        progress_service.clear(2)
        progress_service.start(1, "video 1")
        progress_service.start(2, "video 2")

        release = asyncio.Event()

        async def fake_slot(job_id, video_id, bvid, cid, *, connections):
            if video_id == 1:
                await release.wait()
            return f"/tmp/{video_id}.mp4"

        monkeypatch.setattr(download_service, "_download_bilibili_video_slot", fake_slot)

        task1 = asyncio.create_task(download_service.download_bilibili_video(1, 1, "BV1", 1))
        # Nhường event loop để task1 kịp giữ slot rồi mới thả task2 vào hàng chờ.
        await asyncio.sleep(0)
        task2 = asyncio.create_task(download_service.download_bilibili_video(1, 2, "BV2", 1))
        await asyncio.sleep(0)

        snap = {p.video_id: p.stage for p in progress_service.snapshot() if p.kind == "download"}
        assert snap.get(2) == "queued"

        release.set()
        await task1
        await task2
        progress_service.clear(1)
        progress_service.clear(2)


class TestRunDownloadTask:
    @pytest.mark.anyio
    async def test_missing_video_reports_error_without_raising(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        monkeypatch.setattr(
            download_service, "SessionLocal", sessionmaker(bind=engine)
        )

        # Không raise dù video không tồn tại trong DB.
        await download_service.run_download_task(999)

    @pytest.mark.anyio
    async def test_success_updates_video_status(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db.add(
            Video(
                id=1,
                user_id=1,
                job_id=1,
                platform=Platform.BILIBILI,
                platform_video_id="BV1",
                title="t",
                source_url="https://e.com",
                status=VideoStatus.DOWNLOADING,
            )
        )
        db.commit()

        session_factory = sessionmaker(bind=db.get_bind())
        monkeypatch.setattr(download_service, "SessionLocal", session_factory)

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get_video_cid(self, bvid):
                return 42

        monkeypatch.setattr(download_service, "BilibiliClient", FakeClient)

        async def fake_download(*, job_id, video_id, bvid, cid, connections):
            return "/tmp/original.mp4"

        monkeypatch.setattr(download_service, "download_bilibili_video", fake_download)

        await download_service.run_download_task(1)

        refreshed = db.query(Video).filter(Video.id == 1).one()
        assert refreshed.status == VideoStatus.DOWNLOADED
        assert refreshed.local_path == "/tmp/original.mp4"

    @pytest.mark.anyio
    async def test_failure_marks_failed_download(
        self, db, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db.add(
            Video(
                id=1,
                user_id=1,
                job_id=1,
                platform=Platform.BILIBILI,
                platform_video_id="BV1",
                title="t",
                source_url="https://e.com",
                status=VideoStatus.DOWNLOADING,
            )
        )
        db.commit()

        session_factory = sessionmaker(bind=db.get_bind())
        monkeypatch.setattr(download_service, "SessionLocal", session_factory)

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get_video_cid(self, bvid):
                raise RuntimeError("boom")

        monkeypatch.setattr(download_service, "BilibiliClient", FakeClient)

        await download_service.run_download_task(1)

        refreshed = db.query(Video).filter(Video.id == 1).one()
        assert refreshed.status == VideoStatus.FAILED_DOWNLOAD
        assert "boom" in (refreshed.error_message or "")
