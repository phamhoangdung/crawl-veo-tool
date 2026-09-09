import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class GeneratedAssetType(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"


class GeneratedAsset(Base):
    """Ảnh/video sinh ra bằng AI (Phase 14).

    Tách riêng khỏi bảng `videos` vì khác state machine: không có `platform`/
    `source_url`, không đi qua pipeline crawl → dịch → lồng tiếng.

    `request_hash` dùng để dedupe: cùng prompt + ref + model + duration thì trả
    lại asset cũ thay vì gọi API lần nữa (sinh video rất đắt).
    """

    __tablename__ = "generated_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[GeneratedAssetType] = mapped_column(Enum(GeneratedAssetType))
    file_path: Mapped[str] = mapped_column()
    prompt: Mapped[str] = mapped_column()
    provider: Mapped[str] = mapped_column()
    model: Mapped[str] = mapped_column()
    source_character_ref_id: Mapped[int | None] = mapped_column(
        ForeignKey("character_references.id"), default=None
    )
    source_keyframe_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_assets.id"), default=None
    )
    duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    cost_estimate_usd: Mapped[float] = mapped_column(Float, default=0.0)
    request_hash: Mapped[str | None] = mapped_column(default=None, index=True)
    output_prefix: Mapped[str | None] = mapped_column(default=None)
    sequence_no: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
