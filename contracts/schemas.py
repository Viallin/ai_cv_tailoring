"""Request/response contracts for the prototype's LLM-backed use cases.

Ingestion and vacancy analysis (Phase 3-4) are still single collapsed
calls. Tailoring (originally Phase 5's single collapsed
`03_cv_builder_v1.md` call) is now three real stages per
docs/development_plan.md Phase 8: Matching -> Rewrite Planning -> Bullet
Rewriting.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.models import (
    Candidate,
    CVProjection,
    Evidence,
    Experience,
    Gap,
    MatchResult,
    Requirement,
    RewritePlan,
    Skill,
    Technology,
)


class IngestResumeRequest(BaseModel):
    raw_text: str


class IngestResumeResponse(BaseModel):
    """Result of parsing a raw resume.

    Two layers come back from the same parse, per docs/domain-model.md:

    * `candidate` — the structural profile record (name, contacts, education,
      companies/roles). This is what CandidateService.replace() persists so
      the person never has to re-type data that's already on their resume.
    * `evidence`  — the same experience broken into atomic, semantically
      reusable facts, kept separate for the future Claims/Variants layer
      (docs/development_plan.md Phase 7-8). It is NOT derived from
      `candidate` and NOT written into the Candidate Profile automatically.
    """

    candidate: Candidate
    evidence: list[Evidence] = Field(default_factory=list)


class AnalyzeVacancyRequest(BaseModel):
    raw_text: str


class AnalyzeVacancyResponse(BaseModel):
    """Raw LLM output for `02_jd_parser_v1.md` — a validation target only.

    Deliberately does NOT include `raw_text`: the caller already has the
    original JD text (it's the input), so asking the LLM to echo it back
    would waste tokens and risk drift/paraphrasing. `VacancyAnalysisService.
    analyze()` combines this with the original input to build the final
    `domain.models.Vacancy`, which is what that service actually returns.
    """

    title: str | None = None
    company: str | None = None
    requirements: list[Requirement] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class MatchRequest(BaseModel):
    """Input to `03_cv_jd_matcher_v1.md` (Phase 8 Matching stage).

    `experience` is passed for grouping/context only (company/position
    never regenerated), Evidence carries the Phase 7 `experience_id`/
    `experience_project_id` links the matcher can point matches at.

    `candidate_skills`/`candidate_technologies`/`candidate_languages`/
    `candidate_certifications` (Phase 8.4) are plain declarative facts
    from the Candidate's own flat profile fields — e.g. "English (C1)"
    from `Candidate.languages` — that the matcher couldn't otherwise see:
    a requirement satisfied only by one of these (never mentioned in any
    Evidence bullet) would previously be reported as a gap even though
    the candidate had directly stated it. Same `list[str]` shape as
    `RewriteBulletsRequest.candidate_skills`/`.candidate_technologies`.
    A match grounded in one of these has no Evidence id to cite, so
    `RequirementMatch.evidence_ids` may legitimately stay empty for it.

    `candidate_education` is the same idea, added later after Education
    itself turned out to have the identical gap Phase 8.4 already fixed
    for the other four: a Requirement asking for a specific degree (e.g.
    "higher technical, mathematical, or economic education") was always
    reported missing regardless of the candidate's real Education
    entries, because this stage was never given them at all.

    `candidate_contacts` is the same idea again, added later still after
    Contacts turned out to have the identical gap: a vacancy requiring
    relocation/willingness-to-travel/work authorization was always
    reported as a Gap even when the candidate's own Contacts held a
    directly on-point entry (e.g. a "Relocation" contact whose value is
    "Willing to relocate"), because this stage was never given Contacts
    at all — reported directly, from a real vacancy that stated a
    relocation requirement the candidate's profile already answered.
    Formatted "label: value" per entry (`app/pipeline.py:_format_contact`)
    — a bare `list[str]` like the other four, not `ContactItem` objects,
    same reasoning as those. Unlike the other four, this one is filtered
    before it ever gets here: `app/pipeline.py:_matching_contacts` drops
    any Contact whose value looks like an email address or phone number
    before formatting the rest, so this stage's own actual matching use
    for Contacts (relocation/work authorization/location) is served
    without also sending direct personal identifiers to a third-party LLM
    API on every Matching call/gap recheck for no matching benefit.

    `language` (Version 4, Phase 4.2) is the candidate's own profile
    language (`domain.models.Candidate.language`) — `Gap.description`/
    `.suggested_action` are prose shown to the user directly, so they
    follow it regardless of what language the vacancy text itself is in.
    """

    experience: list[Experience]
    evidence: list[Evidence]
    requirements: list[Requirement]
    candidate_skills: list[str] = Field(default_factory=list)
    candidate_technologies: list[str] = Field(default_factory=list)
    candidate_languages: list[str] = Field(default_factory=list)
    candidate_certifications: list[str] = Field(default_factory=list)
    candidate_education: list[str] = Field(default_factory=list)
    candidate_contacts: list[str] = Field(default_factory=list)
    language: str = "en"


class MatchResponse(BaseModel):
    match_result: MatchResult


class RewritePlanRequest(BaseModel):
    """Input to `04_rewrite_planner_v1.md` (Phase 8 Rewrite Planning stage).

    Same `experience`/`evidence`/`requirements` shape as `MatchRequest`,
    plus the Matching stage's own output (`match_result`) so the plan can
    use its matches/Gaps rather than re-deriving them. `language` — see
    `MatchRequest`'s docstring; `RewriteAction.reason`/`.new_angle` are
    also candidate-facing text.
    """

    experience: list[Experience]
    evidence: list[Evidence]
    requirements: list[Requirement]
    match_result: MatchResult
    language: str = "en"


class RewritePlanResponse(BaseModel):
    plan: RewritePlan


class RewriteBulletsRequest(BaseModel):
    """Input to `05_rewrite_bullets_v1.md` (Phase 8 Bullet Rewriting stage)
    — the final stage, producing the same `CVProjection` shape the old
    collapsed `03_cv_builder_v1.md` call used to in one shot.

    `experience`/`evidence`/`requirements` are passed for the same
    grouping/context reasons as the earlier stages; `plan` is the Rewrite
    Planning stage's output (which Evidence to rewrite/enhance/remove/keep,
    and in what priority order). `candidate_summary` is the Candidate's own
    positioning statement (domain.models.Candidate.summary, if the resume
    had one) — passed in as voice/context for the tailored summary, not
    something to copy verbatim. May be None if the Candidate has no summary
    captured.

    `candidate_headline`/`vacancy_title` (Post-4.10 follow-up) are read-only
    context for the tailored `CVProjection.headline`, same "context, not
    something to copy verbatim" treatment as `candidate_summary` above:
    `candidate_headline` is `Candidate.headline` (the profile's own current
    title, if captured) and `vacancy_title` is `Vacancy.title` (the JD's
    stated title, if the JD parser found one) — either may be `None`.

    `candidate_skills`/`candidate_technologies` are every name from
    `Candidate.skills`/`Candidate.technologies` — the LLM's job for each is
    to rank the given list by relevance to `requirements`, not invent one;
    app/cv_assembler.py enforces that by construction (it looks up each
    name against the Candidate's own records, so an invented name simply
    can't appear in the export, and an omitted one just sorts last rather
    than disappearing). See docs/development_plan.md's Skills addendum.

    `language` — see `MatchRequest`'s docstring. This is the one stage
    where it matters most: the actual exported summary/bullet text is
    generated here.

    `gaps` (from the Matching stage's own `MatchResult.gaps`, unlike
    everything else here which was already available before Matching ran)
    is the Matching stage's own list of Requirements it already determined
    are *not* confirmed by Evidence. Found live: without this, the summary
    asserted "quickly prototypes in Unity" in the very same generation
    whose own Matching stage had just written "no explicit mention of fast
    Unity prototyping" as an open Gap for that identical Requirement — two
    stages of one pipeline directly contradicting each other, because this
    stage had no way to know what the other one had already concluded.
    This is read-only context for staying honest, exactly like Gap's own
    docstring's "purely advisory" stance for the user-facing Gaps panel —
    it must never be treated as a checklist of things to now go fabricate
    (that would be a worse version of the bug it fixes), only as a hard
    stop on asserting a Gap's own claim as true.
    """

    experience: list[Experience]
    evidence: list[Evidence]
    requirements: list[Requirement]
    plan: RewritePlan
    gaps: list[Gap] = Field(default_factory=list)
    candidate_summary: str | None = None
    candidate_headline: str | None = None
    vacancy_title: str | None = None
    candidate_skills: list[str] = Field(default_factory=list)
    candidate_technologies: list[str] = Field(default_factory=list)
    language: str = "en"


class RewriteBulletsResponse(BaseModel):
    cv: CVProjection


class QualityRecheckRequest(BaseModel):
    """Input to `07_bullet_quality_recheck_v1.md` — a final language-quality
    pass over the Bullet Rewriting stage's own output, run before locked
    bullets are spliced back in (see app/pipeline.py:run_cv_generation).

    Deliberately narrow: just the CV to check plus `requirements` as
    read-only context for recognizing keyword-driven filler. No
    `experience`/`evidence` — unlike every earlier stage this one isn't
    grounding new content in Evidence, only removing self-explaining tails
    from wording that's already there, so it doesn't need the source facts
    re-supplied, only the text to check.

    `language` — see `MatchRequest`'s docstring; this pass edits the same
    candidate-facing text Bullet Rewriting produced, so it stays in the
    same language.
    """

    cv: CVProjection
    requirements: list[Requirement]
    language: str = "en"


class QualityRecheckResponse(BaseModel):
    cv: CVProjection


class SkillEvidenceLink(BaseModel):
    """One Skill's or Technology's fresh `evidence_ids`, per
    `06_skill_evidence_linker_v1.md`."""

    id: str
    evidence_ids: list[str] = Field(default_factory=list)


class RelinkSkillEvidenceRequest(BaseModel):
    """Input to `06_skill_evidence_linker_v1.md` — the on-demand
    "Re-evaluate Skill Dependencies" action. Unlike ingestion (which links
    skills to evidence as a side effect of parsing a resume), this is a
    standalone linking-only pass over the profile's *current* Skills,
    Technologies, and Evidence — run whenever a person wants links
    refreshed, not automatically on every edit.
    """

    skills: list[Skill]
    technologies: list[Technology]
    evidence: list[Evidence]


class RelinkSkillEvidenceResponse(BaseModel):
    """One entry per input Skill/Technology id — see
    `app.pipeline.run_skill_evidence_relink`, which applies each link as a
    full replace of that item's `evidence_ids`, not a merge."""

    skills: list[SkillEvidenceLink] = Field(default_factory=list)
    technologies: list[SkillEvidenceLink] = Field(default_factory=list)
