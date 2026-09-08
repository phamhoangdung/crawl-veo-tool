from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.video import Video
from app.schemas.timeline import (
    AudioStemsRead,
    TimelineRead,
    TimelineRenderRead,
    TimelineSaveRequest,
    WaveformRead,
)
from app.services import library_service, timeline_service, waveform_service

router = APIRouter(prefix="/api/videos", tags=["timeline"])


@router.get("/{video_id}/timeline", response_model=TimelineRead)
def get_timeline(video_id: int, db: Session = Depends(get_db)) -> TimelineRead:
    try:
        operations = timeline_service.get_timeline(db, video_id)
    except timeline_service.VideoNotFoundError:
        raise HTTPException(status_code=404, detail="Video not found") from None
    return TimelineRead(tracks=operations["tracks"] if operations else None)


@router.put("/{video_id}/timeline", response_model=TimelineRead)
def save_timeline(
    video_id: int, payload: TimelineSaveRequest, db: Session = Depends(get_db)
) -> TimelineRead:
    """Chỉ LƯU draft — không render. Render là hành động riêng qua endpoint bên dưới,
    do người dùng chủ động bấm (nguyên tắc Phase 13: AI gợi ý, người quyết định)."""
    try:
        operations = timeline_service.save_timeline(db, video_id, payload.model_dump())
    except timeline_service.VideoNotFoundError:
        raise HTTPException(status_code=404, detail="Video not found") from None
    except timeline_service.TimelineValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return TimelineRead(tracks=operations["tracks"])


@router.post("/{video_id}/timeline/render", response_model=TimelineRenderRead)
def render_timeline(video_id: int, db: Session = Depends(get_db)) -> TimelineRenderRead:
    try:
        output_path = timeline_service.render_timeline_for_video(db, video_id)
    except timeline_service.VideoNotFoundError:
        raise HTTPException(status_code=404, detail="Video not found") from None
    except timeline_service.TimelineValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return TimelineRenderRead(rendered_path=str(output_path))


@router.get("/{video_id}/audio-stems", response_model=AudioStemsRead)
def get_audio_stems(video_id: int, db: Session = Depends(get_db)) -> AudioStemsRead:
    """Các track audio đã tách (giọng đọc / nhạc nền) để chỉnh âm lượng riêng."""
    try:
        stems = timeline_service.get_audio_stems(db, video_id)
    except timeline_service.VideoNotFoundError:
        raise HTTPException(status_code=404, detail="Video not found") from None
    return AudioStemsRead(**stems)


@router.get("/{video_id}/waveform", response_model=WaveformRead)
def get_waveform(
    video_id: int, variant: str = "dubbed", db: Session = Depends(get_db)
) -> WaveformRead:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    path = library_service.resolve_download_path(video, variant)
    if path is None or not path.exists():
        raise HTTPException(status_code=404, detail=f"Không có file '{variant}' cho video này")
    peaks = waveform_service.compute_waveform(path)
    return WaveformRead(peaks=peaks)
