from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.video import Video
from app.schemas.clip import ClipCandidateRead, ClipCreateRequest, ClipRead
from app.services import clip_candidate_service, clip_service, library_service

router = APIRouter(prefix="/api/videos", tags=["clips"])


@router.get("/{video_id}/clip-candidates", response_model=list[ClipCandidateRead])
def get_clip_candidates(
    video_id: int,
    target_duration: float = 45.0,
    max_candidates: int = 5,
    db: Session = Depends(get_db),
) -> list[ClipCandidateRead]:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    candidates = clip_candidate_service.suggest_clip_candidates(
        video.transcript_json or [], target_duration=target_duration, max_candidates=max_candidates
    )
    return [ClipCandidateRead(start=c.start, end=c.end, text=c.text, score=c.score) for c in candidates]


@router.post("/{video_id}/clips", response_model=ClipRead)
def create_clip(
    video_id: int, payload: ClipCreateRequest, variant: str = "dubbed", db: Session = Depends(get_db)
) -> ClipRead:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    source_path = library_service.resolve_download_path(video, variant)
    if source_path is None or not source_path.exists():
        raise HTTPException(status_code=404, detail=f"Không có file '{variant}' cho video này")

    video_dir = Path(video.local_path).parent if video.local_path else Path("storage") / str(video_id)
    clips_dir = video_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    output_path = clips_dir / f"clip_{int(payload.start)}_{int(payload.end)}.mp4"

    try:
        clip_service.render_clip(
            str(source_path),
            video.transcript_json or [],
            output_path,
            start=payload.start,
            end=payload.end,
            crop=payload.crop.model_dump() if payload.crop else None,
            cta_text=payload.cta_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    return ClipRead(output_path=str(output_path))
