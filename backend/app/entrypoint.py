"""Điểm khởi động cho bản đóng gói (Phase 12) — PyInstaller compile file này thành
executable, Tauri gọi lên làm sidecar. Gọi `uvicorn.run()` trực tiếp bằng code
thay vì qua CLI `--reload` như `scripts/run-backend.mjs` dùng ở bản dev: reload
mode dùng subprocess watcher (WatchFiles) không tương thích với PyInstaller
(watcher cần theo dõi file mã nguồn — bản đóng gói không có mã nguồn dạng file
rời để theo dõi).
"""

import multiprocessing
import os
import sys

# Cờ để `adapters/demucs.py` chạy lại chính executable này làm tiến trình Demucs
# riêng (bản đóng gói không có `python -m demucs` vì không có interpreter rời).
DEMUCS_FLAG = "--run-demucs"

if __name__ == "__main__":
    # Bản đóng gói trên Windows: `ProcessPoolExecutor` (core/worker_pool.py) sinh
    # worker bằng cách chạy lại chính file .exe này với cờ `--multiprocessing-fork`.
    # Thiếu dòng này, worker chạy lại cả đoạn khởi động uvicorn bên dưới (đụng cổng
    # đang bận) rồi thoát ngay -> "A child process terminated abruptly".
    multiprocessing.freeze_support()

    # Tauri chạy backend không có console: stdout/stderr có thể là None, uvicorn và
    # tqdm (Demucs) gọi .isatty()/.write() lên đó sẽ nổ AttributeError. Nhật ký thật
    # đã ghi ra file (logging_setup).
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))

    if len(sys.argv) > 1 and sys.argv[1] == DEMUCS_FLAG:
        # Import trễ + nằm trước `app.main` để tiến trình Demucs không phải nạp cả server.
        from demucs.separate import main as demucs_main

        demucs_main(sys.argv[2:])
        sys.exit(0)

    import uvicorn

    from app.main import app

    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False, log_level="info")
