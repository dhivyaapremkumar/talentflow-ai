"""Shared FastAPI dependencies — Phase 10's minimal API layer."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.db.session import get_session_local


def get_db() -> Generator[Session, None, None]:
    """Raises `DatabaseNotConfiguredError` (handled by `api/errors.py` as
    a clean 503) if `DATABASE_PATH` does not exist — see
    `db/session.py:get_session_local()`'s docstring for why that check
    lives there, lazily, rather than at import/startup time."""
    session_local = get_session_local()
    db = session_local()
    try:
        yield db
    finally:
        db.close()
