from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.adapters.bilibili.client import BilibiliClient
from app.core.db import get_db
from app.models.video import Video, VideoStatus
from app.schemas.pipeline import TranscriptSegment, TranslateRequest, VideoDetailRead
from app.services import download_service, dubbing_service

router = APIRouter(prefix="/api/videos", tags=["pipeline"])

_DEFAULT_USER_ID = 1


def _get_video_or_404(db: Session, video_id: int) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


def _to_detail(video: Video) -> VideoDetailRead:
    return VideoDetailRead(
        id=video.id,
        status=video.status.value,
        transcript=[TranscriptSegment(**segment) for segment in (video.transcript_json or [])],
        dubbed_path=video.dubbed_path,
    )


@router.get("/{video_id}", response_model=VideoDetailRead)
def get_video_detail(video_id: int, db: Session = Depends(get_db)) -> VideoDetailRead:
    return _to_detail(_get_video_or_404(db, video_id))


@router.post("/{video_id}/download", response_model=VideoDetailRead)
async def download_video(video_id: int, db: Session = Depends(get_db)) -> VideoDetailRead:
    video = _get_video_or_404(db, video_id)
    video.status = VideoStatus.DOWNLOADING
    db.commit()
    try:
        async with BilibiliClient() as client:
            cid = await client.get_video_cid(video.platform_video_id)
        output_path = await download_service.download_bilibili_video(
            job_id=video.job_id, video_id=video.id, bvid=video.platform_video_id, cid=cid
        )
        video.local_path = str(output_path)
        video.status = VideoStatus.DOWNLOADED
        db.commit()
    except Exception:
        video.status = VideoStatus.FAILED_DOWNLOAD
        db.commit()
        raise
    return _to_detail(video)


@router.post("/{video_id}/transcribe", response_model=VideoDetailRead)
def transcribe_video(video_id: int, db: Session = Depends(get_db)) -> VideoDetailRead:
    video = _get_video_or_404(db, video_id)
    dubbing_service.run_transcribe(db, video)
    return _to_detail(video)


@router.post("/{video_id}/translate", response_model=VideoDetailRead)
async def translate_video(
    video_id: int, payload: TranslateRequest, db: Session = Depends(get_db)
) -> VideoDetailRead:
    video = _get_video_or_404(db, video_id)
    await dubbing_service.run_translate(db, _DEFAULT_USER_ID, video, payload.source_lang, payload.target_lang)
    return _to_detail(video)


@router.put("/{video_id}/transcript", response_model=VideoDetailRead)
def update_transcript(
    video_id: int, segments: list[TranscriptSegment], db: Session = Depends(get_db)
) -> VideoDetailRead:
    """Lưu transcript đã người dùng sửa tay — dùng thay hoặc sau bước /translate."""
    video = _get_video_or_404(db, video_id)
    video.transcript_json = [segment.model_dump() for segment in segments]
    db.commit()
    return _to_detail(video)


@router.post("/{video_id}/dub", response_model=VideoDetailRead)
async def dub_video(video_id: int, db: Session = Depends(get_db)) -> VideoDetailRead:
    video = _get_video_or_404(db, video_id)
    await dubbing_service.run_dub_and_mux(db, _DEFAULT_USER_ID, video)
    return _to_detail(video)
