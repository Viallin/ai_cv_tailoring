# Contracts

> This file documents contracts that exist in code today
> (`contracts/schemas.py`, `domain/models.py`), updated through Phase 25,
> plus targeted later additions for the `PrintDocumentBlock.locked`
> behavior change (Phase 28 follow-up — no schema change), the
> `page_break_before` field (Phase 30), the `kind: "compact"` entry
> shape plus widened `runs` scope (Phase 31), `CVProjection.headline` /
> `Experience.company_url` / `ExperienceProject.url` (Post-4.10 follow-up,
> see `docs/development_plan.md`'s Version 4 section), `Requirement.priority`
> and `MatchRequest.candidate_education`/`.candidate_contacts` (Post-4.10
> fixes rounds 3-4) — not a full re-pass of every section below. Phase references below to Phases 0-12.3 point to detail
> now archived in `docs/archive/development_plan_v1.md`; references to
> Phases 13-23 point to `docs/archive/development_plan_v2.md`; references
> to Phases 24-31 point to `docs/archive/development_plan_v3.md` (Version
> 3, shipped). See `docs/domain-model.md` for the conceptual/business-rule
> view of the same entities — this file is the literal shape.

## Data Structures
### Candidate
Мастер-резюме - контентная база, а не конкретное CV! Оно должно быть:
* Атомарным
* Вариативным
* Контекстно-помеченным 
* Без финальной композиции
* У каждого блока в резюме может быть набор вариаций в зависимости от роли и угла подачи информации (название роли, общее описание опыта, ключевые достижения у разных работодателей/на разных проектах)

Master Resume = Knowledge Graph of Career Claims + Text Variants + Semantic Controls

{
  "name": "...",
  "headline": "...",
  "summary": "...",
  "employment_types_sought": [],
  "contacts": [],
  "experience": [],
  "volunteer_experience": [],
  "education": [],
  "skills": [],
  "technologies": [],
  "languages": [],
  "certifications": [],
  "awards": [],
  "projects": [],
  "publications": [],
  "portfolio_links": []
}

Fields added since the original prototype scope (all always-included in
export, not AI-tailored, same treatment as `education`/`projects` — see
`docs/archive/development_plan_v1.md`'s Phase 12.3 addenda for the
reasoning behind each): `employment_types_sought` (job-search preference,
small closed `EmploymentType` enum), `volunteer_experience` (unpaid work,
structurally a simplified `Experience`), `technologies` (mirrors
`skills` — see the Skills section below), `awards` (mirrors
`certifications`), `publications` (mirrors `projects`, with `venue`/`date`
instead of `description`), `portfolio_links` (`url` + optional
`description`, split out of `Contacts` so more than one is possible).

`summary` is the candidate's own positioning statement/"about me" text, as
written in the resume — often untitled, just a paragraph after the contact
block. Captured close to verbatim at ingestion. Distinct from
`CVProjection.summary` below (the AI-generated, per-vacancy tailored
summary) — the latter may draw on this one as context but is written fresh
each time, never copied verbatim. See `docs/development_plan.md` Phase 5
notes.

#### Contacts
{
  "label": "...",
  "value": "..."
}

Flexible label+value pairs — not fixed named fields like `email`/`phone`.
What belongs on a CV header varies by role and location: `Email`, `Phone`,
`LinkedIn`, `Location`, `Work Authorization`, `Portfolio`, `GitHub`,
`Website` are all typical `label`s, but any label the resume actually
supports is valid. A resume without a phone number just has no `Phone`
item.

#### Experience
{
  "company": "...",
  "company_url": null,
  "position": "...",
  "period": "...",
  "location": "...",
  "responsibilities": [],
  "achievements": [],
  "projects": [
    {"name": "...", "period": "...", "achievements": [], "responsibilities": [], "url": null}
  ],
  "is_gap": false
}

`company` is optional — used for explicit employment gaps (`is_gap: true`:
parental leave, sabbatical, career break) that aren't necessarily tied to
one employer. Gap entries always appear in the final assembled CV (see
`RewriteBulletsRequest`/`RewriteBulletsResponse` below) regardless of what
the tailoring LLM calls selected — they're facts about the timeline, not
content to tailor.

`projects` (Phase 7) is for roles structured company -> project -> dates ->
bullets instead of a flat bullet list (e.g. an agency/studio role with
several named client projects) — most Experience entries leave this empty
and just use `responsibilities`/`achievements` directly. Distinct from the
top-level `Candidate.projects` ("Key Projects") below, which is a standalone
portfolio section, not nested inside a role.

`company_url` / `ExperienceProject.url` (Post-4.10 follow-up) are the
employer's/project's own website, closing a real ingestion gap: a source
PDF hyperlinking a company or project name to its own site (rather than
writing the URL out as visible text) previously had nowhere to land —
`app/resume_reader.py` surfaces the link via the PDF's `/Link` annotations,
but the CV Parser had no field to place it in, so it was silently dropped.
Both render as real hyperlinks on the company/project name across plain
Markdown/PDF/DOCX export, the on-screen document editor (via a `TextRun`),
and the Profile Explorer. `graph_writeback.py` strips a hyperlinked
company/project name back to plain text before writing back, so a
hand-edited linked entry can't be corrupted with literal `[text](url)`
syntax.

#### Education

#### Skills
{
  "name": "...",
  "category": "...",
  "proficiency": "...",
  "evidence_ids": [],
  "is_category_header": false
}

`evidence_ids` (Phase 15a) — ids into the sibling `evidence` list (which
Evidence item(s) demonstrate this skill). Many-to-many by design: one
Evidence item can back several skills, one skill can be backed by several
Evidence items. Usually empty — most skills come from a flat "Skills:"
line with nothing bullet-level to link to; only skills a resume bullet
clearly demonstrates get populated, and only at ingestion
(`01_cv_parser_v1.md`) or via `CandidateService.update_skill()` /
`PUT /candidates/{id}/skills/{id}`, which validates every id actually
exists for this candidate (raises `ValidationError` otherwise — see
`Technology`'s note below for why `Evidence.experience_id` is *not* held
to the same eager-validation standard). `Technology` has the identical
`evidence_ids` field and validation, but resume ingestion never populates
it — `01_cv_parser_v1.md` doesn't extract `technologies` at all, so the
link there is manual-only, via `update_technology()`.

A skill/technology's `evidence_ids` can go stale (a bullet gets rewritten
or removed after the link was set) without anything re-checking it — the
link is purely explainability, never consumed by matching/rewriting/
export, so a full resume re-ingestion isn't warranted just to refresh it.
Phase 22 adds an on-demand `POST /jobs` job
(`type: "relink_skill_evidence"`) that re-runs the linking step
(`06_skill_evidence_linker_v1.md`) against the candidate's current
Evidence without touching anything else in the profile.

`is_category_header` (Phase 21) — a normal `Skill`/`Technology` row (same
CRUD routes as any other) whose `name` holds a category label instead of
a real skill, used by the Profile Explorer's editor to render a flat,
drag-orderable list where some rows are section headers. When `true`,
`category`/`proficiency`/`evidence_ids` are unused; a real skill's
`category` is derived client-side from the nearest preceding header row
and written back onto that skill, mirroring the grouped, AI-ranked-
within-category export `app/cv_assembler.py:_rank_by_category` already
produces (see the CVProjection/AssembledCV notes below).

#### Languages
{
  "name": "...",
  "proficiency": "..."
}

#### Certifications
{
  "name": "...",
  "issuer": "...",
  "date": "..."
}

#### Projects
{
  "name": "...",
  "description": "...",
  "url": "..."
}

The standalone "Key Projects" section — distinct from `Experience`, not
tied to one employer. Always included in the exported CV as-is (like
Education), not AI-tailored per vacancy like Experience is — see
`docs/development_plan.md` Phase 5 notes for the reasoning and how to
upgrade this later if needed. `url` here is a per-project link (e.g. a
store page or demo); a person-level link (GitHub profile, personal site)
belongs in `Contacts` instead.

### Vacancy

{
  "title": "...",
  "company": "...",
  "raw_text": "...",
  "requirements": [],
  "keywords": []
}

Note: no separate `responsibilities` field — a JD's responsibilities and
requirements are both captured as `Requirement` items (see below); nothing
downstream currently distinguishes "responsibility" from "requirement".

#### Requirement
{
  "text": "...",
  "keywords": [],
  "priority": "required"
}

`priority` (`"required"` default | `"nice_to_have"`, Post-4.10 fixes round
3) tells the Matching stage whether the JD's own structure frames this as
a baseline expectation or as optional/bonus — set only from the JD's own
explicit framing (a "Nice to have"/"Bonus points"/"Will be a plus"/
"Preferred" heading or equivalent inline phrasing, never from an item
merely sounding less important). Defaults to `"required"` so an
already-persisted `Vacancy` never has a real Gap silently softened. A
`"nice_to_have"` Requirement is capped at `Gap.severity: "medium"`
regardless of how unaddressed it is (see `03_cv_jd_matcher_v1.md`).

### CV

There are two CV-shaped models — don't conflate them (see the
`RewriteBulletsRequest`/`RewriteBulletsResponse` section below for why):

**CVProjection** — AI-tailored content only, per vacancy:
```json
{
  "summary": "...",
  "experience": [
    {"experience_id": "exp-1", "bullets": [{"text": "...", "project": null, "evidence_id": "ev-1"}]}
  ],
  "skills": [],
  "technologies": []
}
```

`bullets[].evidence_id` (Phase 17) links a tailored bullet back to the
Evidence item it was rewritten from — see "AI-edit transparency" below.
`technologies` (Phase 21 addendum) mirrors `skills`: the LLM ranks the
Candidate's existing `technologies` list by relevance the same way it
ranks `skills`, it doesn't invent either list — see that section for why.

**AssembledCV** — the complete, exportable CV (Candidate facts + CVProjection,
merged deterministically, no LLM involved):
```json
{
  "name": "...",
  "headline": "...",
  "employment_types_sought": [],
  "contacts": [],
  "summary": "...",
  "experience": [
    {"experience_id": "exp-1", "company": "...", "position": "...", "period": "...", "location": "...", "bullets": [{"text": "...", "project": null, "evidence_id": "ev-1"}], "is_gap": false}
  ],
  "volunteer_experience": [],
  "education": [],
  "skills": [],
  "technologies": [],
  "languages": [],
  "certifications": [],
  "awards": [],
  "projects": [],
  "publications": [],
  "portfolio_links": []
}
```

`skills`/`technologies` here are the Candidate's own full `Skill`/
`Technology` records (category, proficiency, `is_category_header`) —
**not** `CVProjection.skills`/`.technologies` (plain ranked name lists).
`app/cv_assembler.py:_rank_by_category` applies the LLM's ranking within
each category, grouping itself stays deterministic from the Candidate
list's own order. See "Skills/Technologies: category-header groups"
below.

## LLM Requests

### IngestResumeRequest / IngestResumeResponse

Parses a raw resume (`01_cv_parser_v1.md`) into **two separate things**,
returned together in one response — do not confuse them:

* `candidate` — the structural profile record: name, contacts, education,
  and work history (company/position/period/responsibilities/achievements),
  basically the resume re-typed as structured data. This is what gets saved
  into the local Candidate Profile (see `app/candidate_service.py`,
  `CandidateService.replace`) so a person never has to re-paste their own
  history into the tool.
* `evidence` — the same work history broken into atomic, one-fact-each
  Evidence items. This is a separate semantic layer used later for
  Claim/Variant generation and vacancy matching (deferred; see
  `docs/development_plan.md` Phase 7-8). It is not derived from `candidate`
  and is not written into the Candidate Profile automatically.

```json
{
  "candidate": {
    "name": "...",
    "headline": "...",
    "contacts": [{"id": "contact-1", "label": "Email", "value": "..."}, {"id": "contact-2", "label": "Phone", "value": "..."}],
    "experience": [{"id": "exp-1", "company": "...", "position": "...", "period": "...", "responsibilities": [], "achievements": [], "projects": [{"id": "exp-1-proj-1", "name": "...", "period": "...", "achievements": []}], "is_gap": false}],
    "education": [{"id": "edu-1", "institution": "...", "degree": "...", "field": "...", "period": "..."}],
    "skills": [{"id": "skill-1", "name": "...", "category": "...", "evidence_ids": ["ev-1"]}],
    "languages": [{"id": "lang-1", "name": "...", "proficiency": "..."}],
    "certifications": [{"id": "cert-1", "name": "...", "issuer": "...", "date": "..."}],
    "projects": [{"id": "proj-1", "name": "...", "description": "...", "url": "..."}]
  },
  "evidence": [
    {
      "id": "ev-1",
      "text": "...",
      "source_context": "...",
      "experience_id": "exp-1",
      "experience_project_id": "exp-1-proj-1",
      "locked": false,
      "locked_text": null
    }
  ]
}
```

`experience_id`/`experience_project_id` (Phase 7) are structured links back
into `candidate.experience` (and, when set, one of that entry's `projects`)
— both optional, added so the Matching stage (`03_cv_jd_matcher_v1.md`) and
Bullet Rewriting stage (`05_rewrite_bullets_v1.md`) can point at/group by
role/project directly instead of guessing from `source_context` prose.
Evidence not drawn from a specific role (e.g. from a Key Project or a
summary line) omits both. Unlike `skills[].evidence_ids` (see the Skills
section above), these are never cross-validated against real
`candidate.experience[].id` values at save time — only checked later, at
CV-assembly time (`assemble_cv()`) — so ingestion can't reject a
hallucinated `experience_id` the way `update_skill()` rejects a
hallucinated `evidence_ids` entry.

Re-running resume ingestion overwrites the whole Candidate Profile
(`CandidateService.replace`) — it does not merge with entries added manually
afterward via `add_experience` / `add_education` / `add_skill`. See
`docs/development_plan.md` Phase 2 notes for the reasoning.

`locked`/`locked_text` (Phase 19) — when `locked: true`, every future
Rewrite Planning/Bullet Rewriting call excludes this Evidence item from
the LLM entirely and splices `locked_text` back into the output verbatim
instead (falling back to the raw `text` if `locked_text` was never set).
Durable across every future generate, for any vacancy — not a
per-generate setting like a `TailoredBullet`. This is the cheap
alternative to embedding-based bullet-variant reuse (see
`docs/PROJECT_CONTEXT.md`'s Future Ideas).

### AnalyzeVacancyRequest / AnalyzeVacancyResponse

Parses a raw job description (`02_jd_parser_v1.md`). Unlike
`IngestResumeResponse`, this one is intentionally a thin validation target,
not the final artifact:

* `AnalyzeVacancyResponse` (what the LLM actually returns) — `title`,
  `company`, `requirements`, `keywords`. No `raw_text`: the caller already
  has the JD text it sent in, so asking the model to echo it back would
  waste tokens and risk drift/paraphrasing.
* `VacancyAnalysisService.analyze()` combines that with the original input
  text to build a `domain.models.Vacancy` (adds `raw_text`), and returns the
  `Vacancy` — **not** the raw `AnalyzeVacancyResponse`. Callers should never
  need to construct `raw_text` themselves.

```json
{
  "title": "...",
  "company": "...",
  "requirements": [
    {"text": "...", "keywords": ["...", "..."]}
  ],
  "keywords": ["...", "..."]
}
```

`Requirement.keywords` is a list, not a single value — one requirement can
reasonably name several skills/tools ("5+ years with Python, Django, and
PostgreSQL").

### Tailoring: Matching -> Rewrite Planning -> Bullet Rewriting (Phase 8)

Phase 5-7's single collapsed `03_cv_builder_v1.md` call (Candidate +
Evidence + Requirements -> `CVProjection` in one shot, no visible
matching/gap step) was split into three real stages per
`docs/development_plan.md` Phase 8. Each stage's contract is below; see
that doc's Phase 8 notes for the reasoning.

#### MatchRequest / MatchResponse

Matches the Candidate's Evidence against a vacancy's Requirements
(`03_cv_jd_matcher_v1.md`) — `experience` (grouping/context only),
`evidence`, `requirements` in; a `MatchResult` out.

`MatchResponse.match_result` is a `domain.models.MatchResult` — **not** CV
content. It's informational, surfaced to the user as-is (the "Gaps" panel
in the frontend's `GapsPanel`, `frontend/src/components/`): `matches`
(which Requirements are supported, by which Evidence ids, and how
strongly) and `gaps` (Requirements that are missing or only weakly
supported), plus any `missing_keywords`.

```json
// MatchResponse
{
  "match_result": {
    "matches": [
      {"requirement_text": "5+ years Python", "evidence_ids": ["ev-1", "ev-2"], "strength": "high"}
    ],
    "gaps": [
      {
        "requirement_text": "AWS certification",
        "description": "No cloud certification found.",
        "severity": "high",
        "suggested_action": "If you have any AWS experience, add a bullet naming it explicitly.",
        "status": "open"
      }
    ],
    "missing_keywords": ["AWS"]
  }
}
```

`Gap.severity` (`"high"`/`"medium"`/`"low"`, Phase 8.2) and
`suggested_action` (optional, one advisory sentence) make the Gaps panel
sortable by importance with a concrete next step — both purely advisory,
never fed back into `RewritePlannerService` by any new code path (see
`domain.models.Gap`'s docstring).

`Gap.status` (`"open" | "skipped"`, Phase 18) lets a user dismiss a gap
after manual edits instead of it resurfacing on every re-check. Every
freshly matched Gap is `"open"` — Matching never sets `"skipped"` itself;
the frontend tracks a session-local set of dismissed
`requirement_text`s and applies it after each re-check (there's nowhere
server-side to persist a dismissal until a `CVDraft` exists to attach it
to — see `CVDraft` below). Re-checking Matching against the *current
edited* document, not just once before tailoring, is itself a Phase 18
addition (`MatchingService.match()` was decoupled to be invoked again
on demand).

`RequirementMatch`/`Gap` use `requirement_text` (copied verbatim from the
Requirement), not an id — see `domain.models.RequirementMatch`'s docstring
for why `Requirement` itself doesn't need an id field for this.

`MatchRequest` also carries `candidate_skills`/`candidate_technologies`/
`candidate_languages`/`candidate_certifications`/`candidate_education`
(Phase 8.4, Post-4.10 round 3) and `candidate_contacts` (Post-4.10 round
4) — plain declarative facts from the Candidate's own flat profile fields
that the matcher couldn't otherwise see from Evidence alone (e.g. a
"Relocation" Contacts entry answering a relocation requirement no bullet
ever mentions). `candidate_contacts` is filtered before it reaches the
prompt: `app/pipeline.py:_matching_contacts` drops any Contact whose value
looks like an email address or phone number, so Matching/recheck calls
never send direct personal identifiers to the LLM for fields with no
matching benefit — Resume Ingestion is unaffected and still sees the real
values.

#### RewritePlanRequest / RewritePlanResponse

Decides what to do with each Evidence item (`04_rewrite_planner_v1.md`) —
same `experience`/`evidence`/`requirements` as `MatchRequest`, plus the
Matching stage's own `match_result`, so the plan can use its matches/Gaps
rather than re-deriving them. Produces a `RewritePlan`, **no rewritten text
yet** — that's the next stage.

```json
// RewritePlanResponse
{
  "plan": {
    "actions": [
      {
        "evidence_id": "ev-1",
        "action": "rewrite",
        "reason": "Weak phrasing, strong underlying fact.",
        "target_keywords": ["Python"],
        "new_angle": "Emphasize ownership."
      }
    ],
    "priority_order": ["ev-1", "ev-2"]
  }
}
```

`action` is one of `"rewrite" | "enhance" | "remove" | "keep"` — no
`"merge"` (an early sketch had one; dropped as unneeded complexity for a
prototype, see `domain.models.RewriteAction`'s docstring).

#### RewriteBulletsRequest / RewriteBulletsResponse

The final stage (`05_rewrite_bullets_v1.md`) — produces the same
`CVProjection` shape the old collapsed `03_cv_builder_v1.md` call used to
in one shot, but now driven by the Rewrite Planning stage's `plan` instead
of deciding relevance and rewriting in the same call.

`RewriteBulletsResponse.cv` is a `CVProjection` — **not** the final CV. It's
AI-tailored *content* only: `summary`, `headline`, per-role `bullets`
grouped by `experience_id` (must match an id in the `experience` sent in
the request — the LLM never invents one), and `skills`. Identity, contacts,
education, dates, company names, languages, and certifications are
deliberately absent: those are facts, and letting an LLM regenerate your
own name or employment dates risks hallucination for no benefit.

`CVProjection.headline` (Post-4.10 follow-up) is the one-line role title
shown under the candidate's name — the same "fresh per vacancy, grounded in
Evidence" treatment as `summary`: it must not simply copy
`RewriteBulletsRequest.vacancy_title` (that would risk asserting a
seniority/specialization the candidate isn't evidenced for — the same
invented-title failure `05_rewrite_bullets_v1.md` already guards against
for bullets), nor just copy `candidate_headline` verbatim (that's the bug
being fixed: `Candidate.headline` used to be copied into every tailored CV
regardless of vacancy). `None` for `app/cv_assembler.py:
build_untailored_projection`'s zero-AI path — `assemble_cv()` falls back to
`Candidate.headline` in that case.

Each bullet is `{"text": "...", "project": "..." | null, "evidence_id": "..." | null}`
(Phase 7 + Phase 17) — `project` is the display name of the Experience
entry's nested `ExperienceProject` this bullet came from (resolved from
the linked Evidence's `experience_project_id`), or `null` if the bullet
belongs to the role directly. `project` is a name, not an id — like
`TailoredExperience`, it never references Candidate ids beyond
`experience_id` itself. `evidence_id` echoes the Evidence item the LLM
rewrote this bullet from — see "AI-edit transparency" below for what it's
used for.

`RewriteBulletsRequest.candidate_summary` passes through `Candidate.summary`
(the candidate's own "about me" text, if captured — see the Candidate
section above) as context for the LLM's tone/positioning — it is explicitly
*not* a source of new facts, and the prompt is told not to copy it verbatim.
May be `None`; `BulletRewriteService.rewrite()` substitutes an explicit
"(No summary provided.)" placeholder in that case rather than letting a bare
`None` render literally into the prompt text.

`RewriteBulletsRequest.candidate_headline`/`.vacancy_title` are the same
kind of read-only context, for the tailored `headline` above:
`candidate_headline` passes through `Candidate.headline` and `vacancy_title`
passes through `Vacancy.title` (either may be `None` — an empty string
renders in that case, not a placeholder sentence, since the prompt's Input
section already documents empty as "profile/JD has none").

`app/cv_assembler.py:assemble_cv(candidate, projection)` merges the
Candidate with this stage's `CVProjection` — looks up each `experience_id`'s
company/position/period from the Candidate, attaches the tailored bullets,
and copies education/languages/certifications straight from the Candidate —
to produce the `AssembledCV` that's actually exported. This function raises
`ValidationError` if `CVProjection` references an `experience_id` that isn't
in the Candidate (a stale or hallucinated id) — that's a signal something's
wrong upstream, not something to silently drop.

**Employment gaps (`Experience.is_gap=True`) never go through any of the
three LLM calls** — `MatchingService.match()`, `RewritePlannerService.
plan()`, and `BulletRewriteService.rewrite()` all filter them out of what's
sent to their respective prompts, and `assemble_cv()` includes them in the
output unconditionally, in the Candidate's own chronological order (not the
CVProjection's order — see `docs/development_plan.md` Phase 5 notes). This
is deliberate: a gap has no supporting Evidence for the LLM to match/plan/
tailor, and letting it silently vanish if the LLM doesn't reference it would
recreate exactly the unexplained-gap problem structured data is supposed to
prevent.

```json
// RewriteBulletsResponse.cv (CVProjection — content only)
{
  "summary": "...",
  "headline": "...",
  "experience": [
    {"experience_id": "exp-1", "bullets": [{"text": "...", "project": null, "evidence_id": "ev-1"}]}
  ],
  "skills": ["...", "..."],
  "technologies": ["...", "..."]
}
```

See `docs/development_plan.md` Phase 5 notes for why `CVProjection` and
`AssembledCV` are split into two models instead of one, and its Phase 8
notes for why tailoring itself is three chained calls instead of one.

## AI-edit transparency: BulletProvenance (Phase 17)

`domain.models.BulletProvenance` — one rewritten bullet's before/after/why,
keyed by the Evidence item it came from. Deliberately informational only,
like `MatchResult`: never folded into `AssembledCV`/`CVProjection`, never
exported.

```json
// BulletProvenance
{
  "evidence_id": "ev-1",
  "original_text": "Managed a small team.",
  "rewritten_text": "Led a cross-functional team of 5 engineers, shipping...",
  "action": "rewrite",
  "rationale": "Weak phrasing, strong underlying fact.",
  "locked": false
}
```

`original_text` and `rationale` are both assembled deterministically by
`app/bullet_provenance.py` from data that already exists (`Evidence.text`
and the Rewrite Planning stage's `RewriteAction`) — **not** asked of the
Bullet Rewriting LLM call. The one new thing the LLM does supply is
`TailoredBullet.evidence_id` (see above), which is what lets provenance be
joined back to a specific bullet at all.

`locked` is `true` when this bullet came from a locked Evidence item (see
`locked`/`locked_text` above) — reused verbatim rather than actually
rewritten this round. It's orthogonal to `action` (which falls back to
`"keep"` with no rationale for a locked bullet, since it was excluded from
Rewrite Planning entirely), not a fifth action value — so the frontend can
tell "the AI decided to keep this unchanged" apart from "this bullet was
never sent to the AI at all."

`domain.models.BulletProvenanceReport` wraps a `bullets: list[BulletProvenance]`
(one per bullet that made it into the assembled CV) plus
`unused_evidence: list[Evidence]` — Evidence items that didn't make the
cut, surfaced to the user as "didn't make the cut — add manually?", the
same advisory-only treatment as `MatchResult.gaps`.

## The structured document model: PrintDocument (Phase 16, extended 21/24/25/30/31)

The actual on-screen A4 editor's document shape — what `PUT`s back to a
`CVDraft.document` (see below) and what `POST /export` renders. A
**structural mirror of `frontend/src/lib/structuredDocument.ts`**: the
frontend sends its live editor state as JSON verbatim, so the TS and
Python shapes must be kept in lockstep by hand — there is no shared
schema generation across that boundary, and field names must match
exactly (no camelCase/snake_case aliasing exists anywhere here; a missed
field is silently dropped by Pydantic on every save, not rejected — see
`domain.models.PrintDocumentBlock`'s docstring for a real bug this caused).

```json
// PrintDocument
{
  "sections": [
    {
      "key": "experience",
      "title": "Experience",
      "included": true,
      "page_break_before": false,
      "entries": [
        {
          "id": "exp-1",
          "text": "Senior Engineer, Acme Corp",
          "included": true,
          "locked": null,
          "kind": null,
          "evidence_id": null,
          "runs": null,
          "alignment": null,
          "page_break_before": false,
          "bullets": [
            {
              "id": "exp-1-bullet-1",
              "text": "Led a cross-functional team of 5 engineers...",
              "included": true,
              "locked": false,
              "kind": "item",
              "evidence_id": "ev-1",
              "runs": null,
              "alignment": null
            }
          ]
        }
      ]
    }
  ]
}
```

Per-block fields (`PrintDocumentBlock`, and `PrintDocumentEntry` which
adds `bullets`):
* `included` — the section/entry/bullet include-toggle. **Phase 24
  ("exclude → stash"):** unchecking a block removes it from the rendered
  page entirely and lists it in a frontend-only "Excluded from CV" panel
  with a Restore action — no schema change, `included` already existed
  and already persisted; the stash panel is purely a frontend view
  (`frontend/src/lib/excludedContent.ts`) computed by walking the
  document for `included: false` entries/bullets.
* `locked` — one field, two meanings depending on which kind of block it's
  set on (the source itself, `domain/models.py`'s `PrintDocumentBlock.
  locked`, carries no docstring distinguishing them — noted here since it
  isn't obvious from the field alone):
  * On a **bullet**: Phase 19 bullet locking's on-screen reflection (not
    the same field as `Evidence.locked`, though driven by it) — the
    rewrite stage skipped the LLM call and reused locked text verbatim.
  * On an **entry**: set for a career-gap `Experience.is_gap=True` entry
    (see this section's own note above on gaps never going through the
    LLM calls) — a signal that generation deliberately kept it, *not* a
    restriction on what the user can do with it afterward. Through Phase
    28's own first pass, a locked entry's on-screen checkbox was also
    disabled, forbidding the user from excluding a gap by hand; reported
    directly as unwanted ("we don't throw gaps away during generation,
    but we shouldn't forbid the user from doing it, it's their
    decision") and removed at both the UI layer and
    `structuredDocument.ts::toggleEntryIncluded`'s own independent guard
    — `locked` no longer blocks the include/exclude toggle for either
    kind of block it's set on.
* `kind` (Phase 16/21, extended Post-31) — `"subheading"` for a category
  name (Skills/Technologies) or a project name (Experience bullets),
  rendered without a bullet marker; `"compact"` (Post-31) for a
  Skills/Technologies entry that already holds one whole, pre-joined
  category/flat line (`"Category: item1, item2"` or `"item1 · item2"`) as
  its own `runs` — the stored shape now, not just an export-time
  transform, so it's the one unit that gets checked out, dragged, or
  page-broken; `null`/`"item"` for a normal bulleted line.
* `evidence_id` (Phase 17/20) — only ever set on Experience bullets, links
  a block back to its `BulletProvenance` so the editor can show the
  AI-edit highlight/popover/"revert to original."
* `runs` (Phase 25, editor-producible since Phase 31) — see TextRun below.
* `alignment` (Phase 25, editor-producible since Phase 31) —
  paragraph-level, not a run; mirrors `python-docx`'s own
  `paragraph.alignment`. `None` means "whatever the template's default
  is," not explicitly `"left"`.
* `page_break_before` (Phase 30) — on `PrintDocumentSection` and
  `PrintDocumentEntry` only, not on a bullet-level `PrintDocumentBlock`:
  "start this section/entry on a new page," set via a gutter toggle next
  to the include/exclude checkbox. Every export path with a real page
  concept (templated PDF, plain/ATS PDF, templated DOCX) honors it;
  Markdown export is exempt — it has no page concept at all.

### TextRun — rich inline formatting (Phase 25)

```json
{"text": "...", "bold": false, "italic": false, "underline": false, "link": null}
```

One inline-styled span within a block's text. When a block's `runs` is
set, it is **authoritative over `text`** for rendering — every renderer
checks `runs` first, and `text` should be kept in sync as the
concatenation of `runs[].text` so any fallback path never shows blank or
stale content. Since Phase 31, `runs` is producible from the editor
itself — selecting text anywhere in the document and applying
bold/italic/underline/a link from the BubbleMenu writes a real
ProseMirror mark, and `runs` is derived fresh from those marks whenever
the document is read back out; it is never independently-editable stored
state a user could desync from the marks (the one exception: a
Skills/Technologies `kind: "compact"` entry's bold category label is set
directly by `buildCompactSkillEntries`, with no marks in the node's own
content, since that line is built programmatically, never typed).

**Consumption stays scoped to Summary + Experience + one member of every
other flat section, on purpose** — a *standalone* entry (Contacts,
Education, Certifications, Awards, Publications, Volunteer Experience,
Portfolio Links, and a Skills/Technologies `kind: "compact"` entry) does
get its own `runs` honored by every renderer since Phase 31. What's still
out of scope is the *grouped/joined* rendering path
(`group_entries_by_subheading`'s grouped-category and flat-`" · "`-join
branches for a non-compact Skills/Technologies entry) — several members
still fuse onto one line there, and threading per-member `runs` through
that concatenation is real added complexity, harmless in practice since
every loaded Skills/Technologies draft migrates to standalone
`kind: "compact"` entries before the BubbleMenu could ever reach a
grouped one. Every renderer (`app/cv_markdown.py`, `app/cv_docx.py`,
`app/cv_pdf.py`, `frontend/src/lib/textRuns.tsx`) is kept in that same
scope deliberately, so the Playwright-screenshotted templated PDF never
visually diverges from templated DOCX for the same document.

## CVDraft, CVDraftSummary, PrintSessionPayload (Phase 20)

`domain.models.CVDraft` — a persisted generate-and-refine session: "CV
drafts linked to a JD" as a real, storable concept (`GET/POST/PUT/DELETE
/candidates/{id}/drafts[/{id}]`), not just ephemeral pipeline output.

```json
{
  "id": "draft-1",
  "candidate_id": "cand-1",
  "vacancy": { "...": "Vacancy, see above" },
  "assembled_cv": { "...": "AssembledCV, see above" },
  "document": { "...": "PrintDocument, see above" },
  "match_result": { "...": "MatchResult | null" },
  "provenance": { "...": "BulletProvenanceReport | null" },
  "created_at": "2026-08-01T12:00:00Z",
  "updated_at": "2026-08-01T12:05:00Z"
}
```

One `CVDraft` per generate, not per edit — created once when a generate
finishes, then updated in place as the person keeps editing that same
session. This is deliberately not version history (see
`docs/PROJECT_CONTEXT.md`'s Non-goals): it's always the current state of
*one* session, never a growing history of past states. `match_result`/
`provenance` are `null` for an untailored draft (Phase 23's "export
as-is" path — no LLM call, nothing to report); for a tailored draft
they're persisted alongside `document` so reopening a draft (refresh,
"Your drafts," a direct link) looks identical to the original landing,
not a blank slate with no way to tell which bullets were AI-edited.

`CVDraftSummary` is the lightweight `GET /candidates/{id}/drafts` listing
shape — `id`/`vacancy_title`/`vacancy_company`/`created_at`/`updated_at`
only, none of the full `vacancy`/`assembled_cv`/`document` blobs, so
listing a candidate's drafts stays cheap regardless of document size.

`PrintSessionPayload` no longer exists — it was the server-side
print-session stash (`assembled_cv` + `document` + `template_id`) a
templated-PDF export used to fetch, by id, for a Playwright-driven
print-preview page to render. Removed in Phase 4.9 when templated PDF
export was rebuilt as a browser-free ReportLab renderer (no Chromium, no
frontend HTTP round-trip to navigate to) — see `docs/technology_stack.md`'s
PDF Renderer section and `docs/development_plan.md`'s Version 4, Phase 4.9
notes.

## HTTP API layer (Phase 13)

FastAPI routes (`api/routes/`) wrapping the Application Layer services
above — thin: request/response validation plus a call into `app/`, no
business logic of its own.

| Router | Prefix | Covers |
|---|---|---|
| `candidates.py` | `/candidates` | Candidate CRUD (create/get/update/delete), `GET .../evidence` |
| `entity_crud.py` | `/candidates/{id}/...` | Generic factory-generated CRUD for every simple list field (education, skills, technologies, languages, certifications, awards, contacts, projects, publications, portfolio-links, volunteer-experience) plus experience (incl. nested `experience-projects`), evidence, and drafts — one registration per entity in `_ENTITY_REGISTRATIONS`, no per-entity route code |
| `jobs.py` | `/jobs` | Async job-status pattern (`POST /jobs` + `GET /jobs/{id}`) for the four long-running LLM-backed operations: `ingest`, `generate`, `recheck` (Phase 18 re-evaluation), `relink_skill_evidence` (Phase 22) |
| `cv_drafts.py` | `/candidates/{id}/drafts` | `GET` listing (→ `CVDraftSummary[]`) and `GET /{draft_id}` (→ full `CVDraft`) — create/update/delete are handled by `entity_crud.py`'s generic registration instead |
| `writeback.py` | `/candidates/{id}/writeback` | `POST /preview` (→ `WritebackProposalOut[]`) and `POST /apply` — hand-edited CV content promoted back into the Candidate Profile (Phase 8.3/19) |
| `export.py` | (unprefixed) | `POST /export` (Markdown/DOCX/PDF, plain or templated) and `POST /candidates/{id}/export-untailored` (Phase 23); `POST /export/page-breaks` (Post-4.9 fix, see Version 4 notes) for the on-screen page-break guide |

`entity_crud.py`'s generic factory derives each entity's create-request
body from the real Python signature of the matching `CandidateService.add_X()`
method (not "every domain field minus id" — some `add_X()` methods
deliberately accept fewer fields than their domain model has). Adding a
new simple entity type is one entry in `_ENTITY_REGISTRATIONS`, not a new
route file.
