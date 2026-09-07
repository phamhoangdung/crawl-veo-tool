import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    api_keys,
    clips,
    crawl,
    downloads,
    files,
    health,
    image_proxy,
    library,
    pipeline,
    timeline,
    trending,
)
from app.core.db import Base, SessionLocal, engine, ensure_schema_columns
from app.models.category import Category
from app.models.user import User

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


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_columns()
    _ensure_default_user()
    _ensure_seed_categories()


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
