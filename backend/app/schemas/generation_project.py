from datetime import datetime

from pydantic import BaseModel, Field

from app.models.generation_project import SceneStatus


class SceneRead(BaseModel):
    id: int
    project_id: int
    order_index: int
    prompt: str
    keyframe_asset_id: int | None
    clip_asset_id: int | None
    duration_seconds: float
    transition_in: str
    transition_duration: float
    chain_from_previous: bool
    use_ken_burns: bool
    ken_burns_motion: str
    canvas_x: float
    canvas_y: float
    status: SceneStatus
    error: str | None


class ProjectRead(BaseModel):
    id: int
    title: str
    output_prefix: str
    rendered_path: str | None
    canvas_viewport: dict | None
    created_at: datetime
    updated_at: datetime


class ProjectDetailRead(ProjectRead):
    scenes: list[SceneRead]
    is_rendering: bool


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=1)
    scene_prompts: list[str] | None = None


class SceneCreateRequest(BaseModel):
    prompt: str = ""
    after_scene_id: int | None = None


class SceneUpdateRequest(BaseModel):
    """Every field is optional: partial PATCH, send only what changes."""

    prompt: str | None = None
    duration_seconds: float | None = Field(default=None, gt=0, le=60)
    transition_in: str | None = None
    transition_duration: float | None = Field(default=None, gt=0, le=5)
    chain_from_previous: bool | None = None
    use_ken_burns: bool | None = None
    ken_burns_motion: str | None = None


class ReorderRequest(BaseModel):
    scene_ids: list[int]


class NodePosition(BaseModel):
    scene_id: int
    x: float
    y: float


class CanvasSaveRequest(BaseModel):
    positions: list[NodePosition] = Field(default_factory=list)
    viewport: dict | None = None


class RenderStartResponse(BaseModel):
    project_id: int
    message: str


class ExportToLibraryResponse(BaseModel):
    """`asset_id` is the id in the shared library (a string), unlike the project id (a number)."""

    asset_id: str
    name: str
    kind: str


class ProjectCostEstimate(BaseModel):
    total_scenes: int
    # Only scenes without a clip cost money — already-generated scenes are reused for free.
    pending_scenes: int
    # The scene uses a still image + camera motion (ffmpeg) — no cost.
    free_scenes: int
    image_cost_usd: float
    video_cost_usd: float
    total_cost_usd: float
    warning: str | None
