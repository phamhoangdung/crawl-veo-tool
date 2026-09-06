import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.core.db import Base, engine
from app import models  # noqa: F401  (import needed so models register on Base before create_all)

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Crawl Video Tool API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
