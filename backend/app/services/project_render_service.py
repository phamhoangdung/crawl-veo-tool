"""Dựng toàn bộ dự án nhiều cảnh thành 1 file video (Phase 15).

Chạy nền bằng `BackgroundTasks`: sinh 5 cảnh rồi ghép mất vài phút, làm đồng bộ
như `timeline_service.render_timeline_for_video` (Phase 13) sẽ đụng timeout của
request.
"""

import asyncio
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.adapters import ffmpeg
from app.core.config import _storage_dir
from app.core.db import SessionLocal
from app.models.generated_asset import GeneratedAsset
from app.services import asset_service, progress_service, project_service

logger = logging.getLogger(__name__)

RENDER_KIND = "render_project"
_SUBJECT = "project"


class ProjectRenderError(RuntimeError):
    pass


def output_path_for(project_id: int) -> Path:
    directory = _storage_dir() / "projects" / str(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "final.mp4"


def is_rendering(project_id: int) -> bool:
    return progress_service.is_running(
        project_id, RENDER_KIND, subject_type=_SUBJECT
    )


def start_render(db: Session, user_id: int, project_id: int) -> None:
    """Đăng ký tiến độ trước khi trả request, để UI thấy ngay là job đã nhận."""
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
    """Chạy trong background task — tự mở session riêng vì session của request
    đã đóng khi request trả về."""
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
    """Đưa video đã dựng vào kho file dùng chung (`asset_service`, Phase 9).

    Kho đó là nguồn của `AssetPicker` trong Timeline Editor (Phase 13), nên sau
    bước này video mở được ở editor để thêm lồng tiếng/phụ đề. Copy chứ không
    move: `rendered_path` của dự án phải còn để nút "Xem / tải video" vẫn chạy.
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
    """Chặn trước khi render nếu các clip lệch kích thước.

    `xfade` giả định mọi clip cùng resolution; lệch nhau thì ffmpeg xuất ra file
    hỏng thay vì báo lỗi, nên thà chặn sớm với thông báo rõ. Tự động scale để sau.
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
