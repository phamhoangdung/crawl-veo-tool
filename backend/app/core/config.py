import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Neo theo vị trí file này, không theo CWD của process — nếu không, chạy uvicorn
# từ root repo (thay vì từ backend/) sẽ không load được .env.
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def is_frozen() -> bool:
    """True khi chạy dưới dạng executable đã đóng gói (PyInstaller, Phase 12) —
    `sys.frozen` là cờ chuẩn PyInstaller tự set, không phải quy ước tự nghĩ ra."""
    return getattr(sys, "frozen", False)


def app_data_dir() -> Path:
    """Thư mục dữ liệu người dùng theo chuẩn từng OS — CHỈ dùng khi đã đóng gói.
    Bản dev vẫn dùng `backend/storage` cạnh mã nguồn như trước (không đổi hành vi
    dev để tránh phải cấu hình lại máy đang phát triển)."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "VieDubStudio"


def _storage_dir() -> Path:
    return (app_data_dir() / "storage") if is_frozen() else (BACKEND_DIR / "storage")


DEFAULT_DB_PATH = (_storage_dir() / "app.db").as_posix()


def _ensure_master_key_file() -> str:
    """Tự sinh MASTER_KEY lần đầu chạy bản đóng gói, lưu vào thư mục dữ liệu
    người dùng — không thể bắt người dùng cuối tự điền `.env` như bản dev
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
        "MASTER_KEY (xem docs/phases/phase-0-scaffolding.md mục \"Cách chạy dự án\")."
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None if is_frozen() else str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
    )

    master_key: str = Field(default_factory=_default_master_key)
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"

    # Phase 14 — sinh ảnh/video AI. Mặc định "fake" để phát triển không tốn phí;
    # đặt "real" khi muốn gọi API thật (cần key fal.ai trong pool).
    falai_mode: str = "fake"
    falai_monthly_budget_usd: float = 30.0

    # Chỉ có tác dụng khi falai_mode="fake" — mô phỏng độ trễ và lỗi của API thật.
    falai_fake_image_delay_seconds: float = 0.0
    falai_fake_video_delay_seconds: float = 0.0
    falai_fake_quota_error_rate: float = 0.0
    falai_fake_policy_error_rate: float = 0.0
    falai_fake_force_error: str = ""  # "", "quota", "policy"


@lru_cache
def get_settings() -> Settings:
    return Settings()
