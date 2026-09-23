"""Thông tin hệ thống cho người dùng cuối — hiện chỉ có nhật ký backend."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.services import log_service

router = APIRouter(prefix="/api/system", tags=["system"])


class LogsRead(BaseModel):
    path: str
    exists: bool
    lines: list[str]


@router.get("/logs", response_model=LogsRead)
def get_logs(lines: int = Query(500, ge=1, le=5000)) -> LogsRead:
    tail = log_service.read_tail(lines)
    return LogsRead(path=str(tail.path), exists=tail.exists, lines=tail.lines)
