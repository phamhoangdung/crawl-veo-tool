"""Theo dõi tác vụ đang chạy: tải video, tách lời thoại, dịch, lồng tiếng.

Giữ trong bộ nhớ chứ không ghi DB: tiến độ chỉ có ý nghĩa trong lúc tác vụ chạy,
mất khi restart là đúng (tác vụ dở cũng không tiếp tục được). Tool chạy 1 process
nên dict thường là đủ; nếu sau này chuyển sang Celery/nhiều worker thì phải đổi
sang Redis.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Literal

TaskKind = Literal["download", "transcribe", "translate", "dub", "burn"]

Stage = Literal[
    "pending",
    # Tải video
    "video",
    "audio",
    "merging",
    # Các bước xử lý
    "separating",
    "transcribing",
    "translating",
    "synthesizing",
    "muxing",
    "burning",
    # Kết thúc
    "done",
    "failed",
]

_STAGE_LABELS: dict[str, str] = {
    "pending": "Đang chuẩn bị",
    "video": "Đang tải hình",
    "audio": "Đang tải tiếng",
    "merging": "Đang ghép",
    "separating": "Đang tách nhạc nền",
    "transcribing": "Đang tách lời thoại",
    "translating": "Đang dịch",
    "synthesizing": "Đang tạo giọng đọc",
    "muxing": "Đang ghép âm thanh",
    "burning": "Đang ghép phụ đề",
    "done": "Hoàn tất",
    "failed": "Thất bại",
}

_KIND_LABELS: dict[str, str] = {
    "download": "Tải video",
    "transcribe": "Tách lời thoại",
    "translate": "Dịch phụ đề",
    "dub": "Lồng tiếng",
    "burn": "Ghép phụ đề",
}


@dataclass
class TaskProgress:
    video_id: int
    title: str
    kind: TaskKind = "download"
    stage: Stage = "pending"
    # Đếm theo byte (tải) hoặc theo đơn vị việc (số câu đã dịch/đọc).
    current: int = 0
    total: int | None = None
    started_at: float = field(default_factory=time.monotonic)
    updated_at: float = field(default_factory=time.monotonic)
    error: str | None = None

    @property
    def percent(self) -> float:
        """Phần trăm của chặng hiện tại. Không biết tổng thì trả 0."""
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


# Ghi từ trong tác vụ, đọc từ request khác — cần khoá.
_lock = threading.Lock()
# Khoá theo (video_id, kind) để 1 video chạy nhiều loại tác vụ không ghi đè nhau.
_active: dict[tuple[int, str], TaskProgress] = {}


def start(video_id: int, title: str, kind: TaskKind = "download") -> TaskProgress:
    with _lock:
        progress = TaskProgress(video_id=video_id, title=title, kind=kind)
        _active[(video_id, kind)] = progress
        return progress


def set_stage(
    video_id: int,
    stage: Stage,
    total: int | None = None,
    kind: TaskKind = "download",
) -> None:
    with _lock:
        progress = _active.get((video_id, kind))
        if progress is None:
            return
        progress.stage = stage
        # Mỗi chặng đếm lại từ đầu để phần trăm phản ánh đúng chặng đang chạy.
        progress.current = 0
        progress.total = total
        progress.started_at = time.monotonic()
        progress.updated_at = progress.started_at


def advance(video_id: int, amount: int, kind: TaskKind = "download") -> None:
    with _lock:
        progress = _active.get((video_id, kind))
        if progress is None:
            return
        progress.current += amount
        progress.updated_at = time.monotonic()


def finish(video_id: int, error: str | None = None, kind: TaskKind = "download") -> None:
    with _lock:
        progress = _active.get((video_id, kind))
        if progress is None:
            return
        progress.stage = "failed" if error else "done"
        progress.error = error
        progress.updated_at = time.monotonic()


def clear(video_id: int, kind: TaskKind | None = None) -> None:
    """Bỏ 1 tác vụ khỏi danh sách; không truyền kind thì bỏ mọi tác vụ của video."""
    with _lock:
        if kind is not None:
            _active.pop((video_id, kind), None)
            return
        for key in [k for k in _active if k[0] == video_id]:
            _active.pop(key, None)


def clear_finished() -> int:
    """Dọn mọi tác vụ đã kết thúc. Trả về số mục đã bỏ."""
    with _lock:
        keys = [key for key, p in _active.items() if not p.is_running]
        for key in keys:
            _active.pop(key, None)
        return len(keys)


def is_running(video_id: int, kind: TaskKind) -> bool:
    with _lock:
        progress = _active.get((video_id, kind))
        return progress is not None and progress.is_running


def snapshot() -> list[TaskProgress]:
    """Bản sao danh sách tác vụ để trả cho API mà không giữ khoá lâu."""
    with _lock:
        return list(_active.values())
