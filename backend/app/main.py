import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import cả package models để `create_all()` thấy hết bảng — model nào không được
# module nào import thì bảng của nó sẽ không được tạo.
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
from app.core.logging_setup import setup_file_logging
from app.models.user import User
from app.services import category_service, storage_cleanup_service, trending_service

logging.basicConfig(level=logging.INFO)
setup_file_logging()

app = FastAPI(title="Crawl Video Tool API")

app.add_middleware(
    CORSMiddleware,
    # Vite tự đổi cổng (5173, 5174...) nếu cổng mặc định đang bận — cho phép mọi
    # cổng localhost thay vì cố định 1 cổng, tránh lỗi CORS vặt vãnh lúc dev.
    # Bản đóng gói Tauri chạy webview ở origin tauri.localhost (Windows) hoặc
    # tauri://localhost (macOS/Linux), không phải localhost:<cổng>.
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


# Giữ tham chiếu tới task nền: mất tham chiếu thì Python có thể thu gom task
# giữa chừng, và lúc tắt app không còn gì để huỷ.
_cleanup_task: asyncio.Task | None = None
_snapshot_task: asyncio.Task | None = None


@app.on_event("startup")
async def start_background_jobs() -> None:
    """Dọn thư mục job cũ định kỳ ngay trong process backend (Phase 6).

    Handler riêng và `async` có chủ đích: `asyncio.create_task` cần event loop
    đang chạy, mà handler startup đồng bộ ở trên không đảm bảo điều đó.
    """
    global _cleanup_task, _snapshot_task
    _cleanup_task = asyncio.create_task(storage_cleanup_service.run_periodic_cleanup())
    # Phase 20: ghi snapshot chuyên mục đều đặn, không phụ thuộc ai có mở
    # trang Báo cáo xu hướng hay không — xem docstring `run_periodic_snapshot`.
    _snapshot_task = asyncio.create_task(trending_service.run_periodic_snapshot(SessionLocal))


@app.on_event("shutdown")
async def stop_background_jobs() -> None:
    """Huỷ hẳn task nền khi tắt: bỏ mặc thì uvicorn đợi task không bao giờ kết
    thúc, app đóng gói (Phase 12) sẽ treo lúc thoát."""
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
    """Không để worker process của `worker_pool` (Phase: tối ưu hiệu năng P2) mồ
    côi khi server tắt."""
    worker_pool.shutdown()


def _ensure_seed_categories() -> None:
    with SessionLocal() as db:
        category_service.ensure_default_categories(db)


def _ensure_default_user() -> None:
    """MVP chỉ có 1 user cố định (id=1) — xem docs/overview/plan.md phần multi-tenant."""
    with SessionLocal() as db:
        if db.get(User, 1) is None:
            db.add(User(id=1))
            db.commit()
