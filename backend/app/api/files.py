from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services import file_manager_service, storage_cleanup_service

router = APIRouter(prefix="/api/files", tags=["files"])

# MVP: 1 user cố định — xem app/api/crawl.py.
_DEFAULT_USER_ID = 1


class FileEntryRead(BaseModel):
    variant: str
    path: str
    size_bytes: int
    exists: bool


class VideoFilesRead(BaseModel):
    video_id: int
    title: str
    status: str
    cover_url: str | None
    video_dir: str | None
    files: list[FileEntryRead]
    total_bytes: int


class StorageSummaryRead(BaseModel):
    storage_root: str
    video_count: int
    total_bytes: int
    # File còn trên đĩa nhưng không còn video nào trỏ tới.
    orphan_bytes: int


@router.get("", response_model=list[VideoFilesRead])
def list_files(db: Session = Depends(get_db)) -> list[VideoFilesRead]:
    entries = file_manager_service.list_video_files(db, _DEFAULT_USER_ID)
    return [
        VideoFilesRead(
            video_id=e.video_id,
            title=e.title,
            status=e.status,
            cover_url=e.cover_url,
            video_dir=e.video_dir,
            files=[FileEntryRead(**vars(f)) for f in e.files],
            total_bytes=e.total_bytes,
        )
        for e in entries
    ]


@router.get("/summary", response_model=StorageSummaryRead)
def storage_summary(db: Session = Depends(get_db)) -> StorageSummaryRead:
    return StorageSummaryRead(**file_manager_service.get_storage_summary(db, _DEFAULT_USER_ID))


@router.delete("/{video_id}/{variant}")
def delete_variant(video_id: int, variant: str, db: Session = Depends(get_db)) -> dict[str, bool]:
    try:
        deleted = file_manager_service.delete_variant(db, video_id, variant)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"deleted": deleted}


@router.delete("/{video_id}")
def delete_video_files(video_id: int, db: Session = Depends(get_db)) -> dict[str, int]:
    try:
        freed = file_manager_service.delete_video_files(db, video_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"freed_bytes": freed}


@router.post("/cleanup-orphans")
def cleanup_orphans(db: Session = Depends(get_db)) -> dict[str, int]:
    """Xoá file không còn video nào trỏ tới — dọn sau khi xoá bản ghi hoặc job lỗi."""
    freed = file_manager_service.delete_orphan_files(db, _DEFAULT_USER_ID)
    return {"freed_bytes": freed}


class CleanupOldJobsRead(BaseModel):
    removed_job_ids: list[str]
    max_age_days: int


@router.post("/cleanup-old-jobs", response_model=CleanupOldJobsRead)
def cleanup_old_jobs(
    max_age_days: int = storage_cleanup_service.DEFAULT_MAX_AGE_DAYS,
) -> CleanupOldJobsRead:
    """Chạy ngay việc dọn thư mục job cũ, không đợi chu kỳ nền 24h.

    Cùng hàm mà vòng lặp nền gọi — endpoint này chỉ để bấm tay khi ổ đĩa đầy
    hoặc khi muốn dọn gấp với ngưỡng tuổi khác.
    """
    if max_age_days < 1:
        raise HTTPException(
            status_code=422, detail="max_age_days phải >= 1 (tránh xoá nhầm job hôm nay)"
        )
    removed = storage_cleanup_service.cleanup_old_job_folders(max_age_days)
    return CleanupOldJobsRead(removed_job_ids=removed, max_age_days=max_age_days)


class DashboardStatsRead(BaseModel):
    """Số liệu tổng quan cho trang chủ — đếm từ DB, không phải số minh hoạ."""

    total_videos: int
    downloaded: int
    transcribed: int
    translated: int
    dubbed: int
    failed: int
    total_bytes: int
    running_tasks: int


@router.get("/dashboard-stats", response_model=DashboardStatsRead)
def dashboard_stats(db: Session = Depends(get_db)) -> DashboardStatsRead:
    return DashboardStatsRead(**file_manager_service.get_dashboard_stats(db, _DEFAULT_USER_ID))


# Đặt CUỐI file: route có path param sẽ bắt nhầm các đường dẫn tĩnh phía trên
# (/summary, /dashboard-stats) nếu khai báo trước chúng.
@router.get("/{video_id}", response_model=VideoFilesRead)
def get_video_files(video_id: int, db: Session = Depends(get_db)) -> VideoFilesRead:
    """File của 1 video — trang chi tiết cần, không phải nạp cả danh sách."""
    entries = file_manager_service.list_video_files(db, _DEFAULT_USER_ID)
    entry = next((e for e in entries if e.video_id == video_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Video chưa có file nào")
    return VideoFilesRead(
        video_id=entry.video_id,
        title=entry.title,
        status=entry.status,
        cover_url=entry.cover_url,
        video_dir=entry.video_dir,
        files=[FileEntryRead(**vars(f)) for f in entry.files],
        total_bytes=entry.total_bytes,
    )
