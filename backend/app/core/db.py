from collections.abc import Generator
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


def _ensure_sqlite_dir(database_url: str) -> None:
    """Tạo sẵn thư mục chứa file SQLite.

    `storage/` nằm trong .gitignore nên máy mới clone về sẽ không có thư mục
    này, và SQLite không tự tạo thư mục cha — nó chỉ báo "unable to open
    database file".
    """
    if not database_url.startswith("sqlite"):
        return

    # sqlite:///relative/path → "/relative/path"; sqlite:////abs/path → "//abs/path".
    # Bỏ đúng 1 dấu "/" đầu để giữ nguyên tính tuyệt đối/tương đối của đường dẫn.
    raw_path = urlparse(database_url).path
    db_path = raw_path[1:] if raw_path.startswith("/") else raw_path
    if not db_path or db_path == ":memory:":
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(get_settings().database_url)

engine = create_engine(
    get_settings().database_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_schema_columns() -> None:
    """Thêm các cột mới vào bảng đã tồn tại.

    `Base.metadata.create_all()` chỉ tạo bảng mới, không sửa bảng cũ — thêm cột
    vào model mà không migrate sẽ khiến mọi query bảng đó lỗi "no such column".
    Dự án cá nhân, thay đổi schema thưa nên chưa cần Alembic; chỉ xử lý thêm cột
    nullable, đủ cho nhu cầu hiện tại.
    """
    expected: dict[str, dict[str, str]] = {
        "videos": {"cover_url": "VARCHAR"},
    }

    with engine.begin() as conn:
        for table, columns in expected.items():
            existing = {
                row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            if not existing:
                continue  # bảng chưa tồn tại — create_all() sẽ tạo với đủ cột
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")
