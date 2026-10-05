import pytest

from app.services import progress_service


@pytest.fixture(autouse=True)
def clean_registry():
    """Progress is stored in a module-level dict — clear it between tests so no state leaks."""
    yield
    for progress in progress_service.snapshot():
        progress_service.clear(progress.video_id)


class TestProgressLifecycle:
    def test_start_then_snapshot(self) -> None:
        progress_service.start(1, "Video A")
        items = progress_service.snapshot()

        assert [i.video_id for i in items] == [1]
        assert items[0].stage == "pending"

    def test_advance_accumulates_within_stage(self) -> None:
        progress_service.start(1, "Video A")
        progress_service.set_stage(1, "video", total=1000)
        progress_service.advance(1, 250)
        progress_service.advance(1, 250)

        progress = progress_service.snapshot()[0]
        assert progress.current == 500
        assert progress.percent == 50.0

    def test_new_stage_resets_counter(self) -> None:
        """Each stage counts from the start again, otherwise the later stage's percentage would jump past 100."""
        progress_service.start(1, "Video A")
        progress_service.set_stage(1, "video", total=100)
        progress_service.advance(1, 100)
        progress_service.set_stage(1, "audio", total=50)

        progress = progress_service.snapshot()[0]
        assert progress.current == 0
        assert progress.total == 50

    def test_percent_is_zero_without_total(self) -> None:
        """Bilibili does not always return Content-Length, and transcribe cannot be split up
        — must not divide by None."""
        progress_service.start(1, "Video A")
        progress_service.set_stage(1, "video", total=None)
        progress_service.advance(1, 999)

        assert progress_service.snapshot()[0].percent == 0.0

    def test_percent_capped_at_100(self) -> None:
        progress_service.start(1, "Video A")
        progress_service.set_stage(1, "video", total=100)
        progress_service.advance(1, 250)

        assert progress_service.snapshot()[0].percent == 100.0

    def test_finish_marks_done(self) -> None:
        progress_service.start(1, "Video A")
        progress_service.finish(1)

        progress = progress_service.snapshot()[0]
        assert progress.stage == "done"
        assert progress.error is None

    def test_finish_with_error_marks_failed(self) -> None:
        progress_service.start(1, "Video A")
        progress_service.finish(1, error="hết đĩa")

        progress = progress_service.snapshot()[0]
        assert progress.stage == "failed"
        assert progress.error == "hết đĩa"

    def test_clear_removes_entry(self) -> None:
        progress_service.start(1, "Video A")
        progress_service.clear(1)

        assert progress_service.snapshot() == []

    def test_updates_to_unknown_video_are_ignored(self) -> None:
        """A video cleared midway must not blow up the download loop."""
        progress_service.advance(999, 100)
        progress_service.set_stage(999, "video")
        progress_service.finish(999)

        assert progress_service.snapshot() == []


class TestMultipleTaskKinds:
    """1 video can run several kinds of tasks; they must not overwrite each other."""

    def test_kinds_tracked_separately(self) -> None:
        progress_service.start(1, "Video A", kind="download")
        progress_service.start(1, "Video A", kind="translate")
        progress_service.set_stage(1, "translating", total=10, kind="translate")
        progress_service.advance(1, 4, kind="translate")

        items = {p.kind: p for p in progress_service.snapshot()}

        assert set(items) == {"download", "translate"}
        assert items["translate"].current == 4
        # The download task is not affected by the translation step's progress.
        assert items["download"].current == 0

    def test_finish_only_affects_given_kind(self) -> None:
        progress_service.start(1, "Video A", kind="download")
        progress_service.start(1, "Video A", kind="dub")
        progress_service.finish(1, kind="dub")

        items = {p.kind: p for p in progress_service.snapshot()}

        assert items["dub"].stage == "done"
        assert items["download"].is_running is True

    def test_clear_without_kind_removes_all_for_video(self) -> None:
        progress_service.start(1, "Video A", kind="download")
        progress_service.start(1, "Video A", kind="dub")
        progress_service.start(2, "Video B", kind="download")

        progress_service.clear(1)

        assert [p.video_id for p in progress_service.snapshot()] == [2]

    def test_is_running_reflects_state(self) -> None:
        progress_service.start(1, "Video A", kind="transcribe")

        assert progress_service.is_running(1, "transcribe") is True
        assert progress_service.is_running(1, "dub") is False

        progress_service.finish(1, kind="transcribe")
        assert progress_service.is_running(1, "transcribe") is False

    def test_clear_finished_keeps_running_tasks(self) -> None:
        progress_service.start(1, "Video A", kind="download")
        progress_service.start(2, "Video B", kind="dub")
        progress_service.finish(1, kind="download")

        cleared = progress_service.clear_finished()

        assert cleared == 1
        assert [p.video_id for p in progress_service.snapshot()] == [2]
