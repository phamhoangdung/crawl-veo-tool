"""Chạy cả pipeline cho nhiều video liên tiếp, không phải bấm từng bước.

Đây là thứ chặn việc sản xuất hàng loạt: trước đó mỗi video phải bấm 5 nút
(tải → tách lời → dịch → lồng tiếng → ghép phụ đề), và phải ngồi canh vì bước
sau chỉ bấm được khi bước trước xong.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.video import Video

logger = logging.getLogger(__name__)

# Số video xử lý cùng lúc. Để 1 vì các bước nặng (whisper, demucs) đã ăn hết CPU
# — chạy 2 video song song chỉ làm cả hai cùng chậm, chưa kể tranh RAM.
DEFAULT_CONCURRENCY = 1

Step = str

# Thứ tự pipeline. Bỏ "burn" khỏi mặc định: ghép phụ đề cứng là lựa chọn phong
# cách, không phải bước ai cũng cần.
DEFAULT_STEPS: list[Step] = ["download", "transcribe", "translate", "dub"]


@dataclass
class BatchItem:
    video_id: int
    title: str
    status: str = "pending"
    current_step: str | None = None
    error: str | None = None


@dataclass
class BatchJob:
    id: str
    items: list[BatchItem]
    steps: list[Step]
    concurrency: int = DEFAULT_CONCURRENCY
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    cancelled: bool = False

    @property
    def is_running(self) -> bool:
        return self.finished_at is None and not self.cancelled

    @property
    def done_count(self) -> int:
        return sum(1 for i in self.items if i.status in ("done", "failed", "skipped"))


# Chỉ chạy 1 batch tại một thời điểm — nhiều batch cùng lúc sẽ tranh CPU và làm
# tất cả cùng chậm. Giữ trong bộ nhớ như progress_service (mất khi restart là
# đúng: batch dở không tiếp tục được).
_current: BatchJob | None = None
_lock = asyncio.Lock()


def get_current() -> BatchJob | None:
    return _current


def cancel_current() -> bool:
    """Dừng sau khi video đang chạy xong — không cắt ngang giữa chừng để khỏi
    bỏ lại file dở dang."""
    if _current is None or not _current.is_running:
        return False
    _current.cancelled = True
    return True


def _pick_pending_steps(video: Video, steps: list[Step]) -> list[Step]:
    """Bỏ qua bước đã có kết quả — chạy lại batch không phải làm lại từ đầu."""
    pending: list[Step] = []
    for step in steps:
        if step == "download" and video.local_path:
            continue
        if step == "transcribe" and video.transcript_json:
            continue
        if step == "translate" and any(
            (s.get("translated_text") or "").strip() for s in (video.transcript_json or [])
        ):
            continue
        if step == "dub" and video.dubbed_path:
            continue
        if step == "burn" and video.burned_path:
            continue
        pending.append(step)
    return pending


async def prepare_batch(
    session_factory,
    video_ids: list[int],
    steps: list[Step] | None = None,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> BatchJob:
    """Dựng job và ghi nhận là batch hiện tại, chưa chạy gì.

    Tách khỏi `execute_batch` để API trả trạng thái ban đầu ngay lập tức —
    n8n không phải giữ kết nối mở suốt thời gian xử lý.
    """
    global _current

    async with _lock:
        if _current is not None and _current.is_running:
            raise RuntimeError("Đang có batch chạy — dừng batch đó trước.")

        with session_factory() as db:
            videos = db.query(Video).filter(Video.id.in_(video_ids)).all()
            found = {v.id for v in videos}
            items = [BatchItem(video_id=v.id, title=v.title) for v in videos]
            # Id không tồn tại vẫn phải báo lại, nếu không người gọi tưởng đã chạy.
            items += [
                BatchItem(
                    video_id=vid,
                    title=f"(video {vid})",
                    status="failed",
                    error="Video không tồn tại",
                )
                for vid in video_ids
                if vid not in found
            ]

        job = BatchJob(
            id=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
            items=items,
            steps=steps or DEFAULT_STEPS,
            concurrency=max(1, concurrency),
        )
        _current = job
        return job


async def execute_batch(session_factory, job: BatchJob) -> BatchJob:
    """Chạy pipeline cho từng video. Video lỗi không chặn các video còn lại."""
    # Import ở đây để tránh vòng lặp import (pipeline import batch_service).
    from app.api import pipeline as pipeline_api

    semaphore = asyncio.Semaphore(job.concurrency)

    async def process(item: BatchItem) -> None:
        if item.status == "failed":
            return  # id không tồn tại, đã đánh dấu ở prepare_batch

        async with semaphore:
            if job.cancelled:
                item.status = "skipped"
                return

            item.status = "running"
            with session_factory() as db:
                video = db.get(Video, item.video_id)
                if video is None:
                    item.status = "failed"
                    item.error = "Video không còn tồn tại"
                    return
                pending = _pick_pending_steps(video, job.steps)

            if not pending:
                item.status = "done"
                return

            for step in pending:
                if job.cancelled:
                    item.status = "skipped"
                    return
                item.current_step = step
                try:
                    await pipeline_api.run_step(step, item.video_id)
                except Exception as exc:  # noqa: BLE001 — 1 video lỗi không chặn cả batch
                    logger.exception("Batch: video %s lỗi ở bước %s", item.video_id, step)
                    item.status = "failed"
                    item.error = f"{step}: {exc}"
                    return

            item.current_step = None
            item.status = "done"

    await asyncio.gather(*(process(item) for item in job.items))
    job.finished_at = datetime.now(timezone.utc)
    return job


def list_pending_video_ids(session_factory, limit: int = 50) -> list[int]:
    """Video chưa chạy hết pipeline — nguồn đầu vào cho batch tiếp theo."""
    with session_factory() as db:
        videos = (
            db.query(Video)
            .filter(Video.dubbed_path.is_(None))
            .order_by(Video.created_at.desc())
            .limit(limit)
            .all()
        )
        return [v.id for v in videos]


def summarize(job: BatchJob) -> dict[str, object]:
    counts: dict[str, int] = {}
    for item in job.items:
        counts[item.status] = counts.get(item.status, 0) + 1
    return {
        "id": job.id,
        "total": len(job.items),
        "done": counts.get("done", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "running": counts.get("running", 0),
        "pending": counts.get("pending", 0),
        "is_running": job.is_running,
        "cancelled": job.cancelled,
        "steps": job.steps,
    }
