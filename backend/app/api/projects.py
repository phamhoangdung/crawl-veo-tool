from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.mcp_auth import require_scope
from app.core.db import get_db
from app.models.generation_project import GenerationProject, Scene
from app.schemas.generation_project import (
    CanvasSaveRequest,
    ExportToLibraryResponse,
    ProjectCostEstimate,
    ProjectCreateRequest,
    ProjectDetailRead,
    ProjectRead,
    RenderStartResponse,
    ReorderRequest,
    SceneCreateRequest,
    SceneRead,
    SceneUpdateRequest,
)
from app.services import (
    ai_generation_service,
    asset_service,
    cost_service,
    project_render_service,
    project_service,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# MVP: 1 user cố định — cùng quy ước với app/api/api_keys.py.
_DEFAULT_USER_ID = 1


def _to_scene_read(scene: Scene) -> SceneRead:
    return SceneRead(
        id=scene.id,
        project_id=scene.project_id,
        order_index=scene.order_index,
        prompt=scene.prompt,
        keyframe_asset_id=scene.keyframe_asset_id,
        clip_asset_id=scene.clip_asset_id,
        duration_seconds=scene.duration_seconds,
        transition_in=scene.transition_in,
        transition_duration=scene.transition_duration,
        chain_from_previous=scene.chain_from_previous,
        use_ken_burns=scene.use_ken_burns,
        ken_burns_motion=scene.ken_burns_motion,
        canvas_x=scene.canvas_x,
        canvas_y=scene.canvas_y,
        status=scene.status,
        error=scene.error,
    )


def _to_project_read(project: GenerationProject) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        title=project.title,
        output_prefix=project.output_prefix,
        rendered_path=project.rendered_path,
        canvas_viewport=project.canvas_viewport,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _require_project(db: Session, project_id: int) -> GenerationProject:
    project = project_service.get_project(db, _DEFAULT_USER_ID, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án")
    return project


@router.get("", response_model=list[ProjectRead], dependencies=[Depends(require_scope("assets:read"))])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    return [_to_project_read(p) for p in project_service.list_projects(db, _DEFAULT_USER_ID)]


@router.post("", response_model=ProjectDetailRead, dependencies=[Depends(require_scope("assets:write"))])
def create_project(
    payload: ProjectCreateRequest, db: Session = Depends(get_db)
) -> ProjectDetailRead:
    try:
        project = project_service.create_project(
            db, _DEFAULT_USER_ID, payload.title, scene_prompts=payload.scene_prompts
        )
    except project_service.ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _detail(db, project)


def _detail(db: Session, project: GenerationProject) -> ProjectDetailRead:
    scenes = project_service.list_scenes(db, project.id)
    return ProjectDetailRead(
        **_to_project_read(project).model_dump(),
        scenes=[_to_scene_read(s) for s in scenes],
        is_rendering=project_render_service.is_rendering(project.id),
    )


@router.get("/{project_id}", response_model=ProjectDetailRead, dependencies=[Depends(require_scope("assets:read"))])
def get_project(project_id: int, db: Session = Depends(get_db)) -> ProjectDetailRead:
    return _detail(db, _require_project(db, project_id))


@router.delete("/{project_id}", status_code=204, dependencies=[Depends(require_scope("assets:write"))])
def delete_project(project_id: int, db: Session = Depends(get_db)) -> None:
    if not project_service.delete_project(db, _DEFAULT_USER_ID, project_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy dự án")


@router.post("/{project_id}/scenes", response_model=SceneRead, dependencies=[Depends(require_scope("assets:write"))])
def add_scene(
    project_id: int, payload: SceneCreateRequest, db: Session = Depends(get_db)
) -> SceneRead:
    _require_project(db, project_id)
    try:
        scene = project_service.add_scene(
            db,
            _DEFAULT_USER_ID,
            project_id,
            prompt=payload.prompt,
            after_scene_id=payload.after_scene_id,
        )
    except project_service.ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_scene_read(scene)


@router.patch("/scenes/{scene_id}", response_model=SceneRead, dependencies=[Depends(require_scope("assets:write"))])
def update_scene(
    scene_id: int, payload: SceneUpdateRequest, db: Session = Depends(get_db)
) -> SceneRead:
    try:
        scene = project_service.update_scene(
            db, _DEFAULT_USER_ID, scene_id, **payload.model_dump(exclude_none=True)
        )
    except project_service.ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_scene_read(scene)


@router.delete("/scenes/{scene_id}", status_code=204, dependencies=[Depends(require_scope("assets:write"))])
def delete_scene(scene_id: int, db: Session = Depends(get_db)) -> None:
    try:
        project_service.delete_scene(db, _DEFAULT_USER_ID, scene_id)
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/reorder", response_model=list[SceneRead], dependencies=[Depends(require_scope("assets:write"))])
def reorder_scenes(
    project_id: int, payload: ReorderRequest, db: Session = Depends(get_db)
) -> list[SceneRead]:
    _require_project(db, project_id)
    try:
        scenes = project_service.reorder_scenes(
            db, _DEFAULT_USER_ID, project_id, payload.scene_ids
        )
    except project_service.ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [_to_scene_read(s) for s in scenes]


@router.put("/{project_id}/canvas", status_code=204, dependencies=[Depends(require_scope("assets:write"))])
def save_canvas(
    project_id: int, payload: CanvasSaveRequest, db: Session = Depends(get_db)
) -> None:
    _require_project(db, project_id)
    project_service.save_canvas(
        db,
        _DEFAULT_USER_ID,
        project_id,
        positions={p.scene_id: (p.x, p.y) for p in payload.positions},
        viewport=payload.viewport,
    )


@router.post("/scenes/{scene_id}/generate", response_model=SceneRead, dependencies=[Depends(require_scope("gen:write"))])
async def generate_scene(
    scene_id: int, confirm_expensive: bool = False, db: Session = Depends(get_db)
) -> SceneRead:
    try:
        scene = await project_service.generate_scene(
            db, _DEFAULT_USER_ID, scene_id, confirm_expensive=confirm_expensive
        )
    except ai_generation_service.CostThresholdExceededError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except cost_service.MonthlyBudgetExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except project_service.ProjectValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except project_service.ProjectError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_scene_read(scene)


@router.get(
    "/{project_id}/cost-estimate",
    response_model=ProjectCostEstimate,
    dependencies=[Depends(require_scope("cost:read"))],
)
def get_project_cost_estimate(
    project_id: int, db: Session = Depends(get_db)
) -> ProjectCostEstimate:
    project = _require_project(db, project_id)
    return ProjectCostEstimate(**project_service.estimate_project_cost(db, project))


@router.post("/{project_id}/render", response_model=RenderStartResponse, dependencies=[Depends(require_scope("gen:write"))])
def start_render(
    project_id: int, background: BackgroundTasks, db: Session = Depends(get_db)
) -> RenderStartResponse:
    """Nhận job rồi trả ngay — dựng 5 cảnh mất vài phút, không giữ request."""
    try:
        project_render_service.start_render(db, _DEFAULT_USER_ID, project_id)
    except project_render_service.ProjectRenderError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    background.add_task(project_render_service.render_worker, project_id, _DEFAULT_USER_ID)
    return RenderStartResponse(
        project_id=project_id,
        message="Đã nhận job dựng video — theo dõi tiến độ ở thanh tác vụ.",
    )


@router.post(
    "/{project_id}/export-to-library",
    response_model=ExportToLibraryResponse,
    dependencies=[Depends(require_scope("assets:write"))],
)
def export_project_to_library(
    project_id: int, db: Session = Depends(get_db)
) -> ExportToLibraryResponse:
    """Đưa video đã dựng vào kho dùng chung để mở trong Timeline Editor."""
    try:
        imported = project_render_service.export_to_asset_library(
            db, _DEFAULT_USER_ID, project_id
        )
    except project_render_service.ProjectRenderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except asset_service.AssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExportToLibraryResponse(
        asset_id=imported.id, name=imported.name, kind=imported.kind
    )


@router.get("/{project_id}/output")
def get_project_output(project_id: int, db: Session = Depends(get_db)) -> FileResponse:
    project = _require_project(db, project_id)
    if not project.rendered_path:
        raise HTTPException(status_code=404, detail="Dự án chưa được dựng")
    path = Path(project.rendered_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File video đã bị xoá khỏi ổ đĩa")
    return FileResponse(path, filename=f"{project.output_prefix}.mp4")
