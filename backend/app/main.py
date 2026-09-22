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
    timeline,
    topics,
    translate,
    trending,
    youtube,
)
from app.core import worker_pool
from app.core.db import Base, SessionLocal, engine, ensure_schema_columns
from app.models.category import Category
from app.models.user import User
from app.services import storage_cleanup_service

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Crawl Video Tool API")

app.add_middleware(
    CORSMiddleware,
    # Vite tự đổi cổng (5173, 5174...) nếu cổng mặc định đang bận — cho phép mọi
    # cổng localhost thay vì cố định 1 cổng, tránh lỗi CORS vặt vãnh lúc dev.
    allow_origin_regex=r"http://localhost:\d+",
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


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns()
    _ensure_default_user()
    _ensure_seed_categories()


# Giữ tham chiếu tới task nền: mất tham chiếu thì Python có thể thu gom task
# giữa chừng, và lúc tắt app không còn gì để huỷ.
_cleanup_task: asyncio.Task | None = None


@app.on_event("startup")
async def start_background_jobs() -> None:
    """Dọn thư mục job cũ định kỳ ngay trong process backend (Phase 6).

    Handler riêng và `async` có chủ đích: `asyncio.create_task` cần event loop
    đang chạy, mà handler startup đồng bộ ở trên không đảm bảo điều đó.
    """
    global _cleanup_task
    _cleanup_task = asyncio.create_task(storage_cleanup_service.run_periodic_cleanup())


@app.on_event("shutdown")
async def stop_background_jobs() -> None:
    """Huỷ hẳn task nền khi tắt: bỏ mặc thì uvicorn đợi task không bao giờ kết
    thúc, app đóng gói (Phase 12) sẽ treo lúc thoát."""
    if _cleanup_task is None:
        return
    _cleanup_task.cancel()
    try:
        await _cleanup_task
    except asyncio.CancelledError:
        pass


@app.on_event("shutdown")
def stop_worker_pool() -> None:
    """Không để worker process của `worker_pool` (Phase: tối ưu hiệu năng P2) mồ
    côi khi server tắt."""
    worker_pool.shutdown()


# Chuyên mục mồi để trang Trending không rỗng ở lần chạy đầu; danh sách đầy đủ
# được phát hiện tự động qua POST /api/trending/bilibili/categories/refresh.
_SEED_CATEGORIES: list[tuple[int, str, str, str]] = [
    (211, "美食记录", "Ẩm thực - Ghi chép", "Ẩm thực"),
    (76, "美食制作", "Ẩm thực - Nấu ăn", "Ẩm thực"),
    (21, "日常", "Đời sống thường ngày", "Đời sống"),
    (138, "搞笑", "Hài hước", "Giải trí"),
    (218, "喵星人", "Động vật - Mèo", "Động vật"),
    (219, "汪星人", "Động vật - Chó", "Động vật"),
]


def _ensure_seed_categories() -> None:
    """Chỉ chèn khi bảng còn trống — tránh ghi đè lựa chọn của người dùng."""
    with SessionLocal() as db:
        if db.query(Category).count() > 0:
            return
        for rid, name_zh, name_vi, group in _SEED_CATEGORIES:
            db.add(
                Category(
                    rid=rid,
                    name_zh=name_zh,
                    name_vi=name_vi,
                    group_name=group,
                    is_followed=rid in (211, 138, 21),
                )
            )
        db.commit()


def _ensure_default_user() -> None:
    """MVP chỉ có 1 user cố định (id=1) — xem docs/overview/plan.md phần multi-tenant."""
    with SessionLocal() as db:
        if db.get(User, 1) is None:
            db.add(User(id=1))
            db.commit()
