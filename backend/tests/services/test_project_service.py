from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.db import Base
from app.models.generated_asset import GeneratedAssetType
from app.models.generation_project import SceneStatus
from app.models.user import User
from app.services import ai_generation_service
from app.services import character_reference_service as crs
from app.services import project_service as service

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(User(id=1))
    session.commit()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch) -> Path:
    out = tmp_path / "generated"
    refs = tmp_path / "refs"
    out.mkdir()
    refs.mkdir()
    monkeypatch.setattr(ai_generation_service, "output_dir", lambda: out)
    monkeypatch.setattr(crs, "references_dir", lambda: refs)
    return out


@pytest.fixture(autouse=True)
def fake_adapter(monkeypatch) -> dict:
    calls = {"image": 0, "video": 0, "kenburns": 0, "lastframe": 0}

    async def fake_image(prompt, output_path, **kwargs):
        calls["image"] += 1
        Path(output_path).write_bytes(_PNG)

    async def fake_video(prompt, output_path, **kwargs):
        calls["video"] += 1
        Path(output_path).write_bytes(b"fake-mp4")

    def fake_ken_burns(image_path, output_path, **kwargs):
        calls["kenburns"] += 1
        Path(output_path).write_bytes(b"fake-mp4")

    def fake_last_frame(video_path, output_path, **kwargs):
        calls["lastframe"] += 1
        Path(output_path).write_bytes(_PNG)

    monkeypatch.setattr(ai_generation_service.fake_adapter, "generate_image", fake_image)
    monkeypatch.setattr(ai_generation_service.fake_adapter, "generate_video", fake_video)
    monkeypatch.setattr(
        ai_generation_service.ffmpeg, "make_ken_burns_clip", fake_ken_burns
    )
    monkeypatch.setattr(
        ai_generation_service.ffmpeg, "extract_last_frame", fake_last_frame
    )
    return calls


def _project(db: Session, prompts: list[str] | None = None):
    crs.create_reference(db, 1, "nguoique", [("a.png", _PNG)])
    return service.create_project(db, 1, "Dự án thử", scene_prompts=prompts)


class TestCreateProject:
    def test_creates_scenes_in_order_with_prefix_from_id(self, db: Session) -> None:
        project = _project(db, ["cảnh một", "cảnh hai", "cảnh ba"])

        assert project.output_prefix == f"project_{project.id}"
        scenes = service.list_scenes(db, project.id)
        assert [s.order_index for s in scenes] == [0, 1, 2]
        assert [s.prompt for s in scenes] == ["cảnh một", "cảnh hai", "cảnh ba"]

    def test_first_scene_never_chains(self, db: Session) -> None:
        """Cảnh đầu không có gì phía trước để nối frame từ đó."""
        project = _project(db, ["a", "b", "c"])

        scenes = service.list_scenes(db, project.id)
        assert scenes[0].chain_from_previous is False
        assert all(s.chain_from_previous for s in scenes[1:])

    def test_rejects_blank_title(self, db: Session) -> None:
        with pytest.raises(service.ProjectValidationError, match="cần có tên"):
            service.create_project(db, 1, "   ")


class TestSceneOrdering:
    def test_insert_after_shifts_following_scenes(self, db: Session) -> None:
        project = _project(db, ["a", "b", "c"])
        scenes = service.list_scenes(db, project.id)

        service.add_scene(db, 1, project.id, prompt="chèn", after_scene_id=scenes[0].id)

        assert [s.prompt for s in service.list_scenes(db, project.id)] == [
            "a",
            "chèn",
            "b",
            "c",
        ]

    def test_delete_reindexes_without_gaps(self, db: Session) -> None:
        """Có lỗ trong order_index thì build_operations xuất clip sai thứ tự."""
        project = _project(db, ["a", "b", "c"])
        scenes = service.list_scenes(db, project.id)

        service.delete_scene(db, 1, scenes[1].id)

        remaining = service.list_scenes(db, project.id)
        assert [s.order_index for s in remaining] == [0, 1]
        assert [s.prompt for s in remaining] == ["a", "c"]

    def test_reorder_requires_exact_scene_set(self, db: Session) -> None:
        project = _project(db, ["a", "b"])
        scenes = service.list_scenes(db, project.id)

        with pytest.raises(service.ProjectValidationError, match="đúng và đủ"):
            service.reorder_scenes(db, 1, project.id, [scenes[0].id])

    def test_reorder_applies_new_order(self, db: Session) -> None:
        project = _project(db, ["a", "b", "c"])
        scenes = service.list_scenes(db, project.id)

        service.reorder_scenes(
            db, 1, project.id, [scenes[2].id, scenes[0].id, scenes[1].id]
        )

        assert [s.prompt for s in service.list_scenes(db, project.id)] == ["c", "a", "b"]


class TestUpdateScene:
    def test_rejects_unknown_transition(self, db: Session) -> None:
        project = _project(db, ["a"])
        scene = service.list_scenes(db, project.id)[0]

        with pytest.raises(service.ProjectValidationError, match="chuyển cảnh"):
            service.update_scene(db, 1, scene.id, transition_in="wipe")

    def test_rejects_non_positive_duration(self, db: Session) -> None:
        project = _project(db, ["a"])
        scene = service.list_scenes(db, project.id)[0]

        with pytest.raises(service.ProjectValidationError, match="lớn hơn 0"):
            service.update_scene(db, 1, scene.id, duration_seconds=0)


class TestFrameChaining:
    @pytest.mark.asyncio
    async def test_second_scene_chains_from_first_clip(
        self, db: Session, fake_adapter
    ) -> None:
        """Đây là cơ chế thật đằng sau "đường nối" trên canvas: khung cuối cảnh
        trước thành keyframe cảnh sau, để nhân vật không bị trôi."""
        project = _project(db, ["@nguoique cảnh một", "@nguoique cảnh hai"])
        scenes = service.list_scenes(db, project.id)

        first = await service.generate_scene(db, 1, scenes[0].id)
        second = await service.generate_scene(db, 1, scenes[1].id)

        chained = ai_generation_service.get_asset(db, 1, second.keyframe_asset_id)
        assert chained.type is GeneratedAssetType.IMAGE
        assert chained.source_keyframe_asset_id == first.clip_asset_id
        assert fake_adapter["lastframe"] == 1
        # Cảnh 2 KHÔNG sinh keyframe mới từ prompt — đó là điểm của nối frame.
        assert fake_adapter["image"] == 1

    @pytest.mark.asyncio
    async def test_falls_back_to_previous_keyframe_when_no_clip(
        self, db: Session, fake_adapter
    ) -> None:
        project = _project(db, ["@nguoique cảnh một", "@nguoique cảnh hai"])
        scenes = service.list_scenes(db, project.id)
        keyframe = await ai_generation_service.generate_keyframe(db, 1, "@nguoique a")
        scenes[0].keyframe_asset_id = keyframe.asset.id
        db.commit()

        resolved = service._resolve_start_keyframe(db, 1, scenes[1], scenes[0])

        assert resolved == keyframe.asset.id
        assert fake_adapter["lastframe"] == 0

    @pytest.mark.asyncio
    async def test_no_chaining_generates_fresh_keyframe(
        self, db: Session, fake_adapter
    ) -> None:
        project = _project(db, ["@nguoique cảnh một", "@nguoique cảnh hai"])
        scenes = service.list_scenes(db, project.id)
        service.update_scene(db, 1, scenes[1].id, chain_from_previous=False)

        await service.generate_scene(db, 1, scenes[0].id)
        await service.generate_scene(db, 1, scenes[1].id)

        assert fake_adapter["lastframe"] == 0
        assert fake_adapter["image"] == 2


class TestGenerateScene:
    @pytest.mark.asyncio
    async def test_ken_burns_is_default_and_free(self, db: Session, fake_adapter) -> None:
        project = _project(db, ["@nguoique cảnh một"])
        scene = service.list_scenes(db, project.id)[0]

        result = await service.generate_scene(db, 1, scene.id)

        assert result.status is SceneStatus.CLIP_READY
        assert fake_adapter["kenburns"] == 1
        assert fake_adapter["video"] == 0
        clip = ai_generation_service.get_asset(db, 1, result.clip_asset_id)
        assert clip.cost_estimate_usd == 0.0

    @pytest.mark.asyncio
    async def test_ai_video_used_when_ken_burns_disabled(
        self, db: Session, fake_adapter
    ) -> None:
        project = _project(db, ["@nguoique cảnh một"])
        scene = service.list_scenes(db, project.id)[0]
        service.update_scene(db, 1, scene.id, use_ken_burns=False)

        await service.generate_scene(db, 1, scene.id)

        assert fake_adapter["video"] == 1
        assert fake_adapter["kenburns"] == 0

    @pytest.mark.asyncio
    async def test_records_error_on_scene_when_generation_fails(
        self, db: Session, monkeypatch
    ) -> None:
        """UI cần biết cảnh NÀO hỏng, nên lỗi phải ghi vào chính cảnh đó."""
        project = _project(db, ["@nguoique cảnh một"])
        scene = service.list_scenes(db, project.id)[0]

        async def boom(*args, **kwargs):
            raise RuntimeError("provider sập")

        monkeypatch.setattr(ai_generation_service, "generate_keyframe", boom)

        with pytest.raises(RuntimeError):
            await service.generate_scene(db, 1, scene.id)

        db.refresh(scene)
        assert scene.status is SceneStatus.FAILED
        assert "provider sập" in scene.error

    @pytest.mark.asyncio
    async def test_requires_prompt_when_nothing_to_chain(self, db: Session) -> None:
        project = _project(db, [""])
        scene = service.list_scenes(db, project.id)[0]

        with pytest.raises(service.ProjectValidationError, match="chưa có prompt"):
            await service.generate_scene(db, 1, scene.id)


class TestBuildOperations:
    @pytest.mark.asyncio
    async def test_emits_one_video_track_in_scene_order(
        self, db: Session, fake_adapter
    ) -> None:
        project = _project(db, ["@nguoique a", "@nguoique b", "@nguoique c"])
        for scene in service.list_scenes(db, project.id):
            await service.generate_scene(db, 1, scene.id)

        operations = service.build_operations(db, project)

        tracks = operations["tracks"]
        assert len(tracks) == 1
        assert tracks[0]["type"] == "video"
        assert len(tracks[0]["clips"]) == 3

    @pytest.mark.asyncio
    async def test_first_clip_has_no_transition(self, db: Session, fake_adapter) -> None:
        """Cảnh đầu không có gì phía trước để chuyển cảnh từ đó — nếu gán
        transition_in cho nó, xfade sẽ tính offset âm."""
        project = _project(db, ["@nguoique a", "@nguoique b"])
        for scene in service.list_scenes(db, project.id):
            service.update_scene(db, 1, scene.id, transition_in="fade")
            await service.generate_scene(db, 1, scene.id)

        clips = service.build_operations(db, project)["tracks"][0]["clips"]

        assert "transition_in" not in clips[0]
        assert clips[1]["transition_in"] == "fade"
        assert clips[1]["transition_duration"] == 1.0

    def test_rejects_project_without_scenes(self, db: Session) -> None:
        project = _project(db)

        with pytest.raises(service.ProjectValidationError, match="chưa có cảnh"):
            service.build_operations(db, project)

    def test_rejects_when_a_scene_has_no_clip(self, db: Session) -> None:
        project = _project(db, ["a", "b"])

        with pytest.raises(service.ProjectValidationError, match="chưa có clip"):
            service.build_operations(db, project)
