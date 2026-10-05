"""Entry point for the packaged build (Phase 12) — PyInstaller compiles this file into an
executable that Tauri launches as a sidecar. Calls `uvicorn.run()` directly in code
instead of through the `--reload` CLI that `scripts/run-backend.mjs` uses in dev: reload
mode uses a subprocess watcher (WatchFiles) which is incompatible with PyInstaller
(the watcher needs to follow source files — the packaged build has no loose source
files to follow).
"""

import multiprocessing
import os
import sys

# Flag so `adapters/demucs.py` can re-run this very executable as a separate Demucs
# process (the packaged build has no `python -m demucs` since there is no standalone interpreter).
DEMUCS_FLAG = "--run-demucs"

if __name__ == "__main__":
    # Packaged build on Windows: `ProcessPoolExecutor` (core/worker_pool.py) spawns
    # workers by re-running this .exe with the `--multiprocessing-fork` flag.
    # Without this line, workers would re-run the whole uvicorn startup below (hitting the busy
    # port) and exit immediately -> "A child process terminated abruptly".
    multiprocessing.freeze_support()

    # Tauri runs the backend without a console: stdout/stderr may be None, and uvicorn and
    # tqdm (Demucs) call .isatty()/.write() on them, which would raise AttributeError. The real
    # log is already written to a file (logging_setup).
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))

    if len(sys.argv) > 1 and sys.argv[1] == DEMUCS_FLAG:
        # Late import, before `app.main`, so the Demucs process does not load the whole
        # server. The AI pack must be on sys.path first (demucs/torch live there).
        from app.core import packs

        packs.require_ai()
        from demucs.separate import main as demucs_main

        demucs_main(sys.argv[2:])
        sys.exit(0)

    import uvicorn

    from app.main import app

    port = int(os.environ.get("BACKEND_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False, log_level="info")
