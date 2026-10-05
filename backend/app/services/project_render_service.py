"""Build a whole multi-scene project into 1 video file (Phase 15).

Runs in the background via `BackgroundTasks`: generating 5 scenes then joining takes minutes, doing it synchronously
like `timeline_service.render_timeline_for_video` (Phase 13) would hit the request
timeout.
"""

import asyncio
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.adapters import ffmpeg
from app.core.config import storage_dir
from app.core.db import SessionLocal
from app.models.generated_asset import GeneratedAsset
from app.services import asset_service, progress_service, project_service

logger = logging.getLogger(__name__)

RENDER_KIND = "render_project"
_SUBJECT = "project"


class ProjectRenderError(RuntimeError):
    pass


def output_path_for(project_id: int) -> Path:
    directory = storage_dir() / "projects" / str(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "final.mp4"


def is_rendering(project_id: int) -> bool:
    return progress_service.is_running(
        project_id, RENDER_KIND, subject_type=_SUBJECT
    )


def start_render(db: Session, user_id: int, project_id: int) -> None:
    """Register progress before returning the request, so the UI sees right away that the job was accepted."""
    project = project_service.get_project(db, user_id, project_id)
    if project is None:
        raise ProjectRenderError(f"Không tìm thấy dự án id={project_id}")
    if is_rendering(project_id):
        raise ProjectRenderError("Dự án này đang được dựng, chờ xong đã.")

    scenes = project_service.list_scenes(db, project_id)
    if not scenes:
        raise ProjectRenderError("Dự án chưa có cảnh nào để dựng.")

    progress_service.start(
        project_id, project.title, RENDER_KIND, subject_type=_SUBJECT
    )


def render_worker(project_id: int, user_id: int) -> None:
    """Run in a background task — opens its own session because the request's session
    was already closed when the request returned."""
    try:
        asyncio.run(_render(project_id, user_id))
    except Exception as exc:
        logger.exception("Dựng dự án %d thất bại", project_id)
        progress_service.finish(
            project_id, str(exc)[:500], RENDER_KIND, subject_type=_SUBJECT
        )
    else:
        progress_service.finish(
            project_id, None, RENDER_KIND, subject_type=_SUBJECT
        )


async def _render(project_id: int, user_id: int) -> None:
    with SessionLocal() as db:
        project = project_service.get_project(db, user_id, project_id)
        if project is None:
            raise ProjectRenderError(f"Không tìm thấy dự án id={project_id}")

        scenes = project_service.list_scenes(db, project_id)
        pending = [s for s in scenes if s.clip_asset_id is None]

        progress_service.set_stage(
            project_id,
            "generating",
            total=len(pending) or 1,
            kind=RENDER_KIND,
            subject_type=_SUBJECT,
        )
        for scene in pending:
            await project_service.generate_scene(db, user_id, scene.id)
            progress_service.advance(
                project_id, 1, RENDER_KIND, subject_type=_SUBJECT
            )

        progress_service.set_stage(
            project_id, "rendering", total=1, kind=RENDER_KIND, subject_type=_SUBJECT
        )
        operations = project_service.build_operations(db, project)
        _ensure_uniform_dimensions(db, project_id)

        output = output_path_for(project_id)
        ffmpeg.render_timeline(operations, output)

        project.rendered_path = str(output)
        db.commit()
        progress_service.advance(project_id, 1, RENDER_KIND, subject_type=_SUBJECT)
        logger.info("Đã dựng xong dự án %d -> %s", project_id, output)


def export_to_asset_library(db: Session, user_id: int, project_id: int) -> asset_service.Asset:
    """Put the built video into the shared file library (`asset_service`, Phase 9).

    That library is the source of the `AssetPicker` in the Timeline Editor (Phase 13), so after
    this step the video can be opened in the editor to add dubbing/subtitles. Copy rather than
    move: the project's `rendered_path` must remain so the "View / download video" button still works.
    """
    project = project_service.get_project(db, user_id, project_id)
    if project is None:
        raise ProjectRenderError(f"Không tìm thấy dự án id={project_id}")
    if not project.rendered_path:
        raise ProjectRenderError("Dự án chưa được dựng — bấm 'Dựng video' trước.")

    path = Path(project.rendered_path)
    if not path.exists():
        raise ProjectRenderError("File video đã bị xoá khỏi ổ đĩa.")

    imported = asset_service.import_from_path(str(path))
    logger.info("Đã đưa video dự án %d vào kho dùng chung", project_id)
    return imported


def _ensure_uniform_dimensions(db: Session, project_id: int) -> None:
    """Block before rendering if the clips differ in size.

    `xfade` assumes every clip has the same resolution; if they differ ffmpeg outputs a
    broken file instead of reporting an error, so better to block early with a clear message. Auto-scaling comes later.
    """
    sizes: dict[tuple[int, int], list[int]] = {}
    for scene in project_service.list_scenes(db, project_id):
        asset = db.get(GeneratedAsset, scene.clip_asset_id)
        if asset is None:
            continue
        path = Path(asset.file_path)
        if not path.exists():
            continue
        sizes.setdefault(ffmpeg.get_video_dimensions(path), []).append(
            scene.order_index + 1
        )

    if len(sizes) > 1:
        detail = "; ".join(
            f"{w}x{h}: cảnh {scene_numbers}" for (w, h), scene_numbers in sizes.items()
        )
        raise ProjectRenderError(
            f"Các cảnh lệch kích thước nên không ghép được ({detail}). "
            "Sinh lại các cảnh bằng cùng một model/tỉ lệ."
        )
