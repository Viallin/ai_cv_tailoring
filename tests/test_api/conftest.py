"""Shared fixtures for tests/test_api/.

`client` is wired to a fresh tmp SQLite engine (tables created directly via
SQLModel, bypassing Alembic for test speed — see docs/development_plan.md's
Phase 13 plan) and a tests.fakes.QueuedFakeProvider-backed Services, via
FastAPI's dependency_overrides rather than the real lifespan/build_services
path — no live LLM API key needed to run these tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from api.deps import get_services
from api.main import app
from app.candidate_registry import CandidateRegistry
from app.prompt_loader import PromptLoader
from app.services import Services
from app.use_cases import (
    BulletRewriteService,
    MatchingService,
    QualityRecheckService,
    ResumeIngestionService,
    RewritePlannerService,
    SkillEvidenceLinkingService,
    VacancyAnalysisService,
)
from db.engine import get_engine
from tests.fakes import QueuedFakeProvider

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


@pytest.fixture
def provider() -> QueuedFakeProvider:
    return QueuedFakeProvider()


@pytest.fixture
def services(tmp_path, provider) -> Services:
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    prompt_loader = PromptLoader(prompts_dir=_PROMPTS_DIR)
    return Services(
        resume=ResumeIngestionService(provider, prompt_loader),
        vacancy=VacancyAnalysisService(provider, prompt_loader),
        matching=MatchingService(provider, prompt_loader),
        rewrite_planner=RewritePlannerService(provider, prompt_loader),
        bullet_rewriter=BulletRewriteService(provider, prompt_loader),
        quality_recheck=QualityRecheckService(provider, prompt_loader),
        skill_evidence_linker=SkillEvidenceLinkingService(provider, prompt_loader),
        candidate_registry=CandidateRegistry(engine=engine),
    )


@pytest.fixture
def client(services):
    app.dependency_overrides[get_services] = lambda: services
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
