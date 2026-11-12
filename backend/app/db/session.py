"""Engine and session factory.

SQLite does not enforce foreign keys by default — the event listener below
turns that on for every connection, since FK integrity (VAL-02,
validation_strategy.md §2) depends on it actually being enforced by the
database, not just declared.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_PATH


def make_engine(database_path: str = DATABASE_PATH):
    engine = create_engine(f"sqlite:///{database_path}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
