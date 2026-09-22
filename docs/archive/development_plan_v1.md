# Version 1 — Desktop Prototype (Phases 0–12.3): full phase detail

> Archived from `docs/development_plan.md` on 2026-08-07 when that file was
> split by version to keep the active plan short. This is the verbatim,
> unabridged Version 1 detail — see `docs/development_plan.md` for the
> current summary and links to the other archives.

## Guiding approach

The full architecture (Career Graph, Evidence/Claim/Variant layers, multi-provider
gateway, structured-output validation, ATS-ready PDF export, etc.) is the target
end-state described in `architecture.md` and `domain-model.md`. Building all of it
before anything runs end-to-end is too much surface area for a first prototype.

Instead, Phase 0-6 below build a **thin vertical slice** through every architectural
layer, using the simplest possible version of each domain concept. Each phase after
that thickens one layer at a time without breaking the working slice.

Deliberately deferred past the prototype: CareerGraph as a real graph (Organization/
Role/Project nesting), Claims, Competencies, per-Evidence Variants, Evidence-backed
Skill/Technology provenance, explicit Gap objects, Provider Registry/fallback, DOCX/PDF
export, version history. These are real features, just not required to prove the core
loop works. (Candidate's flat `experience`/`education`/`skills` lists were pulled
forward into Phase 2 — see that section's scope note.)

---

## Phase 0 — Project setup
* Python
* uv
* Qt
* Gemini (single provider only for the prototype — no registry/fallback yet)
* Logging (per error-handling categories in `architecture.md`, even if most aren't triggered yet)

## Phase 1 — Architecture skeleton
* Contracts (minimal versions only, see below)
* Providers (`ILLMProvider` interface + one Gemini implementation)
  * Includes retry-with-backoff for *transient* provider errors (503
    overloaded, 429 rate limit, network timeouts) inside `GeminiProvider`
    itself — configurable via `LLM_MAX_RETRIES` /
    `LLM_RETRY_BASE_DELAY_SECONDS`. This is NOT the same as *fallback* to a
    different provider (Gemini down → try OpenAI/Claude); that needs the
    Provider Registry and stays Phase 9. Retry = same provider, tries again.
    Fallback = different provider, tries once.
  * `GeminiProvider.generate_structured()` separately retries (same budget)
    when Gemini returns a 200 OK whose body is malformed JSON or doesn't
    match `response_schema` — a real bug found via actual usage (Phase 8's
    longer Bullet Rewriting responses occasionally break JSON mid-string;
    `response_mime_type: "application/json"` alone doesn't guarantee valid
    output on every call). Not a network error, so the transient-error retry
    above never sees it; regenerating usually fixes a one-off formatting
    glitch. The final `ParsingError` (if retries are exhausted) includes a
    snippet of the actual malformed text around the failure position, not
    just line/column — otherwise the error dialog in `ui/main_window.py`
    gives no way to tell what actually went wrong. See
    `providers/gemini_provider.py`'s module docstring.
* Prompt loader
* Configuration

## Phase 2 — Candidate Profile (domain, storage, CRUD)
> **Scope note:** originally planned as "Candidate: name + contact only,"
> deferring experience/education/skills to Phase 7's real Career Graph. That
> got pulled forward: nobody wants to re-paste their work history into a new
> tool, so the flat (non-graph) `experience`/`education`/`skills` lists live
> on `Candidate` now. What's still deferred to Phase 7 is the *graph*
> structure — Organization/Role/Project nodes, Evidence-backed Skill
> provenance, cross-candidate dedup — not the fields themselves.

* Candidate: name, headline, `summary` (the candidate's own untitled "about
  me" paragraph, if the resume has one — distinct from CVProjection.summary,
  see Phase 5 notes), flexible `contacts[]` (label+value pairs —
  Email/Phone/LinkedIn/Location/Work Authorization/etc, not fixed named
  fields, since what belongs on a CV header varies by role/location),
  plus flat `experience[]` / `education[]` / `skills[]` / `languages[]` /
  `certifications[]` / `projects[]` ("Key Projects" — standalone
  portfolio highlights, not tied to one employer; always included as-is,
  not AI-tailored, see Phase 5 notes) (no Organization/Role/Project
  nesting yet — see `domain/models.py`)
* Evidence (flat list — no Organization/Role/Project hierarchy yet, just `text` + `source_context` tag)
* Vacancy / Requirement (as sketched in `contracts.md`)
* CVProjection (as sketched in `contracts.md`)
* Local storage as flat JSON on disk (real DB comes later)
* Basic validation
* `CandidateService` CRUD (`app/candidate_service.py`) for manually
  correcting/expanding the profile after import

## Phase 3 — Resume ingestion (collapsed pipeline)
One LLM call instead of the full extract → normalize → variant-generate → graph-merge pipeline:
* Input: raw resume text (paste, or simple PDF-to-text; DOCX/TXT variety deferred)
* Output: **both** a `Candidate` profile (name/contacts/education/work history —
  saved via `CandidateService.replace`) **and** a flat `Evidence[]` list, validated
  against a pydantic schema (`IngestResumeResponse`, see `contracts.md`)
* Store as JSON
* Note: re-running ingestion overwrites the Candidate Profile wholesale; it
  does not merge with entries added manually via `CandidateService` afterward
* PDF input: `app/resume_reader.py` (`.txt`/`.md` read as-is, `.pdf` via
  `pypdf` text extraction, no OCR). DOCX and other formats stay deferred.
* Employment gaps: an explicit gap (parental leave, sabbatical, career
  break) is parsed into its own `experience` entry with `is_gap: true`
  rather than being dropped. `company` is optional on `Experience`
  specifically to support gaps not tied to one employer.

## Phase 4 — Vacancy analysis (collapsed pipeline)
* One LLM call: JD text → `Requirement[]` + keywords, matching `AnalyzeVacancyResponse`
* `VacancyAnalysisService.analyze()` returns a `domain.models.Vacancy`, not
  the raw `AnalyzeVacancyResponse` — the LLM only supplies title/company/
  requirements/keywords; `raw_text` is filled in from the original input
  rather than trusted from the model (see `contracts.md`)
* `Requirement.keywords` is a list (not a single `keyword`), since one
  requirement can reasonably name several skills/tools

## Phase 5 — Tailored CV generation (collapsed pipeline)
Rather than separate Matching → Gap Analysis → Variant Selection/Generation stages,
one LLM call takes the Candidate's Experience list + full Evidence list +
Requirements list and returns a `CVProjection` — AI-tailored *content* only
(summary, per-role bullets grouped by `experience_id`, skills). This sacrifices
explainability (no visible gap analysis) in exchange for a working output fast.
Split into real stages after the prototype works (see Phase 8).

> **CVProjection is not the full CV.** It deliberately excludes identity,
> contacts, education, dates, company names, languages, and certifications —
> those are facts, not creative content. `app/cv_assembler.py:assemble_cv()`
> merges them in deterministically from the Candidate Profile (no LLM call)
> to produce an `AssembledCV`, which is what actually gets exported. This
> keeps names/dates/companies from ever being at risk of hallucination, and
> matches the "LLM never returns final CV text" principle in
> `docs/architecture.md`. Without this split, nothing in the plan actually
> produced a complete, ATS-structured CV — that was a real gap, not an
> intentional deferral; this closes it.

> **Employment gaps are always included, never AI-tailored.**
> `Experience.is_gap=True` entries (parental leave, sabbatical, career
> break) have no supporting Evidence, so a CVProjection never references
> them by design — `app/cv_assembler.py:assemble_cv()` includes them
> unconditionally instead, in the Candidate's own (chronological) order.
> Real, non-gap roles are still only included if the LLM's CVProjection
> references them. This was a real bug found via actual pipeline output
> (a resume with a stated maternity-leave gap silently lost it): the fix
> also changed assembly order from "CVProjection's order" (AI relevance)
> to "Candidate's own order" (chronological) — the former isn't how
> resumes are read, and it's the only order that lets a gap land in its
> correct chronological slot.

> **Key Projects (`Candidate.projects`) are deterministic, like
> Education — not AI-tailored per vacancy, like Experience.** Considered
> both; picked deterministic because (a) this section's actual content
> is usually short name+description labels, not achievement bullets to
> rephrase, and (b) mirroring Experience's fact/tailored-content split
> for Projects too (a second `TailoredProject` + project-scoped Evidence
> grouping) is real added complexity for unclear benefit right now. If
> "always show every project" turns out to feel wrong in practice, this
> is a contained upgrade later — the pattern already exists once.

> **`Candidate.summary` vs `CVProjection.summary`.** Many resumes have an
> untitled "about me" paragraph right after the contact block — it has no
> section heading, so before this it had nowhere to go in the schema and
> was getting dropped or inconsistently absorbed elsewhere by
> `01_cv_parser_v1.md` (a symptom of a missing field, not fixable by
> prompt wording alone). `Candidate.summary` now captures it close to
> verbatim, as a fact like `headline`. It's passed into
> `03_cv_builder_v1.md` as context (tone, positioning, stated career
> goals) for generating `CVProjection.summary` — but the model is told to
> write a fresh, vacancy-tailored, Evidence-grounded summary, not copy it
> verbatim. `BuildCVRequest.candidate_summary` is `None`-safe: a bare
> `None` would literally render as the text "None" via `string.Template`,
> so `CVBuilderService.build()` substitutes an explicit
> "(No summary provided.)" placeholder instead.

## Phase 6 — Manual edit & export (prototype scope)
* Manual edit: editable text field per CV section, no diffing/versioning
* Export: Markdown only
* UI: single window — paste resume → paste JD → Generate → editable output → Export Markdown
  (no Resume Graph Explorer, no AI Suggestions panel yet — those need the richer
  Evidence/Claim/Variant model from later phases)

Implementation notes:
* `ui/main_window.py` — PySide6 QMainWindow. Never calls the LLM or a
  provider directly (per `docs/architecture.md`'s "UI" section) — only
  `app/pipeline.py` and `app/cv_markdown.py`.
* Runs the pipeline on a background `QThread` (`PipelineWorker`), not the
  GUI thread — a Gemini call plus retries can take several seconds and
  would otherwise freeze the window.
* `app/services.py` (new): shared `build_services(config)` wiring for
  production entry points (`main.py`, the UI). `run_pipeline.py` still
  intentionally duplicates its own wiring instead of using this — see its
  module docstring.
* `app/pipeline.py` (new): shared ingest→analyze→build→assemble
  orchestration for the UI. `run_pipeline.py` also keeps its own copy of
  this sequence (for its step-by-step CLI progress printing) rather than
  using this — same reasoning as `app/services.py`.
* `app/cv_markdown.py` (new): the Markdown renderer used to be inline in
  `run_pipeline.py`; it's now shared so the CLI's full-document export and
  the UI's one-editable-field-per-section view can never drift apart.
  `assemble_markdown_from_sections()` is what "no diffing/versioning"
  means concretely: edited section text is concatenated as-is on export,
  never re-parsed back into `AssembledCV`/`Candidate`.

**End of Phase 6 = first working prototype.** It exercises every architectural
layer (UI → App → Contracts → Domain → AI Engine → Provider → External API) even
though each layer is a stub of its final self. This proves the provider
abstraction, structured-output validation, and layer separation hold up in practice.

---

## Phase 7 — Real Career Graph
* Organization → Role → Project → Evidence hierarchy
* Migrate flat JSON storage to the structured CareerGraph model
* CRUD for graph entities

> **Scoped first slice: Project nesting inside Experience.** Full Phase 7
> (Organization as a real linked entity, storage migration to a graph store)
> is a large rewrite. The concrete, reported problem is narrower: some
> resumes are structured company → project → role → dates → achievement
> bullets, not just company → role → dates → bullets, and the current flat
> `Experience.responsibilities`/`achievements` string lists have nowhere to
> record which project a bullet came from — that link is lost at ingestion
> and never recoverable downstream (tailoring, assembly, export). This slice
> fixes exactly that, and leaves `company` as a plain string (no
> `Organization` entity) since that part isn't related to the reported loss
> and adds real extra scope (cross-role dedup, multi-role-per-org). Done in
> 7 steps, each independently testable:
>
> 1. **Domain model** (`domain/models.py`): add `ExperienceProject` (`id`,
>    `name`, `period`, `achievements`); add `Experience.projects:
>    list[ExperienceProject]` (existing flat `responsibilities`/
>    `achievements` stay for roles with no sub-project structure — not every
>    resume has this shape). Add `Evidence.experience_id` /
>    `Evidence.experience_project_id` (structured links, replacing reliance
>    on free-text `source_context` alone for grouping). Add `TailoredBullet`
>    (`text`, `project` display name); `TailoredExperience.bullets` and
>    `AssembledExperienceEntry.bullets` become `list[TailoredBullet]`.
> 2. **Ingestion** (`prompts/01_cv_parser_v1.md`, `docs/contracts.md`): teach
>    the parser to emit `experience[].projects[]` when the resume has that
>    structure, and to set `evidence[].experience_id`/
>    `experience_project_id` instead of only prose `source_context`. No
>    `contracts/schemas.py` or `app/use_cases.py` changes needed — the
>    `Candidate`/`Evidence` models pass through untouched.
> 3. **Tailoring** (`prompts/03_cv_builder_v1.md`): show nested `projects` in
>    the experience input; use the structured Evidence links (not guessing
>    from `source_context`) to decide role/project grouping; output
>    `bullets: [{"text": "...", "project": "..."}]`.
> 4. **Assembly** (`app/cv_assembler.py`): passthrough only —
>    `tailored.bullets` is now `list[TailoredBullet]`, no logic change.
> 5. **Rendering** (`app/cv_markdown.py`): `render_experience_section()`
>    groups bullets by `project` under a `*Project Name*` sub-line within a
>    role; bullets with no `project` render directly under the role as
>    today.
> 6. **`CandidateService` CRUD** (`app/candidate_service.py`): add
>    `add_experience_project`/`update_experience_project`/
>    `remove_experience_project`, mirroring the existing add/update/remove
>    triads (e.g. the standalone `Project` CRUD). Service-layer only — there
>    is no Candidate CRUD UI today to wire up.
> 7. **Full-loop check**: `pytest`, then `python run_pipeline.py` against a
>    resume with real project-under-role structure, confirming the exported
>    Markdown groups achievements under their project.
>
> Explicitly out of scope for this slice: `Organization` as a real entity,
> storage/CRUD migration beyond step 6 (still flat JSON via
> `app/storage.py`), and any UI changes (no Candidate CRUD screen exists to
> update).

## Phase 8 — Explicit semantic layer
* Per-Evidence Variant generation (ATS-friendly / Executive / Technical / Concise)
* Claims and Competencies, derived from Evidence
* Explicit Gap Analysis step, surfaced to the user instead of hidden inside one LLM call
* Split the collapsed Phase 5 call into real Matching → Gap Analysis → Variant Selection stages

> **Scoped first slice: UI ingest/generate split, then Matching + Gap
> Analysis, then split tailoring.** Full Phase 8 (the above) plus
> Claims/Competencies and per-Evidence Variants is a lot of new surface at
> once. This slice does three independently-shippable steps and defers
> Claims/Competencies and per-Evidence Variants (see below):
>
> 1. **UI: separate `Ingest Resume` / `Generate CV` buttons, persist the
>    Candidate profile across relaunches.** Today one `Generate` click
>    re-parses the pasted resume every time, and the app never loads the
>    already-saved `data/candidate.json` on startup. Fixing this also
>    requires persisting `Evidence[]` (until now only ever in-memory for the
>    duration of one `run_full_pipeline()` call) — otherwise a relaunched
>    app has the Candidate back but nothing to tailor bullets from on
>    `Generate`. `app/storage.py` gets `save_evidence`/`load_evidence`
>    (`data/evidence.json`, sibling file — not reusing the existing
>    `save_career_graph`/`load_career_graph`, which would duplicate the
>    Candidate into a second file that could drift from `candidate.json`).
>    `CandidateService.replace()` gains an optional `evidence=` param (kept
>    atomic with the Candidate save) plus `get_evidence()`.
>    `app/pipeline.py:run_full_pipeline()` splits into
>    `run_resume_ingestion(resume_text, services) -> Candidate` and
>    `run_cv_generation(candidate, vacancy_text, services) -> PipelineResult`.
>    `ui/main_window.py` gets two buttons/workers instead of one, and loads
>    any persisted Candidate on startup.
> 2. **Matching + explicit Gap Analysis.** Upgrades the
>    `prompts/03_cv_jd_matcher.md` sketch to real `_v1` contract rigor
>    (archiving the sketch) — Candidate Experience + Evidence + Vacancy
>    Requirements in, structured matches + `Gap`s out, reusing the Phase 7
>    Evidence `experience_id`/`experience_project_id` links so a match can
>    point at exactly which role/project backs it. New `MatchingService`,
>    `MatchRequest`/`MatchResponse`. `run_cv_generation` runs this before
>    tailoring; the UI gets a read-only "Gaps" panel — informational, not
>    editable or exported, same treatment as `Candidate.projects`.
> 3. **Split tailoring into rewrite planning + bullet rewriting.** Replaces
>    the single `03_cv_builder_v1.md` call with the two-stage flow the docs
>    describe: a planning pass (`rewrite`/`enhance`/`remove`/`keep` per
>    Evidence item plus a `priority_order`, using Step 2's match/gap output
>    — no `"merge"` action, dropped as unneeded complexity for a prototype)
>    and a rewriting pass (produces the final `CVProjection`, following the
>    plan exactly), upgrading `04_rewrite_planner.md`/`05_rewrite_bullets.md`
>    to `_v1` contracts (archiving the sketches) as
>    `RewritePlannerService`/`BulletRewriteService`. `CVBuilderService` and
>    `03_cv_builder_v1.md` retired to `prompts/archive/`.
>
> **Deferred, not in this slice:** per-Evidence Variant generation
> (ATS-friendly/Executive/Technical/Concise) — `05_rewrite_bullets` already
> produces one tailored rewrite per bullet on demand, covering most of the
> practical value; pre-generating and storing 4 variants per Evidence item
> is a separate, heavier feature (storage shape, a picker UI). Claims and
> Competencies derived from Evidence — a new semantic layer + "AI
> Suggestions" UI panel that's exploratory rather than blocking; can slot in
> later reusing the same Evidence-linking pattern.

## Phase 8.1 — Multiple Candidate Profiles
* Support more than one Candidate Profile per local install
* Re-ingesting a resume creates a new profile rather than overwriting the
  active one (no merge/overwrite-detection — that's Phase 11 territory)
* UI: switch between existing profiles

## Phase 8.2 — Actionable Gap Analysis
* Extends Phase 8's Gap Analysis: severity/priority per gap
* Gaps sorted by importance instead of a flat list
* Concrete, advisory suggested-edit text per gap — informational, not
  auto-applied to tailoring (would risk inventing ungrounded claims)

## Phase 8.3 — Save Edits Back to the Graph
* Promote hand-edited CV content (Experience bullets, Summary, Skills)
  back into the Candidate Profile / Evidence
* Scoped pull-forward of Phase 11's "Master CV write-back" — conflict
  handling and the fuller graph write-back stay in Phase 11

## Phase 8.4 — Matcher considers declared profile facts, not just Evidence (done)
Found while using the app: a requirement like "conversational English
(B1+)" was reported as a gap even when the candidate's profile had
"English (C1)" in their Languages list — because `MatchingService.match()`
only ever received `experience`/`evidence`/`requirements`; flat profile
fields (Skills, Technologies, Languages, Certifications) were invisible to
the matching LLM call, even though the *rewrite* stage already receives
`candidate_skills`/`candidate_technologies` for a similar reason.
* `contracts.schemas.MatchRequest` gains `candidate_skills`/
  `candidate_technologies`/`candidate_languages`/`candidate_certifications`
  (all `list[str]`, defaulting to `[]` for backward compatibility).
  Languages/Certifications are formatted the same way
  `ui/graph_explorer.py`'s `_summarize_language`/
  `_summarize_certification_like` already display them ("English (C1)",
  "AWS Solutions Architect — Amazon, 2022") — new `app/pipeline.py`
  helpers `_format_language`/`_format_certification` mirror that
  convention rather than inventing a new one.
* `03_cv_jd_matcher_v1.md` gained four new input sections and rule
  updates: a Requirement can now be satisfied by a fact stated directly
  in Skills/Technologies/Languages/Certifications, with no Evidence
  bullet required — `RequirementMatch.evidence_ids` (already
  `list[str] = []` by default) is simply left empty for a match grounded
  that way, since those facts have no Evidence id to cite.
* `run_pipeline.py` (the CLI debug tool) is intentionally left
  unchanged — its own module docstring already establishes it as a
  deliberately-diverging, deletable duplicate of `app/pipeline.py` (it
  doesn't even pass `candidate_skills`/`candidate_technologies` to the
  rewrite stage either), so the new fields there simply default to `[]`,
  same as before this phase.

---

**Reprioritized:** Phases 8.1-8.3 above are the current priority — focus on
the graph/UX "feel" of the product before multi-provider/export/write-back/
polish. Phases 9-12 below stay recorded as originally planned, not
reordered or renumbered, but are on hold until 8.1-8.3 are done.

## Phase 9 — Multi-provider support
> Distinct from the retry-with-backoff already implemented in Phase 1: this
> phase is about *falling back to a different provider* when Gemini itself
> is unavailable/misbehaving even after retries are exhausted, or when the
> person wants to choose a provider. Retry alone does not require any of
> the infrastructure below.
* Provider Registry (done — `providers/registry.py`: name -> factory,
  `app/services.py:build_services()` builds through it instead of
  constructing `GeminiProvider` directly)
* Fallback strategy (done — `providers/fallback_provider.py`:
  `FallbackProvider` tries an ordered list of providers, moving to the next
  only on `ProviderError`; configured via `Config.llm_fallback_providers`
  / `LLM_FALLBACK_PROVIDERS`, empty by default so behavior is unchanged
  unless set)
* OpenAI / Ollama / Claude providers alongside Gemini — **still deferred**:
  the registry/fallback plumbing above is provider-count-agnostic, but no
  concrete provider besides Gemini is registered yet since there's nothing
  to configure or test against. Adding one later is a single factory added
  to `providers/registry.py`'s `DEFAULT_REGISTRY`.

## Phase 10 — Export upgrade
* DOCX export (done — `app/cv_docx.py`, via `python-docx`)
* PDF export, ATS-readable, compressed to < 2 MB (done — `app/cv_pdf.py`,
  via `reportlab`: single-column flow, real selectable text, base-14
  Helvetica, hard 2MB cap enforced at generation time rather than assumed)

## Phase 11 — Master CV write-back
* Save newly generated/edited claims and evidence back into the Career Graph
  — write-back *completeness* done (`app/graph_writeback.py`):
  `build_experience_proposals` now also detects and saves header-fact edits
  (position/company/period, via `_parse_header`) and renames a project in
  place instead of leaving an orphaned old entry plus a duplicate new one
  (the unambiguous case: exactly one project name removed, exactly one
  added). Previously only bullets were ever written back — a title or
  project rename was silently dropped, and a project rename specifically
  created a duplicate.
* Conflict handling when the same Evidence has diverged across CV versions
  — **still open**, deliberately not tackled in the pass above: needs
  staleness detection plus a merge/overwrite UI, a distinct feature from
  write-back completeness. Also covers Phase 8.1's deferred profile
  merge/overwrite-detection note.

## Phase 12 — Polish
> Split into three independent sub-phases rather than tackled as one pass —
> the original three bullets turned out to be different sizes and shapes
> (two bounded fixes, a set of test-coverage gaps, and one item that's
> actually a new domain layer wearing a "polish" label). Each is scoped and
> executed separately.

### Phase 12.1 — Error handling coverage
Two concrete gaps found by auditing every `except` in `ui/main_window.py`
against `architecture.md`'s Error Handling section, not a general sweep:
* `_CallableWorker.run()`'s last-resort `except Exception` (truly
  unexpected errors) never logs anything, despite `app/logging_setup.py`
  being wired up at startup (`main.py`) — nothing outside `providers/`
  calls `get_logger()`. Violates "All unexpected errors should be logged."
* The write-back save flow's `proposal.apply(service)` call is the one
  action in the app not wrapped in `try/except AppError` — a
  `ValidationError`/`StorageError` there raises straight through instead of
  the same clean `QMessageBox.warning` every other action (Ingest/Generate/
  Export) already gets.

### Phase 12.2 — Test coverage gaps (done)
Per `architecture.md`'s Test Pyramid — Contract/Provider/Unit were already
solid; the gaps, now closed:
* Prompt Tests (`tests/test_prompts/`) render the 5 real files in
  `prompts/` with the exact placeholder kwargs `app/use_cases.py` passes
  per stage — previously only the loader mechanism was tested, against
  synthetic templates, so a typo'd placeholder wouldn't have been caught
  until a live LLM call failed. Also cleaned up two files that violated
  `architecture.md`'s own "move superseded prompts to `archive/`" rule:
  `prompts/02_jd_parser.md` (byte-identical duplicate of the already-
  archived copy, deleted) and `prompts/01_cv_parser.md` (a never-archived
  early draft, moved to `archive/`) — neither was referenced anywhere in
  code.
* Integration Tests (`tests/test_integration/`) run
  `run_resume_ingestion`/`run_cv_generation` through the real
  `use_cases.py` services and the real `prompts/` directory, faking only
  the provider boundary — previously every test faked at least one more
  layer than that (whole services, or even the prompt directory itself).
* UI Tests (`tests/test_ui/`) — plain PySide6, no `pytest-qt` added (the
  app only needs a handful of tests). Formalizes the Phase 10/12.1 manual
  smoke scripts into permanent regression tests: export dispatch by file
  suffix, and the write-back save-flow error guard.

### Phase 12.3 — Graph Explorer panel (done)
A read/edit UI surface over the Candidate graph fields that already exist
(Experience + nested Projects/Education/Skills/Languages/Certifications/
standalone Projects/Contacts) — no new domain concepts needed;
`app/candidate_service.py` already had full CRUD for all of it, already
unit-tested, so this was UI-only work.

New `ui/graph_explorer.py`: a generic `_EntityListSection` (title + rows +
Add button, each row Edit/Delete) drives the six shape-identical
collections. Experience gets its own dialog: Position/Company/Period/Is
Gap, an in-memory Projects list, and every Achievement/Responsibility as
its own freely-editable row that can optionally link to one of those
projects via a dropdown (`_BulletRowsEditor`, shared by both) — one
unified save, not a separate "Manage Projects" sub-dialog (that first
design made a role's bullets invisible from its own edit form whenever
they were all tied to a project — a real usability bug, not just a rough
edge, fixed by folding project management into the same dialog). Deleting
a project unlinks its bullets back to role-level rather than dropping
them. `domain.models.ExperienceProject` gained a `responsibilities` field
to mirror `achievements` so responsibility rows get the same project link.

Wired into `ui/main_window.py`'s left column, which is now scrollable and
reordered: Candidate selector -> Graph Explorer -> Resume ingestion -> Job
Description. Switching `profile_selector` refreshes the Graph Explorer to
the newly active candidate; any Graph Explorer edit refreshes
`profile_selector`'s "N entries" label the same way. The resume-paste box
no longer pre-loads `resume.txt` on startup — profiles persist across
restarts now, and manual entry is covered by the Graph Explorer, so that
convenience was dropped. The right panel (tailored output, gaps, export)
is unchanged.

> **Addendum — Portfolio Links.** Portfolio used to be just a `ContactItem`
> (`label="Portfolio"`), so only one link was possible and there was no room
> for a description. New `domain.models.PortfolioLink` (`url` required,
> `description` optional — no separate name field) gets its own
> `Candidate.portfolio_links`/`AssembledCV.portfolio_links` list, its own
> `add_portfolio_link`/`update_portfolio_link`/`remove_portfolio_link` CRUD
> triple (mirrors `Project`'s exactly), its own always-included (not
> AI-tailored) export section — `app/cv_markdown.py`'s `SECTION_TITLES`
> gained a `"portfolio_links": "Portfolio"` entry, which is enough on its
> own to get DOCX/PDF export (including automatic hyperlinking) for free,
> since those renderers already iterate `SECTION_TITLES` generically — and
> its own Graph Explorer section via the same generic `_EntityListSection`
> six other simple collections already use. No automatic migration of
> existing "Portfolio" Contact entries — move them manually via the Graph
> Explorer.

> **Addendum — CV structure gap-filling.** Following a domain-model gap
> analysis against `docs/domain-model.md`'s target shape and the stated
> target audience: `Experience.location` (optional); `Skill.proficiency`
> (free text, mirrors `Language.proficiency`); `Candidate.
> employment_types_sought`/`AssembledCV.employment_types_sought` (a job-
> search preference, not a per-role fact — a small closed `EmploymentType`
> Literal, rendered as a "Seeking: ..." header line, same treatment as
> `headline`); and three new always-included (not AI-tailored) sections
> mirroring existing shapes exactly — `Award` (≡ `Certification`),
> `Publication` (≡ `Project`, with `venue`/`date` replacing `description`),
> `VolunteerExperience` (simplified `Experience`), and `Technology` (≡ the
> now-`proficiency`-bearing `Skill`, kept separate so engineers/data roles
> get a dedicated Tools/Technologies section distinct from Skills). All
> four wired through the same generic `_EntityListSection` Graph Explorer
> pattern and `SECTION_TITLES`-driven export (free DOCX/PDF hyperlinking)
> as every addition since Portfolio Links — no new UI classes.
>
> `Experience.location` rendering deliberately groups with the period
> inside the parenthetical (`(2020-2023, Berlin)`), not comma-appended
> after company — the latter would make `app/graph_writeback.py`'s
> header-rewriting regex unable to tell company text apart from location
> text. `_parse_header`'s return grew to a 4-tuple accordingly.
>
> Caught during testing, not before: `CandidateService.add_skill()`'s
> explicit signature had to also gain `proficiency` (unlike `update_skill`,
> which already accepted it generically via `**fields`) — a reminder that
> the generic-`update`-methods-are-forgiving pattern doesn't extend to the
> explicit-parameter `add_*` methods. Also fixed: `ui/graph_explorer.py`'s
> `_singular()` helper naively did `key.rstrip("s")`, which turns
> `"technologies"` into `"technologie"` instead of `"technology"` — added
> an explicit `-ies` → `-y` rule.

> **Addendum — Skills: category-grouped export, AI-ranked within category.**
> Found while explaining the previous addendum's `Skill.category` field:
> it had zero effect on the export. `AssembledCV.skills`/`CVProjection.skills`
> were `list[str]`, freely invented by the LLM from Evidence/Requirements
> text — completely disconnected from `Candidate.skills`, so your
> maintained/categorized list wasn't even guaranteed to appear on the
> generated CV at all. Fixed: `AssembledCV.skills` is now `list[Skill]`
> (`Candidate.skills`' full records, reordered) — the LLM's job changed
> from *inventing* a skills list to *ranking* the given one
> (`RewriteBulletsRequest.candidate_skills`, prompts/05_rewrite_bullets_v1.md).
> `app/cv_assembler.py:_rank_skills` (since generalized to `_rank_by_category`,
> see next addendum) keeps category **grouping** deterministic
> (`Candidate.skills`' own first-appearance order — never AI-decided, so a
> skill's category membership can never be lost to a bad AI response) and
> uses the AI's ranking only to sort **within** each group; a skill the AI
> didn't mention sorts last in its group rather than disappearing, and an
> invented name is simply never looked up. `app/cv_markdown.py:render_
> skills_section` emits a `**Category**` heading per group (uncategorized
> skills render as plain bullets, no heading). `CVProjection.skills` itself
> stays `list[str]` — only its *meaning* changed, not its shape, so the
> contract-level Pydantic schema didn't need to change, just the prompt's
> instructions and how `app/cv_assembler.py` consumes the result.

> **Addendum — same treatment extended to Tools/Technologies; a Skills
> render bug caught in the process.** You asked whether Technology got the
> same AI-ordering-within-category principle as Skills — it hadn't:
> `render_technologies_section` still used the old flat
> `"name (category, proficiency)"` format, ungrouped and untouched by any
> AI ranking. Extended identically: `CVProjection.technologies: list[str]`
> (the AI's ranked-names output, mirroring `.skills`) and
> `RewriteBulletsRequest.candidate_technologies` (mirroring
> `candidate_skills`) were added; `prompts/05_rewrite_bullets_v1.md`'s
> Skills rule became one combined Skills+Technologies rule, ranking each
> list independently. Since `Skill` and `Technology` are shape-identical
> for this purpose (`name`, `category`, `proficiency`), the ranking and
> rendering logic were generalized rather than duplicated: `app/
> cv_assembler.py:_rank_skills` was renamed to `_rank_by_category` (a
> `TypeVar` bound to `Skill | Technology`) and is now called for both
> `AssembledCV.skills` and `.technologies`; `app/cv_markdown.py`'s
> `render_skills_section`/`render_technologies_section` both now delegate
> to a shared `_render_grouped_by_category` helper.
>
> Caught while writing that shared helper: the original
> `render_skills_section` (previous addendum) had accidentally dropped
> `Skill.proficiency` from the export entirely — it only ever emitted
> `f"- {skill.name}"`. Fixed in the same pass; `_render_grouped_by_category`
> appends `(proficiency)` for both Skills and Technologies, and a
> regression test now asserts this for Skills specifically.

### Deferred out of Phase 12 entirely — AI Suggestions panel
Needs Claims/Competencies/Variants, domain concepts that don't exist
anywhere in `domain/models.py` yet (see Phase 6 notes: "a new semantic
layer... that's exploratory rather than blocking"). This is a new major
phase, not a polish-sized task — left for separate future scoping rather
than folded into Phase 12.

