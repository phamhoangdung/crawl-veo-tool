from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.video import Video
from app.schemas.video_import import ImportedVideoRead
from app.services import import_service

router = APIRouter(prefix="/api/videos", tags=["video-import"])

_DEFAULT_USER_ID = 1


@router.post("/import", response_model=ImportedVideoRead)
def import_video(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> ImportedVideoRead:
    """Nhập 1 file video từ máy. Mỗi lần 1 file để giao diện hiện được tiến độ
    tải lên riêng cho từng file."""
    try:
        video = import_service.import_local_video(
            db, _DEFAULT_USER_ID, file.filename or "", file.file
        )
    except import_service.UnsupportedVideoFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportedVideoRead(
        id=video.id,
        title=video.title,
        status=video.status.value,
        duration_seconds=video.duration_seconds,
        cover_url=video.cover_url,
    )


@router.get("/{video_id}/cover")
def get_cover(video_id: int, db: Session = Depends(get_db)) -> FileResponse:
    video = db.get(Video, video_id)
    path = import_service.cover_path_for(video) if video else None
    if path is None:
        raise HTTPException(status_code=404, detail="Video không có ảnh bìa")
    return FileResponse(path, media_type="image/jpeg")
