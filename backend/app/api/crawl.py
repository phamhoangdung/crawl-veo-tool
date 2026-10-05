from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.adapters.douyin.client import DouyinCookieExpiredError
from app.adapters.douyin.search import DouyinLoginRequiredError, DouyinSearchError
from app.core.db import get_db
from app.models.job import Job
from app.models.video import VideoStatus
from app.schemas.job import (
    JobCreateRequest,
    JobFromSelectionRequest,
    JobPageRead,
    JobWithVideosRead,
    VideoRead,
)
from app.services import cost_service, crawl_service, douyin_service, download_service, progress_service

# States counted as "not downloaded" — matches `DOWNLOADABLE` in the frontend
# (formerly features/crawl/index.tsx, now features/discover/).
_DOWNLOADABLE_STATUSES = {VideoStatus.QUEUED, VideoStatus.FAILED_DOWNLOAD}

router = APIRouter(prefix="/api/jobs", tags=["crawl"])

# MVP: 1 fixed user (see docs/overview/plan.md, multi-tenant section); replace with the
# real user from auth when Phase 7 (packaging to sell) is implemented.
_DEFAULT_USER_ID = 1


@router.post("", response_model=JobWithVideosRead)
async def create_job(payload: JobCreateRequest, db: Session = Depends(get_db)) -> JobWithVideosRead:
    job = await crawl_service.create_bilibili_crawl_job(
        db, _DEFAULT_USER_ID, payload.keyword, translate_keyword=payload.translate_keyword
    )
    return JobWithVideosRead.model_validate(job, from_attributes=True)


@router.post("/from-selection", response_model=JobWithVideosRead)
async def create_job_from_selection(
    payload: JobFromSelectionRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobWithVideosRead:
    """Create a job from the videos the user ticked on the Discovery screen (Phase 20).

    `payload.download=True` (default): fire background downloads right away for every video without a
    file — previously it only created the job and said "open the Crawl page to download", but no
    screen could show that job again (see phase-20, Survey point 1).
    Bulk downloads go through `download_service.run_download_task`, queueing themselves by
    `download_max_videos` — firing 20 background tasks does not mean 20 download streams
    really run at once.
    """
    if not payload.videos:
        raise HTTPException(status_code=400, detail="Chưa chọn video nào.")
    job = await crawl_service.create_job_from_selection(db, _DEFAULT_USER_ID, payload.videos)

    if payload.download:
        to_download = [
            v
            for v in job.result_videos
            if v.status in _DOWNLOADABLE_STATUSES and not v.local_path
        ]
        # Capture id/title into plain variables BEFORE the commit: after `db.commit()`,
        # `expire_on_commit` (the Session default) expires every DB-mapped attribute
        # of these objects — reading `video.id`/`video.title` afterwards
        # is still correct (auto reload) but costs N unnecessary extra queries.
        pending = [(v.id, v.title) for v in to_download]
        for video in to_download:
            video.status = VideoStatus.DOWNLOADING
            video.error_message = None
        if to_download:
            db.commit()
        for video_id, title in pending:
            progress_service.start(video_id, title)
            background.add_task(download_service.run_download_task, video_id)

    return JobWithVideosRead.model_validate(job, from_attributes=True)


@router.post("/{job_id}/load-more", response_model=JobPageRead)
async def load_more_videos(job_id: int, page: int = 2, db: Session = Depends(get_db)) -> JobPageRead:
    """Load one more page of search results into the job — used for infinite scroll on the Crawl page."""
    try:
        videos, has_more = await crawl_service.append_videos_to_job(db, job_id, page)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JobPageRead(
        videos=[VideoRead.model_validate(v, from_attributes=True) for v in videos],
        page=page,
        has_more=has_more,
    )


@router.post("/{job_id}/cost-estimate")
def estimate_job_cost(job_id: int, db: Session = Depends(get_db)) -> dict:
    """Estimate the cost before running translate/dub for the whole batch — see app/services/cost_service.py."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    total_duration = sum(v.duration_seconds or 0 for v in job.videos)
    return cost_service.estimate_batch_cost(db, _DEFAULT_USER_ID, total_duration)


class DouyinStatusRead(BaseModel):
    configured: bool
    hint: str


class DouyinProbeRequest(BaseModel):
    share_url: str = Field(min_length=1)


class DouyinProbeRead(BaseModel):
    aweme_id: str
    top_level_keys: list[str]
    detail_keys: list[str]


@router.get("/douyin/status", response_model=DouyinStatusRead, tags=["douyin"])
def douyin_status() -> DouyinStatusRead:
    """The UI asks before showing the form, to explain clearly why Douyin is not usable yet."""
    configured = douyin_service.is_configured()
    return DouyinStatusRead(
        configured=configured,
        hint=(
            "Đã có cookie Douyin trong cấu hình."
            if configured
            else "Chưa có cookie Douyin — đặt DOUYIN_COOKIE trong backend/.env."
        ),
    )


@router.post("/douyin/probe", response_model=DouyinProbeRead, tags=["douyin"])
async def douyin_probe(payload: DouyinProbeRequest) -> DouyinProbeRead:
    """Probe 1 share link: resolve the id + see which fields the detail JSON has.

    Does not download the video yet — extracting the no-watermark link requires knowing the real
    JSON shape first, which only a real cookie can reveal (see the `douyin_service` docstring).
    """
    try:
        result = await douyin_service.probe_share_url(payload.share_url)
    except douyin_service.DouyinNotConfiguredError as exc:
        # 400 not 500: a missing configuration is something the user can fix.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DouyinCookieExpiredError as exc:
        # 409 so the UI can tell it apart from "no cookie yet" — the action needed is different.
        raise HTTPException(
            status_code=409,
            detail=f"Cookie Douyin đã hết hạn, cần lấy lại cookie mới ({exc}).",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Không đọc được link chia sẻ Douyin: {exc}"
        ) from exc
    return DouyinProbeRead(**result)


class DouyinSearchRequest(BaseModel):
    keyword: str = Field(min_length=1)
    offset: int = 0
    count: int = 15


@router.post("/douyin/search-probe", tags=["douyin"])
async def douyin_search_probe(payload: DouyinSearchRequest) -> dict:
    """Probe keyword search — NOT yet a complete search feature.

    Douyin demands a REAL logged-in account cookie for search (unlike the anonymous cookie
    that suffices for video download) — most calls will get 409 here until you log
    into Douyin yourself and update `DOUYIN_COOKIE`. Returns raw JSON on success because the shape
    on success is unknown, see docs/phases/phase-3-multiprovider-douyin.md.
    """
    try:
        return await douyin_service.search_videos(
            payload.keyword, offset=payload.offset, count=payload.count
        )
    except douyin_service.DouyinNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DouyinLoginRequiredError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Douyin yêu cầu đăng nhập để tìm kiếm ({exc}). Cookie ẩn danh "
                "(đủ để tải video) không đủ — cần đăng nhập tài khoản Douyin thật "
                "trên trình duyệt rồi lấy lại cookie."
            ),
        ) from exc
    except DouyinSearchError as exc:
        raise HTTPException(status_code=502, detail=f"Douyin trả lỗi: {exc}") from exc
