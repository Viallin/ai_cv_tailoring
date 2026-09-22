"""FastAPI application factory (Phase 13, docs/development_plan.md Version 2).

Wraps app/services.py + app/pipeline.py + app/candidate_service.py in an
HTTP API — no business logic lives here, only routing/wiring.

Run with:
    uv run uvicorn api.main:app --reload

Version 4, Phase 4.8: lifespan() runs `alembic upgrade head` itself
(app/migrate.py) before building services, folding migrations into the
backend's own startup rather than a separate step. This still goes through
Alembic's real migration system (app/migrate.py's docstring) — it does
not bypass it the way db/engine.py raw-creating tables from
SQLModel.metadata would, which is what the historical version of this
docstring's warning was actually about.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.errors import register_exception_handlers
from api.routes.candidates import router as candidates_router
from api.routes.cv_drafts import router as cv_drafts_router
from api.routes.entity_crud import router as entity_crud_router
from api.routes.export import router as export_router
from api.routes.jobs import router as jobs_router
from api.routes.writeback import router as writeback_router
from app.config import config
from app.logging_setup import setup_logging
from app.migrate import upgrade_to_head
from app.services import build_services


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    upgrade_to_head()
    app.state.services = build_services(config)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="AI CV Builder API", lifespan=lifespan)
    register_exception_handlers(app)
    app.include_router(candidates_router)
    app.include_router(cv_drafts_router)
    app.include_router(entity_crud_router)
    app.include_router(export_router)
    app.include_router(jobs_router)
    app.include_router(writeback_router)
    return app


app = create_app()
