"""Shared resume+vacancy -> AssembledCV pipeline orchestration for production
entry points (currently just the Phase 6/8 UI, ui/main_window.py).

run_pipeline.py (the CLI debugging tool) intentionally does NOT use this —
see its module docstring for why it duplicates this sequence instead: it's
meant to stay deletable without touching any production code path.

Split into two entry points (Phase 8) instead of one combined
run_full_pipeline(): the UI now has separate "Ingest Resume" and
"Generate CV" buttons, since re-parsing the resume on every generation was
wasted work once the Candidate Profile (and, as of Phase 8, its Evidence)
persist across app relaunches — see docs/development_plan.md Phase 8 notes.

Phase 8.1: `Services` no longer has one fixed candidate — there can be
several profiles now (app/candidate_registry.py) — so these two functions
take the active profile's `Candidate`/`Evidence` as explicit parameters
instead of reaching into `services` for "the" candidate. The caller (the
UI's profile switcher) is what knows which profile is active.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.bullet_locking import partition_locked_evidence, splice_locked_bullets
from app.bullet_provenance import build_report
from app.candidate_service import CandidateService
from app.cv_assembler import assemble_cv
from app.services import Services
from contracts.schemas import (
    MatchRequest,
    QualityRecheckRequest,
    RelinkSkillEvidenceRequest,
    RewriteBulletsRequest,
    RewritePlanRequest,
)
from domain.models import (
    AssembledCV,
    BulletProvenanceReport,
    Candidate,
    Certification,
    ContactItem,
    Education,
    Evidence,
    GenerationTiming,
    Language,
    MatchResult,
    Requirement,
    Vacancy,
)


@dataclass
class PipelineResult:
    candidate: Candidate
    vacancy: Vacancy
    match_result: MatchResult
    assembled_cv: AssembledCV
    provenance: BulletProvenanceReport
    timing: GenerationTiming


# Asked for directly: a person watching "Generating…" for several minutes
# with zero feedback has no way to tell whether it's almost done or stuck.
# These are the six steps `run_cv_generation` reports through `on_stage`
# below, in order — the five real LLM calls (same five `GenerationTiming`
# measures) plus one final label for the fast, deterministic wrap-up
# (locked-bullet splicing, CV assembly, provenance building) so the
# reported progress actually reaches 6/6 instead of jumping from "5/6,
# Quality-checking" straight to "done" with no step covering that tail.
GENERATION_STAGES: tuple[str, ...] = (
    "Analyzing job description",
    "Matching against your profile",
    "Planning the rewrite",
    "Rewriting bullets & summary",
    "Quality-checking the wording",
    "Assembling your CV",
)

# (stage_label, stage_number, stage_count) — called right before that stage
# starts, so the *first* call happens before any LLM request goes out; a
# caller with nothing to do with progress (tests, run_pipeline.py) just
# omits it, same optional-callback shape as elsewhere in this codebase.
OnStageCallback = Callable[[str, int, int], None]


def _noop_on_stage(_label: str, _number: int, _count: int) -> None:
    pass


# Reported when `existing_vacancy` (below) is actually reused instead of
# re-parsed — a distinct label from GENERATION_STAGES[0] so a person
# watching the live progress can tell the two apart (a step that finishes
# near-instantly isn't a bug once you can see *why*).
VACANCY_REUSED_STAGE_LABEL = "Reusing previous job description analysis"


def _format_language(language: Language) -> str:
    # Same convention as ui/graph_explorer.py's _summarize_language, so a
    # requirement grounded in this string reads the same way the profile
    # UI already displays it.
    return f"{language.name}" + (f" ({language.proficiency})" if language.proficiency else "")


def _format_certification(certification: Certification) -> str:
    # Ditto, mirroring _summarize_certification_like.
    details = ", ".join(bit for bit in (certification.issuer, certification.date) if bit)
    return f"{certification.name}" + (f" — {details}" if details else "")


def _format_education(education: Education) -> str:
    # Ditto, mirroring _summarize_education. Reported directly: a
    # Requirement asking for a specific degree (e.g. "higher technical,
    # mathematical, or economic education") was always reported as a Gap
    # regardless of what the candidate's own Education entries actually
    # said, because the Matching stage was never given them at all — the
    # same class of bug candidate_languages/candidate_certifications
    # already fixed for languages/certifications, just never extended to
    # Education when those were added.
    details = ", ".join(bit for bit in (education.degree, education.field) if bit)
    period = f" ({education.period})" if education.period else ""
    return f"{education.institution}" + (f" — {details}" if details else "") + period


def _format_contact(contact: ContactItem) -> str:
    # Ditto, mirroring _format_education/_format_certification/
    # _format_language — same "label: value" shape render_contacts_section
    # (app/cv_markdown.py) already uses, so a Gap grounded in this string
    # reads the same way the Contacts section itself displays it.
    return f"{contact.label}: {contact.value}"


_EMAIL_VALUE_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# A run of digits (optionally `+`-prefixed, with spaces/dashes/dots/parens
# allowed between them) at least 7 digits long — long enough to catch a
# real phone number in any common formatting ("+49 1522 6475201",
# "(555) 123-4567", "0049 152 2647 5201") without false-positiving on a
# short number that might legitimately appear in some other contact value
# (a postal code, a "10+ years" qualifier, etc.).
_PHONE_VALUE_PATTERN = re.compile(r"\+?(?:\d[\s().-]*){7,}")


def _is_sensitive_contact_value(value: str) -> bool:
    """True if `value` looks like an email address or a phone number.

    Matched on the *value*'s shape, not the contact's `label` — `label` is
    free text (`ContactItem`'s own docstring: "Email", "E-mail", "Phone",
    "Почта", "Tel", or anything else a real resume happens to call it), so
    a fixed label vocabulary would systematically miss whatever a given
    resume doesn't spell the "expected" way; a value that looks like an
    email/phone is caught regardless of how its label reads. Deliberately
    errs toward over-filtering a borderline non-phone digit string (e.g. a
    stray reference/certificate number written as a contact) rather than
    under-filtering a real phone number — this exists to keep an
    identifier a matching pass has no use for from ever reaching a
    third-party LLM API, so a false positive here just drops one unused
    line, while a false negative leaks a real phone number.
    """
    stripped = value.strip()
    if _EMAIL_VALUE_PATTERN.search(stripped):
        return True
    return bool(_PHONE_VALUE_PATTERN.search(stripped))


def _matching_contacts(candidate: Candidate) -> list[str]:
    """Contacts formatted for the Matching stage (`MatchRequest.
    candidate_contacts`) only — every Contact except ones whose value
    looks like an email address or phone number (see
    `_is_sensitive_contact_value`).

    Reported directly: after Contacts first reached the Matching prompt at
    all (fixing a relocation Requirement always showing as a Gap even
    though the candidate's own Contacts answered it), the follow-up
    concern was that this now sends the candidate's raw email/phone to a
    third-party LLM API on every Matching call and every gap recheck, for
    zero matching benefit — an email address never satisfies a
    Requirement the way a "Relocation"/"Work Authorization"/"Location"
    entry can. Filtering happens here, once, at the single call site that
    ever sends Contacts to an LLM at all — Resume Ingestion
    (01_cv_parser_v1.md) still needs the real, unfiltered values (parsing
    them out of the raw resume text is genuinely its job), and nothing
    downstream of Matching (Rewrite Planning/Bullet Rewriting/Quality
    Recheck) is ever given Contacts in the first place.
    """
    return [
        _format_contact(contact)
        for contact in candidate.contacts
        if not _is_sensitive_contact_value(contact.value)
    ]


def _real_skill_names(candidate: Candidate) -> list[str]:
    # Phase 21: category header rows (Skill.is_category_header) are a
    # Profile Explorer editing construct, not real skills — never surface
    # their label text to an LLM prompt as if it were one.
    return [skill.name for skill in candidate.skills if not skill.is_category_header]


def _real_technology_names(candidate: Candidate) -> list[str]:
    return [tech.name for tech in candidate.technologies if not tech.is_category_header]


def run_resume_ingestion(resume_text: str, services: Services) -> tuple[str, Candidate]:
    """Parse a raw resume into a Candidate + Evidence[], persisted as a new
    Candidate Profile (Phase 8.1 — ingestion always creates a new profile
    rather than overwriting an existing one; see
    app/candidate_registry.py:CandidateRegistry). Returns the new profile's
    id alongside the Candidate so the caller can switch to it.

    Raises AppError subclasses on failure — callers are responsible for
    catching and presenting those (e.g. ui/main_window.py's worker thread).
    """
    ingest_response = services.resume.ingest(resume_text)
    candidate_id = services.candidate_registry.new_profile_id()
    profile_service = services.candidate_registry.service_for(candidate_id)
    profile_service.replace(ingest_response.candidate, evidence=ingest_response.evidence)
    return candidate_id, ingest_response.candidate


def run_cv_generation(
    candidate: Candidate,
    evidence: list[Evidence],
    vacancy_text: str,
    services: Services,
    existing_vacancy: Vacancy | None = None,
    on_stage: OnStageCallback = _noop_on_stage,
) -> PipelineResult:
    """Analyze a vacancy and build a tailored CV for an already-known Candidate.

    `candidate`/`evidence` are the active profile's, already loaded by the
    caller (see app/candidate_registry.py) — this doesn't re-fetch them
    itself, so a session can generate CVs for many vacancies against one
    ingested profile without re-parsing the resume. Raises AppError
    subclasses on failure, same as run_resume_ingestion().

    Runs the full Phase 8 tailoring chain: Matching -> Rewrite Planning ->
    Bullet Rewriting -> Quality Recheck, replacing the old single collapsed
    CVBuilderService call. MatchResult (matches/Gaps/missing keywords) is
    informational, surfaced to the user as-is via PipelineResult.
    match_result, but also feeds into the Rewrite Planning stage so its
    keep/rewrite/enhance/remove decisions are grounded in the same
    match/gap analysis the user sees.

    Quality Recheck (app/use_cases.py:QualityRecheckService) runs right
    after Bullet Rewriting, on its raw output, before locked bullets are
    spliced back in — a second LLM pass whose only job is to catch
    self-explaining tails ("...demonstrating effective monetization
    design.") that Bullet Rewriting's own prompt tries but doesn't always
    manage to avoid. It never sees locked bullets (those are the user's
    own approved wording, out of scope for an automated rewording pass)
    and it's not allowed to touch anything but bullet/summary text — see
    that prompt for the exact contract.

    Phase 19: `Evidence.locked=True` items are excluded from Bullet
    Rewriting (app/bullet_locking.py:partition_locked_evidence) — the
    actual cost/latency saving, since there's nothing to generate for text
    that's forced verbatim either way — then spliced back into the rewrite
    response before assembly (splice_locked_bullets). Matching and Rewrite
    Planning both still receive the full, unpartitioned `evidence`:
    Matching because a locked bullet is still real signal for Gap
    analysis (hiding it there would risk a false gap), and Planning
    because its `priority_order` ("Evidence ids, most important first")
    is the only thing that keeps a locked bullet from always landing dead
    last in its role's list — a person locks a wording specifically
    because they've already approved it, i.e. usually their strongest
    content, not their weakest; see splice_locked_bullets's docstring.
    Only the *actions* list is filtered down to unlocked evidence before
    reaching Bullet Rewriting (below) — that prompt is instructed to
    produce one bullet per Evidence item it actually receives, and an
    action referencing evidence it was never given text for is an
    unforced, avoidable way to confuse it.

    Also times each of the five stages below plus the whole call, into
    `PipelineResult.timing` (`domain.models.GenerationTiming`) — asked for
    directly, since nothing previously recorded this anywhere durable:
    the app only ever logged to stdout (never captured), and a `CVDraft`'s
    own `created_at`/`updated_at` gap includes however long the person
    then spent editing, not just the generation itself.

    `on_stage` (default a no-op) is called once per `GENERATION_STAGES`
    entry, right before that stage starts — api/routes/jobs.py's
    `_execute_generate` passes one that writes the label onto the shared
    `JobStatus` the frontend is already polling, so "Generating…" becomes
    "Step 3/6: Planning the rewrite" instead of one long unexplained wait.

    `existing_vacancy` (Regenerate/Regenerate as New on an existing
    CVDraft, which already has its own previously-parsed Vacancy — a
    first-time generate has none, and passes `None`) skips re-running the
    JD Parser stage entirely when `vacancy_text` matches
    `existing_vacancy.raw_text` exactly: re-tailoring against the *same*
    job description doesn't need a fresh parse of text that hasn't
    changed, the same "don't redo unchanged work" reasoning
    run_resume_ingestion's own module docstring already applies to the
    resume side. Reported via `on_stage` as `VACANCY_REUSED_STAGE_LABEL`
    instead of the normal stage-1 label, so the near-instant step reads as
    intentional rather than broken. Falls back to a real re-parse whenever
    the text differs even slightly (a person edited the JD before
    regenerating) or `existing_vacancy` is `None`.
    """
    stage_count = len(GENERATION_STAGES)
    pipeline_started = time.perf_counter()

    if existing_vacancy is not None and existing_vacancy.raw_text.strip() == vacancy_text.strip():
        on_stage(VACANCY_REUSED_STAGE_LABEL, 1, stage_count)
        stage_started = time.perf_counter()
        vacancy = existing_vacancy
    else:
        on_stage(GENERATION_STAGES[0], 1, stage_count)
        stage_started = time.perf_counter()
        vacancy = services.vacancy.analyze(vacancy_text)
    vacancy_analysis_seconds = time.perf_counter() - stage_started

    on_stage(GENERATION_STAGES[1], 2, stage_count)
    stage_started = time.perf_counter()
    match_response = services.matching.match(
        MatchRequest(
            experience=candidate.experience,
            evidence=evidence,
            requirements=vacancy.requirements,
            candidate_skills=_real_skill_names(candidate),
            candidate_technologies=_real_technology_names(candidate),
            candidate_languages=[_format_language(lang) for lang in candidate.languages],
            candidate_certifications=[_format_certification(cert) for cert in candidate.certifications],
            candidate_education=[_format_education(edu) for edu in candidate.education],
            candidate_contacts=_matching_contacts(candidate),
            language=candidate.language,
        )
    )
    matching_seconds = time.perf_counter() - stage_started

    unlocked_evidence, locked_evidence = partition_locked_evidence(evidence)

    on_stage(GENERATION_STAGES[2], 3, stage_count)
    stage_started = time.perf_counter()
    plan_response = services.rewrite_planner.plan(
        RewritePlanRequest(
            experience=candidate.experience,
            evidence=evidence,
            requirements=vacancy.requirements,
            match_result=match_response.match_result,
            language=candidate.language,
        )
    )
    rewrite_planning_seconds = time.perf_counter() - stage_started

    unlocked_ids = {item.id for item in unlocked_evidence}
    rewrite_plan = plan_response.plan.model_copy(
        update={"actions": [a for a in plan_response.plan.actions if a.evidence_id in unlocked_ids]}
    )
    on_stage(GENERATION_STAGES[3], 4, stage_count)
    stage_started = time.perf_counter()
    rewrite_response = services.bullet_rewriter.rewrite(
        RewriteBulletsRequest(
            experience=candidate.experience,
            evidence=unlocked_evidence,
            requirements=vacancy.requirements,
            plan=rewrite_plan,
            gaps=match_response.match_result.gaps,
            candidate_summary=candidate.summary,
            candidate_headline=candidate.headline,
            vacancy_title=vacancy.title,
            candidate_skills=_real_skill_names(candidate),
            candidate_technologies=_real_technology_names(candidate),
            language=candidate.language,
        )
    )
    bullet_rewriting_seconds = time.perf_counter() - stage_started

    on_stage(GENERATION_STAGES[4], 5, stage_count)
    stage_started = time.perf_counter()
    recheck_response = services.quality_recheck.recheck(
        QualityRecheckRequest(
            cv=rewrite_response.cv, requirements=vacancy.requirements, language=candidate.language
        )
    )
    quality_recheck_seconds = time.perf_counter() - stage_started

    on_stage(GENERATION_STAGES[5], 6, stage_count)
    # 07_bullet_quality_recheck_v1.md only ever sees/edits summary+bullets —
    # it doesn't know `headline` exists, so its own CVProjection always
    # comes back with headline=None. Re-attach Bullet Rewriting's own
    # headline here rather than teaching the recheck stage about a field
    # it has no business revising in the first place.
    recheck_cv = recheck_response.cv.model_copy(update={"headline": rewrite_response.cv.headline})
    tailored_cv = splice_locked_bullets(
        recheck_cv, candidate, locked_evidence, plan_response.plan.priority_order
    )
    assembled = assemble_cv(candidate, tailored_cv)
    provenance = build_report(evidence, plan_response.plan, assembled, candidate.summary)

    timing = GenerationTiming(
        vacancy_analysis_seconds=vacancy_analysis_seconds,
        matching_seconds=matching_seconds,
        rewrite_planning_seconds=rewrite_planning_seconds,
        bullet_rewriting_seconds=bullet_rewriting_seconds,
        quality_recheck_seconds=quality_recheck_seconds,
        total_seconds=time.perf_counter() - pipeline_started,
    )

    return PipelineResult(
        candidate=candidate,
        vacancy=vacancy,
        match_result=match_response.match_result,
        assembled_cv=assembled,
        provenance=provenance,
        timing=timing,
    )


def run_gap_recheck(
    candidate: Candidate,
    evidence: list[Evidence],
    requirements: list[Requirement],
    excluded_evidence_ids: set[str],
    services: Services,
    edited_bullet_text: dict[str, str] | None = None,
    manual_bullet_text: list[str] | None = None,
    document_skills: list[str] | None = None,
    document_technologies: list[str] | None = None,
) -> MatchResult:
    """Phase 18 (extended Post-4.10): re-run the Matching stage alone,
    against the CV as currently edited in the A4 document — decoupled from
    run_cv_generation's one-time, pre-tailoring call.

    `excluded_evidence_ids` are the ids of Evidence items whose bullet the
    user has since toggled off in the editor (see frontend/src/lib/
    documentEvidence.ts's collectExcludedEvidenceIds).

    The four params below close the gap Phase 18 originally left open —
    reported directly: a person hand-editing a bullet's *text* in the
    editor (to add a skill/achievement the AI's own wording missed) saw
    that edit completely ignored by a subsequent re-check, because this
    function used to always match against the stored Evidence/Candidate
    profile, never the document's own current content.

    - `edited_bullet_text` (evidence_id -> current text) overrides the
      matching `Evidence` item's `.text` with what the bullet actually
      says in the document right now, for every id present here — the
      person may have rewritten it to name something the original,
      stored Evidence text never did. Only ever a copy of that one
      Evidence item, via `model_copy`; the stored Evidence itself is
      never mutated by a recheck.
    - `manual_bullet_text` covers the one case an id-keyed override can't:
      a hand-typed bullet added straight in the editor (documentEvidence.
      ts's collectManualBulletText — DocumentBlock.evidence_id is unset)
      or an Unused-Evidence item added via "Add to Role" that's since been
      edited. Each becomes its own synthetic, unpersisted Evidence item
      (`id="draft-manual-N"`) folded into the same matching call, so its
      content actually counts.
    - `document_skills`/`document_technologies` override
      `_real_skill_names`/`_real_technology_names` wholesale when given
      (the document's Skills/Technologies section, exactly as currently
      shown — frontend/src/lib/structuredDocument.ts's
      collectDocumentSkillNames) — a person may have added or deleted a
      skill line directly in this draft without touching their saved
      Candidate profile. `None` (the default) falls back to the profile,
      so an older caller/test that never learned about this still behaves
      exactly as before.

    No `Vacancy` re-analysis and no Rewrite Planning/Bullet Rewriting —
    `requirements` is whatever the caller already has from the original
    generate, so this is exactly one LLM call, not the full 4-stage chain.
    """
    edited_bullet_text = edited_bullet_text or {}
    active_evidence = [
        item.model_copy(update={"text": edited_bullet_text[item.id]})
        if item.id in edited_bullet_text
        else item
        for item in evidence
        if item.id not in excluded_evidence_ids
    ]
    active_evidence.extend(
        Evidence(id=f"draft-manual-{index}", text=text)
        for index, text in enumerate(manual_bullet_text or [])
    )
    match_response = services.matching.match(
        MatchRequest(
            experience=candidate.experience,
            evidence=active_evidence,
            requirements=requirements,
            candidate_skills=document_skills if document_skills is not None else _real_skill_names(candidate),
            candidate_technologies=(
                document_technologies
                if document_technologies is not None
                else _real_technology_names(candidate)
            ),
            candidate_languages=[_format_language(lang) for lang in candidate.languages],
            candidate_certifications=[_format_certification(cert) for cert in candidate.certifications],
            candidate_education=[_format_education(edu) for edu in candidate.education],
            candidate_contacts=_matching_contacts(candidate),
            language=candidate.language,
        )
    )
    return match_response.match_result


def run_skill_evidence_relink(
    candidate_service: CandidateService,
    candidate: Candidate,
    evidence: list[Evidence],
    services: Services,
) -> tuple[int, int]:
    """The on-demand "Re-evaluate Skill Dependencies" action: one scoped
    LLM call that re-derives every Skill's/Technology's `evidence_ids`
    from the profile's *current* Skills, Technologies, and Evidence —
    distinct from resume ingestion's one-time linking-as-a-side-effect-of-
    parsing (01_cv_parser_v1.md), which only ever runs once and only ever
    links Skills, never Technologies.

    Confirmed as a full **replace**, not a merge: each returned link
    overwrites that item's `evidence_ids` wholesale via the existing
    validated `update_skill`/`update_technology` path (which already
    rejects a hallucinated evidence id via `_validate_evidence_ids` — a
    free correctness guard on top of the prompt's own "never invent an id"
    rule). Returns `(updated_skill_count, updated_technology_count)` for
    the job result — every real (non-header) Skill/Technology gets a
    write, since "no evidence supports this" is itself a meaningful
    (re-)evaluation outcome, not a no-op.
    """
    response = services.skill_evidence_linker.relink(
        RelinkSkillEvidenceRequest(skills=candidate.skills, technologies=candidate.technologies, evidence=evidence)
    )
    for link in response.skills:
        candidate_service.update_skill(link.id, evidence_ids=link.evidence_ids)
    for link in response.technologies:
        candidate_service.update_technology(link.id, evidence_ids=link.evidence_ids)
    return len(response.skills), len(response.technologies)
