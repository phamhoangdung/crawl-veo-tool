"""Sinh tiêu đề/mô tả/tag cho video — dùng từ UI hoặc n8n.

n8n truyền `prompt_template` riêng cho từng loại video (ẩm thực, vlog, tin tức
cần văn phong khác nhau) thay vì dùng chung một khuôn.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.video import Video
from app.services import metadata_service

router = APIRouter(prefix="/api/videos", tags=["metadata"])

_DEFAULT_USER_ID = 1


class MetadataRequest(BaseModel):
    # Bỏ trống thì dùng prompt mặc định theo quy tắc SEO YouTube.
    prompt_template: str | None = None


class MetadataRead(BaseModel):
    title: str
    description: str
    tags: list[str]
    title_truncated: bool


@router.post("/{video_id}/metadata", response_model=MetadataRead)
async def generate_metadata(
    video_id: int, payload: MetadataRequest, db: Session = Depends(get_db)
) -> MetadataRead:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video không tồn tại")

    try:
        result = await metadata_service.generate_metadata(
            db, _DEFAULT_USER_ID, video, payload.prompt_template
        )
    except metadata_service.MetadataGenerationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — báo nguyên nhân thật cho người gọi
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return MetadataRead(**result)


@router.get("/metadata/default-prompt", response_model=str)
def default_prompt() -> str:
    """Prompt mặc định — n8n lấy về làm điểm bắt đầu rồi sửa theo chủ đề."""
    return metadata_service.DEFAULT_PROMPT
