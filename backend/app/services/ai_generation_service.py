"""Sinh ảnh keyframe và video clip bằng AI (Phase 14).

Ba cơ chế kiểm soát chi phí nằm ở đây, vì sinh video đắt hơn dịch/TTS hàng trăm
lần (xem "Chiến lược giảm chi phí" trong phase-14-ai-video-generation.md):

1. Dedupe theo `request_hash` — cùng yêu cầu thì trả asset cũ, không gọi API lại.
2. Hạn mức tháng — chặn trước khi gọi, kể cả khi agent chạy qua MCP.
3. Đường Ken Burns miễn phí — cảnh không cần chuyển động thật thì dùng ffmpeg.
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters import ffmpeg
from app.adapters.falai import client as real_adapter
from app.adapters.falai import fake as fake_adapter
from app.adapters.provider_errors import ProviderQuotaExceededError
from app.core.config import _storage_dir, get_settings
from app.models.generated_asset import GeneratedAsset, GeneratedAssetType
from app.services import (
    api_key_service,
    asset_service,
    character_reference_service,
    cost_service,
)

logger = logging.getLogger(__name__)

PROVIDER_FAKE = "falai-fake"
PROVIDER_FALAI = "falai"
PROVIDER_FALAI = "falai"
PROVIDER_KEN_BURNS = "ffmpeg"

KEN_BURNS_MODEL = "ffmpeg-ken-burns"

DEFAULT_IMAGE_MODEL = "nano-banana"
DEFAULT_VIDEO_MODEL = "kling-3.0"

_PER_CALL_WARNING_USD = 1.0


class GenerationError(RuntimeError):
    pass


class CostThresholdExceededError(RuntimeError):
    """Vượt ngưỡng chi phí cho 1 lần gọi — khác hạn mức tháng: đây là cảnh báo
    người dùng có thể bỏ qua bằng `confirm_expensive=True`, không phải chốt cứng."""

    def __init__(self, estimated_usd: float, threshold_usd: float) -> None:
        super().__init__(
            f"Lần sinh này ước tính ${estimated_usd:.2f}, vượt ngưỡng "
            f"${threshold_usd:.2f} — xác nhận nếu vẫn muốn tiếp tục."
        )
        self.estimated_usd = estimated_usd
        self.threshold_usd = threshold_usd


@dataclass
class GenerationResult:
    asset: GeneratedAsset
    from_cache: bool


def is_fake_mode() -> bool:
    return get_settings().falai_mode != "real"


def output_dir() -> Path:
    path = _storage_dir() / "generated"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _request_hash(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _find_cached(db: Session, user_id: int, request_hash: str) -> GeneratedAsset | None:
    asset = db.execute(
        select(GeneratedAsset)
        .where(
            GeneratedAsset.user_id == user_id,
            GeneratedAsset.request_hash == request_hash,
        )
        .order_by(GeneratedAsset.created_at.desc())
    ).scalars().first()

    # File có thể đã bị dọn (storage_cleanup_service) dù record còn — coi như chưa cache.
    if asset is not None and not Path(asset.file_path).exists():
        return None
    return asset


def _next_sequence_no(db: Session, user_id: int, output_prefix: str | None) -> int | None:
    if not output_prefix:
        return None
    count = len(
        list(
            db.execute(
                select(GeneratedAsset.id).where(
                    GeneratedAsset.user_id == user_id,
                    GeneratedAsset.output_prefix == output_prefix,
                )
            ).scalars()
        )
    )
    return count + 1


def _build_filename(
    asset_type: GeneratedAssetType,
    output_prefix: str | None,
    sequence_no: int | None,
    suffix: str,
) -> str:
    if output_prefix and sequence_no is not None:
        return f"{output_prefix}_{sequence_no:03d}{suffix}"
    return f"{asset_type.value}_{uuid.uuid4().hex[:12]}{suffix}"


def _guard_cost(
    db: Session, user_id: int, estimated_usd: float, confirm_expensive: bool
) -> None:
    cost_service.check_monthly_budget(db, user_id, estimated_usd)
    if estimated_usd > _PER_CALL_WARNING_USD and not confirm_expensive:
        raise CostThresholdExceededError(estimated_usd, _PER_CALL_WARNING_USD)



async def _call_falai_with_pool(db: Session, user_id: int, call) -> None:
    """Gọi fal.ai bằng key lấy từ pool, gặp 429 thì xoay sang key khác (Phase 8).

    `call(api_key)` phải là coroutine tự ghi file kết quả. Cùng khuôn với
    `translate_service.translate_text`, chỉ khác: ở đây KHÔNG có provider free nào
    để fallback — sinh video không có nhà nào cho miễn phí.
    """
    tried_key_ids: set[int] = set()
    last_quota_error: ProviderQuotaExceededError | None = None

    while True:
        picked = api_key_service.pick_decrypted_key(db, user_id, PROVIDER_FALAI)
        if picked is None or picked[0] in tried_key_ids:
            break
        key_id, api_key = picked
        tried_key_ids.add(key_id)
        try:
            await call(api_key)
        except ProviderQuotaExceededError as exc:
            api_key_service.mark_key_result(db, key_id, success=False)
            last_quota_error = exc
            logger.warning("Key fal.ai #%d hết quota, thử key khác trong pool", key_id)
            continue
        api_key_service.mark_key_result(db, key_id, success=True)
        return

    if not tried_key_ids:
        raise GenerationError(
            "Chưa có API key fal.ai nào trong pool. Thêm key ở trang API keys, "
            "hoặc đặt FALAI_MODE=fake để chạy thử không tốn phí."
        )
    if last_quota_error is not None:
        raise last_quota_error
    raise GenerationError("Không gọi được fal.ai bằng key nào trong pool.")


@dataclass
class _Plan:
    """Phần "quyết định" của một lần sinh: dùng lại được gì, tốn bao nhiêu.

    Tách khỏi phần thực thi để chạy được TRƯỚC khi nhận job chạy nền — nếu không,
    cửa kiểm ngưỡng chi phí sẽ nổ bên trong background task, nơi người dùng không
    còn cách nào xác nhận "vẫn muốn chạy". Tức là một cái van an toàn tiền bạc bị
    vô hiệu hoá mà không ai thấy.
    """

    references: list
    effective_model: str
    request_hash: str
    cached: GeneratedAsset | None
    estimated_usd: float


def _plan_keyframe(
    db: Session,
    user_id: int,
    prompt: str,
    *,
    model: str,
    character_ref_id: int | None,
) -> _Plan:
    references, missing = character_reference_service.resolve_mentions(db, user_id, prompt)
    if missing:
        raise GenerationError(
            f"Prompt gọi @{', @'.join(missing)} nhưng chưa có bộ ảnh tham chiếu nào tên vậy."
        )

    if character_ref_id is not None and not any(r.id == character_ref_id for r in references):
        explicit = character_reference_service.get_reference(db, user_id, character_ref_id)
        if explicit is None:
            raise GenerationError(f"Không tìm thấy bộ ảnh tham chiếu id={character_ref_id}")
        references.append(explicit)

    effective_model = "fake-image" if is_fake_mode() else model
    request_hash = _request_hash(
        ["image", prompt, effective_model, *sorted(str(r.id) for r in references)]
    )
    return _Plan(
        references=references,
        effective_model=effective_model,
        request_hash=request_hash,
        cached=_find_cached(db, user_id, request_hash),
        estimated_usd=cost_service.estimate_image_cost(effective_model),
    )


def precheck_keyframe(
    db: Session,
    user_id: int,
    prompt: str,
    *,
    model: str = DEFAULT_IMAGE_MODEL,
    character_ref_id: int | None = None,
    confirm_expensive: bool = False,
) -> None:
    """Chạy đúng các cửa kiểm mà `generate_keyframe` sẽ chạy, nhưng không sinh gì.

    Ném cùng loại lỗi (`CostThresholdExceededError`, `MonthlyBudgetExceededError`,
    `GenerationError`) để endpoint bất đồng bộ trả đúng mã HTTP như bản đồng bộ.
    """
    plan = _plan_keyframe(
        db, user_id, prompt, model=model, character_ref_id=character_ref_id
    )
    if plan.cached is not None:
        return  # dùng lại kết quả cũ thì không tốn gì, không cần hỏi xác nhận
    _guard_cost(db, user_id, plan.estimated_usd, confirm_expensive)


async def generate_keyframe(
    db: Session,
    user_id: int,
    prompt: str,
    *,
    model: str = DEFAULT_IMAGE_MODEL,
    character_ref_id: int | None = None,
    output_prefix: str | None = None,
    confirm_expensive: bool = False,
) -> GenerationResult:
    plan = _plan_keyframe(
        db, user_id, prompt, model=model, character_ref_id=character_ref_id
    )
    references = plan.references
    effective_model = plan.effective_model
    request_hash = plan.request_hash

    if plan.cached is not None:
        logger.info("Dùng lại ảnh đã sinh (hash=%s), không gọi API", request_hash[:12])
        return GenerationResult(asset=plan.cached, from_cache=True)

    estimated = plan.estimated_usd
    _guard_cost(db, user_id, estimated, confirm_expensive)

    sequence_no = _next_sequence_no(db, user_id, output_prefix)
    filename = _build_filename(GeneratedAssetType.IMAGE, output_prefix, sequence_no, ".png")
    target = output_dir() / filename
    reference_paths = [Path(p) for r in references for p in r.file_paths]

    if is_fake_mode():
        await fake_adapter.generate_image(
            prompt, target, reference_images=reference_paths, model=effective_model
        )
        provider = PROVIDER_FAKE
    else:
        await _call_falai_with_pool(
            db,
            user_id,
            lambda api_key: real_adapter.generate_image(
                api_key,
                prompt,
                target,
                reference_images=reference_paths,
                model=effective_model,
            ),
        )
        provider = PROVIDER_FALAI

    return GenerationResult(
        asset=_save_asset(
            db,
            user_id,
            asset_type=GeneratedAssetType.IMAGE,
            file_path=target,
            prompt=prompt,
            provider=provider,
            model=effective_model,
            cost_usd=estimated,
            request_hash=request_hash,
            character_ref_id=references[0].id if references else None,
            output_prefix=output_prefix,
            sequence_no=sequence_no,
        ),
        from_cache=False,
    )


def _plan_video_clip(
    db: Session,
    user_id: int,
    prompt: str,
    *,
    keyframe_start_asset_id: int,
    keyframe_end_asset_id: int | None,
    model: str,
    duration_seconds: float,
) -> tuple[_Plan, GeneratedAsset, GeneratedAsset | None]:
    start_asset = _require_image_asset(db, user_id, keyframe_start_asset_id)
    end_asset = (
        _require_image_asset(db, user_id, keyframe_end_asset_id)
        if keyframe_end_asset_id is not None
        else None
    )

    effective_model = "fake-video" if is_fake_mode() else model
    request_hash = _request_hash(
        [
            "video",
            prompt,
            effective_model,
            str(duration_seconds),
            str(keyframe_start_asset_id),
            str(keyframe_end_asset_id or ""),
        ]
    )
    plan = _Plan(
        references=[],
        effective_model=effective_model,
        request_hash=request_hash,
        cached=_find_cached(db, user_id, request_hash),
        estimated_usd=cost_service.estimate_video_cost(effective_model, duration_seconds),
    )
    return plan, start_asset, end_asset


def precheck_video_clip(
    db: Session,
    user_id: int,
    prompt: str,
    *,
    keyframe_start_asset_id: int,
    keyframe_end_asset_id: int | None = None,
    model: str = DEFAULT_VIDEO_MODEL,
    duration_seconds: float = 5.0,
    confirm_expensive: bool = False,
) -> None:
    """Xem `precheck_keyframe`. Quan trọng hơn ở đây vì sinh video là khâu đắt nhất."""
    plan, _start, _end = _plan_video_clip(
        db,
        user_id,
        prompt,
        keyframe_start_asset_id=keyframe_start_asset_id,
        keyframe_end_asset_id=keyframe_end_asset_id,
        model=model,
        duration_seconds=duration_seconds,
    )
    if plan.cached is not None:
        return
    _guard_cost(db, user_id, plan.estimated_usd, confirm_expensive)


async def generate_video_clip(
    db: Session,
    user_id: int,
    prompt: str,
    *,
    keyframe_start_asset_id: int,
    keyframe_end_asset_id: int | None = None,
    model: str = DEFAULT_VIDEO_MODEL,
    duration_seconds: float = 5.0,
    output_prefix: str | None = None,
    confirm_expensive: bool = False,
) -> GenerationResult:
    plan, start_asset, end_asset = _plan_video_clip(
        db,
        user_id,
        prompt,
        keyframe_start_asset_id=keyframe_start_asset_id,
        keyframe_end_asset_id=keyframe_end_asset_id,
        model=model,
        duration_seconds=duration_seconds,
    )
    effective_model = plan.effective_model
    request_hash = plan.request_hash

    if plan.cached is not None:
        logger.info("Dùng lại video đã sinh (hash=%s), không gọi API", request_hash[:12])
        return GenerationResult(asset=plan.cached, from_cache=True)

    estimated = plan.estimated_usd
    _guard_cost(db, user_id, estimated, confirm_expensive)

    sequence_no = _next_sequence_no(db, user_id, output_prefix)
    filename = _build_filename(GeneratedAssetType.VIDEO, output_prefix, sequence_no, ".mp4")
    target = output_dir() / filename

    if is_fake_mode():
        await fake_adapter.generate_video(
            prompt,
            target,
            keyframe_start=Path(start_asset.file_path),
            keyframe_end=Path(end_asset.file_path) if end_asset else None,
            model=effective_model,
            duration_seconds=duration_seconds,
        )
        provider = PROVIDER_FAKE
    else:
        await _call_falai_with_pool(
            db,
            user_id,
            lambda api_key: real_adapter.generate_video(
                api_key,
                prompt,
                target,
                keyframe_start=Path(start_asset.file_path),
                keyframe_end=Path(end_asset.file_path) if end_asset else None,
                model=effective_model,
                duration_seconds=duration_seconds,
            ),
        )
        provider = PROVIDER_FALAI

    return GenerationResult(
        asset=_save_asset(
            db,
            user_id,
            asset_type=GeneratedAssetType.VIDEO,
            file_path=target,
            prompt=prompt,
            provider=provider,
            model=effective_model,
            cost_usd=estimated,
            request_hash=request_hash,
            keyframe_asset_id=start_asset.id,
            duration_seconds=duration_seconds,
            output_prefix=output_prefix,
            sequence_no=sequence_no,
        ),
        from_cache=False,
    )


def make_ken_burns_clip(
    db: Session,
    user_id: int,
    *,
    keyframe_asset_id: int,
    duration_seconds: float = 5.0,
    motion: str = "zoom_in",
    output_prefix: str | None = None,
) -> GenerationResult:
    """Đường miễn phí thay cho sinh video AI: 1 ảnh tĩnh + chuyển động camera.

    Không cần dedupe/hạn mức vì chi phí bằng 0 — nhưng vẫn lưu `GeneratedAsset`
    để clip dùng được ở thư viện video nền và timeline editor như clip AI.
    """
    image_asset = _require_image_asset(db, user_id, keyframe_asset_id)

    sequence_no = _next_sequence_no(db, user_id, output_prefix)
    filename = _build_filename(GeneratedAssetType.VIDEO, output_prefix, sequence_no, ".mp4")
    target = output_dir() / filename

    ffmpeg.make_ken_burns_clip(
        Path(image_asset.file_path),
        target,
        duration_seconds=duration_seconds,
        motion=motion,
    )

    return GenerationResult(
        asset=_save_asset(
            db,
            user_id,
            asset_type=GeneratedAssetType.VIDEO,
            file_path=target,
            prompt=f"Ken Burns ({motion}) từ ảnh #{image_asset.id}",
            provider=PROVIDER_KEN_BURNS,
            model=KEN_BURNS_MODEL,
            cost_usd=0.0,
            request_hash=None,
            keyframe_asset_id=image_asset.id,
            duration_seconds=duration_seconds,
            output_prefix=output_prefix,
            sequence_no=sequence_no,
        ),
        from_cache=False,
    )


def extract_last_frame_asset(
    db: Session,
    user_id: int,
    *,
    clip_asset_id: int,
    output_prefix: str | None = None,
) -> GenerationResult:
    """Trích khung cuối 1 clip thành `GeneratedAsset` kiểu IMAGE.

    Dùng cho nối frame giữa các cảnh (Phase 15): khung cuối cảnh N làm keyframe
    mở đầu cảnh N+1 để nhân vật/bối cảnh liền mạch. Miễn phí (ffmpeg cục bộ) và
    idempotent nhờ `request_hash` — nối lại nhiều lần không tạo file mới.
    """
    clip = get_asset(db, user_id, clip_asset_id)
    if clip is None:
        raise GenerationError(f"Không tìm thấy asset id={clip_asset_id}")
    if clip.type is not GeneratedAssetType.VIDEO:
        raise GenerationError(f"Asset id={clip_asset_id} không phải video — không trích được frame.")
    if not Path(clip.file_path).exists():
        raise GenerationError(f"File của asset id={clip_asset_id} không còn trên ổ đĩa.")

    request_hash = _request_hash(["lastframe", str(clip_asset_id)])
    cached = _find_cached(db, user_id, request_hash)
    if cached is not None:
        return GenerationResult(asset=cached, from_cache=True)

    sequence_no = _next_sequence_no(db, user_id, output_prefix)
    filename = _build_filename(GeneratedAssetType.IMAGE, output_prefix, sequence_no, ".png")
    target = output_dir() / filename

    ffmpeg.extract_last_frame(Path(clip.file_path), target)

    return GenerationResult(
        asset=_save_asset(
            db,
            user_id,
            asset_type=GeneratedAssetType.IMAGE,
            file_path=target,
            prompt=f"Khung cuối của clip #{clip_asset_id}",
            provider=PROVIDER_KEN_BURNS,
            model="ffmpeg-last-frame",
            cost_usd=0.0,
            request_hash=request_hash,
            keyframe_asset_id=clip_asset_id,
            output_prefix=output_prefix,
            sequence_no=sequence_no,
        ),
        from_cache=False,
    )


def export_to_asset_library(db: Session, user_id: int, asset_id: int) -> asset_service.Asset:
    """Đưa ảnh/clip đã sinh vào kho file dùng chung (`asset_service`, Phase 9).

    Kho đó là nguồn của `AssetPicker` trong Timeline Editor (Phase 13), nên sau
    bước này clip dùng được để ghép như mọi file khác. Copy chứ không move: bản
    trong `storage/generated/` vẫn là nguồn để `request_hash` cache còn hiệu lực.
    """
    asset = get_asset(db, user_id, asset_id)
    if asset is None:
        raise GenerationError(f"Không tìm thấy asset id={asset_id}")
    if not Path(asset.file_path).exists():
        raise GenerationError(f"File của asset id={asset_id} không còn trên ổ đĩa.")

    imported = asset_service.import_from_path(asset.file_path)
    logger.info("Đã đưa asset #%d vào kho dùng chung (%s)", asset_id, imported.kind)
    return imported


def _require_image_asset(db: Session, user_id: int, asset_id: int) -> GeneratedAsset:
    asset = db.execute(
        select(GeneratedAsset).where(
            GeneratedAsset.id == asset_id, GeneratedAsset.user_id == user_id
        )
    ).scalar_one_or_none()
    if asset is None:
        raise GenerationError(f"Không tìm thấy asset id={asset_id}")
    if asset.type is not GeneratedAssetType.IMAGE:
        raise GenerationError(f"Asset id={asset_id} không phải ảnh — cần ảnh làm keyframe.")
    if not Path(asset.file_path).exists():
        raise GenerationError(f"File của asset id={asset_id} không còn trên ổ đĩa.")
    return asset


def _save_asset(
    db: Session,
    user_id: int,
    *,
    asset_type: GeneratedAssetType,
    file_path: Path,
    prompt: str,
    provider: str,
    model: str,
    cost_usd: float,
    request_hash: str | None,
    character_ref_id: int | None = None,
    keyframe_asset_id: int | None = None,
    duration_seconds: float | None = None,
    output_prefix: str | None = None,
    sequence_no: int | None = None,
) -> GeneratedAsset:
    record = GeneratedAsset(
        user_id=user_id,
        type=asset_type,
        file_path=str(file_path),
        prompt=prompt,
        provider=provider,
        model=model,
        source_character_ref_id=character_ref_id,
        source_keyframe_asset_id=keyframe_asset_id,
        duration_seconds=duration_seconds,
        cost_estimate_usd=cost_usd,
        request_hash=request_hash,
        output_prefix=output_prefix,
        sequence_no=sequence_no,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_assets(
    db: Session, user_id: int, asset_type: GeneratedAssetType | None = None
) -> list[GeneratedAsset]:
    query = select(GeneratedAsset).where(GeneratedAsset.user_id == user_id)
    if asset_type is not None:
        query = query.where(GeneratedAsset.type == asset_type)
    return list(db.execute(query.order_by(GeneratedAsset.created_at.desc())).scalars())


def get_asset(db: Session, user_id: int, asset_id: int) -> GeneratedAsset | None:
    return db.execute(
        select(GeneratedAsset).where(
            GeneratedAsset.id == asset_id, GeneratedAsset.user_id == user_id
        )
    ).scalar_one_or_none()
