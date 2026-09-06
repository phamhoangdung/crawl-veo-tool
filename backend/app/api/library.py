from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.video import Video
from app.schemas.library import LibraryItemRead
from app.services import library_service

router = APIRouter(prefix="/api/library", tags=["library"])

_DEFAULT_USER_ID = 1
_ZIP_TMP_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "_zips"


@router.get("", response_model=list[LibraryItemRead])
def list_library(db: Session = Depends(get_db)) -> list[LibraryItemRead]:
    videos = library_service.list_processed_videos(db, _DEFAULT_USER_ID)
    return [
        LibraryItemRead(
            id=v.id,
            title=v.title,
            platform=v.platform.value,
            status=v.status.value,
            has_dubbed=v.dubbed_path is not None,
            has_burned=v.burned_path is not None,
            created_at=v.created_at,
        )
        for v in videos
    ]


@router.get("/{video_id}/download")
def download_video(video_id: int, variant: str = "dubbed", db: Session = Depends(get_db)) -> FileResponse:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    path = library_service.resolve_download_path(video, variant)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail=f"Không có file '{variant}' cho video này")
    return FileResponse(path, filename=f"{video.id}_{path.name}")


@router.get("/download-zip")
def download_zip(
    video_ids: str = Query(..., description="Danh sách id cách nhau bởi dấu phẩy, vd: 1,2,3"),
    variant: str = "dubbed",
    db: Session = Depends(get_db),
) -> FileResponse:
    ids = [int(x) for x in video_ids.split(",") if x.strip()]
    videos = db.query(Video).filter(Video.id.in_(ids)).all()
    if not videos:
        raise HTTPException(status_code=404, detail="Không tìm thấy video nào trong danh sách")

    _ZIP_TMP_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = _ZIP_TMP_DIR / f"library_{'-'.join(map(str, ids))}_{variant}.zip"
    library_service.build_zip(videos, variant, zip_path)
    return FileResponse(zip_path, filename=zip_path.name)
