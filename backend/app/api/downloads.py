import asyncio
import json
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.video import Video
from app.services import download_service, progress_service

router = APIRouter(prefix="/api/downloads", tags=["downloads"])

# Interval for checking changes on the server side. Only sends to the client when the data really
# differs from last time, so this fast interval creates no useless traffic.
_STREAM_TICK_SECONDS = 0.5

# When no task is running we still must emit a periodic comment, otherwise a proxy or the
# browser may consider the connection dead and close it.
_HEARTBEAT_SECONDS = 15.0


class TaskProgressRead(BaseModel):
    # With subject_type="project" this is the project_id (Phase 16).
    video_id: int
    subject_type: str = "video"
    title: str
    kind: str
    kind_label: str
    stage: str
    stage_label: str
    percent: float
    current: int
    total: int | None
    is_running: bool
    # Only meaningful for video downloads (bytes/second); other steps count by sentences.
    speed_per_sec: float
    error: str | None


class StorageLocationRead(BaseModel):
    """Where the files are stored — the tool runs locally so it returns the real path on the machine."""

    storage_root: str
    video_path: str | None = None
    video_dir: str | None = None
    exists: bool = False


@router.get("/progress", response_model=list[TaskProgressRead])
def list_progress() -> list[TaskProgressRead]:
    """Progress of every running task (download, transcribe, translate, dub)."""
    return [
        TaskProgressRead(
            video_id=p.video_id,
            subject_type=p.subject_type,
            title=p.title,
            kind=p.kind,
            kind_label=p.kind_label,
            stage=p.stage,
            stage_label=p.stage_label,
            percent=round(p.percent, 1),
            current=p.current,
            total=p.total,
            is_running=p.is_running,
            speed_per_sec=round(p.speed_per_sec, 1),
            error=p.error,
        )
        for p in progress_service.snapshot()
    ]


def _serialize_tasks() -> list[dict]:
    return [task.model_dump() for task in list_progress()]


@router.get("/stream")
async def stream_progress(request: Request) -> StreamingResponse:
    """Push progress over Server-Sent Events so the client does not have to poll.

    Sends only when the data changed since the last send. The client uses `EventSource`, so the
    browser reconnects by itself when dropped — no reconnect handling needed in the frontend.
    """

    async def event_stream() -> AsyncIterator[str]:
        last_payload: str | None = None
        since_heartbeat = 0.0

        # Send the current state right away so the client does not wait for the first tick.
        while True:
            if await request.is_disconnected():
                break

            payload = json.dumps(_serialize_tasks(), ensure_ascii=False)
            if payload != last_payload:
                last_payload = payload
                since_heartbeat = 0.0
                yield f"data: {payload}\n\n"
            elif since_heartbeat >= _HEARTBEAT_SECONDS:
                since_heartbeat = 0.0
                # A line starting with ':' is an SSE comment — keeps the connection alive,
                # the client ignores it.
                yield ": keep-alive\n\n"

            await asyncio.sleep(_STREAM_TICK_SECONDS)
            since_heartbeat += _STREAM_TICK_SECONDS

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Turn off proxy (nginx...) buffering so events arrive right away instead of being batched.
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/progress/finished")
def clear_finished_progress() -> dict[str, int]:
    """Clear every finished task from the list."""
    return {"cleared": progress_service.clear_finished()}


@router.delete("/progress/{video_id}")
def clear_progress(video_id: int, kind: str | None = None) -> dict[str, bool]:
    """Remove 1 task from the list; without kind, remove every task of the video."""
    progress_service.clear(video_id, kind)  # type: ignore[arg-type]
    return {"ok": True}


@router.get("/location", response_model=StorageLocationRead)
def storage_location(video_id: int | None = None, db: Session = Depends(get_db)) -> StorageLocationRead:
    root = download_service.get_storage_root()
    if video_id is None:
        return StorageLocationRead(storage_root=str(root))

    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video không tồn tại")

    path = Path(video.local_path) if video.local_path else None
    return StorageLocationRead(
        storage_root=str(root),
        video_path=str(path) if path else None,
        video_dir=str(path.parent) if path else None,
        exists=bool(path and path.exists()),
    )


@router.post("/reveal")
def reveal_in_file_manager(video_id: int | None = None, db: Session = Depends(get_db)) -> dict[str, str]:
    """Open the folder containing the file in Finder/Explorer.

    Only possible because the tool runs locally on the user's machine. The path is always taken from the
    DB, never accepted from the client — to avoid turning this endpoint into an arbitrary file opener.
    """
    if video_id is None:
        target = download_service.get_storage_root()
    else:
        video = db.get(Video, video_id)
        if video is None:
            raise HTTPException(status_code=404, detail="Video không tồn tại")
        if not video.local_path:
            raise HTTPException(status_code=400, detail="Video chưa được tải về")
        target = Path(video.local_path)
        if not target.exists():
            raise HTTPException(status_code=404, detail="File không còn trên đĩa")

    target.parent.mkdir(parents=True, exist_ok=True) if target.is_file() else target.mkdir(
        parents=True, exist_ok=True
    )

    try:
        if sys.platform == "darwin":
            # -R preselects the file in Finder instead of just opening the folder.
            args = ["open", "-R", str(target)] if target.is_file() else ["open", str(target)]
        elif sys.platform == "win32":
            args = (
                ["explorer", f"/select,{target}"]
                if target.is_file()
                else ["explorer", str(target)]
            )
        else:
            args = ["xdg-open", str(target if target.is_dir() else target.parent)]
        subprocess.run(args, check=False)
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"Không mở được trình quản lý file: {exc}"
        ) from exc

    return {"opened": str(target)}
