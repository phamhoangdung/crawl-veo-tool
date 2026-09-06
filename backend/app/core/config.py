from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Neo theo vị trí file này, không theo CWD của process — nếu không, chạy uvicorn
# từ root repo (thay vì từ backend/) sẽ không load được .env.
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = (BACKEND_DIR / "storage" / "app.db").as_posix()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8"
    )

    master_key: str
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
