from collections.abc import Generator
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


def _ensure_sqlite_dir(database_url: str) -> None:
    """Pre-create the directory that holds the SQLite file.

    `storage/` is in .gitignore so a freshly cloned machine will not have it,
    and SQLite does not create parent directories — it only reports "unable to open
    database file".
    """
    if not database_url.startswith("sqlite"):
        return

    # sqlite:///relative/path → "/relative/path"; sqlite:////abs/path → "//abs/path".
    # Strip exactly 1 leading "/" to keep the path's absolute/relative nature intact.
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
    """Add new columns to tables that already exist.

    `Base.metadata.create_all()` only creates new tables, it does not alter old ones — adding a column
    to a model without migrating makes every query on that table fail with "no such column".
    Personal project with infrequent schema changes, so Alembic is not needed yet; only nullable
    column additions are handled, which is enough for now.
    """
    _migrate_api_keys_pool()

    # VideoStatus.PAUSED_QUOTA (Phase 8) needs no column migration — SQLite stores Enum
    # as an unconstrained VARCHAR, so adding a new Python enum value in
    # app/models/video.py is enough, without touching the existing `status` column.
    expected: dict[str, dict[str, str]] = {
        "videos": {
            "cover_url": "VARCHAR",
            "timeline_json": "JSON",
            "timeline_rendered_path": "VARCHAR",
            "speaker_voices_json": "JSON",
            # Phase 22: real channel id, see the `models/video.py::Video.channel_id` docstring.
            "channel_id": "VARCHAR",
        },
        "generation_projects": {
            "timeline_json": "JSON",
            "timeline_rendered_path": "VARCHAR",
        },
        "category_snapshots": {
            # Trending improvement phase (2026-09-16): Bilibili's real `pts` score,
            # more reliable than total_plays for measuring "hotness" — see schemas/trending.py.
            "total_pts": "INTEGER DEFAULT 0",
        },
    }

    with engine.begin() as conn:
        for table, columns in expected.items():
            existing = {
                row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")
            }
            if not existing:
                continue  # table does not exist yet — create_all() will create it with all columns
            for name, sql_type in columns.items():
                if name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


def _migrate_api_keys_pool() -> None:
    """Phase 8: the old `api_keys` table has `UNIQUE(user_id, provider)` (1 key/provider).

    SQLite stores a UNIQUE table-constraint as an "autoindex" (`sqlite_autoindex_*`)
    — that kind of index CANNOT be removed with `DROP INDEX`; the only way is to rebuild the table
    (rename → create new table with the current model schema → copy data → drop old table).
    Idempotent: only runs while the old constraint is still detected, so it does not affect runs
    after the migration is done.
    """
    # Local import: app.models.api_key imports Base from this very module (db.py) —
    # importing at the top of the file would create an import cycle.
    from app.models.api_key import ApiKey

    with engine.begin() as conn:
        existing_cols = {
            row[1] for row in conn.exec_driver_sql("PRAGMA table_info(api_keys)")
        }
        if not existing_cols:
            return  # table does not exist yet — create_all() will create the new schema anyway

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
            return  # already on the new schema (or a brand-new DB, no old constraint)

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
