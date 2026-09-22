"""Programmatic Alembic migration runner (Version 4, Phase 4.8).

Used by api/main.py's lifespan() to fold `alembic upgrade head` into the
backend's own startup, so there's one process to run rather than a
separate migration step to sequence before uvicorn.

Path resolution deliberately mirrors app/config.py's own convention:
relative to the current working directory (repo root), not this file's
location. Alembic's own alembic.ini already resolves script_location as
"%(here)s/alembic" (%(here)s = the .ini file's own directory), so pointing
Config at the right alembic.ini is the only path this module needs to get
right; the versions/ directory resolution is Alembic's own job from there.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.logging_setup import get_logger

logger = get_logger(__name__)


def upgrade_to_head(alembic_ini_path: Path = Path("alembic.ini")) -> None:
    """Runs `alembic upgrade head` against DATABASE_URL (read by
    alembic/env.py from app.config.config, the same source
    app/services.py:build_services() uses — never set explicitly here, so
    there is exactly one place the DB URL is configured, matching env.py's
    own comment).
    """
    if not alembic_ini_path.exists():
        raise FileNotFoundError(
            f"alembic.ini not found at {alembic_ini_path.resolve()} — "
            "migrations cannot run. Check the process's working directory."
        )
    logger.info("Running alembic upgrade head (%s)", alembic_ini_path.resolve())
    cfg = Config(str(alembic_ini_path))
    command.upgrade(cfg, "head")
    logger.info("alembic upgrade head: done")
