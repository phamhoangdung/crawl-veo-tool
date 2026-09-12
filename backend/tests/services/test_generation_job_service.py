import pytest

from app.services import generation_job_service as jobs


@pytest.fixture(autouse=True)
def clean_store():
    """Store là dict ở tầng module nên sống xuyên test — không dọn thì test sau
    thấy job của test trước."""
    jobs.clear()
    yield
    jobs.clear()


class TestLifecycle:
    def test_new_job_starts_running(self) -> None:
        job = jobs.create("keyframe", "một con mèo đội mũ")
        assert job.status == "running"
        assert job.finished_at is None
        assert jobs.get(job.id) is job

    def test_success_records_asset_and_cost(self) -> None:
        job = jobs.create("clip", "mèo nhảy")
        jobs.finish_ok(
            job.id, asset_id=42, file_path="/x/a.mp4", cost_usd=0.16, from_cache=False
        )

        stored = jobs.get(job.id)
        assert stored.status == "done"
        assert (stored.asset_id, stored.cost_usd) == (42, 0.16)
        assert stored.finished_at is not None

    def test_failure_records_reason(self) -> None:
        job = jobs.create("clip", "prompt bị chặn")
        jobs.finish_error(job.id, "Prompt vi phạm chính sách")

        stored = jobs.get(job.id)
        assert stored.status == "failed"
        assert "chính sách" in stored.error

    def test_long_error_is_truncated(self) -> None:
        """Traceback của provider có thể dài hàng chục nghìn ký tự — không để nó
        chảy nguyên vào response JSON."""
        job = jobs.create("clip", "x")
        jobs.finish_error(job.id, "e" * 5000)
        assert len(jobs.get(job.id).error) == 500

    def test_long_label_is_truncated(self) -> None:
        job = jobs.create("keyframe", "p" * 1000)
        assert len(job.label) == 120

    def test_finishing_unknown_job_is_ignored(self) -> None:
        """Job đã bị đẩy khỏi lịch sử mà vẫn chạy xong — không được ném lỗi làm
        chết background task."""
        jobs.finish_ok(
            "khong-ton-tai", asset_id=1, file_path="/x", cost_usd=0, from_cache=False
        )
        jobs.finish_error("khong-ton-tai", "lỗi")


class TestHistory:
    def test_newest_first(self) -> None:
        first = jobs.create("keyframe", "cũ")
        second = jobs.create("keyframe", "mới")
        assert [j.id for j in jobs.list_recent()] == [second.id, first.id]

    def test_history_is_capped_dropping_oldest(self) -> None:
        created = [jobs.create("keyframe", str(i)) for i in range(jobs._MAX_JOBS + 5)]

        recent = jobs.list_recent()
        assert len(recent) == jobs._MAX_JOBS
        assert jobs.get(created[0].id) is None, "job cũ nhất phải bị đẩy ra trước"
        assert jobs.get(created[-1].id) is not None
