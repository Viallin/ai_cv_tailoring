from pathlib import Path

from pydantic import BaseModel
from sqlmodel import SQLModel

from app.candidate_registry import CandidateRegistry
from app.config import Config
from app.services import Services, build_services
from app.use_cases import (
    BulletRewriteService,
    MatchingService,
    ResumeIngestionService,
    RewritePlannerService,
    VacancyAnalysisService,
)
from db.engine import get_engine
from providers.base import ILLMProvider
from providers.fallback_provider import FallbackProvider
from providers.registry import ProviderRegistry


def make_config(tmp_path: Path, llm_fallback_providers: tuple[str, ...] = ()) -> Config:
    database_url = f"sqlite:///{tmp_path / 'data' / 'test.db'}"
    # build_services() deliberately doesn't create tables itself (would
    # bypass Alembic's migration history) — tests stand in for
    # `alembic upgrade head`.
    SQLModel.metadata.create_all(get_engine(database_url))
    return Config(
        llm_provider="gemini",
        llm_fallback_providers=llm_fallback_providers,
        llm_model="gemini-2.0-flash",
        gemini_api_key="fake-key",
        llm_max_retries=3,
        llm_retry_base_delay_seconds=1.0,
        prompts_dir=tmp_path / "prompts",
        data_dir=tmp_path / "data",
        log_level="INFO",
        database_url=database_url,
    )


class _FakeProvider(ILLMProvider):
    def generate_structured(
        self,
        prompt: str,
        response_schema: type[BaseModel],
        thinking_budget: int | None = None,
    ) -> BaseModel:
        raise NotImplementedError


def test_build_services_returns_a_fully_wired_bundle(tmp_path):
    services = build_services(make_config(tmp_path))

    assert isinstance(services, Services)
    assert isinstance(services.resume, ResumeIngestionService)
    assert isinstance(services.vacancy, VacancyAnalysisService)
    assert isinstance(services.matching, MatchingService)
    assert isinstance(services.rewrite_planner, RewritePlannerService)
    assert isinstance(services.bullet_rewriter, BulletRewriteService)
    assert isinstance(services.candidate_registry, CandidateRegistry)


def test_build_services_candidate_registry_uses_configured_database(tmp_path):
    config = make_config(tmp_path)

    services = build_services(config)
    services.candidate_registry.service_for("ada").create(name="Ada Lovelace")

    # A second Services built from the same config reaches the same
    # database — proves build_services() actually wired candidate_registry
    # to config.database_url, not some other/default location.
    other_services = build_services(config)
    assert other_services.candidate_registry.service_for("ada").get().name == "Ada Lovelace"


def test_build_services_uses_bare_provider_when_no_fallback_configured(tmp_path):
    config = make_config(tmp_path)
    registry = ProviderRegistry({"gemini": lambda config: _FakeProvider()})

    services = build_services(config, registry=registry)

    assert isinstance(services.resume._provider, _FakeProvider)


def test_build_services_wraps_in_fallback_provider_when_fallbacks_configured(tmp_path):
    config = make_config(tmp_path, llm_fallback_providers=("backup",))
    registry = ProviderRegistry(
        {"gemini": lambda config: _FakeProvider(), "backup": lambda config: _FakeProvider()}
    )

    services = build_services(config, registry=registry)

    assert isinstance(services.resume._provider, FallbackProvider)
