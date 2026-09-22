"""Builds the application's service layer from Config: LLM provider, prompt
loader, the use-case services, and the Candidate Profile registry.

Shared by main.py and ui/main_window.py so production entry points wire up
identically instead of duplicating provider/prompt-loader construction.

run_pipeline.py (the CLI debugging tool) intentionally does NOT use this —
see its module docstring for why it duplicates the wiring instead: it's
meant to stay deletable without touching any production code path.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.candidate_registry import CandidateRegistry
from app.config import Config
from app.prompt_loader import PromptLoader
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
from providers.fallback_provider import FallbackProvider
from providers.registry import DEFAULT_REGISTRY, ProviderRegistry


@dataclass
class Services:
    resume: ResumeIngestionService
    vacancy: VacancyAnalysisService
    matching: MatchingService
    rewrite_planner: RewritePlannerService
    bullet_rewriter: BulletRewriteService
    quality_recheck: QualityRecheckService
    skill_evidence_linker: SkillEvidenceLinkingService
    candidate_registry: CandidateRegistry


def build_services(config: Config, registry: ProviderRegistry = DEFAULT_REGISTRY) -> Services:
    # Primary provider first, then any configured fallbacks, deduped in order
    # (see providers/registry.py, providers/fallback_provider.py — Phase 9).
    provider_names = list(dict.fromkeys([config.llm_provider, *config.llm_fallback_providers]))
    if len(provider_names) == 1:
        provider = registry.build(provider_names[0], config)
    else:
        provider = FallbackProvider([registry.build(name, config) for name in provider_names])
    prompt_loader = PromptLoader(prompts_dir=config.prompts_dir)
    engine = get_engine(config.database_url)
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
