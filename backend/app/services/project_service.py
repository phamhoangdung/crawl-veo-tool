"""Dự án video nhiều cảnh (Phase 15).

Giải quyết nút thắt của AI Studio (Phase 14): mỗi clip sinh ra là một đơn vị rời,
không có thứ tự cảnh và không ghép được thành video hoàn chỉnh.

Ràng buộc cố ý: chuỗi cảnh **tuyến tính**, không phân nhánh. `ffmpeg.render_timeline`
nhận đúng 1 track video, nên cho phép nhánh sẽ dựng được graph mà renderer không
diễn đạt nổi. Ép tuyến tính ở đây là tính năng, không phải hạn chế.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.generated_asset import GeneratedAsset
from app.models.generation_project import GenerationProject, Scene, SceneStatus
from app.services import ai_generation_service, cost_service, timeline_service

logger = logging.getLogger(__name__)

_VALID_TRANSITIONS = ("cut", "fade")


class ProjectError(RuntimeError):
    pass


class ProjectValidationError(ProjectError):
    pass


def create_project(
    db: Session, user_id: int, title: str, *, scene_prompts: list[str] | None = None
) -> GenerationProject:
    cleaned_title = title.strip()
    if not cleaned_title:
        raise ProjectValidationError("Dự án cần có tên.")

    project = GenerationProject(
        user_id=user_id, title=cleaned_title, output_prefix="pending"
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # Cần id trước mới đặt được prefix — dùng id để 2 dự án không đè tên file nhau.
    project.output_prefix = f"project_{project.id}"
    db.commit()

    for index, prompt in enumerate(scene_prompts or []):
        db.add(
            Scene(
                project_id=project.id,
                order_index=index,
                prompt=prompt,
                canvas_x=index * 320.0,
                canvas_y=0.0,
                # Cảnh đầu không có gì để nối vào.
                chain_from_previous=index > 0,
            )
        )
    db.commit()
    db.refresh(project)
    logger.info("Đã tạo dự án '%s' với %d cảnh", cleaned_title, len(scene_prompts or []))
    return project


def get_project(db: Session, user_id: int, project_id: int) -> GenerationProject | None:
    return db.execute(
        select(GenerationProject).where(
            GenerationProject.id == project_id, GenerationProject.user_id == user_id
        )
    ).scalar_one_or_none()


def list_projects(db: Session, user_id: int) -> list[GenerationProject]:
    return list(
        db.execute(
            select(GenerationProject)
            .where(GenerationProject.user_id == user_id)
            .order_by(GenerationProject.updated_at.desc())
        ).scalars()
    )


def list_scenes(db: Session, project_id: int) -> list[Scene]:
    return list(
        db.execute(
            select(Scene)
            .where(Scene.project_id == project_id)
            .order_by(Scene.order_index)
        ).scalars()
    )


def delete_project(db: Session, user_id: int, project_id: int) -> bool:
    project = get_project(db, user_id, project_id)
    if project is None:
        return False
    for scene in list_scenes(db, project_id):
        db.delete(scene)
    db.delete(project)
    db.commit()
    return True


def _require_project(db: Session, user_id: int, project_id: int) -> GenerationProject:
    project = get_project(db, user_id, project_id)
    if project is None:
        raise ProjectError(f"Không tìm thấy dự án id={project_id}")
    return project


def get_scene(db: Session, user_id: int, scene_id: int) -> Scene | None:
    scene = db.get(Scene, scene_id)
    if scene is None:
        return None
    # Kiểm chủ sở hữu qua dự án — Scene không giữ user_id riêng.
    if get_project(db, user_id, scene.project_id) is None:
        return None
    return scene


def _require_scene(db: Session, user_id: int, scene_id: int) -> Scene:
    scene = get_scene(db, user_id, scene_id)
    if scene is None:
        raise ProjectError(f"Không tìm thấy cảnh id={scene_id}")
    return scene


def add_scene(
    db: Session, user_id: int, project_id: int, *, prompt: str = "", after_scene_id: int | None = None
) -> Scene:
    _require_project(db, user_id, project_id)
    scenes = list_scenes(db, project_id)

    if after_scene_id is None:
        position = len(scenes)
    else:
        previous = _require_scene(db, user_id, after_scene_id)
        position = previous.order_index + 1
        for scene in scenes:
            if scene.order_index >= position:
                scene.order_index += 1

    scene = Scene(
        project_id=project_id,
        order_index=position,
        prompt=prompt,
        canvas_x=position * 320.0,
        canvas_y=0.0,
        chain_from_previous=position > 0,
    )
    db.add(scene)
    db.commit()
    db.refresh(scene)
    return scene


def update_scene(db: Session, user_id: int, scene_id: int, **patch) -> Scene:
    scene = _require_scene(db, user_id, scene_id)

    transition = patch.get("transition_in")
    if transition is not None and transition not in _VALID_TRANSITIONS:
        raise ProjectValidationError(
            f"Hiệu ứng chuyển cảnh không hợp lệ: {transition!r} (chỉ {_VALID_TRANSITIONS})"
        )
    duration = patch.get("duration_seconds")
    if duration is not None and duration <= 0:
        raise ProjectValidationError("Thời lượng cảnh phải lớn hơn 0.")

    for field, value in patch.items():
        if value is not None and hasattr(scene, field):
            setattr(scene, field, value)
    db.commit()
    db.refresh(scene)
    return scene


def delete_scene(db: Session, user_id: int, scene_id: int) -> None:
    scene = _require_scene(db, user_id, scene_id)
    project_id = scene.project_id
    db.delete(scene)
    db.commit()

    # Đánh lại order_index liên tục 0..n-1, nếu không thứ tự sẽ có lỗ và
    # `build_operations` xuất clip sai thứ tự.
    for index, remaining in enumerate(list_scenes(db, project_id)):
        remaining.order_index = index
        remaining.chain_from_previous = remaining.chain_from_previous and index > 0
    db.commit()


def reorder_scenes(
    db: Session, user_id: int, project_id: int, scene_ids: list[int]
) -> list[Scene]:
    _require_project(db, user_id, project_id)
    scenes = {s.id: s for s in list_scenes(db, project_id)}

    if set(scene_ids) != set(scenes):
        raise ProjectValidationError(
            "Danh sách sắp xếp phải chứa đúng và đủ các cảnh của dự án."
        )

    for index, scene_id in enumerate(scene_ids):
        scenes[scene_id].order_index = index
    db.commit()
    return list_scenes(db, project_id)


def save_canvas(
    db: Session,
    user_id: int,
    project_id: int,
    *,
    positions: dict[int, tuple[float, float]] | None = None,
    viewport: dict | None = None,
) -> None:
    project = _require_project(db, user_id, project_id)
    if viewport is not None:
        project.canvas_viewport = viewport

    if positions:
        scenes = {s.id: s for s in list_scenes(db, project_id)}
        for scene_id, (x, y) in positions.items():
            scene = scenes.get(scene_id)
            if scene is not None:
                scene.canvas_x, scene.canvas_y = x, y
    db.commit()


def _resolve_start_keyframe(
    db: Session, user_id: int, scene: Scene, previous: Scene | None
) -> int | None:
    """Keyframe mở đầu cảnh này khi bật nối frame.

    Thứ tự ưu tiên: khung cuối clip cảnh trước → keyframe cảnh trước → không có
    (phía gọi sẽ sinh mới từ prompt).
    """
    if not scene.chain_from_previous or previous is None:
        return None

    if previous.clip_asset_id is not None:
        chained = ai_generation_service.extract_last_frame_asset(
            db, user_id, clip_asset_id=previous.clip_asset_id
        )
        return chained.asset.id
    return previous.keyframe_asset_id


async def generate_scene(
    db: Session, user_id: int, scene_id: int, *, confirm_expensive: bool = False
) -> Scene:
    """Sinh keyframe (nếu chưa có) rồi tạo clip cho 1 cảnh."""
    scene = _require_scene(db, user_id, scene_id)
    project = _require_project(db, user_id, scene.project_id)
    scenes = list_scenes(db, scene.project_id)
    previous = next(
        (s for s in scenes if s.order_index == scene.order_index - 1), None
    )

    try:
        if scene.keyframe_asset_id is None:
            chained_id = _resolve_start_keyframe(db, user_id, scene, previous)
            if chained_id is not None:
                scene.keyframe_asset_id = chained_id
            else:
                if not scene.prompt.strip():
                    raise ProjectValidationError(
                        f"Cảnh {scene.order_index + 1} chưa có prompt và không nối được "
                        "frame từ cảnh trước — nhập prompt trước khi sinh."
                    )
                keyframe = await ai_generation_service.generate_keyframe(
                    db,
                    user_id,
                    scene.prompt,
                    output_prefix=project.output_prefix,
                    confirm_expensive=confirm_expensive,
                )
                scene.keyframe_asset_id = keyframe.asset.id
            scene.status = SceneStatus.KEYFRAME_READY
            db.commit()

        if scene.clip_asset_id is None:
            if scene.use_ken_burns:
                clip = ai_generation_service.make_ken_burns_clip(
                    db,
                    user_id,
                    keyframe_asset_id=scene.keyframe_asset_id,
                    duration_seconds=scene.duration_seconds,
                    motion=scene.ken_burns_motion,
                    output_prefix=project.output_prefix,
                )
            else:
                clip = await ai_generation_service.generate_video_clip(
                    db,
                    user_id,
                    scene.prompt,
                    keyframe_start_asset_id=scene.keyframe_asset_id,
                    duration_seconds=scene.duration_seconds,
                    output_prefix=project.output_prefix,
                    confirm_expensive=confirm_expensive,
                )
            scene.clip_asset_id = clip.asset.id
            scene.status = SceneStatus.CLIP_READY
            scene.error = None
            db.commit()
    except Exception as exc:
        # Ghi lỗi vào cảnh để UI chỉ đúng cảnh nào hỏng, rồi raise tiếp cho
        # phía gọi xử lý (worker render cần biết để dừng).
        scene.status = SceneStatus.FAILED
        scene.error = str(exc)[:500]
        db.commit()
        raise

    db.refresh(scene)
    return scene


def estimate_project_cost(db: Session, project: GenerationProject) -> dict:
    """Ước tính chi phí dựng cả dự án — chỉ tính cảnh CHƯA có clip.

    Cảnh đã sinh rồi thì bấm dựng lại không tốn thêm (clip tái dùng), nên gộp
    chúng vào ước tính sẽ doạ người dùng bằng con số không có thật.
    """
    scenes = list_scenes(db, project.id)
    pending = [s for s in scenes if s.clip_asset_id is None]

    image_cost = 0.0
    video_cost = 0.0
    free_scenes = 0

    for scene in pending:
        # Nối frame lấy khung cuối clip cảnh trước (ffmpeg, miễn phí) nên chỉ
        # cảnh phải sinh keyframe mới mới tốn tiền ảnh.
        if scene.keyframe_asset_id is None and not scene.chain_from_previous:
            image_cost += cost_service.estimate_image_cost(
                ai_generation_service.DEFAULT_IMAGE_MODEL
            )

        if scene.use_ken_burns:
            free_scenes += 1
        else:
            video_cost += cost_service.estimate_video_cost(
                ai_generation_service.DEFAULT_VIDEO_MODEL, scene.duration_seconds
            )

    total = round(image_cost + video_cost, 4)
    return {
        "total_scenes": len(scenes),
        "pending_scenes": len(pending),
        "free_scenes": free_scenes,
        "image_cost_usd": round(image_cost, 4),
        "video_cost_usd": round(video_cost, 4),
        "total_cost_usd": total,
        "warning": (
            f"Dựng dự án này ước tính ${total:.2f} — kiểm tra lại trước khi chạy."
            if total > 1.0
            else None
        ),
    }


def build_operations(db: Session, project: GenerationProject) -> dict:
    """Dựng cấu trúc timeline từ các cảnh, theo shape `ffmpeg.render_timeline`.

    Chỉ 1 track video, các clip nối tiếp theo `order_index` — đúng ràng buộc
    tuyến tính. Transition lấy từ cảnh đích (cạnh đi vào cảnh đó).
    """
    scenes = list_scenes(db, project.id)
    if not scenes:
        raise ProjectValidationError("Dự án chưa có cảnh nào.")

    missing = [s.order_index + 1 for s in scenes if s.clip_asset_id is None]
    if missing:
        raise ProjectValidationError(
            f"Các cảnh sau chưa có clip: {missing}. Sinh clip trước khi ghép."
        )

    clips: list[dict] = []
    for position, scene in enumerate(scenes):
        asset = db.get(GeneratedAsset, scene.clip_asset_id)
        if asset is None:
            raise ProjectValidationError(
                f"Cảnh {scene.order_index + 1} trỏ tới clip không còn tồn tại."
            )

        clip: dict = {
            "source": asset.file_path,
            "start": 0.0,
            "end": asset.duration_seconds or scene.duration_seconds,
        }
        # Cảnh đầu không có gì phía trước để chuyển cảnh từ đó.
        if position > 0:
            clip["transition_in"] = scene.transition_in
            if scene.transition_in == "fade":
                clip["transition_duration"] = scene.transition_duration
        clips.append(clip)

    operations = {"tracks": [{"type": "video", "clips": clips}]}
    timeline_service.validate_operations(operations)
    return operations
