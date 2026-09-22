from logging.config import fileConfig

from sqlmodel import SQLModel

from alembic import context

import db.models  # noqa: F401  # registers CandidateRow/EvidenceRow on SQLModel.metadata
from app.config import config as app_config
from db.engine import get_engine

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
#
# disable_existing_loggers=False (Version 4, Phase 4.8): fileConfig()'s
# default (True) walks every already-registered logger in the process and
# disables it. Harmless when `alembic upgrade head` runs as its own CLI
# process (dev.bat, this project's historical usage) — there's nothing
# else logging in that process. Actively broke app/migrate.py's
# programmatic `command.upgrade()` call from api/main.py's lifespan
# (Phase 4.8): it silently killed uvicorn's own loggers and
# app/logging_setup.py's, live-reproduced as migrations completing (their
# INFO lines print fine, before this call) but every log line after —
# including app/migrate.py's own "done" message — vanishing with no
# further output and no traceback.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Real target metadata: db/models.py's SQLModel table classes (imported
# above purely for the registration side effect).
target_metadata = SQLModel.metadata

# The real DB URL comes from app.config.config.database_url (same source
# app/services.py:build_services() uses) — alembic.ini's own sqlalchemy.url
# is left blank/unused so there's exactly one place this is configured.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    context.configure(
        url=app_config.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    Uses db.engine.get_engine() (same helper app/services.py:build_services()
    uses) rather than alembic's own engine_from_config, so the FK-enforcement
    pragma and connect_args stay identical between migrations and the app.
    """
    connectable = get_engine(app_config.database_url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
