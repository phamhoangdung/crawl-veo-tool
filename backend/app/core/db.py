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
    _migrate_api_keys_pool()

    # VideoStatus.PAUSED_QUOTA (Phase 8) không cần migrate cột — SQLite lưu Enum
    # dưới dạng VARCHAR không ràng buộc, thêm 1 giá trị enum Python mới ở
    # app/models/video.py là đủ, không đụng tới cột `status` đã có sẵn.
    expected: dict[str, dict[str, str]] = {
        "videos": {
            "cover_url": "VARCHAR",
            "timeline_json": "JSON",
            "timeline_rendered_path": "VARCHAR",
        },
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


def _migrate_api_keys_pool() -> None:
    """Phase 8: bảng `api_keys` cũ có `UNIQUE(user_id, provider)` (1 key/provider).

    SQLite lưu UNIQUE table-constraint dưới dạng "autoindex" (`sqlite_autoindex_*`)
    — loại index này KHÔNG thể xoá bằng `DROP INDEX`, chỉ có cách dựng lại bảng
    (rename → tạo bảng mới đúng schema model hiện tại → copy dữ liệu → xoá bảng cũ).
    Idempotent: chỉ chạy khi còn phát hiện constraint cũ, không ảnh hưởng lần chạy
    sau khi đã migrate xong.
    """
    # Import cục bộ: app.models.api_key import Base từ chính module này (db.py) —
    # import ở đầu file sẽ tạo vòng lặp import.
    from app.models.api_key import ApiKey

    with engine.begin() as conn:
        existing_cols = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(api_keys)")
        }
        if not existing_cols:
            return  # bảng chưa tồn tại — create_all() sẽ tạo đúng schema mới luôn

        legacy_unique_index = None
        for row in conn.exec_driver_sql("PRAGMA index_list(api_keys)"):
            index_name, is_unique, origin = row[1], row[2], row[3]
            if not is_unique or origin != "u":
                continue
            cols = [
                info_row[2]
                for info_row in conn.exec_driver_sql(f"PRAGMA index_info({index_name})")
            ]
            if set(cols) == {"user_id", "provider"}:
                legacy_unique_index = index_name
                break

        if legacy_unique_index is None:
            return  # đã ở schema mới (hoặc DB mới tinh, không có constraint cũ)

        conn.exec_driver_sql("ALTER TABLE api_keys RENAME TO api_keys_legacy")
        ApiKey.__table__.create(bind=conn)
        conn.exec_driver_sql(
            """
            INSERT INTO api_keys
                (id, user_id, provider, encrypted_key, label, status,
                 cooldown_until, request_count, error_count, last_used_at,
                 created_at, updated_at)
            SELECT id, user_id, provider, encrypted_key, NULL, 'ACTIVE',
                   NULL, 0, 0, NULL, created_at, updated_at
            FROM api_keys_legacy
            """
        )
        conn.exec_driver_sql("DROP TABLE api_keys_legacy")
