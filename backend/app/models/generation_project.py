import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class SceneStatus(str, enum.Enum):
    DRAFT = "draft"
    KEYFRAME_READY = "keyframe_ready"
    CLIP_READY = "clip_ready"
    FAILED = "failed"


class GenerationProject(Base):
    """Một dự án video nhiều cảnh (Phase 15).

    Tách khỏi bảng `videos` có chủ đích: `Video` là video crawl về (bắt buộc có
    `platform`/`source_url`/`job_id`, đi qua state machine tải → dịch → lồng
    tiếng), còn dự án này sinh từ đầu bằng AI nên không có gì trong số đó.
    """

    __tablename__ = "generation_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column()
    # Chỉ dùng để đặt tên file (EP001_001.png) — KHÔNG phải khoá quan hệ.
    # Mọi truy vấn cần đúng phải đi qua FK của Scene.
    output_prefix: Mapped[str] = mapped_column()
    rendered_path: Mapped[str | None] = mapped_column(default=None)
    canvas_viewport: Mapped[dict | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Scene(Base):
    """Một phân cảnh trong dự án.

    Không có bảng `edges` riêng: với chuỗi tuyến tính, cạnh nối vào cảnh này
    được xác định đủ bởi `order_index` + `transition_in` + `chain_from_previous`.
    Bảng edges sẽ cho phép vẽ nhánh mà `ffmpeg.render_timeline` không diễn đạt
    được (nó nhận đúng 1 track video).
    """

    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("generation_projects.id"), index=True
    )
    order_index: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(default="")

    keyframe_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_assets.id"), default=None
    )
    clip_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_assets.id"), default=None
    )

    duration_seconds: Mapped[float] = mapped_column(Float, default=5.0)
    # Thuộc CẠNH đi vào cảnh này, không phải cảnh trước — cảnh đầu tiên luôn "cut".
    transition_in: Mapped[str] = mapped_column(String, default="cut")
    transition_duration: Mapped[float] = mapped_column(Float, default=1.0)
    # Nối frame: lấy khung cuối clip cảnh trước làm keyframe mở đầu cảnh này.
    chain_from_previous: Mapped[bool] = mapped_column(default=True)
    # Dùng ảnh tĩnh + chuyển động camera (miễn phí) thay vì sinh video AI.
    use_ken_burns: Mapped[bool] = mapped_column(default=True)
    ken_burns_motion: Mapped[str] = mapped_column(String, default="zoom_in")

    canvas_x: Mapped[float] = mapped_column(Float, default=0.0)
    canvas_y: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[SceneStatus] = mapped_column(
        Enum(SceneStatus), default=SceneStatus.DRAFT
    )
    error: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
