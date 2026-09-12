"""Theo dõi các lần sinh ảnh/clip chạy nền (Phase 14).

Vì sao cần: sinh 1 clip bằng provider thật mất 1-5 phút. Gọi đồng bộ thì trình
duyệt treo suốt thời gian đó, và chỉ cần người dùng lỡ tay F5 là mất dấu kết quả
— trong khi tiền thì đã tiêu rồi. Job store giữ lại kết quả để quay lại xem được.

Giữ trong bộ nhớ như `progress_service`: job dở dang không tiếp tục được sau khi
restart, nên lưu DB cũng không cứu được gì. Khác `progress_service` ở chỗ job ở
đây KHÔNG gắn với video hay dự án nào — một lần sinh ảnh lẻ ở AI Studio không có
chủ thể nào để neo vào.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

JobKind = Literal["keyframe", "clip"]
JobStatus = Literal["running", "done", "failed"]

# Giữ lại lịch sử gần đây thôi — đây là bộ nhớ tạm, không phải sổ cái. Chi phí
# thật đã ghi vào bảng `GeneratedAsset`, mất job cũ không mất dữ liệu nào.
_MAX_JOBS = 50


@dataclass
class GenerationJob:
    id: str
    kind: JobKind
    # Prompt rút gọn, để nhận ra job nào là job nào trong danh sách.
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
# dict giữ thứ tự chèn (Python 3.7+), nên job cũ nhất luôn là phần tử đầu.
_jobs: dict[str, GenerationJob] = {}


def create(kind: JobKind, label: str) -> GenerationJob:
    with _lock:
        job = GenerationJob(id=uuid.uuid4().hex, kind=kind, label=label[:120])
        _jobs[job.id] = job
        while len(_jobs) > _MAX_JOBS:
            # `next(iter(...))` là job cũ nhất — xoá từ đầu chứ không xoá bừa.
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
    """Mới nhất trước — đúng thứ tự người dùng muốn nhìn khi quay lại trang."""
    with _lock:
        return list(reversed(_jobs.values()))


def clear() -> None:
    """Chỉ dùng trong test: dict ở tầng module sống xuyên suốt nhiều test."""
    with _lock:
        _jobs.clear()
