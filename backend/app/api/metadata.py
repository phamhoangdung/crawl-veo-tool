"""Generate title/description/tags for a video — used from the UI or n8n.

n8n passes its own `prompt_template` for each kind of video (cooking, vlog, news
need different writing styles) instead of sharing one mold.
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
    # When empty, use the default prompt following YouTube SEO rules.
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
    except Exception as exc:  # noqa: BLE001 — report the real cause to the caller
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return MetadataRead(**result)


@router.get("/metadata/default-prompt", response_model=str)
def default_prompt() -> str:
    """Default prompt — n8n fetches it as a starting point and then edits it per topic."""
    return metadata_service.DEFAULT_PROMPT
