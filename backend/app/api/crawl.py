from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.job import Job
from app.schemas.job import JobCreateRequest, JobWithVideosRead
from app.services import cost_service, crawl_service

router = APIRouter(prefix="/api/jobs", tags=["crawl"])

# MVP: 1 user cố định (xem docs/overview/plan.md phần multi-tenant); thay bằng
# user thật từ auth khi Phase 7 (đóng gói bán) triển khai.
_DEFAULT_USER_ID = 1


@router.post("", response_model=JobWithVideosRead)
async def create_job(payload: JobCreateRequest, db: Session = Depends(get_db)) -> JobWithVideosRead:
    job = await crawl_service.create_bilibili_crawl_job(db, _DEFAULT_USER_ID, payload.keyword)
    return JobWithVideosRead.model_validate(job, from_attributes=True)


@router.post("/{job_id}/cost-estimate")
def estimate_job_cost(job_id: int, db: Session = Depends(get_db)) -> dict:
    """Ước tính chi phí trước khi chạy dịch/lồng tiếng cho cả batch — xem app/services/cost_service.py."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    total_duration = sum(v.duration_seconds or 0 for v in job.videos)
    return cost_service.estimate_batch_cost(db, _DEFAULT_USER_ID, total_duration)
