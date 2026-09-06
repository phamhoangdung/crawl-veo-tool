from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.job import JobCreateRequest, JobWithVideosRead
from app.services import crawl_service

router = APIRouter(prefix="/api/jobs", tags=["crawl"])

# MVP: 1 user cố định (xem docs/overview/plan.md phần multi-tenant); thay bằng
# user thật từ auth khi Phase 7 (đóng gói bán) triển khai.
_DEFAULT_USER_ID = 1


@router.post("", response_model=JobWithVideosRead)
async def create_job(payload: JobCreateRequest, db: Session = Depends(get_db)) -> JobWithVideosRead:
    job = await crawl_service.create_bilibili_crawl_job(db, _DEFAULT_USER_ID, payload.keyword)
    return JobWithVideosRead.model_validate(job, from_attributes=True)
