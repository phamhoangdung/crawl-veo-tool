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

# Trạng thái coi là "chưa tải" — khớp `DOWNLOADABLE` ở frontend
# (features/crawl/index.tsx trước đây, giờ features/discover/).
_DOWNLOADABLE_STATUSES = {VideoStatus.QUEUED, VideoStatus.FAILED_DOWNLOAD}

router = APIRouter(prefix="/api/jobs", tags=["crawl"])

# MVP: 1 user cố định (xem docs/overview/plan.md phần multi-tenant); thay bằng
# user thật từ auth khi Phase 7 (đóng gói bán) triển khai.
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
    """Tạo job từ các video người dùng tick chọn ở màn Khám phá (Phase 20).

    `payload.download=True` (mặc định): bắn tải nền ngay cho mọi video chưa có
    file — trước đây chỉ tạo job rồi báo "mở trang Crawl để tải", nhưng không
    màn hình nào hiển thị lại được job đó (xem phase-20 mục Khảo sát điểm 1).
    Tải hàng loạt qua `download_service.run_download_task`, tự xếp hàng theo
    `download_max_videos` — bắn 20 background task không có nghĩa 20 luồng tải
    chạy thật cùng lúc.
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
        # Chốt id/title ra biến thường TRƯỚC khi commit: sau `db.commit()`,
        # `expire_on_commit` (mặc định của Session) làm mọi attribute ánh xạ
        # DB của các object này hết hạn — đọc lại `video.id`/`video.title` sau
        # đó vẫn đúng (tự load lại) nhưng tốn thêm N query không cần thiết.
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
    """Tải thêm 1 trang kết quả search vào job — dùng cho infinite scroll trang Crawl."""
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
    """Ước tính chi phí trước khi chạy dịch/lồng tiếng cho cả batch — xem app/services/cost_service.py."""
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
    """UI hỏi trước khi hiện form, để nói rõ vì sao Douyin chưa dùng được."""
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
    """Thăm dò 1 link chia sẻ: resolve id + xem JSON detail có những trường gì.

    Chưa tải video — phần bóc tách link không watermark cần biết hình dạng JSON
    thật trước, mà chỉ cookie thật mới cho biết (xem docstring `douyin_service`).
    """
    try:
        result = await douyin_service.probe_share_url(payload.share_url)
    except douyin_service.DouyinNotConfiguredError as exc:
        # 400 chứ không 500: thiếu cấu hình là việc người dùng sửa được.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DouyinCookieExpiredError as exc:
        # 409 để UI phân biệt với "chưa có cookie" — hành động cần làm khác nhau.
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
    """Thăm dò tìm kiếm từ khoá — CHƯA phải tính năng tìm kiếm hoàn chỉnh.

    Douyin đòi cookie ĐĂNG NHẬP tài khoản thật cho tìm kiếm (khác cookie ẩn danh
    đủ dùng cho tải video) — hầu hết sẽ nhận 409 ở đây cho tới khi bạn tự đăng
    nhập Douyin và cập nhật `DOUYIN_COOKIE`. Trả JSON thô khi thành công vì hình
    dạng lúc thành công chưa biết, xem docs/phases/phase-3-multiprovider-douyin.md.
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
