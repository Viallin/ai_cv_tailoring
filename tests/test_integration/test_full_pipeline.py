"""Integration Tests (docs/architecture.md Testing Strategy): exercise
run_resume_ingestion/run_cv_generation (app/pipeline.py) through the real
use_cases.py services and the real prompts/ directory, faking only the
provider boundary (the actual LLM call) — the one genuinely external,
non-deterministic, costly dependency. Every other existing test fakes at
least one more layer than that: tests/test_app/test_pipeline.py fakes
whole services, tests/test_app/test_use_cases.py fakes the prompt
directory itself. This is the first test to prove real prompts + real
use_cases.py + real pipeline.py + real cv_assembler.py all fit together.
"""

from pathlib import Path

from sqlmodel import SQLModel

from app.candidate_registry import CandidateRegistry
from app.pipeline import run_cv_generation, run_resume_ingestion
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
from contracts.schemas import (
    AnalyzeVacancyResponse,
    IngestResumeResponse,
    MatchResponse,
    QualityRecheckResponse,
    RewriteBulletsResponse,
    RewritePlanResponse,
)
from db.engine import get_engine
from domain.models import (
    Candidate,
    CVProjection,
    Evidence,
    Experience,
    MatchResult,
    Requirement,
    RequirementMatch,
    RewriteAction,
    RewritePlan,
    Skill,
    TailoredBullet,
    TailoredExperience,
)
from tests.fakes import QueuedFakeProvider as _QueuedFakeProvider

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def make_services(tmp_path, provider: _QueuedFakeProvider) -> Services:
    prompt_loader = PromptLoader(prompts_dir=_PROMPTS_DIR)
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
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


def test_full_resume_ingestion_end_to_end(tmp_path):
    candidate = Candidate(
        name="Ada Lovelace",
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
    )
    evidence = [Evidence(id="ev-1", text="Did a thing", experience_id="exp-1")]
    provider = _QueuedFakeProvider([IngestResumeResponse(candidate=candidate, evidence=evidence)])
    services = make_services(tmp_path, provider)

    candidate_id, result = run_resume_ingestion("Ada Lovelace's resume text", services)

    assert result == candidate
    saved_service = services.candidate_registry.service_for(candidate_id)
    assert saved_service.get() == candidate
    assert saved_service.get_evidence() == evidence


def test_full_cv_generation_end_to_end(tmp_path):
    candidate = Candidate(
        name="Ada Lovelace",
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
        skills=[Skill(id="skill-1", name="Python")],
    )
    evidence = [Evidence(id="ev-1", text="Did a thing", experience_id="exp-1")]

    vacancy_response = AnalyzeVacancyResponse(
        title="Senior Engineer",
        company="Globex",
        requirements=[Requirement(text="Python")],
        keywords=["python"],
    )
    match_result = MatchResult(
        matches=[
            RequirementMatch(requirement_text="Python", evidence_ids=["ev-1"], strength="high")
        ]
    )
    plan = RewritePlan(
        actions=[RewriteAction(evidence_id="ev-1", action="keep", reason="Strong as-is.")],
        priority_order=["ev-1"],
    )
    rewrite_response = RewriteBulletsResponse(
        cv=CVProjection(
            summary="Tailored summary.",
            experience=[
                TailoredExperience(
                    experience_id="exp-1",
                    bullets=[TailoredBullet(text="Did a thing", evidence_id="ev-1")],
                )
            ],
            skills=["Python"],
        )
    )
    provider = _QueuedFakeProvider(
        [
            vacancy_response,
            MatchResponse(match_result=match_result),
            RewritePlanResponse(plan=plan),
            rewrite_response,
            QualityRecheckResponse(cv=rewrite_response.cv),
        ]
    )
    services = make_services(tmp_path, provider)

    result = run_cv_generation(candidate, evidence, "Senior Engineer at Globex, needs Python", services)

    assert result.candidate == candidate
    assert result.vacancy.title == "Senior Engineer"
    assert result.vacancy.raw_text == "Senior Engineer at Globex, needs Python"
    assert result.match_result == match_result
    assert result.assembled_cv.name == "Ada Lovelace"
    assert result.assembled_cv.summary == "Tailored summary."
    assert result.assembled_cv.experience[0].bullets == [
        TailoredBullet(text="Did a thing", evidence_id="ev-1")
    ]
    assert [s.name for s in result.assembled_cv.skills] == ["Python"]
    # All 5 stages called through in order: analyze -> match -> plan ->
    # rewrite -> quality recheck.
    assert provider.calls == [
        AnalyzeVacancyResponse,
        MatchResponse,
        RewritePlanResponse,
        RewriteBulletsResponse,
        QualityRecheckResponse,
    ]
    # Phase 17: the provenance report is built from the same plan+evidence,
    # with zero extra LLM calls (still only the 5 provider.calls above).
    assert len(result.provenance.bullets) == 1
    provenance = result.provenance.bullets[0]
    assert provenance.evidence_id == "ev-1"
    assert provenance.original_text == "Did a thing"
    assert provenance.rewritten_text == "Did a thing"
    assert provenance.action == "keep"
    assert provenance.rationale == "Strong as-is."
    assert result.provenance.unused_evidence == []
