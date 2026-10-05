from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.models.user import User
from app.services import ai_generation_service, progress_service, project_service
from app.services import character_reference_service as crs
from app.services import project_render_service as service

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture
def db(monkeypatch) -> Session:
    """Use a temp file rather than in-memory `sqlite://`: `render_worker` runs in the
    background so it opens its own `SessionLocal()` (correct, since the request's session is closed),
    and an in-memory DB cannot be shared with another session."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{tmp}/test.db")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        # The worker must see the same DB as the test.
        monkeypatch.setattr(service, "SessionLocal", factory)

        session = factory()
        session.add(User(id=1))
        session.commit()
        yield session
        session.close()
        # Windows cannot delete a file with an open handle: `session.close()` only
        # returns the connection to the pool without closing the file, so without this line
        # TemporaryDirectory cleanup would raise PermissionError in every test.
        engine.dispose()


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch) -> Path:
    out = tmp_path / "generated"
    refs = tmp_path / "refs"
    projects = tmp_path / "projects"
    for directory in (out, refs, projects):
        directory.mkdir()
    monkeypatch.setattr(ai_generation_service, "output_dir", lambda: out)
    monkeypatch.setattr(crs, "references_dir", lambda: refs)
    monkeypatch.setattr(
        service, "output_path_for", lambda pid: projects / f"{pid}.mp4"
    )
    return projects


@pytest.fixture(autouse=True)
def fake_pipeline(monkeypatch) -> dict:
    calls = {"render": 0, "operations": None}

    async def fake_image(prompt, output_path, **kwargs):
        Path(output_path).write_bytes(_PNG)

    def fake_ken_burns(image_path, output_path, **kwargs):
        Path(output_path).write_bytes(b"fake-mp4")

    def fake_last_frame(video_path, output_path, **kwargs):
        # The fake clip is only a few bytes, not a real video — real ffmpeg would fail
        # extracting a frame from it, so the frame-chaining step must be stubbed too.
        Path(output_path).write_bytes(_PNG)

    def fake_render(operations, output_path):
        calls["render"] += 1
        calls["operations"] = operations
        Path(output_path).write_bytes(b"rendered-mp4")

    monkeypatch.setattr(ai_generation_service.fake_adapter, "generate_image", fake_image)
    monkeypatch.setattr(ai_generation_service.ffmpeg, "make_ken_burns_clip", fake_ken_burns)
    monkeypatch.setattr(ai_generation_service.ffmpeg, "extract_last_frame", fake_last_frame)
    monkeypatch.setattr(service.ffmpeg, "render_timeline", fake_render)
    # The fake clip has no readable dimensions, and the uniformity check has its own test
    # in TestUniformDimensions (that test does NOT use this fixture).
    monkeypatch.setattr(service.ffmpeg, "get_video_dimensions", lambda path: (1280, 720))
    return calls


@pytest.fixture(autouse=True)
def clean_progress():
    """`progress_service._active` is a module-level dict so it lives across tests, while each
    test uses a fresh in-memory DB so project ids always start from 1 — if not cleaned,
    the "running" entry of an earlier test makes a later test think it is rendering.
    `clear_finished()` is not enough because it deliberately keeps unfinished entries."""
    progress_service._active.clear()
    yield
    progress_service._active.clear()


def _project(db: Session, count: int = 3):
    crs.create_reference(db, 1, "nguoique", [("a.png", _PNG)])
    return project_service.create_project(
        db, 1, "Dự án render", scene_prompts=[f"@nguoique cảnh {i}" for i in range(count)]
    )


class TestStartRender:
    def test_registers_progress_before_returning(self, db: Session) -> None:
        """The UI must see the job as soon as the request returns, not wait for the worker to run."""
        project = _project(db)

        service.start_render(db, 1, project.id)

        assert service.is_rendering(project.id) is True

    def test_rejects_second_render_while_running(self, db: Session) -> None:
        project = _project(db)
        service.start_render(db, 1, project.id)

        with pytest.raises(service.ProjectRenderError, match="đang được dựng"):
            service.start_render(db, 1, project.id)

    def test_rejects_project_without_scenes(self, db: Session) -> None:
        crs.create_reference(db, 1, "nguoique", [("a.png", _PNG)])
        empty = project_service.create_project(db, 1, "Rỗng")

        with pytest.raises(service.ProjectRenderError, match="chưa có cảnh"):
            service.start_render(db, 1, empty.id)

    def test_rejects_unknown_project(self, db: Session) -> None:
        with pytest.raises(service.ProjectRenderError, match="Không tìm thấy"):
            service.start_render(db, 1, 999)


class TestRenderWorker:
    def test_generates_missing_scenes_then_renders_once(
        self, db: Session, fake_pipeline, storage
    ) -> None:
        project = _project(db, count=3)
        service.start_render(db, 1, project.id)

        service.render_worker(project.id, 1)

        assert fake_pipeline["render"] == 1
        assert len(fake_pipeline["operations"]["tracks"][0]["clips"]) == 3
        db.expire_all()
        refreshed = project_service.get_project(db, 1, project.id)
        assert refreshed.rendered_path is not None
        assert Path(refreshed.rendered_path).exists()

    def test_progress_reaches_done_under_project_subject(
        self, db: Session, fake_pipeline
    ) -> None:
        """Progress must be tagged subject_type='project' — if stuffed into the video slot
        every query by video_id would silently return wrong results."""
        project = _project(db, count=2)
        service.start_render(db, 1, project.id)

        service.render_worker(project.id, 1)

        entries = [
            t
            for t in progress_service.snapshot()
            if t.subject_type == "project" and t.video_id == project.id
        ]
        assert len(entries) == 1
        assert entries[0].stage == "done"
        assert entries[0].kind == "render_project"

    def test_failure_marks_progress_failed_not_left_running(
        self, db: Session, monkeypatch
    ) -> None:
        """Background worker: if progress is not closed on error, the UI spins forever."""
        project = _project(db, count=1)
        service.start_render(db, 1, project.id)

        def boom(operations, output_path):
            raise RuntimeError("ffmpeg sập")

        monkeypatch.setattr(service.ffmpeg, "render_timeline", boom)

        service.render_worker(project.id, 1)

        entry = next(
            t
            for t in progress_service.snapshot()
            if t.subject_type == "project" and t.video_id == project.id
        )
        assert entry.stage == "failed"
        assert "ffmpeg sập" in entry.error
        assert service.is_rendering(project.id) is False


class TestUniformDimensions:
    def test_raises_with_scene_numbers_when_clips_differ(
        self, db: Session, monkeypatch
    ) -> None:
        """A size mismatch makes xfade output a broken file without an error, so it must
        be blocked early and say clearly which scene mismatches."""
        project = _project(db, count=2)
        scenes = project_service.list_scenes(db, project.id)
        for index, scene in enumerate(scenes):
            asset = ai_generation_service._save_asset(
                db,
                1,
                asset_type=ai_generation_service.GeneratedAssetType.VIDEO,
                file_path=ai_generation_service.output_dir() / f"c{index}.mp4",
                prompt="p",
                provider="ffmpeg",
                model="m",
                cost_usd=0.0,
                request_hash=None,
            )
            Path(asset.file_path).write_bytes(b"fake")
            scene.clip_asset_id = asset.id
        db.commit()

        sizes = iter([(1280, 720), (1920, 1080)])
        monkeypatch.setattr(
            service.ffmpeg, "get_video_dimensions", lambda path: next(sizes)
        )

        with pytest.raises(service.ProjectRenderError, match="lệch kích thước"):
            service._ensure_uniform_dimensions(db, project.id)
