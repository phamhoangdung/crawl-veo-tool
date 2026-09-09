from datetime import datetime

from pydantic import BaseModel, Field

from app.models.generated_asset import GeneratedAssetType


class CharacterReferenceRead(BaseModel):
    id: int
    name: str
    description: str | None
    image_count: int
    created_at: datetime


class GeneratedAssetRead(BaseModel):
    id: int
    type: GeneratedAssetType
    prompt: str
    provider: str
    model: str
    duration_seconds: float | None
    cost_estimate_usd: float
    source_character_ref_id: int | None
    source_keyframe_asset_id: int | None
    output_prefix: str | None
    sequence_no: int | None
    created_at: datetime


class GenerationResponse(BaseModel):
    asset: GeneratedAssetRead
    from_cache: bool


class KeyframeRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str | None = None
    character_ref_id: int | None = None
    output_prefix: str | None = None
    confirm_expensive: bool = False


class VideoClipRequest(BaseModel):
    prompt: str = Field(min_length=1)
    keyframe_start_asset_id: int
    keyframe_end_asset_id: int | None = None
    model: str | None = None
    duration_seconds: float = Field(default=5.0, gt=0, le=60)
    output_prefix: str | None = None
    confirm_expensive: bool = False


class KenBurnsRequest(BaseModel):
    keyframe_asset_id: int
    duration_seconds: float = Field(default=5.0, gt=0, le=60)
    motion: str = "zoom_in"
    output_prefix: str | None = None


class CostEstimateResponse(BaseModel):
    estimated_cost_usd: float
    model: str
    warning: str | None = None


class BudgetStatusResponse(BaseModel):
    spent_this_month_usd: float
    monthly_budget_usd: float
    remaining_usd: float


class GenerationModeResponse(BaseModel):
    mode: str
    is_fake: bool


class ExportToLibraryResponse(BaseModel):
    """Kết quả đưa asset vào kho dùng chung — `asset_id` là id trong kho đó
    (chuỗi), khác id của `GeneratedAsset` (số)."""

    asset_id: str
    name: str
    kind: str
