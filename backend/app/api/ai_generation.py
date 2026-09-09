from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.adapters.falai.errors import PromptBlockedError
from app.adapters.provider_errors import ProviderQuotaExceededError
from app.api.mcp_auth import require_scope
from app.core.db import get_db
from app.models.character_reference import CharacterReference
from app.models.generated_asset import GeneratedAsset, GeneratedAssetType
from app.schemas.ai_generation import (
    BudgetStatusResponse,
    CharacterReferenceRead,
    CostEstimateResponse,
    ExportToLibraryResponse,
    GeneratedAssetRead,
    GenerationModeResponse,
    GenerationResponse,
    KenBurnsRequest,
    KeyframeRequest,
    VideoClipRequest,
)
from app.services import (
    ai_generation_service,
    asset_service,
    character_reference_service,
    cost_service,
)

router = APIRouter(prefix="/api/ai-studio", tags=["ai-studio"])

# MVP: 1 user cố định — cùng quy ước với app/api/api_keys.py.
_DEFAULT_USER_ID = 1


def _to_reference_read(record: CharacterReference) -> CharacterReferenceRead:
    return CharacterReferenceRead(
        id=record.id,
        name=record.name,
        description=record.description,
        image_count=len(record.file_paths),
        created_at=record.created_at,
    )


def _to_asset_read(record: GeneratedAsset) -> GeneratedAssetRead:
    return GeneratedAssetRead(
        id=record.id,
        type=record.type,
        prompt=record.prompt,
        provider=record.provider,
        model=record.model,
        duration_seconds=record.duration_seconds,
        cost_estimate_usd=record.cost_estimate_usd,
        source_character_ref_id=record.source_character_ref_id,
        source_keyframe_asset_id=record.source_keyframe_asset_id,
        output_prefix=record.output_prefix,
        sequence_no=record.sequence_no,
        created_at=record.created_at,
    )


def _to_generation_response(result: ai_generation_service.GenerationResult) -> GenerationResponse:
    return GenerationResponse(asset=_to_asset_read(result.asset), from_cache=result.from_cache)


@router.get("/mode", response_model=GenerationModeResponse)
def get_mode() -> GenerationModeResponse:
    is_fake = ai_generation_service.is_fake_mode()
    return GenerationModeResponse(mode="fake" if is_fake else "real", is_fake=is_fake)


@router.get(
    "/budget",
    response_model=BudgetStatusResponse,
    dependencies=[Depends(require_scope("cost:read"))],
)
def get_budget(db: Session = Depends(get_db)) -> BudgetStatusResponse:
    return BudgetStatusResponse(**cost_service.budget_status(db, _DEFAULT_USER_ID))


@router.get(
    "/character-references",
    response_model=list[CharacterReferenceRead],
    dependencies=[Depends(require_scope("assets:read"))],
)
def list_character_references(db: Session = Depends(get_db)) -> list[CharacterReferenceRead]:
    records = character_reference_service.list_references(db, _DEFAULT_USER_ID)
    return [_to_reference_read(r) for r in records]


@router.post(
    "/character-references",
    response_model=CharacterReferenceRead,
    dependencies=[Depends(require_scope("assets:write"))],
)
async def create_character_reference(
    name: str = Form(...),
    description: str | None = Form(None),
    images: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> CharacterReferenceRead:
    payload = [(image.filename or "image.png", await image.read()) for image in images]
    try:
        record = character_reference_service.create_reference(
            db, _DEFAULT_USER_ID, name, payload, description
        )
    except character_reference_service.CharacterReferenceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_reference_read(record)


@router.delete(
    "/character-references/{reference_id}",
    status_code=204,
    dependencies=[Depends(require_scope("assets:write"))],
)
def delete_character_reference(reference_id: int, db: Session = Depends(get_db)) -> None:
    deleted = character_reference_service.delete_reference(db, _DEFAULT_USER_ID, reference_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy bộ ảnh tham chiếu")


@router.get("/assets/{asset_id}/file")
def get_asset_file(asset_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Trả file để frontend xem trước ảnh keyframe / phát video clip."""
    asset = ai_generation_service.get_asset(db, _DEFAULT_USER_ID, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy asset")
    path = Path(asset.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File đã bị xoá khỏi ổ đĩa")
    return FileResponse(path, filename=path.name)


@router.post(
    "/assets/{asset_id}/export-to-library",
    response_model=ExportToLibraryResponse,
    dependencies=[Depends(require_scope("assets:write"))],
)
def export_asset_to_library(
    asset_id: int, db: Session = Depends(get_db)
) -> ExportToLibraryResponse:
    """Đưa clip/ảnh đã sinh vào kho file dùng chung để ghép trong Timeline Editor."""
    try:
        imported = ai_generation_service.export_to_asset_library(db, _DEFAULT_USER_ID, asset_id)
    except ai_generation_service.GenerationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except asset_service.AssetError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExportToLibraryResponse(
        asset_id=imported.id, name=imported.name, kind=imported.kind
    )


@router.get(
    "/assets",
    response_model=list[GeneratedAssetRead],
    dependencies=[Depends(require_scope("jobs:read"))],
)
def list_generated_assets(
    asset_type: GeneratedAssetType | None = Query(None),
    db: Session = Depends(get_db),
) -> list[GeneratedAssetRead]:
    records = ai_generation_service.list_assets(db, _DEFAULT_USER_ID, asset_type)
    return [_to_asset_read(r) for r in records]


@router.get(
    "/cost-estimate",
    response_model=CostEstimateResponse,
    dependencies=[Depends(require_scope("cost:read"))],
)
def get_cost_estimate(
    asset_type: GeneratedAssetType = Query(...),
    model: str | None = Query(None),
    duration_seconds: float = Query(5.0, gt=0, le=60),
    count: int = Query(1, ge=1, le=10),
) -> CostEstimateResponse:
    is_fake = ai_generation_service.is_fake_mode()
    if asset_type is GeneratedAssetType.IMAGE:
        effective = "fake-image" if is_fake else (model or ai_generation_service.DEFAULT_IMAGE_MODEL)
        cost = cost_service.estimate_image_cost(effective, count)
    else:
        effective = "fake-video" if is_fake else (model or ai_generation_service.DEFAULT_VIDEO_MODEL)
        cost = cost_service.estimate_video_cost(effective, duration_seconds)

    warning = (
        f"Ước tính ${cost:.2f} cho một lần sinh — kiểm tra lại trước khi chạy."
        if cost > 1.0
        else None
    )
    return CostEstimateResponse(estimated_cost_usd=cost, model=effective, warning=warning)


@router.post(
    "/generate/keyframe",
    response_model=GenerationResponse,
    dependencies=[Depends(require_scope("gen:write"))],
)
async def generate_keyframe(
    payload: KeyframeRequest, db: Session = Depends(get_db)
) -> GenerationResponse:
    try:
        result = await ai_generation_service.generate_keyframe(
            db,
            _DEFAULT_USER_ID,
            payload.prompt,
            model=payload.model or ai_generation_service.DEFAULT_IMAGE_MODEL,
            character_ref_id=payload.character_ref_id,
            output_prefix=payload.output_prefix,
            confirm_expensive=payload.confirm_expensive,
        )
    except ai_generation_service.CostThresholdExceededError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except cost_service.MonthlyBudgetExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except PromptBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ai_generation_service.GenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_generation_response(result)


@router.post(
    "/generate/video-clip",
    response_model=GenerationResponse,
    dependencies=[Depends(require_scope("gen:write"))],
)
async def generate_video_clip(
    payload: VideoClipRequest, db: Session = Depends(get_db)
) -> GenerationResponse:
    try:
        result = await ai_generation_service.generate_video_clip(
            db,
            _DEFAULT_USER_ID,
            payload.prompt,
            keyframe_start_asset_id=payload.keyframe_start_asset_id,
            keyframe_end_asset_id=payload.keyframe_end_asset_id,
            model=payload.model or ai_generation_service.DEFAULT_VIDEO_MODEL,
            duration_seconds=payload.duration_seconds,
            output_prefix=payload.output_prefix,
            confirm_expensive=payload.confirm_expensive,
        )
    except ai_generation_service.CostThresholdExceededError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except cost_service.MonthlyBudgetExceededError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except PromptBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProviderQuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ai_generation_service.GenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_generation_response(result)


@router.post(
    "/generate/ken-burns",
    response_model=GenerationResponse,
    dependencies=[Depends(require_scope("gen:write"))],
)
def generate_ken_burns(
    payload: KenBurnsRequest, db: Session = Depends(get_db)
) -> GenerationResponse:
    """Đường miễn phí: 1 ảnh tĩnh + chuyển động camera, không gọi API nào."""
    try:
        result = ai_generation_service.make_ken_burns_clip(
            db,
            _DEFAULT_USER_ID,
            keyframe_asset_id=payload.keyframe_asset_id,
            duration_seconds=payload.duration_seconds,
            motion=payload.motion,
            output_prefix=payload.output_prefix,
        )
    except ai_generation_service.GenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_generation_response(result)
