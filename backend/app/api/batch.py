"""Chạy pipeline hàng loạt — dùng được cả từ UI lẫn từ n8n/script ngoài.

Thiết kế cho máy gọi: 1 request khởi động cả batch rồi trả về ngay, tiến độ đọc
qua endpoint riêng. n8n không phải giữ kết nối mở suốt hàng giờ.
"""

import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.core.db import SessionLocal
from app.services import batch_service

router = APIRouter(prefix="/api/batch", tags=["batch"])


class BatchStartRequest(BaseModel):
    video_ids: list[int] = Field(..., min_length=1)
    # Bỏ trống thì chạy pipeline mặc định (tải → tách lời → dịch → lồng tiếng).
    steps: list[str] | None = None
    concurrency: int = Field(default=batch_service.DEFAULT_CONCURRENCY, ge=1, le=4)


class BatchItemRead(BaseModel):
    video_id: int
    title: str
    status: str
    current_step: str | None
    error: str | None


class BatchStatusRead(BaseModel):
    id: str
    total: int
    done: int
    failed: int
    skipped: int
    running: int
    pending: int
    is_running: bool
    cancelled: bool
    steps: list[str]
    items: list[BatchItemRead]


def _to_status(job: batch_service.BatchJob) -> BatchStatusRead:
    summary = batch_service.summarize(job)
    return BatchStatusRead(
        **summary,  # type: ignore[arg-type]
        items=[
            BatchItemRead(
                video_id=i.video_id,
                title=i.title,
                status=i.status,
                current_step=i.current_step,
                error=i.error,
            )
            for i in job.items
        ],
    )


@router.post("/start", response_model=BatchStatusRead)
async def start_batch(
    payload: BatchStartRequest, background: BackgroundTasks
) -> BatchStatusRead:
    """Khởi động batch rồi trả về ngay — tiến độ xem ở `GET /api/batch/status`."""
    current = batch_service.get_current()
    if current is not None and current.is_running:
        raise HTTPException(
            status_code=409,
            detail="Đang có batch chạy. Dừng batch đó trước khi bắt đầu batch mới.",
        )

    invalid = set(payload.steps or []) - {"download", "transcribe", "translate", "dub", "burn"}
    if invalid:
        raise HTTPException(status_code=400, detail=f"Bước không hợp lệ: {sorted(invalid)}")

    # Tạo job trước để trả trạng thái ban đầu, rồi chạy nền.
    job = await batch_service.prepare_batch(
        SessionLocal, payload.video_ids, payload.steps, payload.concurrency
    )
    background.add_task(batch_service.execute_batch, SessionLocal, job)
    return _to_status(job)


@router.get("/status", response_model=BatchStatusRead | None)
def batch_status() -> BatchStatusRead | None:
    job = batch_service.get_current()
    return _to_status(job) if job else None


@router.post("/cancel")
def cancel_batch() -> dict[str, bool]:
    """Dừng sau khi video đang chạy xong — không cắt ngang để khỏi bỏ file dở."""
    return {"cancelled": batch_service.cancel_current()}


@router.get("/pending-videos", response_model=list[int])
def pending_videos(limit: int = 50) -> list[int]:
    """ID các video chưa xử lý xong — n8n gọi cái này rồi đưa thẳng vào /start."""
    return batch_service.list_pending_video_ids(SessionLocal, limit=limit)
