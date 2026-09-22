"""Core domain entities — prototype scope.

Cut down from the full model in docs/domain-model.md. Deliberately flat for the
first working slice:

* No Organization / Role / Project hierarchy yet — Evidence is a flat list.
* No Claim / Competency / per-Evidence Variant objects yet.
* No CareerGraph as a real graph — just a container of Evidence.

These simplifications are intentional (see docs/development_plan.md, Phase 2)
and will be replaced in Phase 7-8 without changing the public shape of the
Application Layer's use cases.

CVProjection vs AssembledCV: CVProjection is AI-tailored *content* only
(summary/bullets/skills); AssembledCV is the complete, exportable CV with
Candidate facts (identity/contacts/education/dates/languages/certifications/
projects) merged in deterministically by app/cv_assembler.py. See
docs/development_plan.md Phase 5 notes for why these are two separate
models instead of one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _collapse_to_single_line(value: str) -> str:
    """Collapses any run of whitespace (including embedded newlines) into a
    single space and strips the ends — `" ".join(value.split())` is the
    idiomatic way to do this in Python, `.split()` with no argument already
    splits on any whitespace run and drops empty pieces.

    `CVProjection.summary`/`TailoredBullet.text` are always meant to render
    as exactly one visual line each — every renderer downstream
    (app/cv_markdown.py, app/cv_pdf.py, app/cv_docx.py) assumes a 1:1
    mapping between "one of these fields" and "one line of output". A
    Gemini response occasionally hands back a summary with leading blank
    lines (seen live: `"\\n\\n\\n\\nОпытный гейм-дизайнер..."`) — harmless
    on its own, but `app/cv_pdf.py:compute_page_breaks` builds a section's
    body by joining per-line text with "\\n" and later re-splitting on
    "\\n" to align each rendered line back to its source id
    (`app/cv_markdown.py::iter_section_lines_with_ids`); the embedded
    newlines turn that one summary into five split lines against a
    `line_ids` list sized for one, and `_render_body` raises `IndexError`
    reading past the end of it (caught live from exactly this — a
    generation for a tougher, more technical vacancy). Normalizing here,
    at the boundary where the LLM's raw string becomes a validated
    domain object, means every caller/renderer downstream can keep relying
    on that 1:1 assumption instead of each having to defend against it
    separately.
    """
    return " ".join(value.split())


class ExperienceProject(BaseModel):
    """A project nested inside one Experience/Role entry.

    Some resumes are structured company -> project -> role -> dates ->
    achievement bullets rather than just company -> role -> dates -> bullets
    (e.g. an agency or studio employee who worked several distinct
    client/internal projects under one position). Not every Experience entry
    has this — most bullets stay in `Experience.responsibilities`/
    `achievements` directly. See docs/development_plan.md Phase 7 notes.

    `responsibilities` (Phase 12.3) mirrors `achievements` — added so the
    Graph Explorer's per-role bullet rows (ui/graph_explorer.py) can link
    a responsibility to a project the same way an achievement can.

    `url` (Post-4.10 follow-up) is this project's own website — distinct
    from `Experience.company_url` (the employer's site) and from the
    standalone `Project.url` (a Key Projects portfolio entry, unrelated to
    any Experience). Added alongside `company_url` to close a real
    ingestion gap: a source PDF hyperlinking a company or project name to
    its own site (rather than writing the URL out as visible text) had
    nowhere to put that URL at all — `app/resume_reader.py` surfaces the
    link, but the CV Parser had no field to place it in, so it was silently
    dropped. `app/cv_markdown.py:render_experience_section` turns a
    non-null `url` into a hyperlink on this project's name in the exported
    CV, the same treatment `company_url` gets for the company name.
    """

    id: str
    name: str
    period: str | None = None
    achievements: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    url: str | None = None


class Experience(BaseModel):
    """A position held at a company — one entry in the Candidate Profile.

    Also used for explicit employment gaps (parental leave, sabbatical,
    career break) — set `is_gap=True` for those. Gaps are facts, not
    AI-tailored content: app/cv_assembler.py always includes them in the
    final CV regardless of what the vacancy-tailoring LLM call selected, so
    an unexplained employment gap never silently disappears from the output.
    `company` is optional specifically to support gaps not tied to a single
    employer (e.g. a career break between two unrelated jobs).

    Kept flat (no separate Organization hierarchy) per the Phase 2 thin-slice
    scope; see docs/domain-model.md for the eventual full shape. `projects`
    is the one piece of nesting pulled forward from that full shape (Phase 7)
    — see ExperienceProject's docstring.

    `company_url` (Post-4.10 follow-up) is the employer's own website — see
    `ExperienceProject.url`'s docstring for the ingestion gap this closes
    and `app/cv_markdown.py:render_experience_section` for how it turns
    `company` into a hyperlink in the exported CV.
    """

    id: str
    company: str | None = None
    company_url: str | None = None
    position: str
    period: str | None = None
    location: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    projects: list[ExperienceProject] = Field(default_factory=list)
    is_gap: bool = False


class VolunteerExperience(BaseModel):
    """Unpaid work — open-source maintenance, mentorship programs,
    hackathon organizing, community leadership. Structurally close to
    `Experience` but deliberately simpler (no nested achievements/
    responsibilities/projects split, no `is_gap`) since these entries are
    typically much shorter; kept as its own model rather than folded into
    `Experience` so exporting/rendering doesn't have to guess which is
    which from context.
    """

    id: str
    organization: str
    role: str
    period: str | None = None
    description: str | None = None


class Education(BaseModel):
    id: str
    institution: str
    degree: str | None = None
    field: str | None = None
    period: str | None = None


class Skill(BaseModel):
    """`evidence_ids` (Phase 15) are ids into the sibling Evidence[] list —
    which Evidence item(s) demonstrate this skill, so the app can always
    explain why a skill exists rather than just asserting it (see
    docs/domain-model.md's Skill section). Many-to-many by design: one
    Evidence item can back several skills, one skill can be backed by
    several Evidence items — a list here, not a single id, and not a
    field on Evidence instead (a `Skill`/`Technology`-side list is the
    only one of the two directions that can express "backed by multiple
    items" at all). Not eagerly validated against real Evidence ids at
    every read; `CandidateService.update_skill()` validates on write —
    see its docstring.
    """

    id: str
    name: str
    category: str | None = None
    proficiency: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    # Phase 21: a "category header" row in the Profile Explorer's editor —
    # a normal Skill entry (draggable/CRUD'd through the same routes as
    # any other) whose `name` holds a category label rather than a real
    # skill. When true, `category`/`proficiency`/`evidence_ids` are unused.
    # A real skill's own `category` is derived client-side from the
    # nearest preceding header row and written back here — see
    # EntitySection.tsx's deriveCategories/groupItemsByHeader.
    is_category_header: bool = False


class Technology(BaseModel):
    """A tool, framework, platform, or technology (Unity, Python, AWS,
    Jira, ...) — named as its own entity in docs/domain-model.md's target
    model but never implemented; kept distinct from `Skill` (which covers
    broader competencies like "Product Management" or "System Design") so
    the exported CV can show a dedicated Tools/Technologies section
    engineers and data roles commonly expect, separate from Skills.

    `evidence_ids` — see `Skill.evidence_ids`'s docstring; same shape,
    same reasoning. Unlike Skill's, this isn't populated by resume
    ingestion yet (`prompts/01_cv_parser_v1.md` doesn't extract
    `technologies` at all today, only `skills` — a pre-existing gap, not
    something Phase 15 adds), only settable manually via
    `update_technology()`.
    """

    id: str
    name: str
    category: str | None = None
    proficiency: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    # See Skill.is_category_header's docstring — same mechanism, same reasoning.
    is_category_header: bool = False


class Language(BaseModel):
    id: str
    name: str
    proficiency: str | None = None


class Certification(BaseModel):
    id: str
    name: str
    issuer: str | None = None
    date: str | None = None


class Award(BaseModel):
    """An award or honor — distinct from `Certification` (a vendor/
    professional credential like "AWS Certified" or "PMP"): "Game of the
    Year nominee," "Employee of the Quarter," "Best Paper Award" don't fit
    that concept and would look out of place rendered under a
    "Certifications" heading. Same shape as `Certification` otherwise, and
    the same always-included (not AI-tailored) treatment as `Project`.
    """

    id: str
    name: str
    issuer: str | None = None
    date: str | None = None


class ContactItem(BaseModel):
    """One labeled piece of contact/identity info.

    Deliberately generic instead of named fields (email, phone, linkedin,
    ...): what belongs on a CV's header varies by role and location — email
    and phone are near-universal, but location, LinkedIn, work authorization/
    visa status, a personal site, or a GitHub profile are all just as
    legitimate depending on context, and a fixed field set means adding a
    new named field every time a new kind of contact info comes up. `label`
    is free text (e.g. "Email", "Phone", "LinkedIn", "Location", "Work
    Authorization") rather than an enum, for the same reason.
    """

    id: str
    label: str
    value: str


class Project(BaseModel):
    """One entry in a candidate's standalone "Key Projects" / portfolio
    section — distinct from Experience, which is chronological employer
    history. A Project is not tied to a single employer and may span or sit
    alongside several Experience entries (e.g. the same shipped game
    mentioned both as a Project highlight and within an Experience role's
    bullets — that overlap is fine, they serve different reading purposes).

    Currently always included in the exported CV as-is (like Education) —
    not AI-tailored per vacancy like Experience is. See
    docs/development_plan.md Phase 5 notes for why, and for how to promote
    this to tailored content later if needed.
    """

    id: str
    name: str
    description: str | None = None
    url: str | None = None


class Publication(BaseModel):
    """A published paper, article, blog post, or conference talk. Same
    always-included (not AI-tailored) treatment as `Project`, which it
    otherwise mirrors — `venue`/`date` (e.g. "PyData 2023", "Medium")
    replace `Project.description`, since what matters for a publication is
    where/when it appeared, not a free-text blurb.
    """

    id: str
    title: str
    venue: str | None = None
    date: str | None = None
    url: str | None = None


class PortfolioLink(BaseModel):
    """One link to external work — a portfolio site, ArtStation/Behance/
    GitHub profile, a specific case study page, etc. Split out from
    `ContactItem` since a candidate may want several, each with its own
    description of what it shows — a flat label+value pair can only hold
    one. Same non-AI-tailored treatment as `Project`: always included in
    the exported CV as-is, never per-vacancy tailored.
    """

    id: str
    url: str
    description: str | None = None


EmploymentType = Literal["Full-time", "Part-time", "Contract", "Freelance", "Internship", "Temporary"]


class Candidate(BaseModel):
    """The person's structural profile. See domain/models.py's module
    docstring and docs/domain-model.md for the prototype-scope notes.

    `summary` is the candidate's own positioning statement/"about me" text
    as written in their resume (often untitled — it just appears after the
    contact block, before the first real section). It's a Candidate fact,
    captured close to verbatim at ingestion time, distinct from
    CVProjection.summary (the AI-generated, per-vacancy tailored summary) —
    the latter may draw on this one as context but is written fresh each
    time, not copied. See docs/development_plan.md Phase 5 notes.

    `employment_types_sought` is a job-search preference ("what kind of
    work am I looking for"), not a historical fact about past roles (a
    per-role employment type isn't something real CVs state) — rendered
    near the header alongside `headline`/`contacts`, same as how "Work
    Authorization" already appears there today. A small closed vocabulary
    (`EmploymentType`), unlike `ContactItem.label`'s deliberately open one.

    `language` (Version 4, Phase 4.2) is the language every generated CV
    for this profile is written in — an ISO 639-1 code (e.g. "en", "ru"),
    lowercase. Fixed per-profile, set once at creation and never edited in
    place: a candidate wanting output in a different language creates a
    new profile rather than translating this one (see
    docs/development_plan.md's Version 4 section). Two ways it gets set,
    both landing in this same field: resume ingestion detects it from the
    resume's own text (`prompts/01_cv_parser_v1.md`); creating an empty
    profile (no resume text to detect from) takes it as an explicit
    choice instead (`api/schemas.py:CandidateCreateRequest`). Deliberately
    a plain `str`, not a closed set — header localization
    (`app/cv_locales.py`) only needs to support a couple of languages so
    far and falls back to English for any it doesn't recognize, but
    detection/storage here shouldn't be limited to that same short list.
    Defaults to `"en"` so every profile created before this field existed
    validates as English without a migration — `db/models.py`'s
    `CandidateRow.data` is a schemaless JSON column, so an old row missing
    this key entirely just picks up the Pydantic default on load.
    """

    name: str
    language: str = "en"
    headline: str | None = None
    summary: str | None = None
    employment_types_sought: list[EmploymentType] = Field(default_factory=list)
    contacts: list[ContactItem] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    volunteer_experience: list[VolunteerExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    technologies: list[Technology] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    awards: list[Award] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)
    portfolio_links: list[PortfolioLink] = Field(default_factory=list)


class Evidence(BaseModel):
    """The smallest reusable unit of professional experience.

    Example: "Increased D30 retention by 12%."

    `experience_id`/`experience_project_id` are structured links into the
    Candidate's `experience` (and, when set, an Experience entry's nested
    `projects`) — added in Phase 7 so the tailoring step
    (prompts/03_cv_builder_v1.md) can group bullets by role/project
    directly instead of guessing from `source_context` prose. Both are
    optional: Evidence not tied to a specific role (or a role's specific
    project) simply omits them.
    """

    id: str
    text: str
    source_context: str | None = Field(
        default=None,
        description="Free-text hint of where this came from, e.g. company/role name.",
    )
    experience_id: str | None = Field(
        default=None,
        description="Id of the Candidate.experience entry this came from, if any.",
    )
    experience_project_id: str | None = Field(
        default=None,
        description=(
            "Id of the ExperienceProject (within the linked experience_id) "
            "this came from, if the role has that nested structure."
        ),
    )
    locked: bool = Field(
        default=False,
        description=(
            "Phase 19: when set, app/bullet_locking.py excludes this item from "
            "Rewrite Planning/Bullet Rewriting and splices locked_text back in "
            "verbatim instead — durable across every future generate, for any "
            "vacancy, not a per-generate setting like TailoredBullet."
        ),
    )
    locked_text: str | None = Field(
        default=None,
        description=(
            "The verbatim bullet text to reuse while locked=True (typically a "
            "previously AI-rewritten phrasing the person approved). Meaningless "
            "while locked=False. Falls back to `text` (the raw Evidence) if "
            "locked=True but this was never set."
        ),
    )


class CareerGraph(BaseModel):
    """Prototype-scope container. Becomes a real graph in Phase 7."""

    candidate: Candidate
    evidence: list[Evidence] = Field(default_factory=list)


class Requirement(BaseModel):
    """One line item from a job description — a responsibility, skill, or
    qualification the JD Parser stage (02_jd_parser_v1.md) extracted
    verbatim.

    `priority` (Version 4, Phase 4.11) tells the Matching stage
    (03_cv_jd_matcher_v1.md) whether the JD's own structure frames this as
    a baseline expectation or as optional/bonus — a requirement listed
    under a "Nice to have"/"Will be a plus"/"Bonus points" heading, or
    phrased that way inline. Defaults to `"required"`: both for the common
    case (most JD line items are baseline expectations) and for backward
    compatibility with a `Vacancy` persisted before this field existed,
    where treating an unmarked requirement as anything less than required
    would silently soften gaps that were correctly `"high"` before. See
    Gap.severity's docstring for how the Matching stage is instructed to
    use this — a `"nice_to_have"` Requirement being unaddressed is a real
    gap worth surfacing, but can never justify `"high"` severity the way an
    unaddressed core requirement can.
    """

    text: str
    keywords: list[str] = Field(default_factory=list)
    priority: Literal["required", "nice_to_have"] = "required"


class Vacancy(BaseModel):
    title: str | None = None
    company: str | None = None
    raw_text: str
    requirements: list[Requirement] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class RequirementMatch(BaseModel):
    """How well the Candidate's Evidence supports one vacancy Requirement
    (Phase 8 Matching stage).

    `requirement_text` echoes `Requirement.text` verbatim rather than an id
    — unlike Evidence's `experience_id`/`experience_project_id` links
    (Phase 7), a Requirement is only ever referenced within the single
    Matching call that already has its full text as structured input, so
    there's no cross-call id-stability need that would justify adding an id
    field to `Requirement` itself.
    """

    requirement_text: str
    evidence_ids: list[str] = Field(default_factory=list)
    strength: Literal["high", "medium", "low"]


class Gap(BaseModel):
    """A mismatch between one vacancy Requirement and the Candidate's
    Evidence — per docs/domain-model.md's Gap entity: missing evidence,
    weak supporting experience, or missing terminology for that
    requirement. See RequirementMatch's docstring for why `requirement_text`
    is text, not an id.

    `severity`/`suggested_action` (Phase 8.2) make the Gaps panel
    actionable: sortable by importance, with a concrete next step. Both
    stay purely advisory — surfaced to the user as-is, never fed back into
    RewritePlannerService by any new code path (auto-applying a suggestion
    would mean inventing a bullet ungrounded in Evidence).

    `status` (Phase 18) is never set by the Matching stage itself — every
    freshly matched Gap is "open". It exists so a dismissed gap can be
    round-tripped through the API at all; the actual "don't resurface a
    dismissed gap across a re-check" logic lives client-side (a session-
    local set of dismissed `requirement_text`s, applied after each match),
    since there's nowhere server-side to persist it until Phase 20's
    CVDraft exists.
    """

    requirement_text: str
    description: str
    severity: Literal["high", "medium", "low"]
    suggested_action: str | None = None
    status: Literal["open", "skipped"] = "open"


class SkillToSurface(BaseModel):
    """A JD keyword the candidate's Evidence already supports, but that
    isn't named explicitly anywhere in their Skills/Technologies lists —
    a distinct, cheaper-to-fix signal from Gap (which is about missing or
    weak *experience*). This is about experience that's already there but
    isn't labeled, the same "add 'A/B Testing' to your Skills list" signal
    a JD-matching tool's hard-skills checklist gives, which the
    Requirement-sentence-level `gaps` above can't surface on its own: a
    keyword like this is never reported in `gaps` (the underlying
    Requirement it belongs to is already a `matches` entry, often
    `"high"`) and, because it *is* backed by Evidence, it's also excluded
    from `missing_keywords` (reserved for keywords absent from Evidence
    too) — without this field it would be invisible in the output
    entirely, even though it's the single cheapest fix a candidate can
    make to their profile.
    """

    keyword: str
    evidence_ids: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    """Output of the Matching stage (Phase 8): how the Candidate's Evidence
    aligns with a Vacancy's Requirements, and where it doesn't.

    Deliberately informational, not CV content — surfaced to the user
    directly (docs/development_plan.md Phase 8: "Explicit Gap Analysis step,
    surfaced to the user instead of hidden inside one LLM call"), not part
    of CVProjection/AssembledCV and never exported to Markdown.
    """

    matches: list[RequirementMatch] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    skills_to_add: list[SkillToSurface] = Field(default_factory=list)


class RewriteAction(BaseModel):
    """One planning decision for a single Evidence item (Phase 8 Rewrite
    Planning stage) — what to do with it, not the rewritten text itself
    (that's the separate Bullet Rewriting stage, see 05_rewrite_bullets_v1.md).

    `"merge"` (combining several Evidence items into one bullet) from the
    original prompt sketch is deliberately not supported — it would need a
    many-to-one id mapping the rewriting stage doesn't otherwise need, for
    a case with no evidence yet that combined bullets read better; can be
    added later if it turns out to matter.
    """

    evidence_id: str
    action: Literal["rewrite", "enhance", "remove", "keep"]
    reason: str
    target_keywords: list[str] = Field(default_factory=list)
    new_angle: str | None = None


class RewritePlan(BaseModel):
    """Output of the Rewrite Planning stage (Phase 8): what to do with each
    Evidence item and in what order, using the Matching stage's MatchResult
    as input — but still no actual rewritten text. That's produced from
    this plan by the Bullet Rewriting stage."""

    actions: list[RewriteAction] = Field(default_factory=list)
    priority_order: list[str] = Field(
        default_factory=list,
        description="Evidence ids, most important first.",
    )


class TailoredBullet(BaseModel):
    """One tailored achievement bullet, optionally tagged with the
    ExperienceProject it came from.

    `project` is a display *name* (not an id) — like the rest of
    CVProjection, it deliberately doesn't reference Candidate ids beyond
    `TailoredExperience.experience_id`. `None` means the bullet belongs to
    the role directly, not to any of its nested projects.

    `evidence_id` (Phase 17) links this bullet back to the Evidence item it
    was rewritten from — echoed verbatim by the LLM, same convention as
    `TailoredExperience.experience_id`. It's the one new field this phase
    actually needs from the LLM: `original_text`/`rationale` are both
    derivable deterministically once a bullet's `evidence_id` is known (see
    app/bullet_provenance.py), so they're not asked of the LLM at all.
    `None` only as a defensive default if the LLM omits it — every bullet
    is produced from exactly one included Evidence item, so it should
    always be set in practice.
    """

    text: str
    project: str | None = None
    evidence_id: str | None = None

    @field_validator("text")
    @classmethod
    def _normalize_text(cls, value: str) -> str:
        return _collapse_to_single_line(value)


class TailoredExperience(BaseModel):
    """AI-selected/rephrased bullets for one Candidate.Experience entry.

    `experience_id` must match an id in the Candidate's `experience` list —
    company/position/period are never re-generated by the LLM; they're
    looked up from the Candidate at assembly time (see app/cv_assembler.py).
    """

    experience_id: str
    bullets: list[TailoredBullet] = Field(default_factory=list)


class CVProjection(BaseModel):
    """AI-tailored *content* for a specific vacancy — never the full CV.

    Deliberately excludes identity, contacts, education, dates, and company
    names: those are facts, not creative content, and get merged in
    deterministically from the Candidate Profile by app/cv_assembler.py
    rather than risked through an LLM call (see docs/development_plan.md
    Phase 5 notes, and the "LLM never returns final CV text" principle in
    docs/architecture.md). Disposable output, never the source of truth —
    see docs/domain-model.md > Resume Projection.

    `headline` (Post-4.10 follow-up) is the one-line role title shown under
    the candidate's name — same "fresh per vacancy, grounded in Evidence"
    treatment as `summary`, added because `Candidate.headline` used to be
    copied verbatim into every tailored CV regardless of vacancy (reported
    directly: a candidate tailoring for "Senior 3D Character Artist" still
    saw their untouched profile headline, "Character Art Supervisor", on
    the output). `None` when Bullet Rewriting has nothing to add (should
    only happen for `app/cv_assembler.py:build_untailored_projection`'s
    zero-AI path) — `assemble_cv()` falls back to `Candidate.headline` in
    that case, so untailored export behaves exactly as before this field
    existed.
    """

    summary: str
    headline: str | None = None
    experience: list[TailoredExperience] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def _normalize_summary(cls, value: str) -> str:
        return _collapse_to_single_line(value)

    @field_validator("headline")
    @classmethod
    def _normalize_headline(cls, value: str | None) -> str | None:
        return _collapse_to_single_line(value) if value else value


class AssembledExperienceEntry(BaseModel):
    """One dated entry in the final assembled CV: facts from a Candidate's
    Experience entry, plus this vacancy's tailored bullets (empty for
    `is_gap=True` entries — see Experience.is_gap).

    `experience_id` (Phase 8.3) is facts-only plumbing — never rendered to
    Markdown or exported, see app/cv_markdown.py — that lets
    app/graph_writeback.py know which Candidate.experience entry a
    hand-edited block of text corresponds to, without fragile position/
    company/period text-matching (the same person/company can have
    multiple roles with identical position text).

    `company_url`/`project_urls` (Post-4.10 follow-up) are copied straight
    from `Experience.company_url`/each `ExperienceProject.url` by
    `app/cv_assembler.py:assemble_cv` — facts, not AI-tailored content, so
    they're merged in deterministically like every other field here rather
    than asked of the Bullet Rewriting LLM call. `project_urls` maps a
    project *name* (as it appears in a `TailoredBullet.project` string,
    e.g. from `_render_bullets_grouped_by_project`) to its URL rather than
    living on `TailoredBullet` itself — `TailoredBullet` is AI-tailored
    content the LLM produces, and a project's URL is exactly the kind of
    fact that must never be risked through that call (same reasoning as
    `AssembledCV.skills`/`.technologies` never being `CVProjection`'s own
    LLM-produced lists — see that field's docstring). A project without a
    known URL simply has no entry in this dict, same as `company_url`
    being `None`.
    """

    experience_id: str | None = None
    company: str | None = None
    company_url: str | None = None
    position: str
    period: str | None = None
    location: str | None = None
    bullets: list[TailoredBullet] = Field(default_factory=list)
    is_gap: bool = False
    project_urls: dict[str, str] = Field(default_factory=dict)


class AssembledCV(BaseModel):
    """The complete, ATS-structured CV ready for export.

    Built by app/cv_assembler.py: Candidate facts (name/contacts/education/
    languages/certifications/projects) merged deterministically with this
    vacancy's AI-tailored content (summary/bullets) from a CVProjection.
    Never constructed directly from an LLM response.

    `skills`/`technologies` are `Candidate.skills`/`Candidate.technologies`
    (full records — category, proficiency), not `CVProjection.skills`/
    `.technologies` (the LLM's raw output, just names): the LLM only ranks
    each Candidate list's names by relevance, it doesn't decide membership.
    app/cv_assembler.py applies that ranking within each category
    (deterministic, from the Candidate list's own order) and produces
    these lists — see its `_rank_by_category`.

    `language` (Version 4, Phase 4.2) is copied verbatim from
    `Candidate.language` by `app/cv_assembler.py:assemble_cv()` — see that
    field's own docstring. Carried here (not read live off `Candidate`)
    because every render function downstream (`app/cv_markdown.py`,
    `app/cv_pdf.py`, `app/cv_docx.py`, `app/cv_pdf_playwright.py`) only
    ever receives an `AssembledCV`, never a `Candidate`.
    """

    name: str
    language: str = "en"
    headline: str | None = None
    employment_types_sought: list[EmploymentType] = Field(default_factory=list)
    contacts: list[ContactItem] = Field(default_factory=list)
    summary: str
    experience: list[AssembledExperienceEntry] = Field(default_factory=list)
    volunteer_experience: list[VolunteerExperience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    technologies: list[Technology] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    awards: list[Award] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    publications: list[Publication] = Field(default_factory=list)
    portfolio_links: list[PortfolioLink] = Field(default_factory=list)


class BulletProvenance(BaseModel):
    """One rewritten bullet's before/after/why (Phase 17), keyed by the
    Evidence item it came from.

    Deliberately informational only — like `MatchResult`, never folded into
    `AssembledCV`/`CVProjection` and never exported. `original_text` and
    `rationale` are both assembled deterministically by
    app/bullet_provenance.py from data that already exists (`Evidence.text`
    and the Rewrite Planning stage's `RewriteAction`), not asked of the
    Bullet Rewriting LLM call — see `TailoredBullet.evidence_id`'s
    docstring. The UI's inline highlight/popover/"revert to original"
    reads this by `evidence_id`, joined against whichever bullet block is
    currently showing `rewritten_text` (possibly further hand-edited since).

    `locked` (Phase 19) is True when this bullet came from a locked
    Evidence item (app/bullet_locking.py), reused verbatim rather than
    actually rewritten this round. `action` falls back to "keep" with no
    rationale for these (excluded from Rewrite Planning entirely, so
    there's no RewriteAction to report) — `locked` is orthogonal to
    `action`, not a fifth value, so the frontend can tell "the AI decided
    to keep this unchanged" apart from "this bullet was never sent to the
    AI at all".
    """

    evidence_id: str
    original_text: str
    rewritten_text: str
    action: Literal["rewrite", "enhance", "remove", "keep"]
    rationale: str | None = None
    locked: bool = False


class SummaryProvenance(BaseModel):
    """The tailored summary's before/after — the same before/after/revert
    affordance `BulletProvenance` gives each bullet, for the one CV field
    that isn't tied to a single Evidence item.

    No `evidence_id`/`action`/`rationale`: the Rewrite Bullets stage always
    writes a fresh summary from the whole Evidence/Requirements set rather
    than rewriting one Evidence item under one `RewriteAction` (see
    05_rewrite_bullets_v1.md's summary rule), so there's no single action
    or per-item reason to report the way a bullet has one. `original_text`
    is the candidate's own profile summary (`Candidate.summary`) — omitted
    entirely (this whole object is `None` on the report) when the
    candidate had none to compare against, or when the tailored summary
    came out identical to it, mirroring `BulletProvenance`'s own
    only-report-a-genuine-edit precedent (see build_report's docstring).
    """

    original_text: str
    rewritten_text: str


class BulletProvenanceReport(BaseModel):
    """Output of app/bullet_provenance.py:build_report() (Phase 17): one
    `BulletProvenance` per bullet that made it into the assembled CV, plus
    the Evidence items that didn't — surfaced to the user as "didn't make
    the cut," same advisory-only treatment as `MatchResult.gaps`.
    """

    bullets: list[BulletProvenance] = Field(default_factory=list)
    unused_evidence: list[Evidence] = Field(default_factory=list)
    summary: SummaryProvenance | None = None


class GenerationTiming(BaseModel):
    """How long one `run_cv_generation` call (app/pipeline.py) took, broken
    down by LLM stage — asked for directly, to answer "how long does a
    generation actually take" from real data instead of guessing from
    `CVDraft.created_at`/`updated_at` (which include however long the
    person then spent editing in the browser, not just the generation
    itself).

    Each `*_seconds` field is wall-clock time around exactly one stage's
    call in app/pipeline.py, measured with `time.perf_counter()` — not a
    token count or a provider-reported figure, so it includes network
    latency and any client-side retry the provider layer does, same as a
    person watching a spinner would experience. `total_seconds` is the
    full `run_cv_generation` call, not a sum of the stages below — it
    also covers the (normally negligible) local deterministic work
    between them (locking partition/splice, CV assembly, provenance
    building), so `total_seconds` is always >= the sum of the five stage
    figures, never less.

    Informational only, exactly like `BulletProvenanceReport` — never
    re-derived from or folded into `AssembledCV`, and no behavior in the
    app reads it back; it exists purely so a `CVDraft`'s own timing can be
    inspected later (SQLite, GET /candidates/{id}/drafts/{draft_id}),
    the same durable place `provenance` already lives, rather than only
    living in a log line nobody captures.
    """

    vacancy_analysis_seconds: float
    matching_seconds: float
    rewrite_planning_seconds: float
    bullet_rewriting_seconds: float
    quality_recheck_seconds: float
    total_seconds: float


class TextRun(BaseModel):
    """Phase 25 — one inline-styled span within a `PrintDocumentBlock`.
    Structural mirror of frontend/src/lib/structuredDocument.ts's `TextRun`
    (same field-name-must-match-exactly rule as `PrintDocumentBlock`'s own
    docstring below). `link`, not `url` — this is a person applying a
    hyperlink to arbitrary selected text (Phase 31's BubbleMenu), distinct
    from `app/markdown_inline.py::InlineRun.url`, which is auto-*detected*
    from a bare `http(s)://` substring rather than explicitly applied.
    """

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    link: str | None = None


class PrintDocumentBlock(BaseModel):
    """One editable unit in the Phase 16a on-screen document editor — a
    section entry, or (nested) one of an Experience entry's bullets.

    Structural mirror of frontend/src/lib/structuredDocument.ts's
    `DocumentBlock` — the frontend sends its live editor state verbatim as
    JSON, so these two shapes must stay in lockstep by hand (no shared
    schema generation crosses the TS/Python boundary here). Field names
    must match exactly (no camelCase/snake_case aliasing exists anywhere
    on this boundary) — `evidence_id` below was missing here entirely
    until Phase 20b's follow-up, which meant the frontend's own
    `DocumentBlock.evidenceId` was silently dropped by Pydantic on every
    save (unrecognized-field, ignored by default) the instant a document
    round-tripped through the backend at all — disabling the "AI-edited
    bullet" Sparkles marker from the very first draft save, not just on a
    reopen. Reported directly, from a real generated draft with zero
    Sparkles despite genuinely AI-rewritten bullets and (by then)
    correctly-persisted provenance.
    """

    id: str
    text: str
    included: bool
    locked: bool | None = None
    # "subheading" = a category name (Skills/Technologies) or a project
    # name (Experience bullets) — rendered without a bullet marker.
    # None/"item" = a normal bulleted line. Post-31 — "compact" is a
    # third value, entry-level only (never a bullet): a whole Skills/
    # Technologies category or uncategorized run already pre-joined onto
    # one line (structuredDocument.ts's buildCompactSkillEntries) —
    # app/cv_markdown.py's group_entries_by_subheading/app/cv_docx.py's
    # identical branch both check for it first and skip grouping
    # entirely for a section where every entry already carries it, since
    # re-grouping/re-joining already-final lines would wrongly fuse
    # multiple of them onto one. See structuredDocument.ts's matching
    # field for the full rationale.
    kind: str | None = None
    # Only ever set on Experience bullets (see `TailoredBullet.evidence_id`'s
    # docstring) — links a bullet block back to its `BulletProvenance` so
    # the editor can show the AI-edit highlight/popover/"revert to
    # original". `None` for every other block (section entries, gap
    # entries, project-name subheadings).
    evidence_id: str | None = None
    # Phase 25 — rich-run content model, no editor UI to produce this yet
    # (Phase 31). `None` for every block today (every existing draft, and
    # every block the current A4 editor can still only edit as one plain
    # string) — `text` stays the authoritative plain-text fallback for
    # search/ATS parsing/every renderer's "no runs" path. When `runs` IS
    # set, it is authoritative over `text` for rendering (every renderer
    # checks `runs` first) — `text` should still be kept in sync as the
    # concatenation of `runs[].text` so a renderer with no runs support
    # left (there are none after this phase, but the fallback exists for
    # robustness) never shows blank/stale content.
    runs: list[TextRun] | None = None
    # Paragraph-level, not a run — mirrors `python-docx`'s own
    # `paragraph.alignment`. `None` means "whatever the template's default
    # is" (today's behavior, unchanged), not explicitly "left".
    alignment: Literal["left", "center", "right"] | None = None


class PrintDocumentEntry(PrintDocumentBlock):
    """Mirrors `DocumentEntry` — `bullets` is only ever populated for
    Experience entries; every other section's entries are flat."""

    bullets: list[PrintDocumentBlock] | None = None
    # Phase 30 — manual pagination control, confirmed with the user
    # directly: the automatic break-after/break-inside CSS rules
    # (index.css's `@media print` block, Phase 16c) are "hidden rules" a
    # person can't see or override from the editor — a person can only
    # tell where a page will actually break by exporting and looking.
    # This is the deliberate escape hatch: when true, every export format
    # forces a real page break immediately before this entry, giving the
    # person direct, visible control over pagination instead of hoping
    # the automatic heuristics land where they want. Declared here (not
    # on `PrintDocumentBlock`, the base class bullets also share) since
    # it's meaningful only at entry granularity — a bullet-level version
    # was considered and explicitly ruled out in favor of this simpler
    # scope (see docs/development_plan.md's Phase 30 notes).
    page_break_before: bool = False


class PrintDocumentSection(BaseModel):
    """Mirrors `DocumentSection`."""

    key: str
    title: str
    included: bool
    entries: list[PrintDocumentEntry]
    # Phase 30 — same manual-break escape hatch as
    # `PrintDocumentEntry.page_break_before`, one level up: forces a
    # break immediately before this whole section (heading included).
    page_break_before: bool = False


class PrintDocument(BaseModel):
    """Mirrors `DocumentModel` — the whole edited document as the Phase
    16a A4 Preview tab currently holds it (reordered/toggled/edited),
    sent to `/export` for a templated PDF/DOCX export (Phase 16b)."""

    sections: list[PrintDocumentSection]


class CVDraft(BaseModel):
    """Phase 20: a persisted generate-and-refine session — "previous CV
    drafts linked to a JD" as a real, storable concept, not just ephemeral
    pipeline output.

    `match_result`/`provenance` are `None` for an untailored draft (no LLM
    call, nothing to report) and, until Phase 20b, were *never* persisted
    even for a tailored one — deliberately ephemeral, matching
    `domain.models.MatchResult`/`BulletProvenance`'s own "informational,
    not CV content" docstrings, carried through the *first* navigation
    only (`ExportScreen.tsx`'s `navigate(..., {state})`) and lost on any
    reopen (refresh, "Your drafts", a direct link). Reported directly as
    confusing in practice: a reopened tailored CV showed genuinely-edited
    bullet text with no way to tell *which* bullets were AI-edited or why
    (no Sparkles marker, no Gaps panel) — indistinguishable from a draft
    the AI barely touched. Now persisted alongside `document` so a reopen
    looks identical to the original landing. Still informational only —
    never re-derived from or folded into `assembled_cv`, same as before.

    One `CVDraft` per generate, not per edit — created once when a
    generate finishes, then updated in place (`document`, and via it
    `assembled_cv`'s companion structured content) as the person keeps
    editing that same session, never a new row per edit. This is what
    keeps it from becoming version history (`docs/PROJECT_CONTEXT.md`'s
    Non-goals): it's always the current state of *one* session, not a
    growing history of past states.
    """

    id: str
    candidate_id: str
    vacancy: Vacancy
    assembled_cv: AssembledCV
    document: PrintDocument
    match_result: MatchResult | None = None
    provenance: BulletProvenanceReport | None = None
    # `None` for the same cases `provenance` is: an untailored draft (no
    # LLM call, nothing to time) and any draft saved before this field
    # existed — never backfilled, same "old data simply predates the
    # field" precedent as `BulletProvenanceReport.summary`.
    timing: GenerationTiming | None = None
    created_at: datetime
    updated_at: datetime


class CVDraftSummary(BaseModel):
    """A lightweight listing entry (`GET /candidates/{id}/drafts`) — not
    the full `vacancy`/`assembled_cv`/`document` blobs, so listing a
    candidate's drafts stays cheap regardless of how large any one draft's
    document has grown."""

    id: str
    vacancy_title: str | None
    vacancy_company: str | None
    created_at: datetime
    updated_at: datetime
