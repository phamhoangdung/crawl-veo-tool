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
    """Dùng file tạm chứ không phải `sqlite://` in-memory: `render_worker` chạy
    nền nên tự mở `SessionLocal()` riêng (đúng, vì session của request đã đóng),
    mà in-memory DB không chia sẻ được sang session khác."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{tmp}/test.db")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine)
        # Worker phải nhìn thấy cùng DB với test.
        monkeypatch.setattr(service, "SessionLocal", factory)

        session = factory()
        session.add(User(id=1))
        session.commit()
        yield session
        session.close()


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
        # Clip giả chỉ là vài byte, không phải video thật — ffmpeg thật sẽ fail
        # khi trích frame từ nó, nên phải stub cả bước nối frame.
        Path(output_path).write_bytes(_PNG)

    def fake_render(operations, output_path):
        calls["render"] += 1
        calls["operations"] = operations
        Path(output_path).write_bytes(b"rendered-mp4")

    monkeypatch.setattr(ai_generation_service.fake_adapter, "generate_image", fake_image)
    monkeypatch.setattr(ai_generation_service.ffmpeg, "make_ken_burns_clip", fake_ken_burns)
    monkeypatch.setattr(ai_generation_service.ffmpeg, "extract_last_frame", fake_last_frame)
    monkeypatch.setattr(service.ffmpeg, "render_timeline", fake_render)
    # Clip giả không đọc được kích thước, còn kiểm tra đồng nhất đã có test riêng
    # ở TestUniformDimensions (test đó KHÔNG dùng fixture này).
    monkeypatch.setattr(service.ffmpeg, "get_video_dimensions", lambda path: (1280, 720))
    return calls


@pytest.fixture(autouse=True)
def clean_progress():
    """`progress_service._active` là dict ở module nên sống xuyên test, còn mỗi
    test lại dùng DB in-memory mới nên project id luôn bắt đầu từ 1 — không dọn
    sạch thì entry "đang chạy" của test trước làm test sau tưởng đang render.
    `clear_finished()` không đủ vì nó cố ý giữ lại entry chưa kết thúc."""
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
        """UI phải thấy job ngay khi request trả về, không đợi worker chạy."""
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
        """Tiến độ phải gắn subject_type='project' — nếu nhét vào ô video thì
        mọi query theo video_id sẽ lặng lẽ trả sai."""
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
        """Worker chạy nền: nếu không đóng tiến độ khi lỗi, UI sẽ quay mãi."""
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
        """Lệch kích thước làm xfade xuất file hỏng mà không báo lỗi, nên phải
        chặn sớm và nói rõ cảnh nào lệch."""
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
