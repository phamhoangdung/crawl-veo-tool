"""Đọc đuôi file nhật ký backend cho màn "Nhật ký hệ thống"."""

from dataclasses import dataclass
from pathlib import Path

from app.core.logging_setup import log_file_path

# Đọc tối đa ngần này byte cuối file — đủ cho vài nghìn dòng mà không nạp cả file.
_TAIL_BYTES = 512_000


@dataclass
class LogTail:
    path: Path
    exists: bool
    lines: list[str]


def read_tail(max_lines: int, path: Path | None = None) -> LogTail:
    path = path or log_file_path()
    if not path.is_file():
        return LogTail(path=path, exists=False, lines=[])
    with path.open("rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - _TAIL_BYTES))
        data = f.read()
    lines = data.decode("utf-8", errors="replace").splitlines()
    if size > _TAIL_BYTES and lines:
        lines = lines[1:]  # dòng đầu có thể bị cắt giữa chừng
    return LogTail(path=path, exists=True, lines=lines[-max_lines:])
