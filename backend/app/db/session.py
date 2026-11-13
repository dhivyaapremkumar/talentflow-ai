"""Engine and session factory.

SQLite does not enforce foreign keys by default — the event listener below
turns that on for every connection, since FK integrity (VAL-02,
validation_strategy.md §2) depends on it actually being enforced by the
database, not just declared.
"""

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_PATH


def make_engine(database_path: str = DATABASE_PATH):
    """Generic engine constructor — used both by the live application
    (via `get_session_local()` below) and by `data_generation/generator.py`/
    `validation/evaluate.py`, which call this directly with an explicit
    path that often does *not* exist yet, because they are the code that
    creates it. This function must never refuse to connect to a missing
    file — only the live application's default session factory does
    that (see `DatabaseNotConfiguredError` below)."""
    engine = create_engine(f"sqlite:///{database_path}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


class DatabaseNotConfiguredError(RuntimeError):
    """Raised by `get_session_local()` when the live application's
    configured `DATABASE_PATH` does not exist on disk — a clear,
    actionable failure instead of SQLite silently creating an empty file
    and every query 500ing on "no such table" later.

    Deliberately checked lazily, on first actual use, rather than at
    import time of this module or of `app.main`: `tests/test_api.py`
    imports `app.main` and exercises the live `FastAPI` app via
    `TestClient` with `app.dependency_overrides[get_db]` pointing at a
    throwaway in-memory database, and must keep working in a fresh
    checkout that has never run the generator — an eager check (at
    import time, or in a `lifespan` startup hook, which `TestClient`'s
    context-manager form also executes) would break that regardless of
    the override, since dependency overrides only apply to routes, not
    to module-import or lifespan code.
    """


_default_session_local: sessionmaker | None = None


def get_session_local() -> sessionmaker:
    """Returns the live application's default session factory
    (`api/deps.py:get_db()`'s only caller), built lazily against
    `DATABASE_PATH` the first time it's actually needed. Raises
    `DatabaseNotConfiguredError` if that file does not exist, rather than
    silently creating an empty one."""
    global _default_session_local
    if _default_session_local is None:
        if not Path(DATABASE_PATH).exists():
            raise DatabaseNotConfiguredError(
                f"Configured database not found at {DATABASE_PATH!r}. Generate it first "
                "(from backend/): "
                ".venv/Scripts/python.exe -m app.data_generation.generator --mode starter "
                "— or set the DATABASE_PATH environment variable to point at an existing "
                "database file."
            )
        _default_session_local = sessionmaker(bind=make_engine(DATABASE_PATH), autoflush=False, autocommit=False)
    return _default_session_local
