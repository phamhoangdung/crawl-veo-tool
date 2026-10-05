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
    """A multi-scene video project (Phase 15).

    Deliberately separate from the `videos` table: `Video` is a crawled video (it must have
    `platform`/`source_url`/`job_id` and goes through the download → translate → dub
    state machine), while this project is generated from scratch by AI so it has none of those.
    """

    __tablename__ = "generation_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column()
    # Only used to name files (EP001_001.png) — NOT a relational key.
    # Any query that needs correctness must go through the Scene FK.
    output_prefix: Mapped[str] = mapped_column()
    rendered_path: Mapped[str | None] = mapped_column(default=None)
    canvas_viewport: Mapped[dict | None] = mapped_column(JSON, default=None)
    # Timeline refined after the rough cut (Phase 13 opened to AI projects). Kept apart from
    # `rendered_path` on purpose: the rough cut from the canvas is the editor's input,
    # while `timeline_rendered_path` is the final version after drag-editing.
    timeline_json: Mapped[dict | None] = mapped_column(JSON, default=None)
    timeline_rendered_path: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Scene(Base):
    """One scene in the project.

    There is no separate `edges` table: for a linear chain, the edge entering this scene
    is fully determined by `order_index` + `transition_in` + `chain_from_previous`.
    An edges table would allow branches that `ffmpeg.render_timeline` cannot express
    (it accepts exactly 1 video track).
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
    # Belongs to the EDGE entering this scene, not the previous scene — the first scene is always "cut".
    transition_in: Mapped[str] = mapped_column(String, default="cut")
    transition_duration: Mapped[float] = mapped_column(Float, default=1.0)
    # Frame chaining: use the last frame of the previous scene's clip as the opening keyframe of this one.
    chain_from_previous: Mapped[bool] = mapped_column(default=True)
    # Use a still image + camera motion (free) instead of generating AI video.
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
