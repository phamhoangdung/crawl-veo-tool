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

# Nhịp kiểm tra thay đổi ở phía server. Chỉ gửi xuống client khi dữ liệu thực sự
# khác lần trước, nên nhịp này nhanh mà không tạo lưu lượng vô ích.
_STREAM_TICK_SECONDS = 0.5

# Không có tác vụ nào chạy thì vẫn phải nhả comment định kỳ, nếu không proxy hoặc
# trình duyệt có thể coi kết nối là chết và đóng nó.
_HEARTBEAT_SECONDS = 15.0


class TaskProgressRead(BaseModel):
    video_id: int
    title: str
    kind: str
    kind_label: str
    stage: str
    stage_label: str
    percent: float
    current: int
    total: int | None
    is_running: bool
    # Chỉ có nghĩa với tải video (byte/giây); các bước khác đếm theo số câu.
    speed_per_sec: float
    error: str | None


class StorageLocationRead(BaseModel):
    """Nơi file được lưu — tool chạy local nên trả đường dẫn thật trên máy."""

    storage_root: str
    video_path: str | None = None
    video_dir: str | None = None
    exists: bool = False


@router.get("/progress", response_model=list[TaskProgressRead])
def list_progress() -> list[TaskProgressRead]:
    """Tiến độ mọi tác vụ đang chạy (tải, tách lời, dịch, lồng tiếng)."""
    return [
        TaskProgressRead(
            video_id=p.video_id,
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
    """Đẩy tiến độ qua Server-Sent Events để client không phải poll.

    Chỉ gửi khi dữ liệu đổi so với lần gửi trước. Client dùng `EventSource`, nên
    trình duyệt tự kết nối lại khi đứt — không cần xử lý reconnect ở frontend.
    """

    async def event_stream() -> AsyncIterator[str]:
        last_payload: str | None = None
        since_heartbeat = 0.0

        # Gửi ngay trạng thái hiện tại để client không phải chờ tick đầu tiên.
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
                # Dòng bắt đầu bằng ':' là comment của SSE — giữ kết nối sống,
                # client bỏ qua.
                yield ": keep-alive\n\n"

            await asyncio.sleep(_STREAM_TICK_SECONDS)
            since_heartbeat += _STREAM_TICK_SECONDS

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Tắt buffering của proxy (nginx...) để event tới ngay thay vì bị gom.
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/progress/finished")
def clear_finished_progress() -> dict[str, int]:
    """Dọn mọi tác vụ đã kết thúc khỏi danh sách."""
    return {"cleared": progress_service.clear_finished()}


@router.delete("/progress/{video_id}")
def clear_progress(video_id: int, kind: str | None = None) -> dict[str, bool]:
    """Bỏ 1 tác vụ khỏi danh sách; không truyền kind thì bỏ mọi tác vụ của video."""
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
    """Mở thư mục chứa file trong Finder/Explorer.

    Chỉ dùng được vì tool chạy local trên máy người dùng. Đường dẫn luôn lấy từ
    DB, không nhận từ client — tránh biến endpoint này thành công cụ mở file tuỳ ý.
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
            # -R chọn sẵn file trong Finder thay vì chỉ mở thư mục.
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
