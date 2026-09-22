"""Engine construction — one Engine per process (or per test), shared
across every Session opened by db.session/app.candidate_service/api.deps.

Not a Session: Engine is thread-safe to open new connections from, which is
what lets CandidateService, FastAPI's request threadpool, and the /jobs
executor threads all use the same Engine without coordinating a shared
connection.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, event
from sqlmodel import SQLModel, create_engine

import db.models  # noqa: F401  # registers CandidateRow/EvidenceRow on SQLModel.metadata


def get_engine(database_url: str) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        # SQLite (unlike app/storage.py's old save_candidate/save_evidence,
        # which always did mkdir(parents=True, exist_ok=True) first) will
        # not create a missing parent directory itself — connecting fails
        # outright on a fresh checkout before data_dir/ has ever been
        # written to. Mirror that same mkdir here instead of only in
        # storage.py.
        sqlite_path = _sqlite_path_from_url(database_url)
        if sqlite_path is not None:
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine = create_engine(database_url, connect_args=connect_args)
    if is_sqlite:
        # SQLite ignores FK constraints (including EvidenceRow's ON DELETE
        # CASCADE to CandidateRow) unless enabled per-connection — off by
        # default for backward-compat reasons unrelated to us.
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_db_and_tables(engine: Engine) -> None:
    """Creates tables directly from SQLModel metadata, bypassing Alembic.

    Used by tests (for speed) and can be used for a from-scratch local dev
    DB; the real migration history lives in alembic/versions/ and is what
    `alembic upgrade head` applies — this is not a substitute for that in
    any environment that needs to track schema changes over time.
    """
    SQLModel.metadata.create_all(engine)


def _sqlite_path_from_url(database_url: str) -> Path | None:
    """Best-effort helper for callers (e.g. the migration script) that need
    to ensure a sqlite file's parent directory exists before connecting —
    SQLite itself won't create missing parent directories."""
    if not database_url.startswith("sqlite:///"):
        return None
    return Path(database_url.removeprefix("sqlite:///"))
