"""Điểm khởi động cho bản đóng gói (Phase 12) — PyInstaller compile file này thành
executable, Tauri gọi lên làm sidecar. Gọi `uvicorn.run()` trực tiếp bằng code
thay vì qua CLI `--reload` như `scripts/run-backend.mjs` dùng ở bản dev: reload
mode dùng subprocess watcher (WatchFiles) không tương thích với PyInstaller
(watcher cần theo dõi file mã nguồn — bản đóng gói không có mã nguồn dạng file
rời để theo dõi).
"""

import os
import sys

import uvicorn

from app.main import app

if __name__ == "__main__":
    # Tauri chạy backend không có console: stdout/stderr có thể là None, uvicorn gọi
    # .isatty() lên đó sẽ nổ AttributeError. Nhật ký thật đã ghi ra file (logging_setup).
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False, log_level="info")
