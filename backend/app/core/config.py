import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchored to this file's location, not the process CWD — otherwise running uvicorn
# from the repo root (instead of backend/) would not load .env.
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def is_frozen() -> bool:
    """True when running as a packaged executable (PyInstaller, Phase 12) —
    `sys.frozen` is the standard flag PyInstaller sets itself, not a made-up convention."""
    return getattr(sys, "frozen", False)


def app_data_dir() -> Path:
    """Per-OS user data directory — ONLY used when packaged.
    The dev build still uses `backend/storage` next to the source as before (dev behavior
    is unchanged so the development machine needs no reconfiguration)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(
            os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        )
    return base / "VieDubStudio"


def storage_dir() -> Path:
    return (app_data_dir() / "storage") if is_frozen() else (BACKEND_DIR / "storage")


def resource_dir() -> Path:
    """Resources packaged WITH the source (e.g. bundled fonts), as opposed to
    `storage_dir()` which holds user data created at runtime. PyInstaller unpacks
    `datas` into `sys._MEIPASS` at runtime — read from there when packaged, and read
    `app/resources` next to the source when running in dev."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", BACKEND_DIR)) / "app" / "resources"
    return BACKEND_DIR / "app" / "resources"


DEFAULT_DB_PATH = (storage_dir() / "app.db").as_posix()


def _ensure_master_key_file() -> str:
    """Auto-generate MASTER_KEY on the first run of the packaged build and store it in the
    user data directory — end users cannot be asked to fill `.env` by hand like in dev
    (docs/phases/phase-12-desktop-packaging.md)."""
    from cryptography.fernet import Fernet

    key_file = app_data_dir() / "master.key"
    if key_file.exists():
        existing = key_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    key_file.parent.mkdir(parents=True, exist_ok=True)
    new_key = Fernet.generate_key().decode()
    key_file.write_text(new_key, encoding="utf-8")
    return new_key


def _default_master_key() -> str:
    if is_frozen():
        return _ensure_master_key_file()
    raise RuntimeError(
        "MASTER_KEY chưa được cấu hình — copy .env.example thành .env rồi điền "
        'MASTER_KEY (xem docs/phases/phase-0-scaffolding.md mục "Cách chạy dự án").'
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None if is_frozen() else str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
    )

    master_key: str = Field(default_factory=_default_master_key)
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"

    # Phase: performance optimization (P2) — number of worker processes for pure CPU/GPU
    # compute (faster-whisper, SpeechBrain diarization). Defaults to 1 to match current
    # behavior (one heavy job at a time, avoiding RAM contention on a personal machine) —
    # raise via env when deploying on a server with more cores (Phase 18), not guessed upfront.
    cpu_worker_count: int = 1

    # Phase 14 — AI image/video generation. Defaults to "fake" so development costs nothing;
    # set "real" to call the real API (needs a fal.ai key in the pool).
    falai_mode: str = "fake"
    falai_monthly_budget_usd: float = 30.0

    # Only effective when falai_mode="fake" — simulates the real API's latency and errors.
    falai_fake_image_delay_seconds: float = 0.0
    falai_fake_video_delay_seconds: float = 0.0
    falai_fake_quota_error_rate: float = 0.0
    falai_fake_policy_error_rate: float = 0.0
    falai_fake_force_error: str = ""  # "", "quota", "policy"

    # Phase 3 — Douyin. Some endpoints only return full data with a login cookie.
    # When empty, every Douyin action is rejected with instructions, instead of
    # calling the API and getting a confusing error.
    douyin_cookie: str = ""

    # Phase 20 — Discovery screen for downloading many videos at once (bulk selection
    # in the Trending grid). Limits the NUMBER OF VIDEOS downloading in parallel, which is
    # different from the per-video connection count of Phase 21 — two separate layers,
    # do not merge them. Default 3: enough to avoid waiting sequentially, not so many that
    # personal bandwidth clogs or Bilibili rate limiting kicks in.
    download_max_videos: int = 3

    # Phase 21 — faster downloads via HTTP Range splitting. Measured (2026-09-22):
    # 8 streams are ~2.9x faster than 1, 16 streams are WORSE than 8 (contention +
    # TLS handshake overhead) — so hard-capped at 8, not just limited in the UI. Default
    # 1 = the old behavior (straight to `_stream_to_file`, no splitting) — users opt in
    # when they know their machine/network can take it, same philosophy as
    # `cpu_worker_count` above. This is the value used when the DB (table
    # `app_settings`) has no record yet — see `services/settings_service.py`.
    download_connections: int = 1
    # Threshold below which splitting is skipped: files smaller than this download on one
    # stream — splitting only costs an extra HEAD request + TLS handshake for no gain.
    download_part_min_bytes: int = 8 * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
