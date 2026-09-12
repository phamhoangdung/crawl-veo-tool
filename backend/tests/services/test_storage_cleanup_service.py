import asyncio
import os
import time
from unittest.mock import patch

import pytest

from app.services import storage_cleanup_service


def test_cleanup_removes_only_old_numeric_job_folders(tmp_path):
    old_job = tmp_path / "1"
    old_job.mkdir()
    (old_job / "video.mp4").write_bytes(b"x")

    new_job = tmp_path / "2"
    new_job.mkdir()

    not_a_job = tmp_path / "_zips"
    not_a_job.mkdir()

    old_time = time.time() - 40 * 86400
    os.utime(old_job, (old_time, old_time))

    with patch("app.services.storage_cleanup_service._STORAGE_ROOT", tmp_path):
        removed = storage_cleanup_service.cleanup_old_job_folders(max_age_days=30)

    assert removed == ["1"]
    assert not old_job.exists()
    assert new_job.exists()
    assert not_a_job.exists()


def test_get_storage_usage_bytes_sums_file_sizes(tmp_path):
    (tmp_path / "1").mkdir()
    (tmp_path / "1" / "a.mp4").write_bytes(b"12345")
    (tmp_path / "1" / "b.mp4").write_bytes(b"12")

    with patch("app.services.storage_cleanup_service._STORAGE_ROOT", tmp_path):
        assert storage_cleanup_service.get_storage_usage_bytes() == 7


class TestPeriodicCleanup:
    """Vòng lặp dọn dẹp nền (Phase 6) — chạy ngay lần đầu, không chết vì 1 lỗi."""

    @staticmethod
    async def _run_until(task: asyncio.Task, reached: asyncio.Event) -> None:
        """Chờ tới mốc cần rồi huỷ task.

        Không đếm bằng `await asyncio.sleep(0)`: vòng lặp gọi `asyncio.to_thread`
        nên có bước nhảy sang thread khác, số lần nhường điều khiển cần thiết là
        không xác định — test kiểu đó sẽ lúc xanh lúc đỏ.
        """
        try:
            await asyncio.wait_for(reached.wait(), timeout=5)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    @pytest.mark.asyncio
    async def test_cleans_immediately_then_sleeps(self, monkeypatch) -> None:
        calls: list[int] = []
        done = asyncio.Event()
        loop = asyncio.get_running_loop()

        def record(days: int) -> list[str]:
            calls.append(days)
            loop.call_soon_threadsafe(done.set)
            return []

        monkeypatch.setattr(storage_cleanup_service, "cleanup_old_job_folders", record)

        task = asyncio.create_task(
            storage_cleanup_service.run_periodic_cleanup(
                max_age_days=7, interval_seconds=3600
            )
        )
        await self._run_until(task, done)

        assert calls == [7], "phải dọn ngay lần đầu chứ không đợi hết chu kỳ"

    @pytest.mark.asyncio
    async def test_one_failure_does_not_kill_the_loop(self, monkeypatch) -> None:
        attempts: list[int] = []
        second_attempt = asyncio.Event()
        loop = asyncio.get_running_loop()

        def flaky(days: int) -> list[str]:
            attempts.append(days)
            if len(attempts) == 1:
                raise OSError("ổ đĩa bận")
            loop.call_soon_threadsafe(second_attempt.set)
            return []

        monkeypatch.setattr(storage_cleanup_service, "cleanup_old_job_folders", flaky)
        # interval=0 để chu kỳ 2 chạy ngay, không phải chờ thật.
        task = asyncio.create_task(
            storage_cleanup_service.run_periodic_cleanup(interval_seconds=0)
        )
        await self._run_until(task, second_attempt)

        assert len(attempts) >= 2, "lỗi ở chu kỳ đầu không được làm chết vòng lặp"
