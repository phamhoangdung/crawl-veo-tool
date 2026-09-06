import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_keys, crawl, health, pipeline, trending
from app.core.db import Base, SessionLocal, engine
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


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_default_user()


def _ensure_default_user() -> None:
    """MVP chỉ có 1 user cố định (id=1) — xem docs/overview/plan.md phần multi-tenant."""
    with SessionLocal() as db:
        if db.get(User, 1) is None:
            db.add(User(id=1))
            db.commit()
