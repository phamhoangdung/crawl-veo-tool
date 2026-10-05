"""System info for end users — currently the backend log and the download packs."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core import packs
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


class PackRead(BaseModel):
    id: str
    label: str
    approx_size_mb: int
    installed: bool
    state: str
    downloaded: int
    total: int | None
    error: str | None


@router.get("/packs", response_model=list[PackRead])
def list_packs() -> list[dict]:
    return packs.status()


@router.post("/packs/{pack_id}/install", response_model=list[PackRead])
def install_pack(pack_id: str) -> list[dict]:
    try:
        packs.start_install(pack_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Gói không tồn tại") from None
    return packs.status()
