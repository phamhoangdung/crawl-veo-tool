import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import the whole models package so `create_all()` sees every table — a model that no
# module imports will not get its table created.
from app import models  # noqa: F401
from app.api import (
    ai_generation,
    api_keys,
    assets,
    batch,
    channels,
    clips,
    crawl,
    downloads,
    files,
    fonts,
    health,
    image_proxy,
    library,
    mcp_tokens,
    metadata,
    pipeline,
    projects,
    settings,
    system,
    timeline,
    topics,
    translate,
    trending,
    video_import,
    youtube,
)
from app.core import worker_pool
from app.core.db import Base, SessionLocal, engine, ensure_schema_columns
from app.core.ffmpeg_locator import ensure_ffmpeg_on_path
from app.core.logging_setup import setup_file_logging
from app.models.user import User
from app.services import category_service, storage_cleanup_service, trending_service

logging.basicConfig(level=logging.INFO)
setup_file_logging()

app = FastAPI(title="Crawl Video Tool API")

app.add_middleware(
    CORSMiddleware,
    # Vite changes port (5173, 5174...) if the default port is busy — allow any
    # localhost port instead of pinning one, avoiding petty CORS errors in dev.
    # The Tauri packaged build runs the webview at origin tauri.localhost (Windows) or
    # tauri://localhost (macOS/Linux), not localhost:<port>.
    allow_origin_regex=r"http://localhost:\d+|https?://tauri\.localhost|tauri://localhost",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(crawl.router)
app.include_router(trending.router)
app.include_router(api_keys.router)
app.include_router(pipeline.router)
app.include_router(timeline.router)
app.include_router(clips.router)
app.include_router(library.router)
app.include_router(image_proxy.router)
app.include_router(downloads.router)
app.include_router(files.router)
app.include_router(fonts.router)
app.include_router(batch.router)
app.include_router(metadata.router)
app.include_router(assets.router)
app.include_router(translate.router)
app.include_router(ai_generation.router)
app.include_router(mcp_tokens.router)
app.include_router(projects.router)
app.include_router(youtube.router)
app.include_router(topics.router)
app.include_router(settings.router)
app.include_router(channels.router)
app.include_router(system.router)
app.include_router(video_import.router)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns()
    _ensure_default_user()
    _ensure_seed_categories()
    if not ensure_ffmpeg_on_path():
        logging.getLogger(__name__).warning(
            "Không tìm thấy ffmpeg — tải/ghép video sẽ lỗi tới khi cài (winget install Gyan.FFmpeg)."
        )


# Keep a reference to the background task: without one Python may garbage-collect the task
# midway, and on shutdown there is nothing left to cancel.
_cleanup_task: asyncio.Task | None = None
_snapshot_task: asyncio.Task | None = None


@app.on_event("startup")
async def start_background_jobs() -> None:
    """Periodically clean old job directories inside the backend process (Phase 6).

    A separate, `async` handler on purpose: `asyncio.create_task` needs a running
    event loop, which the synchronous startup handler above does not guarantee.
    """
    global _cleanup_task, _snapshot_task
    _cleanup_task = asyncio.create_task(storage_cleanup_service.run_periodic_cleanup())
    # Phase 20: write category snapshots regularly, regardless of whether anyone has the
    # trend report page open — see the `run_periodic_snapshot` docstring.
    _snapshot_task = asyncio.create_task(trending_service.run_periodic_snapshot(SessionLocal))


@app.on_event("shutdown")
async def stop_background_jobs() -> None:
    """Cancel the background task for good on shutdown: if left alone uvicorn waits for a task that never
    ends, and the packaged app (Phase 12) would hang on exit."""
    for task in (_cleanup_task, _snapshot_task):
        if task is None:
            continue
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.on_event("shutdown")
def stop_worker_pool() -> None:
    """Do not leave the `worker_pool` worker processes (Phase: performance optimization P2) as
    orphans when the server stops."""
    worker_pool.shutdown()


def _ensure_seed_categories() -> None:
    with SessionLocal() as db:
        category_service.ensure_default_categories(db)


def _ensure_default_user() -> None:
    """The MVP has a single fixed user (id=1) — see docs/overview/plan.md, multi-tenant section."""
    with SessionLocal() as db:
        if db.get(User, 1) is None:
            db.add(User(id=1))
            db.commit()
