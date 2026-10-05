"""Run the whole pipeline for several videos in a row, without clicking each step.

This is what blocked mass production: before, every video needed 5 button clicks
(download → transcribe → translate → dub → burn subtitles), and someone had to sit and watch because the next
step could only be clicked once the previous one finished.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.video import Video

logger = logging.getLogger(__name__)

# Number of videos processed at once. Set to 1 because the heavy steps (whisper, demucs) already eat all the CPU
# — running 2 videos in parallel only makes both slow, not to mention RAM contention.
DEFAULT_CONCURRENCY = 1

Step = str

# Pipeline order. "burn" is left out of the default: burning in subtitles is a style
# choice, not a step everyone needs.
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


# Only run 1 batch at a time — several batches at once would fight for CPU and make
# everything slow. Kept in memory like progress_service (losing it on restart is
# correct: a half-done batch cannot continue).
_current: BatchJob | None = None
_lock = asyncio.Lock()


def get_current() -> BatchJob | None:
    return _current


def cancel_current() -> bool:
    """Stop after the currently running video finishes — do not cut in midway so no
    half-written files are left behind."""
    if _current is None or not _current.is_running:
        return False
    _current.cancelled = True
    return True


def _pick_pending_steps(video: Video, steps: list[Step]) -> list[Step]:
    """Skip a step that already has a result — re-running a batch does not redo work from scratch."""
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
    """Build the job and register it as the current batch, running nothing yet.

    Split from `execute_batch` so the API can return the initial state immediately —
    n8n does not have to keep a connection open for the whole processing time.
    """
    global _current

    async with _lock:
        if _current is not None and _current.is_running:
            raise RuntimeError("Đang có batch chạy — dừng batch đó trước.")

        with session_factory() as db:
            videos = db.query(Video).filter(Video.id.in_(video_ids)).all()
            found = {v.id for v in videos}
            items = [BatchItem(video_id=v.id, title=v.title) for v in videos]
            # A nonexistent id must still be reported back, otherwise the caller thinks it ran.
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
    """Run the pipeline for each video. A failing video does not block the remaining videos."""
    # Imported here to avoid an import cycle (pipeline imports batch_service).
    from app.api import pipeline as pipeline_api

    semaphore = asyncio.Semaphore(job.concurrency)

    async def process(item: BatchItem) -> None:
        if item.status == "failed":
            return  # id does not exist, already marked in prepare_batch

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
                except Exception as exc:  # noqa: BLE001 — 1 failing video must not block the whole batch
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
    """Videos that have not finished the whole pipeline — the input source for the next batch."""
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
