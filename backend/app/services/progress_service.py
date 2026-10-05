"""Track running tasks: video download, transcription, translation, dubbing.

Kept in memory rather than written to the DB: progress only matters while the task runs,
and losing it on restart is correct (an interrupted task cannot continue anyway). The tool runs 1 process
so a plain dict is enough; if it later moves to Celery/multiple workers it must change
to Redis.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Literal

TaskKind = Literal[
    "download", "transcribe", "translate", "diarize", "dub", "burn", "render_project"
]

# A task can belong to 1 video (crawl pipeline) or 1 multi-scene project
# (Phase 15). Distinguished explicitly with a separate field instead of encoding into the id —
# stuffing project_id into the video_id slot would make every query by video_id silently return
# empty instead of reporting an error.
SubjectType = Literal["video", "project"]

Stage = Literal[
    "pending",
    # Phase 20 — bulk download via the Discovery screen: the video is queued waiting for its turn
    # (status=DOWNLOADING already set but no semaphore slot obtained yet).
    "queued",
    # Video download — "video"/"audio" (2 sequential stages) are no longer used since
    # Phase 21 (video+audio now download in parallel), kept in the Literal so the old
    # data type is not broken, replaced by a single "downloading" stage.
    "video",
    "audio",
    "downloading",
    "merging",
    # Processing steps
    "separating",
    "transcribing",
    "translating",
    "diarizing",
    "synthesizing",
    "muxing",
    "burning",
    # Building a multi-scene project video (Phase 15)
    "generating",
    "rendering",
    # Finished
    "done",
    "failed",
]

_STAGE_LABELS: dict[str, str] = {
    "pending": "Đang chuẩn bị",
    "queued": "Đang chờ lượt",
    "video": "Đang tải hình",
    "audio": "Đang tải tiếng",
    "downloading": "Đang tải",
    "merging": "Đang ghép",
    "separating": "Đang tách nhạc nền",
    "transcribing": "Đang tách lời thoại",
    "translating": "Đang dịch",
    "diarizing": "Đang phân vai người nói",
    "synthesizing": "Đang tạo giọng đọc",
    "muxing": "Đang ghép âm thanh",
    "burning": "Đang ghép phụ đề",
    "generating": "Đang sinh các cảnh",
    "rendering": "Đang ghép video",
    "done": "Hoàn tất",
    "failed": "Thất bại",
}

_KIND_LABELS: dict[str, str] = {
    "download": "Tải video",
    "transcribe": "Tách lời thoại",
    "translate": "Dịch phụ đề",
    "diarize": "Phân vai người nói",
    "dub": "Lồng tiếng",
    "burn": "Ghép phụ đề",
    "render_project": "Dựng video dự án",
}


@dataclass
class TaskProgress:
    # With subject_type="project" this is the project_id, not a video_id.
    # The field name is kept so all the APIs/frontend already using it need not change.
    video_id: int
    title: str
    kind: TaskKind = "download"
    subject_type: SubjectType = "video"
    stage: Stage = "pending"
    # Counted in bytes (download) or in work units (sentences translated/read).
    current: int = 0
    total: int | None = None
    started_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    error: str | None = None

    @property
    def percent(self) -> float:
        """Percentage of the current stage. Returns 0 when the total is unknown."""
        if not self.total:
            return 0.0
        return min(100.0, self.current / self.total * 100)

    @property
    def is_running(self) -> bool:
        return self.stage not in ("done", "failed")

    @property
    def speed_per_sec(self) -> float:
        elapsed = max(self.updated_at - self.started_at, 0.001)
        return self.current / elapsed

    @property
    def stage_label(self) -> str:
        return _STAGE_LABELS.get(self.stage, self.stage)

    @property
    def kind_label(self) -> str:
        return _KIND_LABELS.get(self.kind, self.kind)


# Written from inside tasks, read from other requests — a lock is needed.
_lock = threading.Lock()
# Keyed by (subject_type, subject_id, kind): 1 video running several kinds of tasks
# does not overwrite them, and project id=7 does not touch video id=7.
_active: dict[tuple[str, int, str], TaskProgress] = {}


def start(
    video_id: int,
    title: str,
    kind: TaskKind = "download",
    *,
    subject_type: SubjectType = "video",
) -> TaskProgress:
    with _lock:
        progress = TaskProgress(
            video_id=video_id, title=title, kind=kind, subject_type=subject_type
        )
        _active[(subject_type, video_id, kind)] = progress
        return progress


def set_stage(
    video_id: int,
    stage: Stage,
    total: int | None = None,
    kind: TaskKind = "download",
    *,
    subject_type: SubjectType = "video",
) -> None:
    with _lock:
        progress = _active.get((subject_type, video_id, kind))
        if progress is None:
            return
        progress.stage = stage
        # Each stage counts from the start again so the percentage reflects the running stage.
        progress.current = 0
        progress.total = total
        progress.started_at = time.monotonic()
        progress.updated_at = progress.started_at


def advance(
    video_id: int,
    amount: int,
    kind: TaskKind = "download",
    *,
    subject_type: SubjectType = "video",
) -> None:
    with _lock:
        progress = _active.get((subject_type, video_id, kind))
        if progress is None:
            return
        progress.current += amount
        progress.updated_at = time.monotonic()


def finish(
    video_id: int,
    error: str | None = None,
    kind: TaskKind = "download",
    *,
    subject_type: SubjectType = "video",
) -> None:
    with _lock:
        progress = _active.get((subject_type, video_id, kind))
        if progress is None:
            return
        progress.stage = "failed" if error else "done"
        progress.error = error
        progress.updated_at = time.monotonic()


def clear(
    video_id: int,
    kind: TaskKind | None = None,
    *,
    subject_type: SubjectType = "video",
) -> None:
    """Remove 1 task from the list; without kind, remove every task of the video."""
    with _lock:
        if kind is not None:
            _active.pop((subject_type, video_id, kind), None)
            return
        for key in [k for k in _active if k[0] == subject_type and k[1] == video_id]:
            _active.pop(key, None)


def clear_finished() -> int:
    """Clear every finished task. Returns the number of entries removed."""
    with _lock:
        keys = [key for key, p in _active.items() if not p.is_running]
        for key in keys:
            _active.pop(key, None)
        return len(keys)


def is_running(
    video_id: int, kind: TaskKind, *, subject_type: SubjectType = "video"
) -> bool:
    with _lock:
        progress = _active.get((subject_type, video_id, kind))
        return progress is not None and progress.is_running


def snapshot() -> list[TaskProgress]:
    """A copy of the task list to return to the API without holding the lock long."""
    with _lock:
        return list(_active.values())
