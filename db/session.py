"""Session context manager — commits on clean exit, translates any
SQLAlchemy failure into app.errors.StorageError (mirroring how
app/storage.py wrapped OSError/json.JSONDecodeError for the old flat-JSON
backend) so callers keep catching the same AppError hierarchy regardless of
which storage backend is underneath.

Every CandidateService/CandidateRegistry method opens a fresh session
through this rather than sharing one Session across calls or threads — see
db/engine.py's module docstring for why (Engine is thread-safe to open new
connections from; a shared open Session is not).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.errors import StorageError


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise StorageError(f"Database operation failed: {exc}") from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
