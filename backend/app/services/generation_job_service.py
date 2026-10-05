"""Track image/clip generations running in the background (Phase 14).

Why it is needed: generating 1 clip with a real provider takes 1-5 minutes. Calling synchronously freezes the
browser for that whole time, and all it takes is the user accidentally hitting F5 to lose track of the result
— while the money is already spent. The job store keeps the result so it can be viewed again later.

Kept in memory like `progress_service`: a half-done job cannot continue after a
restart, so storing it in the DB would save nothing. Unlike `progress_service`, a job here
is NOT tied to any video or project — a one-off image generation in AI Studio has no
subject to anchor to.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

JobKind = Literal["keyframe", "clip"]
JobStatus = Literal["running", "done", "failed"]

# Keep only recent history — this is scratch memory, not a ledger. The real cost
# was already written to the `GeneratedAsset` table, losing an old job loses no data.
_MAX_JOBS = 50


@dataclass
class GenerationJob:
    id: str
    kind: JobKind
    # Shortened prompt, to recognize which job is which in the list.
    label: str
    status: JobStatus = "running"
    asset_id: int | None = None
    file_path: str | None = None
    cost_usd: float = 0.0
    from_cache: bool = False
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None


_lock = threading.Lock()
# dict keeps insertion order (Python 3.7+), so the oldest job is always the first element.
_jobs: dict[str, GenerationJob] = {}


def create(kind: JobKind, label: str) -> GenerationJob:
    with _lock:
        job = GenerationJob(id=uuid.uuid4().hex, kind=kind, label=label[:120])
        _jobs[job.id] = job
        while len(_jobs) > _MAX_JOBS:
            # `next(iter(...))` is the oldest job — delete from the front, not at random.
            del _jobs[next(iter(_jobs))]
        return job


def finish_ok(
    job_id: str,
    *,
    asset_id: int,
    file_path: str,
    cost_usd: float,
    from_cache: bool,
) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "done"
        job.asset_id = asset_id
        job.file_path = file_path
        job.cost_usd = cost_usd
        job.from_cache = from_cache
        job.finished_at = datetime.now(timezone.utc)


def finish_error(job_id: str, error: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        job.status = "failed"
        job.error = error[:500]
        job.finished_at = datetime.now(timezone.utc)


def get(job_id: str) -> GenerationJob | None:
    with _lock:
        return _jobs.get(job_id)


def list_recent() -> list[GenerationJob]:
    """Newest first — the order users want to see when coming back to the page."""
    with _lock:
        return list(reversed(_jobs.values()))


def clear() -> None:
    """Test use only: the module-level dict lives across many tests."""
    with _lock:
        _jobs.clear()
