import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.adapters import ffmpeg
from app.adapters.bilibili.client import BilibiliClient
from app.core.db import SessionLocal, get_db
from app.models.video import Video, VideoStatus
from app.schemas.pipeline import TranscriptSegment, TranslateRequest, VideoDetailRead
from app.services import (
    download_service,
    dubbing_service,
    progress_service,
    subtitle_service,
)

logger = logging.getLogger(__name__)

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
        burned_path=video.burned_path,
    )


@router.get("/{video_id}", response_model=VideoDetailRead)
def get_video_detail(video_id: int, db: Session = Depends(get_db)) -> VideoDetailRead:
    """Đầy đủ thông tin cho trang chi tiết (khác _to_detail chỉ trả trạng thái)."""
    video = _get_video_or_404(db, video_id)
    detail = _to_detail(video)
    detail.title = video.title
    detail.author_name = video.author_name
    detail.cover_url = video.cover_url
    detail.source_url = video.source_url
    detail.duration_seconds = video.duration_seconds
    detail.local_path = video.local_path
    detail.error_message = video.error_message
    return detail


async def _run_download(video_id: int) -> None:
    """Chạy nền: tự mở session riêng vì session của request đã đóng khi hàm này chạy."""
    with SessionLocal() as db:
        video = db.get(Video, video_id)
        if video is None:
            progress_service.finish(video_id, error="Video không còn tồn tại")
            return
        try:
            async with BilibiliClient() as client:
                cid = await client.get_video_cid(video.platform_video_id)
            output_path = await download_service.download_bilibili_video(
                job_id=video.job_id,
                video_id=video.id,
                bvid=video.platform_video_id,
                cid=cid,
            )
            video.local_path = str(output_path)
            video.status = VideoStatus.DOWNLOADED
            video.error_message = None
            db.commit()
            progress_service.finish(video.id)
        except Exception as exc:  # noqa: BLE001 — chạy nền, không ai bắt được lỗi này
            logger.exception("Tải video %s thất bại", video_id)
            video.status = VideoStatus.FAILED_DOWNLOAD
            video.error_message = str(exc)
            db.commit()
            progress_service.finish(video.id, error=str(exc))


@router.post("/{video_id}/download", response_model=VideoDetailRead)
async def download_video(
    video_id: int, background: BackgroundTasks, db: Session = Depends(get_db)
) -> VideoDetailRead:
    """Khởi động tải rồi trả về ngay.

    Tải chạy nền để UI không bị treo và người dùng rời trang vẫn theo dõi được
    qua `GET /api/downloads/progress`.
    """
    video = _get_video_or_404(db, video_id)

    if video.status == VideoStatus.DOWNLOADING:
        raise HTTPException(status_code=409, detail="Video này đang được tải.")

    video.status = VideoStatus.DOWNLOADING
    video.error_message = None
    db.commit()

    progress_service.start(video.id, video.title)
    background.add_task(_run_download, video.id)
    return _to_detail(video)


def _run_transcribe(video_id: int) -> None:
    """Chạy nền: faster-whisper mất vài phút, không thể giữ request mở suốt thời gian đó."""
    with SessionLocal() as db:
        video = db.get(Video, video_id)
        if video is None:
            progress_service.finish(video_id, error="Video không còn tồn tại", kind="transcribe")
            return
        try:
            dubbing_service.run_transcribe(db, video)
            progress_service.finish(video_id, kind="transcribe")
        except Exception as exc:  # noqa: BLE001 — chạy nền, không ai bắt được lỗi này
            logger.exception("Tách lời thoại video %s thất bại", video_id)
            video.error_message = str(exc)
            db.commit()
            progress_service.finish(video_id, error=str(exc), kind="transcribe")


@router.post("/{video_id}/transcribe", response_model=VideoDetailRead)
def transcribe_video(
    video_id: int, background: BackgroundTasks, db: Session = Depends(get_db)
) -> VideoDetailRead:
    video = _get_video_or_404(db, video_id)
    if progress_service.is_running(video_id, "transcribe"):
        raise HTTPException(status_code=409, detail="Video này đang được tách lời thoại.")
    if not video.local_path:
        raise HTTPException(status_code=400, detail="Chưa tải video về máy.")

    progress_service.start(video.id, video.title, kind="transcribe")
    background.add_task(_run_transcribe, video.id)
    return _to_detail(video)


async def _run_translate(video_id: int, source_lang: str, target_lang: str) -> None:
    with SessionLocal() as db:
        video = db.get(Video, video_id)
        if video is None:
            progress_service.finish(video_id, error="Video không còn tồn tại", kind="translate")
            return
        try:
            await dubbing_service.run_translate(
                db, _DEFAULT_USER_ID, video, source_lang, target_lang
            )
            progress_service.finish(video_id, kind="translate")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Dịch video %s thất bại", video_id)
            video.error_message = str(exc)
            db.commit()
            progress_service.finish(video_id, error=str(exc), kind="translate")


@router.post("/{video_id}/translate", response_model=VideoDetailRead)
async def translate_video(
    video_id: int,
    payload: TranslateRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> VideoDetailRead:
    video = _get_video_or_404(db, video_id)
    if progress_service.is_running(video_id, "translate"):
        raise HTTPException(status_code=409, detail="Video này đang được dịch.")
    if not video.transcript_json:
        raise HTTPException(status_code=400, detail="Chưa có lời thoại để dịch.")

    progress_service.start(video.id, video.title, kind="translate")
    background.add_task(_run_translate, video.id, payload.source_lang, payload.target_lang)
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


async def _run_dub(video_id: int, keep_background: bool) -> None:
    with SessionLocal() as db:
        video = db.get(Video, video_id)
        if video is None:
            progress_service.finish(video_id, error="Video không còn tồn tại", kind="dub")
            return
        try:
            await dubbing_service.run_dub_and_mux(
                db, _DEFAULT_USER_ID, video, keep_background=keep_background
            )
            progress_service.finish(video_id, kind="dub")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Lồng tiếng video %s thất bại", video_id)
            video.error_message = str(exc)
            db.commit()
            progress_service.finish(video_id, error=str(exc), kind="dub")


@router.post("/{video_id}/dub", response_model=VideoDetailRead)
async def dub_video(
    video_id: int,
    background: BackgroundTasks,
    keep_background: bool = True,
    db: Session = Depends(get_db),
) -> VideoDetailRead:
    video = _get_video_or_404(db, video_id)
    if progress_service.is_running(video_id, "dub"):
        raise HTTPException(status_code=409, detail="Video này đang được lồng tiếng.")
    if not video.transcript_json:
        raise HTTPException(status_code=400, detail="Chưa có lời thoại để lồng tiếng.")

    progress_service.start(video.id, video.title, kind="dub")
    background.add_task(_run_dub, video.id, keep_background)
    return _to_detail(video)


@router.get("/{video_id}/subtitles.srt", response_class=PlainTextResponse)
def get_subtitles(video_id: int, db: Session = Depends(get_db)) -> str:
    video = _get_video_or_404(db, video_id)
    return subtitle_service.build_bilingual_srt(video.transcript_json or [])


def _burn_subtitles_for(video: Video) -> None:
    """Ghép phụ đề cứng vào bản đã lồng tiếng (ưu tiên) hoặc bản gốc nếu chưa dub."""
    source_path = Path(video.dubbed_path or video.local_path)
    video_dir = source_path.parent

    srt_path = subtitle_service.write_srt(video.transcript_json or [], video_dir / "subtitles.srt")
    width, height = ffmpeg.get_video_dimensions(source_path)
    font_size = subtitle_service.pick_font_size_for(width, height)

    output_path = video_dir / "burned.mp4"
    ffmpeg.burn_subtitles(source_path, srt_path, output_path, font_size=font_size)
    video.burned_path = str(output_path)


@router.post("/{video_id}/burn-subtitles", response_model=VideoDetailRead)
def burn_subtitles(video_id: int, db: Session = Depends(get_db)) -> VideoDetailRead:
    """Ghép phụ đề cứng vào video."""
    video = _get_video_or_404(db, video_id)
    _burn_subtitles_for(video)
    db.commit()
    return _to_detail(video)


async def run_step(step: str, video_id: int) -> None:
    """Chạy 1 bước pipeline và **ném lỗi ra ngoài** nếu hỏng.

    Khác các hàm `_run_*` (chạy nền, nuốt lỗi vì không ai bắt được): batch cần
    biết bước nào hỏng để đánh dấu đúng video và bỏ qua các bước sau của nó.
    """
    with SessionLocal() as db:
        video = db.get(Video, video_id)
        if video is None:
            raise ValueError(f"Video {video_id} không còn tồn tại")

        progress_service.start(video.id, video.title, kind=step)  # type: ignore[arg-type]
        try:
            if step == "download":
                async with BilibiliClient() as client:
                    cid = await client.get_video_cid(video.platform_video_id)
                output_path = await download_service.download_bilibili_video(
                    job_id=video.job_id,
                    video_id=video.id,
                    bvid=video.platform_video_id,
                    cid=cid,
                )
                video.local_path = str(output_path)
                video.status = VideoStatus.DOWNLOADED
            elif step == "transcribe":
                dubbing_service.run_transcribe(db, video)
            elif step == "translate":
                await dubbing_service.run_translate(db, _DEFAULT_USER_ID, video, "zh", "vi")
            elif step == "dub":
                await dubbing_service.run_dub_and_mux(db, _DEFAULT_USER_ID, video)
            elif step == "burn":
                _burn_subtitles_for(video)
            else:
                raise ValueError(f"Bước không hợp lệ: {step}")

            video.error_message = None
            db.commit()
            progress_service.finish(video.id, kind=step)  # type: ignore[arg-type]
        except Exception as exc:
            video.error_message = str(exc)
            db.commit()
            progress_service.finish(video.id, error=str(exc), kind=step)  # type: ignore[arg-type]
            raise
