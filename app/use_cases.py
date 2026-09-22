"""Application Layer use cases — prototype scope.

Each function coordinates: prompt rendering -> provider call -> validated
response. Per docs/architecture.md, this layer never talks to the LLM SDK
directly and never contains prompt text or UI logic.

ResumeIngestionService and VacancyAnalysisService are still the "collapsed
pipeline" versions from docs/development_plan.md Phase 3-4. Tailoring
(originally a third collapsed call here, CVBuilderService) was split into
three real stages for Phase 8: MatchingService -> RewritePlannerService ->
BulletRewriteService — see docs/development_plan.md Phase 8 notes.
"""

from __future__ import annotations

import json

from app.prompt_loader import PromptLoader
from contracts.schemas import (
    AnalyzeVacancyResponse,
    IngestResumeResponse,
    MatchRequest,
    MatchResponse,
    QualityRecheckRequest,
    QualityRecheckResponse,
    RelinkSkillEvidenceRequest,
    RelinkSkillEvidenceResponse,
    RewriteBulletsRequest,
    RewriteBulletsResponse,
    RewritePlanRequest,
    RewritePlanResponse,
)
from domain.models import Vacancy
from providers.base import ILLMProvider

# thinking_budget experiment, phase 2 (see ILLMProvider.generate_structured's
# and providers/gemini_provider.py's docstrings for the full backstory):
# real generation logging showed JD Parsing/Quality Recheck spending more
# tokens "thinking" than writing their actual (much shorter) output, so
# those two got `thinking_budget=0` outright. Rewrite Planning/Bullet
# Rewriting are the reasoning-heaviest stages instead — Bullet Rewriting's
# own prompt (05_rewrite_bullets_v1.md) walks through seven separate
# fabrication-failure variants it must actively check for — so a first,
# more conservative try capped both at a reduced but non-zero budget
# instead of disabling thinking outright the way JD Parsing/Quality
# Recheck's `0` does.
#
# That first try (both at 4096) found Rewrite Planning fine — nothing in
# its own output (target_keywords/new_angle/reason) looked any different —
# but Bullet Rewriting produced two real regressions on a real generation:
# a case-agreement grammar error in an "enhance" bullet (comparable to the
# same Evidence item's grammatically-correct `auto` output), and a
# genuine fabrication — "...учитывая принципы сетевых взаимодействий и
# синергии для кооперативных игр" added to a cooperative-event bullet
# whose Evidence never mentions networking/synergy at all, chasing a
# Gap the plan's own `new_angle` explicitly admitted was "to close a gap"
# (05_rewrite_bullets_v1.md's Rules section says to follow the Evidence
# over the angle in exactly this situation — with only 4096 tokens of
# thinking room, it didn't). Rewrite Planning stayed at the reduced
# budget; Bullet Rewriting moved up to its own, higher intermediate
# budget instead — confirmed clean on a fresh generation against the
# same vacancy (neither the grammar error nor the fabrication
# reproduced; see docs/development_plan.md's "Post-4.10 fixes, round 2"
# for the one milder, arguable case that surfaced instead) while still
# cutting Bullet Rewriting's own time ~41% versus `auto`. Settled as of
# that round — revisit with the same real-generation-comparison rigor,
# not just a vibe check, before changing either value again.
_REWRITE_PLANNING_THINKING_BUDGET = 4096
_BULLET_REWRITING_THINKING_BUDGET = 8192


class ResumeIngestionService:
    def __init__(self, provider: ILLMProvider, prompt_loader: PromptLoader):
        self._provider = provider
        self._prompts = prompt_loader

    def ingest(self, raw_text: str) -> IngestResumeResponse:
        """Parse a raw resume into a Candidate profile + atomic Evidence[].

        Callers are responsible for persisting the returned `candidate` (see
        app.candidate_service.CandidateService.replace) — this service only
        talks to the LLM and validates its output; it has no storage side
        effects itself.
        """
        prompt = self._prompts.render("01_cv_parser_v1.md", resume_text=raw_text)
        return self._provider.generate_structured(prompt, IngestResumeResponse)


class VacancyAnalysisService:
    def __init__(self, provider: ILLMProvider, prompt_loader: PromptLoader):
        self._provider = provider
        self._prompts = prompt_loader

    def analyze(self, raw_text: str) -> Vacancy:
        """Parse a raw job description into a Vacancy.

        `raw_text` is preserved verbatim from the input rather than trusting
        the LLM to reproduce it (see AnalyzeVacancyResponse's docstring).

        Passes `thinking_budget=0` (see ILLMProvider.generate_structured's
        docstring) — this stage is a mostly-mechanical extraction of
        requirements/keywords already present in the vacancy text, not the
        open-ended reasoning Bullet Rewriting/Matching do, so it's one of
        the first two stages (Quality Recheck is the other) tried with
        thinking disabled outright, per the retry/thoughts-token logging in
        providers/gemini_provider.py showing this stage alone spending ~1.5x
        its visible output on hidden thinking. Revisit if real generations
        show a quality regression this stage's own tests don't catch.
        """
        prompt = self._prompts.render("02_jd_parser_v1.md", vacancy_text=raw_text)
        parsed = self._provider.generate_structured(
            prompt, AnalyzeVacancyResponse, thinking_budget=0
        )
        return Vacancy(
            title=parsed.title,
            company=parsed.company,
            raw_text=raw_text,
            requirements=parsed.requirements,
            keywords=parsed.keywords,
        )


class MatchingService:
    """Phase 8 Matching stage: how well the Candidate's Evidence supports a
    vacancy's Requirements, and where it doesn't (Gaps). Its output
    (domain.models.MatchResult) is informational, surfaced to the user
    as-is, not CV content — see RewritePlannerService for where it feeds
    into the actual tailoring."""

    def __init__(self, provider: ILLMProvider, prompt_loader: PromptLoader):
        self._provider = provider
        self._prompts = prompt_loader

    def match(self, request: MatchRequest) -> MatchResponse:
        # Gap entries (Experience.is_gap=True) have no supporting Evidence
        # to match against.
        tailorable_experience = [e for e in request.experience if not e.is_gap]
        prompt = self._prompts.render(
            "03_cv_jd_matcher_v1.md",
            experience_json=json.dumps([e.model_dump() for e in tailorable_experience]),
            evidence_json=json.dumps([e.model_dump() for e in request.evidence]),
            requirements_json=json.dumps([r.model_dump() for r in request.requirements]),
            candidate_skills_json=json.dumps(request.candidate_skills),
            candidate_technologies_json=json.dumps(request.candidate_technologies),
            candidate_languages_json=json.dumps(request.candidate_languages),
            candidate_certifications_json=json.dumps(request.candidate_certifications),
            candidate_education_json=json.dumps(request.candidate_education),
            candidate_contacts_json=json.dumps(request.candidate_contacts),
            language=request.language,
        )
        return self._provider.generate_structured(prompt, MatchResponse)


class RewritePlannerService:
    """Phase 8 Rewrite Planning stage: decides what to do with each Evidence
    item (rewrite/enhance/remove/keep) using the Matching stage's output,
    without generating any rewritten text itself — see BulletRewriteService
    for that."""

    def __init__(self, provider: ILLMProvider, prompt_loader: PromptLoader):
        self._provider = provider
        self._prompts = prompt_loader

    def plan(self, request: RewritePlanRequest) -> RewritePlanResponse:
        # thinking_budget — see the module-level _REWRITE_PLANNING_THINKING_
        # BUDGET/_BULLET_REWRITING_THINKING_BUDGET comment above for what
        # this experiment is and why they're two separate constants.
        tailorable_experience = [e for e in request.experience if not e.is_gap]
        prompt = self._prompts.render(
            "04_rewrite_planner_v1.md",
            experience_json=json.dumps([e.model_dump() for e in tailorable_experience]),
            evidence_json=json.dumps([e.model_dump() for e in request.evidence]),
            requirements_json=json.dumps([r.model_dump() for r in request.requirements]),
            match_result_json=json.dumps(request.match_result.model_dump()),
            language=request.language,
        )
        return self._provider.generate_structured(
            prompt, RewritePlanResponse, thinking_budget=_REWRITE_PLANNING_THINKING_BUDGET
        )


class BulletRewriteService:
    """Phase 8 Bullet Rewriting stage: the final tailoring step, producing
    the same CVProjection shape the old collapsed CVBuilderService used to
    in one shot — but now driven by RewritePlannerService's plan instead of
    deciding relevance and rewriting in the same call."""

    def __init__(self, provider: ILLMProvider, prompt_loader: PromptLoader):
        self._provider = provider
        self._prompts = prompt_loader

    def rewrite(self, request: RewriteBulletsRequest) -> RewriteBulletsResponse:
        # Gap entries (Experience.is_gap=True) are never AI-tailored — they
        # have no supporting Evidence and are always included later by
        # app/cv_assembler.py regardless of what this call returns. Exclude
        # them from the prompt so the LLM isn't asked to invent bullets for
        # a career break.
        tailorable_experience = [e for e in request.experience if not e.is_gap]
        # PromptLoader.render() does plain string substitution — a bare
        # None would literally render as the text "None" in the prompt, so
        # fall back to an explicit placeholder instead.
        candidate_summary_text = request.candidate_summary or "(No summary provided.)"
        prompt = self._prompts.render(
            "05_rewrite_bullets_v1.md",
            experience_json=json.dumps([e.model_dump() for e in tailorable_experience]),
            evidence_json=json.dumps([e.model_dump() for e in request.evidence]),
            requirements_json=json.dumps([r.model_dump() for r in request.requirements]),
            plan_json=json.dumps(request.plan.model_dump()),
            gaps_json=json.dumps([g.model_dump() for g in request.gaps]),
            candidate_summary=candidate_summary_text,
            candidate_headline=request.candidate_headline or "",
            vacancy_title=request.vacancy_title or "",
            candidate_skills_json=json.dumps(request.candidate_skills),
            candidate_technologies_json=json.dumps(request.candidate_technologies),
            language=request.language,
        )
        # thinking_budget — see the module-level _REWRITE_PLANNING_THINKING_
        # BUDGET/_BULLET_REWRITING_THINKING_BUDGET comment above.
        return self._provider.generate_structured(
            prompt, RewriteBulletsResponse, thinking_budget=_BULLET_REWRITING_THINKING_BUDGET
        )


class QualityRecheckService:
    """Language-quality recheck stage: a second pass over the Bullet
    Rewriting stage's own output, run before locked bullets are spliced
    back in (app/pipeline.py:run_cv_generation) so it only ever revises
    text the LLM itself just generated, never a user-approved locked
    wording. Catches the specific defect Bullet Rewriting is instructed to
    avoid but doesn't always fully avoid: bullets ending in a
    self-explaining tail ("...demonstrating effective monetization
    design.") that just restates the accomplishment the sentence already
    proved — see 07_bullet_quality_recheck_v1.md."""

    def __init__(self, provider: ILLMProvider, prompt_loader: PromptLoader):
        self._provider = provider
        self._prompts = prompt_loader

    def recheck(self, request: QualityRecheckRequest) -> QualityRecheckResponse:
        # thinking_budget=0 — see VacancyAnalysisService.analyze's docstring
        # for the reasoning and the logging that motivated it; this stage
        # is a narrow, pattern-matching-shaped edit pass (trim
        # self-explaining tails) over text Bullet Rewriting already wrote,
        # not a stage that needs to reason about Evidence/Requirements from
        # scratch, so it's the other of the first two stages tried with
        # thinking disabled outright.
        prompt = self._prompts.render(
            "07_bullet_quality_recheck_v1.md",
            cv_json=json.dumps(request.cv.model_dump()),
            requirements_json=json.dumps([r.model_dump() for r in request.requirements]),
            language=request.language,
        )
        return self._provider.generate_structured(
            prompt, QualityRecheckResponse, thinking_budget=0
        )


class SkillEvidenceLinkingService:
    """The on-demand "Re-evaluate Skill Dependencies" action — a
    standalone linking-only pass over the profile's current Skills,
    Technologies, and Evidence, distinct from ingestion's own one-time
    linking-as-a-side-effect-of-parsing. See
    app.pipeline.run_skill_evidence_relink for how the response gets
    applied back onto the Candidate Profile (a full replace per item, not
    a merge)."""

    def __init__(self, provider: ILLMProvider, prompt_loader: PromptLoader):
        self._provider = provider
        self._prompts = prompt_loader

    def relink(self, request: RelinkSkillEvidenceRequest) -> RelinkSkillEvidenceResponse:
        # Phase 21's category header rows (Skill/Technology.
        # is_category_header) are a Profile Explorer editing construct,
        # not real skills — never surface their label text as if they
        # were one to link against evidence.
        real_skills = [s for s in request.skills if not s.is_category_header]
        real_technologies = [t for t in request.technologies if not t.is_category_header]
        prompt = self._prompts.render(
            "06_skill_evidence_linker_v1.md",
            skills_json=json.dumps([{"id": s.id, "name": s.name} for s in real_skills]),
            technologies_json=json.dumps([{"id": t.id, "name": t.name} for t in real_technologies]),
            evidence_json=json.dumps([e.model_dump() for e in request.evidence]),
        )
        return self._provider.generate_structured(prompt, RelinkSkillEvidenceResponse)
