# Version 2 — Web App & WYSIWYG UX (Phases 13-23): full phase detail

> Archived from `docs/development_plan.md` on 2026-08-07 when that file was
> split by version to keep the active plan short. This is the verbatim,
> unabridged Version 2 detail — see `docs/development_plan.md` for the
> current summary and links to the other archives. (The heading below still
> says "Phases 13-20" as originally written; the version ultimately grew
> through Phase 23 without the heading being updated at the time.)

# Version 2 — Web App & WYSIWYG UX (Phases 13-20)

Phases 0-12.3 above delivered a working desktop prototype: the full
ingest → match → plan → rewrite → assemble → export pipeline runs
end-to-end, with real Gap Analysis, write-back, multi-provider fallback
plumbing, and CRUD coverage for the whole Candidate Profile (the "on hold
until 8.1-8.3 done" note above Phase 9 is resolved — 8.1-8.3 and 12.1-12.3
are all done). What's missing isn't pipeline capability, it's product
feel: the output is "an OK version of a CV," not something that inspires
confidence to hand the AI's edits off sight-unseen.

This stage keeps the pipeline and domain layers largely as they are and
rebuilds everything above them: PySide6 → a browser-based web app, flat
Candidate-Profile CRUD → an editable WYSIWYG document, one-shot generation
→ a transparent, re-checkable, user-correctable loop. Scope is
deliberately **single-user/local** for this stage — no auth, no
multi-tenant storage, no hosting. That is left for a later "marketable"
stage per `docs/PROJECT_CONTEXT.md`'s Future Ideas; nothing in Phases
13-20 should add auth middleware, tenant-scoped data, or hosting
infrastructure "just in case."

**Stack (see `docs/technology_stack.md`, revised in this pass):**
React/TypeScript/Vite/Tailwind/shadcn/TanStack Query frontend;
FastAPI/Pydantic backend reusing `contracts/schemas.py` directly as
request/response models; **SQLite via SQLModel/Alembic**, not the
originally-sketched Postgres — a single local user doesn't need a DB
server, and the ORM layer makes a later Postgres migration a
connection-string change rather than a rewrite; **no Docker
Compose/Nginx** as required infrastructure for this stage (nothing to
orchestrate, nothing to reverse-proxy on localhost); an async
in-process job-status endpoint instead of a task queue, replacing the
`QThread`/`PipelineWorker` pattern `ui/main_window.py` uses today for the
same reason — LLM calls take several seconds and can't block a
request/render thread.

## Phase 13 — Backend API + storage migration (done)
No user-visible change; this phase makes everything after it possible.
* Wrap `app/services.py` / `app/pipeline.py` / `app/candidate_service.py`
  in FastAPI routes, reusing `contracts/schemas.py` Pydantic models as
  request/response bodies directly.
* Migrate storage from flat JSON (`data/candidates/<uuid>/candidate.json`
  + `evidence.json`, via `app/storage.py`) to SQLite via SQLModel, with
  Alembic migrations from the first commit. One-time script to import
  existing `data/candidates/` profiles.
* Add an async job-status endpoint (`POST /jobs` returns a job id;
  `GET /jobs/{id}` returns status/result) for ingest/analyze/generate
  calls — the web equivalent of `PipelineWorker`.
* Verified via `httpx`/pytest against the API only; no frontend yet.

New `db/` package: `CandidateRow`/`EvidenceRow` (`db/models.py`) — two
tables, not a full relational mirror of every nested list on `Candidate`.
`CandidateRow.data` holds the whole `Candidate` (all 14 nested lists) as
one JSON blob, matching `CandidateService`'s existing "load whole
Candidate, mutate in-memory, save whole Candidate" pattern exactly; only
`Evidence` gets a real table, ahead of need, specifically because Phase 15
needs a real FK-able Skill<->Evidence link and pulling Evidence out later
would be a second migration over the same rows. `domain.models.Candidate`
gained no `id` field — identity stays a storage-layer-only concern
(`CandidateService`'s constructor arg), exactly as it was with directory
names pre-Phase-13.

`EvidenceRow`'s primary key is `(candidate_id, id)`, not `id` alone — a
real bug caught by the migration script's own test run, not a
hypothetical: `Evidence.id` (e.g. `"ev-1"`) was only ever guaranteed
unique *within* one candidate's list, and the two real committed profiles
(`33e010af`, `695d389b`) both legitimately use `"ev-1"`. A single-column
PK broke on the second profile's insert.

`CandidateService`/`CandidateRegistry` kept their exact public method
signatures (only the constructor — `candidate_id`/`engine` instead of
`data_dir` — and the load/save internals changed), which is what let
`ui/main_window.py` and `app/pipeline.py` keep working with zero changes
of their own — confirmed by launching the real desktop UI against the
migrated DB and checking the profile picker + Graph Explorer.

`api/routes/entity_crud.py`'s generic factory (mirroring
`ui/graph_explorer.py`'s `_EntityListSection` precedent) generates
create/update request bodies dynamically per entity: the create body's
fields come from the real Python signature of `CandidateService`'s own
`add_X()` method (not "every domain field minus id" — some `add_X()`
methods deliberately accept fewer fields than their domain model has,
e.g. `add_experience_project()` has no `responsibilities` param even
though `ExperienceProject` does). This module deliberately does **not**
use `from __future__ import annotations` — a real bug hit during
implementation: with postponed evaluation, `body: create_request_model`
(a closure-local dynamically-created class) becomes a string FastAPI can't
resolve back to a real type, and it silently falls back to treating `body`
as a query parameter instead of a request body.

`db/engine.py:get_engine()` creates a sqlite file's parent directory if
missing (mirroring `app/storage.py`'s old `mkdir(parents=True,
exist_ok=True)`) — SQLite itself does not do this, and a fresh checkout
would otherwise fail outright the first time anything touches the DB.

Jobs (`api/routes/jobs.py`): in-memory `dict[str, JobStatus]` behind a
`threading.Lock`, dispatched via `asyncio`'s `run_in_executor` — the
async-native equivalent of `ui/main_window.py`'s `_CallableWorker(QThread)`
pattern, same two-tier `except AppError / except Exception` catch shape.

## Phase 14 — React shell, feature-parity slice (done)
* Vite + React + TS + Tailwind + shadcn/ui + TanStack Query, reproducing
  exactly what `ui/main_window.py` does today: candidate picker, ingest,
  paste JD, generate, one editable text field per CV section, export
  buttons.
* No cross-links, no A4 preview, no diffing yet — this phase's only goal
  is proving the new stack holds together end-to-end, the same role
  Phase 6 played for the original stack.

"Save edits to profile" (Phase 8.3 write-back) was confirmed with the user
as out of scope for this slice — not in the phase's own bullet list above,
and it's not wired into the API yet either. Deferred, not forgotten.

New `frontend/` (React 19 + TS + Vite 8 + Tailwind v4 + shadcn/ui +
TanStack Query + React Hook Form + Zod). TypeScript types are **generated**
from the backend's live OpenAPI schema (`npm run gen:types`, via
`openapi-typescript`), not hand-written — committed to `src/api/types.ts`
and regenerated on demand rather than reimplementing ~15 Pydantic model
shapes by hand. Dev-mode talks to the backend through Vite's dev-server
proxy (`vite.config.ts`'s `server.proxy`, `/api/*` → `localhost:8000`),
not `CORSMiddleware` — production eventually serves the built frontend
*from* FastAPI itself (single origin), so the proxy is architecturally
closer to that end state than a dev-only CORS workaround would be.

State ownership mirrors `MainWindow` directly: `App.tsx` holds everything
`main_window.py` holds on `self` (active candidate, section text, last
result, status message); child components are controlled/presentational,
not independent state owners. `GapsPanel` ports `_gaps_html`'s exact
branching (high/medium shown individually and colored, low collapsed into
one count line, trailing missing-keywords line) as real JSX instead of an
HTML string. `SectionEditor`'s 12 fields are plain `useState`, not React
Hook Form — there are no validation rules for freeform CV text, so RHF's
submission-shaped model would fight the tool for no benefit; RHF stays
reserved for Phase 15+'s structured entity forms.

**A real gap found while wiring the section editor, not anticipated in
planning:** `GenerateJobResult` (`api/routes/jobs.py`) originally returned
only `{vacancy, match_result, assembled_cv}` — nothing that already
existed could turn an `AssembledCV` into the 12 section-key strings the
editor needs except `app/cv_markdown.py:render_all_sections()`, a Python
function with real formatting logic (bullet grouping, category grouping)
that would otherwise have had to be reimplemented in TypeScript and kept
in sync by hand forever — exactly the kind of drift risk generating API
types was meant to avoid, just for formatting logic instead of data
shapes. Fixed by adding a `sections: dict[str, str]` field to
`GenerateJobResult`, computed server-side via `render_all_sections()`
inside `_execute_generate()` — the frontend never reimplements CV
rendering, it only displays and edits what the backend already rendered.

New `POST /export` (`api/routes/export.py`) — stateless: the client resends
the full `AssembledCV` plus its current (possibly-edited) `sections`, the
same data `ui/main_window.py`'s `_on_export_clicked` already holds
client-side, rather than looking anything up server-side (there's nothing
durable to look up by job id — `/jobs` storage is in-memory, and there's
no `CVDraft` persistence until Phase 20). The header is always computed
server-side via `render_header(cv)`, never trusted from the client.
Wraps `app/cv_docx.py:render_docx()`/`app/cv_pdf.py:render_pdf()`/
`app/cv_markdown.py:assemble_markdown_from_sections()` directly — no new
Python dependency, no new error-handling code (`ExportError` already maps
through `api/errors.py`'s existing handler).

No Playwright this phase (no config exists yet; earmarked for Phase 16,
also as the PDF renderer) — primary end-to-end verification is manual,
driving the real running app in a browser through ingest → generate →
edit → export.

## Phase 15 — Candidate profile: cross-linked view
* New Skill/Technology ↔ Evidence link — this closes a gap
  `docs/domain-model.md`'s Skill section already describes ("Skills are
  linked to supporting Evidence... always able to explain why a skill
  exists") but that was never actually implemented; today `Skill` has no
  relationship to `Evidence` at all.
* `01_cv_parser_v1.md` updated to populate the link where inferable at
  ingestion; manual linking also supported via the API.
* UI: replaces the Graph Explorer's modal-CRUD-dialog pattern with an
  inline-editable LinkedIn/Notion-style profile page — clicking a skill
  highlights/scrolls to the experience bullets that back it, and vice
  versa. No graph-visualization library — this is cross-references within
  a normal page layout, not a node/edge diagram (confirmed scope: a
  literal graph view was considered and explicitly rejected in favor of
  this).

> **Scoped first slice: 15a backend now, 15b frontend as a follow-up.**
> Turned out to be as large as Phases 13+14 combined — a brand-new
> inline-editable profile page (nothing like it exists in the web app
> yet; Phase 14 only built the CV-generation workflow) plus the linking
> itself. Confirmed with the user: split it the same way 13→14 were
> split, backend fully landed and tested before any UI work starts.

### Phase 15a — Skill/Technology ↔ Evidence linking, backend only (done)
* `domain.models.Skill`/`Technology` gain `evidence_ids: list[str]`
  (default `[]`) — ids into the sibling Evidence[] list. Chosen over the
  other viable direction (a single `skill_id` on `Evidence`, which
  `db/models.py`'s Phase-13-era docstring had assumed without this being
  thought through yet) because the real relationship is many-to-many —
  one bullet can demonstrate several skills, one skill can be backed by
  several bullets — which only a list on `Skill`/`Technology` can
  express. Zero DB schema change (`Skill`/`Technology` still live inside
  `CandidateRow.data`'s JSON blob), and `api/routes/entity_crud.py`'s
  generic factory picks the field up automatically for
  `PUT .../skills/{id}` / `.../technologies/{id}` — no route code needed.
* New individual Evidence CRUD on `CandidateService` — `add_evidence`,
  `update_evidence`, `remove_evidence` — which didn't exist at all before
  this (only bulk `get_evidence()`/a private wholesale-replace used by
  ingestion). These query `EvidenceRow` directly by its composite
  `(candidate_id, id)` primary key rather than the list-search-in-JSON-
  blob pattern every other entity uses, since Evidence is the one entity
  with its own real table. `remove_evidence` cascades: strips the removed
  id from any `Skill`/`Technology.evidence_ids` referencing it.
* These new methods needed **zero new route file** — `entity_crud.py`'s
  factory only requires matching `add_X`/`update_X`/`remove_X` methods to
  exist, not that the entity be a `Candidate` list field, so one more
  entry in `_ENTITY_REGISTRATIONS` (`path_segment="evidence"`) was enough
  to get `POST/PUT/DELETE /candidates/{id}/evidence[/{id}]` for free,
  alongside the pre-existing hand-written bulk `GET`.
* Validation is deliberately asymmetric between the two link types:
  `update_skill`/`update_technology` reject an `evidence_ids` value
  containing an id that doesn't exist for the candidate
  (`ValidationError`) — but ingestion (`replace()`) does *not* eagerly
  validate the ids the LLM emits, matching the existing, older precedent
  that `Evidence.experience_id` is likewise never cross-validated at save
  time, only later at CV-assembly time. Validation lives at the one place
  a person explicitly sets a link, not at the bulk-import boundary.
* `01_cv_parser_v1.md` updated for `skills[].evidence_ids` only, not
  `technologies` — the prompt doesn't extract `technologies` at all today
  (a pre-existing gap, not introduced here), so `Technology.evidence_ids`
  exists and is settable via `update_technology()`, just never
  auto-populated by ingestion.

### Phase 15b — Inline-editable cross-linked profile page
The actual frontend: a new candidate profile page in `frontend/`
consuming Phase 15a's API, replacing what the desktop Graph Explorer does
today but inline-editable rather than modal-dialog-based, plus the
click-a-skill/click-a-bullet cross-link interaction itself.

> **Scoped first slice: 15b-i simple-entity CRUD now, 15b-ii Experience +
> cross-linking as a follow-up.** Turned out to be as large again as
> Phase 15a on its own — a brand-new profile page covering all ~12 entity
> types Graph Explorer handles, *plus* the genuinely novel
> Evidence-backed-bullets/cross-link interaction. Confirmed with the
> user: split it the same way 13→14 and 15→15a/15b were split, so the
> novel interaction design isn't sharing a review with routine CRUD
> plumbing.

#### Phase 15b-i — Profile shell + inline CRUD for simple entities (done)
* `App.tsx` restructured into a shared header (title + `CandidatePicker` +
  a plain two-button "CV Workflow / Profile" toggle, `useState`-backed —
  no router, matching Phase 14's existing choice to defer React Router)
  over two views. Phase 14's original two-column CV-generation JSX moved
  verbatim into a new `CvWorkflowView.tsx` with no behavior change; a new
  `ProfileView.tsx` is the profile page.
* One generic, config-driven `EntitySection.tsx` component covers all 11
  "simple" entity types (education, skills, technologies, languages,
  certifications, awards, contacts, projects, publications, portfolio
  links, volunteer experience) — a direct frontend mirror of the same
  "factory, not hand-duplication" choice already made twice elsewhere in
  the stack: `api/routes/entity_crud.py`'s backend route factory, and the
  desktop `ui/graph_explorer.py`'s `_EntityListSection`/`_ENTITY_SPECS`
  pattern, which this pass ported directly into `lib/entityConfigs.ts`
  (field lists, labels, and summarize strings carried over verbatim).
  Rows render read-only by default (LinkedIn/Notion convention) with
  Edit/Delete affordances; Edit expands an inline form; an "Add" row
  opens the same blank form. Delete confirms via native
  `window.confirm()`, not a new `AlertDialog` component — one destructive
  action, single-user local tool, same "simplest idiomatic option"
  reasoning as Phase 14's toast-over-modal choice.
* New `useEntityMutations(candidateId, pathSegment)` hook factory
  (`api/entities.ts`) generates the create/update/remove mutations for
  all 11 entities from one implementation, hitting the generic
  `entity_crud.py` routes Phase 15a already exposed; all three invalidate
  `["candidates", candidateId]`.
* Blank optional fields submit as `null`, not `""` — required fields
  (e.g. `name`) still validate non-empty; this is a frontend submission-
  shaping choice only, no new backend validation needed.
* `Skill`/`Technology.evidence_ids` is untouched this pass — no badge, no
  editing affordance, deliberately deferred whole to 15b-ii so the
  cross-link visualization gets designed once rather than half-built now
  and reworked later.
* New shadcn components: `input`, `checkbox`, `card` — nothing else
  (no `Badge`/`Popover`/`Dialog`/`Accordion`/`Tabs`, which belong to
  15b-ii's cross-link UI or aren't needed at all here).
* Bug found and fixed along the way: `apiFetch<T>()` unconditionally
  called `response.json()`, which throws on a 204 No Content response —
  never triggered until this pass's `useEntityMutations`'s `remove`
  mutation became the first frontend code to call `DELETE`. Fixed by
  returning `undefined` for a 204 before attempting to parse a body.
* Verified against real production data in a live browser session (both
  candidate profiles in the dev DB): all 11 sections render correct
  `summarize()` output, and a full add → edit → delete cycle for a test
  Skill was confirmed to persist correctly at each step via direct API
  checks. Confirmed switching between the two views preserves the shared
  selected candidate.

#### Phase 15b-ii — Experience, nested Projects/Evidence-backed bullets, and the skill↔bullet cross-link interaction (done)
The remaining, genuinely novel part of Phase 15: Experience's nested
Projects and role/project-level bullet lists (not a "simple" flat entity
like the 11 above), plus the Skill/Technology↔Evidence cross-link
display. No backend changes were needed — everything (Experience CRUD,
nested Project CRUD, Evidence CRUD) already existed from Phase 13/15a.
* **Confirmed with the user**: the cross-link goes only as deep as a
  read-only "backed by" list (quoted Evidence text + source context)
  under each Skill/Technology row, plus a matching "Evidence & skill
  links" panel inside each Experience card — not a live scroll-to/
  highlight interaction. Rejected because plain-text bullets
  (`Experience.responsibilities`/`.achievements`) have no stable id to
  highlight — `Evidence` is a separate, parallel extraction of similar
  content (CV rendering pulls from the plain-text fields, never from
  `Evidence`), not the same object as a bullet.
* Experience got a dedicated, hand-written component tree
  (`ExperienceSection`/`ExperienceForm`/`ExperienceProjectsManager`/
  `ExperienceEvidencePanel`), not forced into `EntityConfig`/
  `EntitySection` — its nested Projects and `string[]` bullet lists don't
  fit that generic component's `FieldSpec`/`toRequestBody` shape.
* Nested Project CRUD reuses `useEntityMutations` **verbatim** with a
  computed 3-segment `pathSegment`
  (`` `experience/${experienceId}/projects` ``) — confirmed the hook
  needed zero changes, since `pathSegment` was already just interpolated
  into a template literal.
* New `BulletListEditor` component (controlled over `string[]`, add/edit/
  remove rows) is the one genuinely novel piece of UI — used for role-
  level and project-level Responsibilities/Achievements. Deliberate
  departure from Graph Explorer's per-bullet project-reassignment
  dropdown: role-level and project-level bullets are edited in their own
  form and saved via their own already-atomic PUT/POST, trading exact Qt-
  UX parity for avoiding client-side unsaved-id juggling.
* `add_experience_project` has no `responsibilities` param (a pre-
  existing backend gap, not invented or silently "fixed" here) — the Add-
  Project form only shows Name/Period/Achievements; the Edit form (an
  existing project) shows all four fields once the project exists.
* Cross-link mechanism: a pure-data `EntityConfig.evidenceIds?: (item) =>
  string[]` accessor, set only on `skills`/`technologies` — keeps
  `entityConfigs.ts` JSX-free (`summarize`'s existing "config returns
  data, component owns markup" split) and leaves the other 9 entity
  configs provably unaffected, since the accessor is `undefined` for
  them. Explicit regression test confirms an Education row renders
  nothing extra even when the same `evidenceById` prop is passed.
* New `useEvidence(candidateId)` hook — Evidence isn't embedded in the
  `Candidate` object, so it's fetched separately; its query key is a
  strict extension of `["candidates", candidateId]`, so every existing
  mutation already invalidates it for free via TanStack Query's default
  prefix-match `invalidateQueries`.
* Verified against real production data in a live browser session: all
  9 real Experience entries rendered correctly (incl. a `[GAP]` entry);
  a full add → edit (add nested Project) → delete cycle for a test
  Experience was confirmed to persist at each step via direct API
  checks; a skill was manually linked to a real Evidence item via the
  API to confirm the "backed by" list renders its text + source context
  correctly, then reverted. This closes out the full "Phase 15: candidate
  profile, cross-linked view" scope.

> **Addendum — Experience rework: unified Achievements/Responsibilities
> list with a per-bullet Project dropdown, replacing the per-project
> nested form.** Found while using the app on real production data: the
> "Evidence & skill links" panel duplicated every bullet's text (ingestion
> commonly sets `Evidence.source_context` to "Company, Project: <bullet
> text again>", which the panel then rendered right after the identical
> bullet text — already fully redundant with the panel's own project-name
> heading). Separately — the real issue — a role whose achievements were
> entirely tied to a Project showed a completely empty top-level
> Achievements editor; the actual content was one more "Edit" click away
> on that Project's own row. Both were reported directly, with a real
> screenshot, as "the user should not have to work this hard to find data
> they entered."
> * `ExperienceEvidencePanel.tsx`: dropped `source_context` from the
>   rendered line entirely — `Evidence.experience_id`/
>   `.experience_project_id` (Phase 7) already provide the structured
>   role/project grouping this panel displays via its heading; the
>   free-text field never added anything a person couldn't already see.
> * The achievements-visibility fix was a real fork with two different
>   amounts of rework — confirmed with the user which one to build: (a) a
>   cheap read-only preview under each collapsed Project row, or (b) port
>   `ui/graph_explorer.py`'s original design (a single flat bullet list per
>   role, each row taggable to a Project via a dropdown, one combined
>   save) — which Phase 15b-ii's own note had explicitly deferred as
>   `BulletListEditor`'s "departure from Graph Explorer's per-bullet
>   project-reassignment dropdown... trading exact Qt-UX parity for
>   avoiding client-side unsaved-id juggling." The user picked (b).
> * New `BulletRowsEditor.tsx` replaces `BulletListEditor.tsx` (deleted,
>   along with its test — fully superseded, no other caller existed) for
>   Experience specifically: one row per bullet, a Textarea plus a
>   project `Select` ("(none)" = role-level), ported directly from
>   `ui/graph_explorer.py`'s `_BulletRowsEditor`.
> * `ExperienceForm.tsx` gained an inline Projects manager (name/period
>   only, no nested achievements editor of its own) — Projects are now
>   in-memory state (`LocalProject[]`) inside the same form, not
>   independently persisted, mirroring `_ExperienceFormDialog`'s `_projects`
>   list exactly. New projects get a client-generated id
>   (`` `local-${crypto.randomUUID()}` ``) that simply becomes the real
>   persisted id on save — same scheme as `_new_local_id()`
>   (`uuid.uuid4().hex[:8]`) on the desktop side. Deleting a project
>   reassigns (not drops) any bullet tagged to it back to role-level,
>   porting `refresh_project_options()`'s "unlink, don't drop" rule.
>   `toExperienceRequestBody()` partitions the flat rows back into
>   role-level lists plus each Project's own nested `achievements`/
>   `responsibilities`, and silently drops a Project left with a blank
>   name at save time — reassigning its rows to role-level first, the same
>   unlink-don't-drop treatment as an explicit delete.
> * **No backend change needed.** `update_experience(experience_id,
>   **fields)` already does `entry.model_copy(update=fields)`, and
>   `api/routes/entity_crud.py`'s generic update-body factory already
>   builds its Pydantic model from every field on the `Experience` domain
>   model (not a hand-picked subset) — so `PUT .../experience/{id}` already
>   accepted a full nested `projects` array in one call, atomically,
>   without ever being exercised that way from the frontend before now.
> * `ExperienceSection.tsx`'s `handleSave` mirrors
>   `ui/graph_explorer.py`'s `_add_experience` exactly for a **new**
>   Experience: `add_experience` has no `projects` param (nothing to
>   attach a nested Project to before the entry itself has an id), so
>   Save does one `POST` without `projects`, then — only if the form has
>   any — a follow-up `PUT .../experience/{newId}` with `{projects}`. This
>   also **removes** the old "Save this role first, then add Projects"
>   gate: Projects are addable immediately in new-Experience mode now,
>   same as editing an existing one, since they're just in-memory form
>   state either way.
> * `useEntityMutations` gained an optional `<T = unknown>` type param
>   (defaulting to its previous behavior for every other caller) so
>   `ExperienceSection.tsx` can read a freshly-created Experience's real
>   `id` out of `create.mutate`'s `onSuccess` callback, needed for that
>   follow-up PUT.
> * Verified: full suite (483 backend / 118 frontend, up from 109 —
>   `BulletRowsEditor.test.tsx` and `ExperienceForm.test.tsx` are new; the
>   latter unit-tests `toExperienceRequestBody`'s partitioning/blank-name/
>   blank-row-dropping directly as a pure function rather than through the
>   UI, since driving a Radix `Select` open/select interaction isn't
>   reliable under jsdom — the same limitation `ExportButton.test.tsx`
>   already worked around), `tsc --noEmit`, `oxlint`, `vite build`. Then a
>   real browser session against the actual production candidate profile
>   from the bug report (9 Experience entries): confirmed the duplicated
>   "Evidence & skill links" text was gone; opened Edit on the
>   Expedition-and-Meta role and confirmed all 6 of its `Supercity web`
>   Project achievements rendered directly in the unified Achievements
>   list (each showing "Supercity web" in its own dropdown) instead of an
>   empty top-level list; edited one achievement's text via a real
>   `PUT`, confirmed via a direct follow-up `GET` that it persisted
>   correctly alongside the other 5 and the Project's own id/name/period,
>   then reverted that edit via the API to leave the real profile
>   unchanged.

## Phase 16 — A4 WYSIWYG preview, templates, section/bullet toggles
* New structured-document model: ordered sections → ordered entries
  (Experience additionally has ordered bullets nested per entry), each
  with `included: bool`. This single field implements the section/bullet
  exclude-toggle ask — not a separate feature.
* Block-based editor renders the document as an actual A4 page via print
  CSS; drag-reorder within a section (and within an Experience entry's
  bullets); every entry/bullet, including section headers, is directly
  editable (plain text — confirmed with the user: no rich-text formatting
  within a block, so no TipTap; a controlled input per block is enough).
* Template = a named set of typography/spacing CSS variables (heading/
  body font, bullet style, section spacing) the same structured document
  renders through — confirmed with the user: font/spacing only, not
  structural/multi-column changes, so templates can't regress
  ATS-readability the way a layout template could. Ship 2 built-in
  templates.
* Export: PDF via Playwright/headless Chromium navigating to the live
  frontend's own print-preview route (screenshot-to-PDF of the actually-
  rendered page — guarantees preview/export fidelity by construction,
  confirmed with the user over a second independent server-side HTML
  templating implementation); DOCX via `app/cv_docx.py` gaining a
  `template_id` param and applying the same font/bullet/spacing choices
  directly via `python-docx` styling (confirmed with the user — no HTML/
  Playwright involved for DOCX). The existing plain reportlab PDF export
  stays available unchanged as a separate "ATS-safe" format option
  alongside the new templated one, not replaced by it.

> **Scoped first slice: 16a on-screen editor now, 16b templated export as
> a follow-up.** Turned out to span a new structured-document model, a
> drag-reorder block editor, an on-screen A4 print-CSS preview with
> templates, AND a new Playwright PDF pipeline — bigger than any phase so
> far. Confirmed with the user: split it the same way every previous
> large phase was split, on-screen editing landing first and reviewed on
> its own before the export pipeline it will eventually drive.

### Phase 16a — Structured document model + A4 WYSIWYG block editor, preview only (done)
* The structured document (`frontend/src/lib/structuredDocument.ts`) is
  built purely client-side from `AssembledCV` (already sent on every
  successful generate) — no new backend model, endpoint, or persistence
  this pass, matching the confirmed "ephemeral for now" scope for all of
  Phase 16's edit state and "no `CVDraft` persistence until Phase 20."
* **Not wired into `/export` this pass, by design.** `AssembledCV` is
  structured, but what `/export` actually consumes
  (`sections: dict[str,str]`, from `app/cv_markdown.py::render_all_sections`)
  is a one-way-flattened opaque Markdown-convention string per section,
  never reconstructed back into structured data anywhere in the stack.
  Faithfully reverse-engineering that exact formatting from a block list
  just to keep 16a's toggles/reorders flowing into the *existing* export
  pipeline would mean duplicating real formatting logic from
  `cv_markdown.py` in TypeScript — a drift risk for a bridge getting torn
  out the moment 16b lands a real consumer of the document model. The new
  editor ships as an honestly-labeled **preview** this pass (a small note
  in the UI says so explicitly); the existing Text Editor tab / Export
  button are completely untouched and still work exactly as before.
* Component shape mirrors the "generic pattern + one dedicated exception
  for Experience" shape this codebase now uses three times over
  (`entity_crud.py`'s route factory, `entityConfigs.ts`/`EntitySection.tsx`,
  `ExperienceSection.tsx`): `DocumentSectionBlock.tsx` (generic — one
  draggable/toggleable/editable row per entry) for the 11 non-Experience
  sections plus `summary`; `DocumentExperienceSection.tsx` (dedicated) for
  Experience, whose entries have their own nested sortable bullet lists.
  `entityConfigs.ts`'s existing `summarize()` functions are reused
  directly to seed each entry's initial text (its `listField` values
  already match `AssembledCV`'s own field names) rather than writing 11
  new summarizers.
* `is_gap` Experience entries are `locked: true` in the new model — can't
  be excluded, matching the existing invariant that a gap never silently
  disappears from the output.
* New dependency: `@dnd-kit/core`/`@dnd-kit/sortable`/`@dnd-kit/utilities`
  (no drag-and-drop library existed before; chosen over the unmaintained
  `react-beautiful-dnd`).
* Integration: a small "Text Editor / A4 Preview" tab toggle inside
  `CvWorkflowView`'s output column, not a new top-level view —
  `CvHeader`/`GapsPanel`/`ExportButton` are untouched.
* Two research-time doc conflicts were found and resolved with the user
  (recorded here since they shape 16b, not 16a's own work): whether DOCX
  export becomes template-aware (yes, in 16b, via `python-docx` directly
  — no HTML/Playwright), and how "export renders the same HTML the editor
  shows" actually works (Playwright navigates to the live frontend's own
  print-preview route, not a second independent HTML templating path).

### Phase 16b — Templated PDF/DOCX export via Playwright (done)
Wires 16a's structured document + template choice into real export. No
production deployment target exists yet, so this only wires up dev-mode
reachability (backend → Vite dev server) — real single-origin static
serving stays out of scope until an actual deployment target exists.
* New `frontend/src/main.tsx` pathname branch (`/print/{sessionId}`,
  matched via a plain `window.location.pathname` regex, no routing
  library) renders a chrome-free `PrintPreview.tsx` instead of the normal
  `App` tree — the stable URL Playwright navigates to. New read-only
  `PrintSectionBlock.tsx`/`PrintExperienceSection.tsx`/`CvPrintHeader.tsx`
  (no drag handle/`Checkbox`/`Input` — excluded entries/bullets filtered
  out entirely, not shown-with-strikethrough) render inside the same
  `A4Page` the on-screen editor uses.
* Backend: `api/routes/export.py` gained a short-lived, single-use,
  in-memory "print session" stash (`_print_sessions`/`_print_sessions_lock`,
  mirroring `jobs.py`'s own store-ownership shape) — read-once-then-
  deleted by `GET /export/print-session/{id}`, needing no TTL/cleanup
  thread since a session has exactly one legitimate reader. The whole
  create → Playwright-navigate → read → delete sequence happens inside
  one `POST /export` call; the existing plain pdf/docx/md request shape
  is unchanged (two new optional fields, `template_id`/`document`, both
  omitted by the untouched Text-Editor-tab `ExportButton`).
* New `app/cv_pdf_playwright.py::render_templated_pdf(session_id, config)`
  — sync Playwright API (matches `/export`'s handler already being a
  plain sync `def` FastAPI runs in its own threadpool; confirmed via an
  early smoke test that sync Playwright works fine inside a
  `ThreadPoolExecutor` worker thread, since its documented restriction is
  specifically against a thread with an *active* asyncio event loop).
  Waits on an explicit `[data-print-ready="true"]` selector rather than
  generic `networkidle`/font-load heuristics. New `@page`/`@media print`
  CSS (`index.css`) reuses the same `.cv-a4-page` class for both on-screen
  and print — Playwright's `page.pdf()` applies `@media print`
  automatically, so no separate print-target component/class was needed,
  just a rule that strips the drop-shadow/fixed-height and adds
  `break-inside: avoid` on entry/bullet rows.
* New `app/cv_docx.py::render_templated_docx(cv, document, template_id)`
  — confirmed with the user: also consumes the *edited* `PrintDocument`
  (respecting Preview-tab toggles/reorder), not just fonts/spacing, so
  templated PDF and DOCX stay content-consistent with each other. Switches
  to literal-character-prefixed bullets (mirroring `cv_pdf.py`'s own
  existing approach) only on this path, since Word's native "List Bullet"
  style can't express a template-chosen bullet character without
  `numbering.xml` surgery — `render_docx`'s existing non-templated bullet
  handling is untouched. New `app/cv_templates.py::DOCX_TEMPLATES` is a
  deliberately separate, parallel table from `cvTemplates.ts` (python-docx
  has no CSS-variable concept).
* New `Config.frontend_url` (defaults to `http://localhost:5173`) and a
  new `playwright>=1.47` dependency + one-time `playwright install
  chromium` step — no README/Makefile/CI existed anywhere to document
  that step in, so a missing-browser-binary error is instead caught and
  re-raised as a self-documenting `ExportError` pointing at the fix,
  matching `cv_docx.py`/`cv_pdf.py`'s own lazy-import error pattern.
* Reconciled during 16a's own planning, acted on here: `docs/
  technology_stack.md`'s Export section and this file previously
  disagreed on both the DOCX-template question and the "same HTML the
  editor shows" mechanism — both now match what's actually built.
* Playwright's own browser-launch-and-screenshot step is deliberately not
  covered by an automated test (same precedent Phase 14 already set —
  no CI exists anywhere to gate a slow/real-browser test behind); all
  automated tests exercise the route/rendering logic with
  `render_templated_pdf` mocked. Verified for real via direct API calls
  (a templated PDF/DOCX export with an excluded bullet and reordered
  entries, confirming both the exclusion and the order are reflected in
  the actual output bytes) and a full browser-driven click-through
  (generate a real CV, toggle a bullet off in the A4 Preview tab, click
  Export Templated — 200 response; switched back to the Text Editor tab
  and confirmed the original plain `ExportButton` still works
  unaffected). This closes out the full "Phase 16: A4 WYSIWYG preview,
  templates, section/bullet toggles" scope.

> **Post-16b fix: A4 preview rendering didn't match `app/cv_markdown.py`'s
> real conventions.** A real exported PDF surfaced five issues: empty
> sections (Portfolio, Certifications, etc.) showed in the on-screen
> editor (already correctly hidden on export); Contacts never appeared in
> the on-screen editor at all (it never rendered a header, only the
> export path did); Skills/Technologies rendered as a flat "Name
> (Category)" list instead of a bold category subheading + bulleted
> items; nothing rendered as a real bulleted list (plain, unbulleted
> paragraphs); Experience role headers weren't visibly bold, and a
> bullet's source project showed as an inline "Project: " text prefix
> instead of a proper subheading line. Root cause: `structuredDocument.ts`
> reused `entityConfigs.ts`'s flat single-line summaries (built for the
> profile-editing CRUD UI) instead of mirroring `cv_markdown.py`'s actual
> category-grouped/project-grouped CV-rendering rules. Fixed by rebuilding
> the Skills/Technologies and Experience section builders to match
> `cv_markdown.py` exactly (a new `kind?: "item" | "subheading"` field on
> `DocumentBlock` marks category/project names, styled boldly or
> italically with no bullet marker by whichever component renders them);
> switching all print/DOCX bullets from a CSS `::before` marker to a
> literal character prefix (`CvTemplate.bulletChar` /
> `DocxTemplate.bullet_char`), which incidentally also fixes a pypdf
> text-extraction ordering quirk and is more ATS-robust; adding
> empty-section hiding and the missing header to the on-screen editor;
> and updating `render_templated_docx` to match all of the above so PDF
> and DOCX stay visually consistent. Verified via a direct templated PDF
> export reproducing the original bug report's exact shape (category
> subheadings, project-grouped bullets, an empty section) and inspecting
> the output bytes.

### Phase 16c — A4 editor as the only CV editor + real pagination polish (done)
Confirmed with the user: this phase both retires the old flat Text Editor
tab in favor of the A4 block editor as the single CV-editing surface, and
gives the templated PDF's pagination CSS (added but never exercised in
16b) a real multi-page stress test.
* `DocumentEditor` (the A4 block editor) is now the *only* CV editor.
  `SectionEditor.tsx`, its `sections: Record<string,string>` state, and
  `CvHeader.tsx` (redundant with `CvPrintHeader` inside the A4 page) are
  all deleted; the two previously-separate Export controls (the old
  `ExportButton` reading `sections`, and `DocumentEditor`'s own inline
  "Export Templated" button reading `DocumentModel`) are merged into one
  `ExportButton`, now a sibling of `DocumentEditor` in `CvWorkflowView`
  rather than owned by either. `DocumentEditor` keeps owning its
  `DocumentModel` state internally (no state lifted) but gained an
  `onModelChange` callback so the merged `ExportButton` can read a live
  mirror of the edited document.
* Backend: since the plain (non-templated) PDF/DOCX/Markdown renderers
  (`render_pdf`/`render_docx`/`assemble_markdown_from_sections`) are
  shared with the desktop app/CLI and hard-wired to a flat
  `dict[str,str]` shape, the only new code needed was a serializer —
  `cv_markdown.py::render_sections_from_document` — turning the *edited*
  `PrintDocument` back into that same flat shape, so plain export now
  reflects live edits instead of a stale server-computed snapshot. The
  renderers themselves are untouched. `ExportRequest.sections` is
  removed entirely (not deprecated) and `document: PrintDocument` is now
  required for every export; `GenerateJobResult.sections` (a
  never-since-edited snapshot nothing in the frontend read anymore) is
  also removed.
* Pagination: confirmed a real gap in 16b's CSS — a section's `<h2>`/
  `<h3>` and its first entry are flat siblings, so a page break could
  legitimately land right after a heading, stranding it alone at the
  bottom of a page. Fixed with `break-after: avoid-page` on
  `.cv-a4-page h2, h3` (deliberately not `break-inside: avoid` on the
  whole `<section>`, which would force a long, page-spanning section
  like Experience to jump as one atomic block instead of flowing
  naturally) plus `orphans`/`widows: 3` as a minor safeguard. Also fixed
  a font-load race in `PrintPreview.tsx`: `data-print-ready="true"` now
  also waits on `document.fonts.ready`, so Playwright's `page.pdf()`
  never fires mid-webfont-swap for the Modern template's Geist Variable
  font.
* Verified: full backend suite (470 passed) and frontend suite (101
  passed, build + lint clean); a real browser click-through (generate a
  CV, confirm only the A4 editor shows with no tab toggle, toggle a
  bullet off, export plain PDF, then Classic templated PDF, then Classic
  DOCX — all three 200s, header shown exactly once); and a pagination
  stress test — a synthetic 12-entry/60-bullet `PrintDocument` posted
  directly to `/export` with a template produced a 5-page PDF where
  every section/role heading (Experience, Education, Skills, and every
  per-role heading) is immediately followed by its own content on the
  same page, none stranded alone at a page bottom.

## Phase 17 — LLM-edit transparency
* Bullet rewriting (`05_rewrite_bullets_v1.md`) extended to retain
  `{original_text, rewritten_text, rationale}` per bullet instead of only
  the final text — a short prompt addition, not a new stage.
* Diff the full Evidence set against what actually appears in the
  assembled document; surface unused-but-plausibly-relevant Evidence as
  "didn't make the cut — add manually?" prompts.
* UI: inline highlight on edited blocks with a popover (rationale +
  "revert to original," which resets that block's text to
  `original_text` — a client-side/data operation, no new pipeline call).
* Distinct from, and narrower than, the still-deferred "AI Suggestions
  panel" noted above (Phase 6/12.3) — that needs the full
  Claims/Competencies/Variant semantic layer. This phase only needs
  per-bullet original/rewritten text pairs, already producible from the
  existing rewrite stage without new domain concepts.

> **Scoped first slice: 17a backend provenance plumbing now, 17b the
> highlight/popover/revert UI + unused-Evidence panel as a follow-up.**
> Confirmed with the user: same backend-then-UI split as every other large
> phase since 13.

### Phase 17a — Backend: bullet provenance, no UI (done)
Reviewing what `{original_text, rewritten_text, rationale}` actually
requires turned up that most of it doesn't need new LLM output at all:
`original_text` is just `Evidence.text`, and `rationale` is exactly what
the Rewrite Planning stage's `RewriteAction.reason`/`target_keywords`/
`new_angle` (already computed per `evidence_id` in `app/pipeline.py`,
then previously discarded once `plan_response.plan` went out of scope)
already says. The only real gap was that nothing linked a final
`TailoredBullet` back to the Evidence item it came from at all.
* `domain.models.TailoredBullet` gains `evidence_id: str | None` — echoed
  verbatim by the LLM, the same convention `TailoredExperience.
  experience_id` already uses. This is the one new field actually asked
  of the Bullet Rewriting call; `05_rewrite_bullets_v1.md` gained one rule
  (mirroring the existing `experience_id` verbatim-copy rule) plus an
  updated JSON output example.
* New `domain.models.BulletProvenance` (`evidence_id`, `original_text`,
  `rewritten_text`, `action`, `rationale`) and `BulletProvenanceReport`
  (`bullets`, `unused_evidence`) — sibling to `MatchResult`: purely
  informational, never folded into `AssembledCV`/`CVProjection`, never
  exported.
* New `app/bullet_provenance.py::build_report(evidence, plan, cv)` — a
  pure function, no LLM call. Joins `plan.actions` and `evidence` (both
  by id) against every bullet already in the just-assembled `AssembledCV`.
  A bullet with no `evidence_id`, or one that matches no known Evidence
  id, is skipped rather than raised on — same "ignore, harmless"
  precedent `app/cv_assembler.py`'s `_rank_by_category` already set for an
  unrecognized name. `unused_evidence` (Evidence ids no bullet ever
  referenced) naturally covers both plan-removed items and Evidence with
  no `experience_id` at all (never eligible for a bullet in the first
  place, a pre-existing gap this pass didn't introduce).
* `app/pipeline.py`: `PipelineResult` gains `provenance:
  BulletProvenanceReport`, computed in `run_cv_generation` right after
  `assemble_cv` — no new provider call, so the stage count stays at 4
  (analyze → match → plan → rewrite).
* `api/routes/jobs.py`: `GenerateJobResult` gains `provenance`, wired in
  `_execute_generate` — same mechanical addition `match_result` got in
  Phase 14.
* No frontend change this slice — `ui/main_window.py` needed none either,
  since it only ever receives a `PipelineResult` from `run_cv_generation`
  rather than constructing one by hand (the one place that did,
  `tests/test_ui/test_main_window.py`'s fixture, was updated to pass an
  empty `BulletProvenanceReport()`).
* Verified via the full pytest suite (483 passed, up from 475): new unit
  tests for `build_report` (rewrite/enhance/keep/remove actions, a bullet
  with no `evidence_id`, a stale/hallucinated `evidence_id`, evidence
  never referenced by any bullet, multiple Experience entries), a
  `run_cv_generation` unit test asserting `PipelineResult.provenance` is
  wired correctly against fake services, an integration test exercising
  the real prompts/use_cases/pipeline/cv_assembler stack end to end
  (confirming zero extra provider calls), and an API test asserting
  `GenerateJobResult.provenance` round-trips through `POST /jobs` +
  `GET /jobs/{id}`.

### Phase 17b — Frontend: highlight, rationale popover, revert; unused-Evidence panel (done)
* `src/api/types.ts` regenerated (`openapi-typescript` against a live
  backend) to pick up `TailoredBullet.evidence_id` and `GenerateJobResult.
  provenance` / `BulletProvenance` / `BulletProvenanceReport`; `src/api/
  models.ts` gained the two new named aliases, same convention as every
  prior schema addition.
* `lib/structuredDocument.ts`: `DocumentBlock` gains `evidenceId?: string`,
  set on Experience bullets only (`buildExperienceBullets`, from
  `TailoredBullet.evidence_id`) — every other section's blocks never set
  it, since only Experience bullets are ever AI-rewritten from Evidence.
* New `lib/bulletProvenanceIndex.ts::buildProvenanceByEvidenceId()` — a
  one-line `Map` build, mirroring `evidenceIndex.ts`'s
  `buildEvidenceById()` exactly (same "id-keyed Map for O(1) lookup"
  shape Phase 15b-ii already established).
* New shadcn `popover` component (`npx shadcn add popover`) — no new
  dependency; it's part of the already-installed `radix-ui` package the
  same way `select`/`checkbox` already consume it.
* `DocumentExperienceSection.tsx`: `BulletRow` gains an `isSubstantiveEdit()`
  check (`action` is `"rewrite"` or `"enhance"` — a `"keep"` action is
  light grammar cleanup only, per `05_rewrite_bullets_v1.md`'s Rules, not
  worth flagging as "AI-edited"). A substantively-edited bullet gets a
  left-border highlight plus a small `Sparkles`-icon `PopoverTrigger`
  showing the action label, rationale, and original text, with a "Revert
  to original" button — which just calls the existing `onTextChange`
  prop with `provenance.original_text`, so no new callback/prop plumbing
  was needed beyond threading the provenance map itself down from
  `DocumentEditor`. Reverting doesn't clear the highlight (provenance is
  static per-generate metadata, not a diff against current text) — by
  design, so re-opening the popover after a revert still shows the same
  rationale if the person wants to redo the edit differently.
* New `UnusedEvidencePanel.tsx`, read-only like `GapsPanel` — lists
  `provenance.unused_evidence` (text + source_context) under a "Didn't
  make the cut for this vacancy — add manually?" nudge. No auto-add
  wiring, same reasoning as `Gap.suggested_action` staying advisory-only.
  Wired into `CvWorkflowView.tsx` next to the Gaps panel.
* Verified via the full frontend suite (109 passed, up from 101 — new
  tests for `buildProvenanceByEvidenceId`, the highlight/popover/revert
  behavior in `DocumentExperienceSection`, and `UnusedEvidencePanel`'s
  empty/non-empty states), `tsc --noEmit`, `oxlint`, and a real
  browser-driven click-through: selected a real candidate profile (9
  Experience entries), pasted a real vacancy, and generated an actual CV
  through the live Gemini-backed pipeline (all 4 stages) rather than a
  mocked one. Confirmed 13 bullets rendered with the AI-edit highlight,
  opened the popover on one (`action: "enhance"`, real rationale text,
  real `original_text`), clicked "Revert to original," and confirmed the
  block's text changed to exactly that original text with no new network
  request — and confirmed the Unused Evidence panel listed the real
  Evidence items with no `experience_id` link (candidate-summary and
  standalone-Projects text, never eligible for a bullet in the first
  place) exactly as `build_report`'s Phase 17a design predicted. This
  closes out the full "Phase 17: LLM-edit transparency" scope.

## Phase 18 — Re-evaluation loop
* Decouple `MatchingService.match()` (real since Phase 8) so it can be
  invoked against the *current edited* document, not only once before
  tailoring.
* `domain.models.Gap` gains a `status: "open" | "skipped"` field (extends
  Phase 8.2's severity model) so a user can acknowledge-and-dismiss a gap
  instead of it resurfacing on every re-check.

> **Scoped first slice: 18a backend now, 18b the Re-check Gaps
> button/dismiss UI as a follow-up.** Same backend-then-UI split as every
> other phase spanning both since Phase 13.

### Phase 18a — Backend: recheck job + dismissible Gap, no UI (done)
The concrete, implementable definition of "the current edited document"
this phase settled on: the Evidence still backing an `included: true`
Experience bullet in the on-screen document (Phase 17a already threads
`evidence_id` onto every `TailoredBullet`/`DocumentBlock` for exactly this
kind of lookup). A hand-typed bullet, or an Evidence item never tied to
any bullet, can't be represented this way — left as a documented limit,
not solved this pass, mirroring `app/bullet_provenance.py`'s own "no
`evidence_id` → skipped" precedent. Skills/Technologies section toggles
are also out of scope: the original generate call already ignores
document-level toggles for those (flat name lists straight from the
Candidate profile), so re-check stays consistent with that rather than
silently fixing only one side of an existing gap.
* `domain.models.Gap.status: Literal["open", "skipped"] = "open"` — never
  set by the Matching stage itself (every freshly matched Gap is "open").
  It exists so a dismissed gap can round-trip through the API at all; the
  actual "don't resurface a dismissed gap across a re-check" logic is
  deliberately left to the client side (18b) — a session-local set of
  dismissed `requirement_text`s applied after each match — since there's
  nowhere server-side to persist it before Phase 20's `CVDraft` exists.
* New `app/pipeline.py::run_gap_recheck(candidate, evidence, requirements,
  excluded_evidence_ids, services) -> MatchResult` — reuses the existing
  `_format_language`/`_format_certification` helpers, filters `evidence`
  by `excluded_evidence_ids`, and calls `services.matching.match()`
  directly. Exactly one LLM call, decoupled from `run_cv_generation`'s
  4-stage chain (no vacancy re-analysis, no Rewrite Planning/Bullet
  Rewriting) — `requirements` is whatever the caller already has from the
  original generate.
* `api/routes/jobs.py`: new `RecheckJobRequest(type="recheck",
  candidate_id, requirements: list[Requirement],
  excluded_evidence_ids: list[str] = [])` / `RecheckJobResult(match_result)`,
  wired into the existing `JobRequest`/`JobStatus` unions and
  `create_job()`'s three-way dispatch — same job-polling shape
  `ingest`/`generate` already use, no new infrastructure.
* Verified via the full pytest suite (489 passed, up from 483): unit
  tests for `run_gap_recheck` (excluded ids drop their Evidence from the
  matcher's input, an empty exclusion set behaves like a full recheck,
  candidate skills/technologies/languages/certifications are passed
  through the same as `run_cv_generation` does), and an API test round-
  tripping a `recheck` job through `POST /jobs` + `GET /jobs/{id}`
  (confirming exactly one provider call — the Matching stage alone, not
  the full chain) plus a missing-candidate failure case.

### Phase 18b — Frontend: Re-check Gaps button + dismissible gaps (done)
* `src/api/types.ts` regenerated to pick up `Gap.status`, `RecheckJobRequest`/
  `RecheckJobResult`, and the widened `JobStatus`/`JobRequest` unions;
  `src/api/models.ts` gained `Requirement`/`RecheckJobResult` aliases.
* New `lib/documentEvidence.ts::collectExcludedEvidenceIds(document)` —
  walks the Experience section's entries/bullets, collecting a bullet's
  `evidenceId` whenever its own toggle, its role entry's toggle, or the
  whole Experience section's toggle is off. Only Experience bullets ever
  carry an `evidenceId` (Phase 17b), so every other section is irrelevant
  here, matching 18a's scoping exactly.
* New `useRecheckGapsJob` in `api/jobs.ts`, mirroring `useGenerateJob`
  structurally — posts `{type: "recheck", candidate_id, requirements,
  excluded_evidence_ids}` and polls the same `/jobs/{id}` shape.
* New `lib/dismissedGaps.ts::applyDismissed(matchResult, dismissed)` — the
  client-side-only "don't resurface a dismissed gap" logic 18a's plan
  deferred here: re-stamps `status: "skipped"` onto any gap whose
  `requirement_text` is in a session-local `Set`, since every fresh
  `MatchResult` (a generate or a recheck) comes back with every Gap at
  `"open"` — the LLM has no memory of a previous dismissal.
* `GapsPanel.tsx` gained an optional `onDismiss` prop: a "Dismiss" button
  next to each shown (high/medium) gap, and a skipped one collapses into
  a "+ N dismissed" line, mirroring the existing low-severity collapse
  treatment exactly (low-severity gaps stay excluded from that count —
  they were never shown individually to begin with, dismissed or not).
* `CvWorkflowView.tsx`: new `vacancy`/`dismissedRequirements` state (the
  latter reset on every fresh generate, since a new vacancy means entirely
  different requirement wording); a "Re-check Gaps" button next to the
  Gaps heading, disabled until both a vacancy and a live document exist;
  `recheckJob`'s busy state folds into the existing ingest/generate busy
  flag so all three stay mutually exclusive, matching `ui/main_window.py`'s
  original convention.
* Verified via the full test suite (132 frontend tests, up from 118 —
  new tests for `collectExcludedEvidenceIds`, `applyDismissed`,
  `useRecheckGapsJob`'s request shape, and `GapsPanel`'s Dismiss/collapse
  behavior), `tsc --noEmit`, `oxlint`. Then a real browser session against
  the actual production candidate profile: generated a CV for a vacancy
  requiring "A/B testing experience for monetization experiments" (fully
  covered — no individual gap shown); excluded the one Experience bullet
  mentioning A/B testing; clicked Re-check Gaps and confirmed a fresh MED
  gap appeared naming exactly that (missing keywords updated to match);
  clicked Dismiss and confirmed it collapsed into "+ 1 dismissed"
  immediately, client-side, no network call; clicked Re-check Gaps again
  (a second real LLM call) and confirmed the same gap did NOT resurface —
  still "+ 1 dismissed" — proving the client-side carry-forward works
  across a genuinely fresh match result, not just a cached one. This
  closes out the full "Phase 18: Re-evaluation loop" scope.

> **Addendum — four issues found using Phase 17/18 on real production
> data.** Four separate reports from the same session, three real bugs
> and one feature gap:
> * The AI-edit highlight/popover could show for a bullet whose
>   `rewritten_text` was byte-identical to `original_text` (the Rewrite
>   Planning stage called for `"enhance"` but the Bullet Rewriting stage
>   ended up not actually changing anything) — nothing to explain or
>   revert, so it shouldn't have looked AI-edited at all.
> * Clicking "Revert to original" left the highlight/trigger in place —
>   `BulletProvenance` is a static, per-generate record, so reverting
>   (which only changes the document's live text) never changed it.
>   `DocumentExperienceSection.tsx`'s `isSubstantiveEdit` fixed both at
>   once by checking the bullet's *current* live text against
>   `original_text`, instead of `action` plus `rewritten_text` vs
>   `original_text`: a "keep"-or-unchanged bullet never highlights, and a
>   reverted one stops highlighting immediately, since its current text
>   now equals the original.
> * A rewritten bullet fabricated a claim beyond the original Evidence
>   ("balance pipelines" became "level balancing pipelines... across
>   levels", inventing a per-level granularity never stated) chasing a
>   `target_keyword` — exactly the keyword-forcing failure
>   `05_rewrite_bullets_v1.md`'s Rules already guarded against in the
>   grammatical case (noun/verb splicing) but not the semantic one.
>   Extended that rule with this failure's shape as a concrete negative
>   example. Prompt-wording changes are inherently probabilistic, not a
>   guaranteed fix — no automated test can assert an LLM won't fabricate,
>   only that the instruction exists.
> * The Unused Evidence panel's "add manually?" nudge had no actual way to
>   add anything — the A4 editor had no "add a new bullet" capability at
>   all (`structuredDocument.ts` only had toggle/reorder/edit-existing-
>   text). Confirmed with the user: two related capabilities, not one —
>   (a) a generic "+ Add Bullet" on any Experience entry, for hand-
>   addressing a Gap the AI didn't cover, and (b) an "Add to Role" button
>   per Unused Evidence item, using the same mechanism. New
>   `structuredDocument.ts::addBullet()` appends a plain, untailored
>   bullet (a hand-typed blank one, or an Unused Evidence item's exact
>   text with its `evidenceId` preserved) to one Experience entry.
>   "Add to Role" only appears for an Unused Evidence item whose
>   `experience_id` matches a role in the *current* assembled CV — a
>   summary/Key-Project-derived item, or one whose role wasn't tailored
>   into this particular CV at all, has no single sensible target and
>   gets no button, not a guess. Since `DocumentEditor` deliberately keeps
>   its `DocumentModel` state un-lifted (Phase 16c), "Add to Role" (owned
>   by a sibling, `UnusedEvidencePanel` via `CvWorkflowView`) reaches it
>   through a `forwardRef`/`useImperativeHandle` escape hatch
>   (`DocumentEditorHandle.addBulletFromEvidence`) rather than lifting
>   that state.
> * Also caught in the process: this session's `tsc --noEmit` sanity
>   checks throughout Phase 17b/18b had been silently checking nothing —
>   the bare command targets the root `tsconfig.json`, which only holds
>   project references with no `include` of its own. `npx tsc --noEmit -p
>   tsconfig.app.json` (or `npm run build`'s real `tsc -b`) is the command
>   that actually type-checks `src/`. Running it correctly for the first
>   time surfaced two real, pre-existing type errors from earlier in this
>   same work: `Gap` test fixtures missing the now-required `status`
>   field, and `CvWorkflowView.tsx` passing a possibly-`undefined`
>   `vacancy.requirements` into `useRecheckGapsJob`. Both fixed alongside
>   this addendum's own changes.
> * Verified: full suite (489 backend / 145 frontend, up from 140 — new
>   tests for the highlight/revert fix, `addBullet`, the `+ Add Bullet`
>   button, `DocumentEditorHandle`, and `UnusedEvidencePanel`'s "Add to
>   Role"), `tsc --noEmit -p tsconfig.app.json`, `oxlint`, `vite build`.
>   Then a real browser session against the actual production candidate
>   profile: generated a CV, clicked "Add to Role" on a real Unused
>   Evidence item and confirmed its exact text landed as a plain
>   (unhighlighted, no AI-edit trigger) bullet under the correct role;
>   clicked a role's "+ Add Bullet" and typed a hand-written bullet
>   directly addressing that generate's real Gap.

## Phase 19 — Write-back, bullet locking, cost instrumentation (done)
* Wire Phase 8.3's `app/graph_writeback.py` into the new UI, extended to
  read from the Phase 16 structured-document edits instead of only the
  flat per-section text fields it handles today.
* Add a `locked: bool` flag on Evidence-backed bullets: when set,
  `BulletRewriteService.rewrite()` skips the LLM call for that bullet and
  reuses the locked text verbatim for any vacancy. This is the direct,
  cheap answer to the cost/latency question behind bullet-variant reuse —
  it falls out of Phase 17's provenance data, needs no embeddings or
  similarity infrastructure.
* Add token-count/latency logging around every LLM call
  (`providers/gemini_provider.py` and future providers) so a future
  decision about fuzzy variant-matching (finding a *similar*, not
  identical, previously-approved phrasing for a new JD) is based on real
  numbers instead of a guess. Explicitly not building that fuzzy-matching
  feature in this stage — see the Non-goals note in
  `docs/PROJECT_CONTEXT.md`.

> **Scoped into five slices: 19.1 cost instrumentation (standalone), then
> 19.2a/19.2b write-back backend/frontend, then 19.3a/19.3b bullet-locking
> backend/frontend.** Same backend-then-frontend split every prior phase
> spanning both has used since Phase 13; cost instrumentation needed no
> split at all (backend-only, no UI, no dependency on the other two).

### Phase 19.1 — Cost instrumentation (done)
`providers/gemini_provider.py::generate_structured()` logs one INFO line
per successful call — model, elapsed seconds, attempt count, and
`prompt_token_count`/`candidates_token_count`/`total_token_count` from the
SDK response's `usage_metadata` — right before returning the validated
result. Deliberately numbers only, per `app/logging_setup.py`'s own
"prompts, generated resume content must never be logged" rule; `usage`
fields are read via `getattr(..., None)` since the SDK doesn't always
populate them. `providers/base.py` gained a docstring note (not an
interface requirement, same as retry-with-backoff isn't) so a future
OpenAI/Ollama/Claude provider (Phase 9) follows the same convention.
Verified via a new test asserting the log line's fields and asserting the
raw prompt/response text never appears in it.

### Phase 19.2a — Write-back backend (done)
Reviewing what "read from the Phase 16 structured-document edits" actually
required turned up that the three existing proposal builders
(`build_summary_proposal`/`build_skills_proposals`/
`build_experience_proposals`) didn't need to change at all: Phase 16c's
`app/cv_markdown.py::render_sections_from_document()` (built for plain
export) already turns an edited `PrintDocument` into the exact flat
`{key: markdown-text}` shape those builders were written against. The only
new code is a thin composer, `app/graph_writeback.py::
build_proposals_from_document(candidate, assembled_experience, document)`,
plus a new bespoke `api/routes/writeback.py` (not the generic
`entity_crud.py` factory — a two-step preview/apply flow, same shape class
as `export.py`'s own hand-written route): stateless `POST .../writeback/
preview` and `POST .../writeback/apply`, mirroring `/export`'s "client
resends its own state" convention. Proposal identity across the two calls
is just an index (`key: "0"`, `"1"`, ...) — both endpoints rebuild the same
deterministic list from the same input.

Two real bugs found while wiring this up against real production data
(`ui/graph_explorer.py`'s desktop write-back had simply never been
exercised together with a proficiency-bearing skill or the web's own
header-line convention before):
* `_parse_header`'s regex required `**Position**` (bold wraps *only*
  Position) — the exact convention `render_experience_section()` (desktop)
  emits, but not what `render_sections_from_document()` (web) emits, which
  bolds the *whole* header line (`**Position — Company (Period)**`).
  Fixed by disambiguating structurally (a line ending in `**` only happens
  when the whole line is wrapped) rather than picking one convention:
  strip the outer wrapper and parse the plain remainder in that case,
  otherwise require the original `**Position**`-only shape unchanged — so
  a desktop line with its bold markers deleted still correctly fails safe
  (returns `None`, facts left alone) exactly as before.
* `build_skills_proposals` matched by comparing the *whole* edited line
  against the candidate's bare skill name — but `_render_grouped_by_
  category` appends `" (Proficiency)"` to a skill's line when set, so any
  candidate skill with a proficiency (e.g. "Roadmapping (Expertise)", a
  real skill on the real committed profile `33e010af`) never matched its
  own stored name and was proposed as a brand-new skill on *every*
  write-back. Fixed with `_split_skill_line()` (inverts the `Name
  (Proficiency)` format) — matching is now name-only, and a genuinely new
  skill's proficiency is passed through to `add_skill(name=, proficiency=)`
  instead of being baked into the name string.

Verified via new API tests (`tests/test_api/test_writeback.py`) and new
`app/graph_writeback.py` tests for both fixes, plus a real browser session
against the real `33e010af` profile: generated a CV, hand-edited the
Summary in the A4 editor, opened Save to Profile, confirmed the preview
correctly showed no phantom skill proposal, applied the summary edit,
confirmed via `GET /candidates/{id}` that it landed, then reverted it via
the API to leave the real profile unchanged.

### Phase 19.2b — Write-back frontend (done)
New `WritebackDialog.tsx` (shadcn `dialog`, newly added — only
`checkbox`/`popover`/etc. existed before), opened from a new "Save to
Profile" button next to `ExportButton` in `CvWorkflowView.tsx`, reading
the same `assembledCv`/`cvDocument` state `ExportButton` already reads.
One `Checkbox` per proposal (pre-checked when enabled, disabled+
`text-destructive` when not, mirroring the desktop `_WritebackDialog`'s
exact treatment), "Save selected" posts the checked keys, `sonner` toast
on success/failure. New `src/api/writeback.ts`
(`useWritebackPreview`/`useWritebackApply`), mirroring `api/export.ts`'s
shape. Verified via new component tests and the same real-browser session
as 19.2a above (one combined click-through covered both).

### Phase 19.3a — Bullet locking backend (done)
`domain.models.Evidence` gained `locked: bool = False` / `locked_text: str
| None = None` (durable — persisted per-candidate, reused for any
vacancy, not a per-generate `TailoredBullet` setting); `db/models.py`'s
`EvidenceRow` gained matching columns via a new Alembic migration
(`270c25eb93a8`, the second migration ever) with an explicit
`server_default=sa.false()` on `locked` — required by hand, not part of
the autogenerate output, since SQLite rejects a `NOT NULL` column added to
a non-empty table without one, and `evidence` already has real rows.
`CandidateService.update_evidence`'s explicit row-field assignment
extended to the two new fields; **no new route code** —
`api/routes/entity_crud.py`'s update-body factory already derives from
`Evidence.model_fields`, so `PUT .../evidence/{id}` accepted `{locked,
locked_text}` for free (same zero-new-route precedent as Phase 15a).

New `app/bullet_locking.py` (pure functions, no LLM call, same shape as
`app/bullet_provenance.py`): `partition_locked_evidence()` splits Evidence
into (unlocked, locked) — "locked" requires both `locked=True` and a real
`experience_id` (unlinked Evidence can't back a bullet at all, same
precedent `app/bullet_provenance.py` already set); `splice_locked_
bullets()` appends a `TailoredBullet` per locked item back into the
matching `TailoredExperience` after Bullet Rewriting.

`app/pipeline.py::run_cv_generation` wires this in: Matching still
receives the *full*, unpartitioned `evidence` (a locked bullet is still
real Gap-analysis signal, no cost reason to hide it there); Rewrite
Planning and Bullet Rewriting receive `unlocked_evidence` only — the
actual cost/latency saving, since there's nothing to plan or generate for
text that's forced verbatim either way; `splice_locked_bullets()` runs
right before `assemble_cv`. The one real bug this needed to guard against,
found by reading `app/cv_assembler.py::assemble_cv` (`if tailored is None:
continue`) rather than observed in production: a role whose *entire*
evidence set is locked never appears in the Bullet Rewriting response at
all (nothing left to say about it), so without `splice_locked_bullets`
creating a `TailoredExperience` for it when none exists, that role would
silently vanish from the assembled CV — same class of bug as the Phase 5
maternity-leave-gap incident.

`app/bullet_provenance.py::build_report` already fell back to
`action="keep", rationale=None` when `plan.actions` has no entry for an
evidence_id — which is now *always* true for a locked item (excluded from
planning by design) as well as the pre-existing "shouldn't normally
happen" case, indistinguishable from a real "keep" decision. Fixed by
adding `BulletProvenance.locked: bool = False`, set from `source.locked` —
orthogonal to `action`, not a fifth value.

Verified via new tests (`tests/test_app/test_bullet_locking.py`, new
`run_cv_generation` cases including the fully-locked-role case, a
`CandidateService.update_evidence` round-trip test) — full suite 512
passed, up from 489.

### Phase 19.3b — Bullet locking frontend (done)
First version built the Lock/Unlock toggle into `DocumentExperienceSection.
tsx`'s `BulletRow` (the A4 CV editor), rendered for any evidence-linked
bullet once a candidate is selected. Calls
`useEntityMutations<Evidence>(candidateId, "evidence").update` with
`{locked: true, locked_text: <current text>}` / `{locked: false}` — no
backend changes needed, confirming 19.3a's "zero new route code" claim in
practice.

A real bug found via a real regenerate against the real `33e010af`
profile, not caught by any test until added after the fact: since
`provenance` is a static per-generate snapshot, not a live query, a lock/
unlock click needed local optimistic state to make the icon flip
immediately — the first attempt seeded a bare `useState(provenance?.
locked)` once per mount. But `structuredDocument.ts::
buildExperienceBullets`'s bullet ids are *positional*
(`${entryId}-bullet-${index}`), not evidence-keyed — a fresh generate that
reorders bullets can land a *different* evidenceId on the same positional
id, and React reuses the existing `BulletRow` instance instead of
remounting it, so the stale `locked` state from the previous generate
stuck to whichever bullet happened to occupy that slot next. Reproduced
live: locked a real bullet, generated for a second vacancy (confirmed
correct), generated for a *third*, and the lock icon showed up on a
completely unrelated bullet. A `useEffect` resyncing `locked` from
`provenance?.locked` whenever `evidenceId` or that value changes fixed the
symptom (a same-session click stays optimistic; a genuine identity change
on remount reuse no longer carries stale state).

> **Addendum — relocated to the Profile Explorer, replacing the A4-editor
> version entirely.** Fixing the bug above didn't remove its root cause:
> the A4 editor's bullet identity is fundamentally positional, not
> evidence-keyed, which is exactly the kind of state a *durable*,
> per-candidate fact like `locked`/`locked_text` doesn't belong next to.
> Raised directly and confirmed with the user: the Profile Explorer's
> `ExperienceEvidencePanel.tsx` (the "Evidence & skill links" panel) is
> the better home — it's the canonical, cross-generation view of Evidence,
> already keyed by the real, stable `Evidence.id`, and already rendered
> off `ProfileView`'s live `useEvidence(candidateId)` query rather than a
> per-generate snapshot. `useEntityMutations`'s existing invalidation
> (`["candidates", candidateId]`, a prefix `useEvidence`'s own query key
> extends) means the panel needs **no local state at all** — a lock/unlock
> click just mutates and lets the query refetch, eliminating the entire
> staleness/positional-identity bug class rather than working around it.
>
> The A4 editor's Lock/Unlock icon, its `useState`/`useEffect` resync
> pair, and the `candidateId`/`evidenceId` prop threading through
> `DocumentEditor.tsx`/`DocumentExperienceSection.tsx` were removed
> entirely — `isSubstantiveEdit`'s `!provenance.locked` guard was kept
> (still correct and still needed: a locked bullet must never show the
> AI-edit sparkle, regardless of which screen you locked it from).
> `ExperienceEvidencePanel.tsx` gained a new required `candidateId` prop
> and a Lock/Unlock icon + popover per Evidence row (mirroring the removed
> A4-editor popover's copy), wired via `ExperienceSection.tsx` (which
> already had `candidateId` in scope). Verified via a real browser session
> against the real `33e010af` profile: locked a real Evidence item from
> the Profile Explorer, confirmed the icon flipped immediately off the
> query refetch (no manual reload, no local state to manage), confirmed
> `locked_text` was saved correctly via a direct API check, unlocked it
> the same way, and restored the row's exact original state (`locked_text:
> null`) afterward to leave the real profile unchanged.

Verified via new/updated component tests (`ExperienceEvidencePanel.test.
tsx` gained the lock/unlock cases; `DocumentExperienceSection.test.tsx`
lost the A4-editor lock tests but kept one pinning the `!provenance.locked`
sparkle-suppression guard) — frontend suite 152 passed — `tsc --noEmit -p
tsconfig.app.json`, `oxlint`, `vite build`, plus the real browser session
described in the addendum above. Separately (unrelated to the app): a
JD-textarea edit via `ctrl+a` + type during this same verification effort
appended instead of replacing (a browser-automation artifact, not a
product bug), which briefly concatenated two vacancies into one Gemini
call and produced a `ValidationError` from a malformed
`AnalyzeVacancyResponse` — worth recording only because it looked like a
real failure until traced back to the test harness, not the app. This
closes out the full "Phase 19: write-back, bullet locking, cost
instrumentation" scope.

> **Addendum — locked bullets were always sorted dead last, regardless of
> actual relevance.** Reported directly, from a real screenshot: a role's
> AI-tailored bullets all showed the sparkle-edit highlight, followed by
> two unhighlighted (locked) bullets always at the very bottom of that
> role/project's list — `app/bullet_locking.py::splice_locked_bullets`
> simply appended each locked bullet to whatever Bullet Rewriting already
> produced. Backwards: locking is something a person does specifically to
> a wording they've already approved, i.e. usually their *strongest*
> content, not their weakest.
> * `app/pipeline.py::run_cv_generation`: Rewrite Planning now receives the
>   full, unpartitioned `evidence` (previously `unlocked_evidence` only) —
>   its `RewritePlan.priority_order` ("Evidence ids, most important
>   first") is the only stage that ever ranks importance at all, and it's
>   cheap enough (short structured output, not full prose) that including
>   locked evidence costs little. Bullet Rewriting still only receives
>   `unlocked_evidence` — the actual cost/latency saving stays intact. Its
>   `plan` is now a filtered copy (`actions` limited to unlocked evidence
>   ids only) rather than the full plan, since `05_rewrite_bullets_v1.md`
>   produces one bullet per Evidence item it's actually given — an action
>   referencing evidence it has no text for was an unforced, avoidable way
>   to risk confusing it.
> * `splice_locked_bullets` gained a `priority_order` parameter: after
>   appending each locked bullet, it stable-sorts the *whole* affected
>   role's bullet list (locked and LLM-produced together) by
>   `priority_order` rank. Bullets missing from `priority_order` (should
>   no longer normally happen, but kept as a fallback) sort last, stable
>   relative to each other — backward-compatible with every existing
>   caller that doesn't pass a `priority_order` at all (empty rank map
>   makes every bullet compare equal, so Python's stable sort leaves the
>   prior append order untouched). Sorting the flat list this way never
>   breaks project-name grouping, since `structuredDocument.ts::
>   buildExperienceBullets` already gathers a project's bullets together
>   under one subheading regardless of their raw list position.
> * Verified via two new unit tests (Planning/Rewriting each see the right
>   evidence subset and filtered plan; a locked bullet ranked *above* an
>   unlocked one by `priority_order` lands first, not last) plus a live
>   regenerate against the real `33e010af` profile: locked a real Evidence
>   item, generated a real CV for a vacancy with zero topical overlap with
>   that item's content (confirmed via the real `MatchResult` — no match,
>   no gap referenced it), and the bullet legitimately still sorted last —
>   the correct, relevance-driven outcome for genuinely irrelevant locked
>   content, not the previous unconditional append. Unlocked and restored
>   the real profile's evidence to its exact prior state afterward. Full
>   suite: 513 backend passed, up from 512.

## Phase 20 — Advisory checks + full app flow
* Deterministic heuristics over the assembled document (estimated page
  count, bullets-per-role outliers, empty sections) surfaced as advisory
  chips. LLM-assisted advice ("this bullet is vague") is an optional
  stretch once the heuristic version ships, not required for this phase.
* New `CVDraft` entity (candidate + vacancy + generated document,
  persisted) — "previous CV drafts linked to a JD" doesn't exist as a
  stored concept today, only ephemeral pipeline output does; this is a
  genuinely new domain object, not a UI-only change (needs a migration in
  Phase 13's SQLite schema, added here once the schema it stores — Phase
  16's structured document — actually exists).
* Full routed flow (React Router): Candidate picker/ingest → profile +
  cross-links (Phase 15) → JD picker/insert + generate → preview/edit/
  export (Phases 16-19), as distinct screens instead of one dense window.

> **Scoped slicing (confirmed with the user):** 20.1 advisory checks
> (frontend-only, fully independent) ships first; 20.2 CVDraft backend
> second; 20.3 the routed flow, built directly on CVDraft persistence,
> last. The key decision behind that order: the routed flow's biggest
> open question was how generate-result state (`assembledCv`/`vacancy`/
> `matchResult`/`cvDocument`, all local `useState` in `CvWorkflowView.tsx`
> today) survives navigating between the new JD/Generate screen and the
> Preview/Edit/Export screen — a lifted-state layout route vs. persisting
> through CVDraft itself. Confirmed with the user: persist through
> CVDraft. Every successful generate creates a real `CVDraft` row, the
> Preview screen loads it by id from the URL, and edits autosave back to
> that same row. This directly satisfies the CVDraft bullet too (listing a
> candidate's drafts *is* "previous CV drafts linked to a JD"), merging
> two of this phase's three bullets into one mechanism — and stays out of
> the still-excluded "Version history" non-goal
> (`docs/PROJECT_CONTEXT.md`) because it always overwrites *one* row per
> generate-and-refine session, never keeping a history of past states.
> CVDraft's backend therefore has no separate frontend slice of its own —
> its UI *is* 20.3's Generate/Preview screens.

### Phase 20.1 — Advisory checks (done)
All three heuristics ("estimated page count, bullets-per-role outliers,
empty sections") turned out to need zero backend involvement — they're
cheap, deterministic computations over data already in the browser (the
live `DocumentModel`, `frontend/src/lib/structuredDocument.ts`), so this
slice is frontend-only.
* New `frontend/src/lib/advisories.ts`: `estimatePageCount` (sums an
  approximate line count for every *included* block — headings/
  subheadings = 1 line, body text = `ceil(length / charsPerLine)` — across
  included sections, divided by an approximate lines-per-A4-page constant;
  explicitly an estimate, not a promise of the real Playwright-rendered
  page count, since the on-screen A4 editor is a single continuous
  scrollable box, not really paginated — real pagination only happens
  inside Playwright during templated export, Phase 16b), `findBulletCount
  Outliers` (flags a non-gap Experience entry with zero included bullets,
  or with a bullet count notably above the other roles' average — a
  plain, explainable threshold, not a statistical model), and
  `findEmptySections` (an included section with zero included entries —
  the exact same condition `app/cv_markdown.py::render_sections_from_
  document` already silently skips on export; this surfaces it as a chip
  instead of a silent omission). `buildAdvisoryChips` combines all three
  into one ordered list (page count first).
* New `AdvisoryChips.tsx` — read-only, same "informational, never
  exported" treatment as `GapsPanel`/`UnusedEvidencePanel`; recomputed on
  every render off the live `cvDocument` (cheap enough to skip
  memoization). Rendered as small rounded-pill spans rather than pulling
  in a new shadcn `Badge` component for something this simple. Wired into
  `CvWorkflowView.tsx` next to `DocumentEditor`, ahead of 20.3's screen
  split landing.
* Verified via 17 new unit/component tests (`advisories.test.ts`,
  `AdvisoryChips.test.tsx`) — full frontend suite 169 passed, up from 152
  — `tsc --noEmit -p tsconfig.app.json`, `oxlint`, `vite build`. Then a
  real browser session against the real `33e010af` profile: generated a
  CV for a genuinely well-matched vacancy and confirmed exactly 5 chips
  rendered — `~2 pages (estimate)` first, then four correct empty-section
  flags (Publications & Talks, Volunteer Experience, Certifications,
  Awards & Honors — sections this candidate's profile has no data for)
  and, correctly, no bullet-count-outlier chip (this profile's real
  per-role bullet counts are fairly even).

### Phase 20.2 — CVDraft backend (done)
New `domain.models.CVDraft` (`id`, `candidate_id`, `vacancy`,
`assembled_cv`, `document`, `created_at`, `updated_at`) and
`CVDraftSummary` (listing shape — no full blobs); new `db.models.
CVDraftRow` (own table, composite `(candidate_id, id)` PK — same
collision-safety precedent as `EvidenceRow`) plus a new Alembic migration
(third, after `c0c0928f0aa2`/`270c25eb93a8`).

`CandidateService` gained `add_cv_draft`/`update_cv_draft` (generic
`**fields` merge, same shape as `update_evidence` — this is what makes
20.3's debounced autosave a plain `PUT {document: ...}` with no new
mechanism)/`remove_cv_draft`/`list_cv_drafts`/`get_cv_draft`.
`add_cv_draft` is deliberately the *only* creation path (no separate
"Save Draft" action) — see its own docstring: one row per generate, not
per edit, is what keeps this from drifting into the still-excluded
"Version history" non-goal.

`CVDraft` is registered in `api/routes/entity_crud.py`'s
`_ENTITY_REGISTRATIONS` for `POST`/`PUT`/`DELETE` — new
`api/routes/cv_drafts.py` hand-writes the two `GET`s the factory has never
provided for any entity (list summaries, get one full), mirroring
`candidates.py`'s own hand-written bulk-Evidence-`GET` precedent.

**A real, latent bug in the generic factory, found and fixed in the
process — the first entity registered whose create/update fields include
a full nested Pydantic model, not just flat scalars.** `create_entity`/
`update_entity` (`api/routes/entity_crud.py`) built their kwargs via
`body.model_dump()`, which recursively flattens *every* nested field into
a plain dict — silently fine for the 12 entities registered before this
one, all flat-scalar-only, but `add_cv_draft(vacancy: Vacancy, ...)`
received a `dict` where it needed a real `Vacancy` instance, and promptly
broke calling `.model_dump()` on it. Fixed by building kwargs via
`getattr(body, name)` per field instead (`type(body).model_fields` for
create, `body.model_fields_set` for update — preserving the existing
`exclude_unset` partial-patch semantics) — preserves real nested model
instances, byte-identical behavior for every existing scalar-only entity.
Considered writing bespoke POST/PUT/DELETE routes for CVDraft instead (the
precedent Experience Projects already set for "the one nested case isn't
pushed through this factory") but fixing the factory directly is more
surgical, keeps the "zero new route code" claim genuinely true, and
benefits any future entity with the same shape.

Verified via 13 new tests (`test_candidate_service.py`: CRUD round-trip
including partial-update-via-autosave shape, candidate-scoping,
missing-id errors; `test_cv_drafts.py`: the same through the real routes,
confirming list returns summaries not full blobs) — full backend suite
526 passed, up from 513. A real SQLite round-trip bug caught along the
way: `CVDraftRow.created_at`/`.updated_at` came back *naive* (SQLite's
`DateTime` column has no native timezone storage, so SQLAlchemy silently
drops tzinfo on read) even though every write goes through a tz-aware
`datetime.now(timezone.utc)` — harmless for `CandidateRow`/`EvidenceRow`,
whose timestamps never leave the storage layer, but `CVDraft.created_at`/
`.updated_at` are part of the domain model surfaced to the API. Fixed
with a small `_as_utc()` helper re-attaching UTC on read. Then a real
end-to-end smoke test against the live `--reload` server and the real
`33e010af` profile (not the fake-provider test DB): applied the migration,
created a real draft, listed it, fetched it by id, deleted it, and
confirmed the list was empty again afterward.

### Phase 20.3 — Full routed flow (done)
New dependency `react-router-dom` (nothing routed existed before —
`App.tsx` was a manual `useState<"workflow"|"profile">` toggle;
`main.tsx`'s `/print/{sessionId}` branch is a separate, chrome-free render
tree that never mounted `<App>` at all and needed no changes).

Routes, all under `App.tsx`'s `<Router>`: `/` (`CandidateHomeScreen` —
candidate picker + Ingest, moved here from `CvWorkflowView`'s left column,
since the phase's own screen breakdown puts ingest on screen 1, not
alongside JD/generate) and `/candidates/:candidateId/*`
(`CandidateWorkflowLayout` — candidate identity from the URL param, a
small Profile/Generate nav, `<CandidatePicker>` to switch candidates
without returning to `/`, and an `<Outlet/>`) nesting `profile`
(`ProfileView`, unchanged — just fed `candidateId` from `useParams()`
instead of a prop), `generate` (new `GenerateScreen`), and
`drafts/:draftId` (new `DraftScreen`). `CvWorkflowView.tsx` itself is
deleted — its content is fully redistributed between the two new screens.

**`GenerateScreen`** never holds generate-result state — a successful
generate builds the initial `DocumentModel` (`buildDocumentFromAssembledCv`,
reused as-is), `POST`s a new `CVDraft`, and navigates straight to
`drafts/:newDraftId`. Also lists the candidate's existing drafts
(`GET .../drafts`) to reopen instead of generating fresh — the concrete
form Phase 20's "previous CV drafts linked to a JD" bullet takes. Every
Generate click always creates a *new* draft, never overwrites an existing
one, so "new generate = new session" stays unambiguous.

**`DraftScreen`** loads its draft on mount and autosaves edits back to
that same row ~1.5s after the last change (new `lib/useDebouncedEffect.ts`
— no debounce library existed, and nothing here needs one — driving a
plain partial `PUT {document: ...}`, the same `update_cv_draft` shape
20.2 built for exactly this). `DocumentEditor` gained a new
`initialDocument` prop for this: it used to unconditionally rebuild its
`DocumentModel` from `assembledCv` on every prop change; reopening a
draft needs to seed from the *already-edited* document instead, exactly
once per mount (a `useRef` guard, not a dependency on the prop's own
identity) — so a background query refetch's new object reference never
resets in-progress edits mid-session.

**A meaningful gap identified and closed before it shipped, not
discovered afterward:** since `CVDraft` deliberately never persists
`match_result`/`provenance` (see its own docstring), a naive "just fetch
the draft" implementation would make the Gaps/Unused-Evidence/AI-edit-
sparkle UI go blank *immediately* after every single generate too — not
just on a later reopen — since `GenerateScreen` navigates to the draft
right away rather than ever holding that data itself. Fixed by having
`GenerateScreen` pass `match_result`/`provenance` through React Router's
`navigate(path, {state})` on that *one* initial navigation only —
`DraftScreen` reads `location.state` for them, falling back to `null`.
This is genuinely ephemeral (browser session-history state, not app
state) and exactly matches the confirmed design: full AI-edit
transparency immediately after generating, gracefully degraded (Gaps
recoverable via Phase 18's recheck endpoint, which only needs
`vacancy.requirements` + the document; Unused Evidence/AI-edit sparkle
simply unavailable, since `BulletProvenanceReport` has no recheck-only
equivalent) on any later direct visit — a refresh, or reopening from
"Your drafts."

Verified via 12 new tests across 4 screens (`CandidateHomeScreen`,
`CandidateWorkflowLayout`, `GenerateScreen`, `DraftScreen`, all
`MemoryRouter`-based) plus `useDebouncedEffect.test.ts` (4 tests, fake
timers) and 3 new `DocumentEditor.test.tsx` cases for `initialDocument` —
frontend suite 187 passed, up from 152. Interactive Radix `Select`
open/click interactions were avoided throughout (jsdom's missing
`hasPointerCapture`, the same limitation `ExportButton.test.tsx`/
`DocumentEditor.test.tsx` already established a precedent for working
around). `tsc --noEmit -p tsconfig.app.json`, `oxlint`, `vite build`.

Then a full real-browser session against the real `33e010af` profile,
covering every scenario the design above depends on: ingest/select on
`/`; generated a real CV for a genuinely relevant vacancy on
`/candidates/:id/generate`, confirming a `CVDraft` was created and the
app navigated straight to it, with Gaps/Unused Evidence/AI-edit
highlighting all populated (proving the `location.state` handoff);
hand-edited a bullet and confirmed the debounced autosave `PUT` fired and
persisted server-side; opened the exact same draft URL in a **brand-new
browser tab** (not just a same-tab reload, which would have silently
reused the browser's already-set `history.state` and defeated the test)
and confirmed the edit survived while Unused Evidence correctly rendered
nothing and Gaps rendered empty-but-present; clicked Re-check Gaps and
confirmed Gaps repopulated for real; exported successfully from the
reopened draft; then deleted the test draft via the API, leaving the real
profile's draft list empty again. This closes out the full "Phase 20:
advisory checks + full app flow" scope, and with it Version 2 of
`docs/PROJECT_CONTEXT.md`'s Product Stages.

> **Addendum — two real bugs found from real exported output.** Reported
> directly, from an actual exported document:
> * **A literal "[GAP]" showed up in exported CVs.**
>   `structuredDocument.ts::summarizeAssembledExperience` appended
>   `" [GAP]"` to a career-gap entry's display text — a helpful on-screen
>   hint originally, but that same text is `DocumentBlock.text`, which
>   flows verbatim into the real exported document
>   (`app/cv_markdown.py::render_sections_from_document`) and into
>   write-back proposals. Root cause: gap status was being encoded twice —
>   once structurally (`locked`, already driving italic styling and a
>   disabled checkbox) and once as literal text — and only the text form
>   leaked downstream. Fixed by removing the bracket suffix entirely and
>   relying on `locked` alone, matching `ui/main_window.py`'s own
>   export (`render_experience_section`), which has only ever used italics
>   for this, no bracket tag, since Phase 6. `ExperienceSection.tsx`'s own
>   `[GAP]` (Profile Explorer's read-only row summary, never exported) and
>   `ui/graph_explorer.py`'s (desktop, also display-only) were
>   deliberately left untouched — same reasoning, different consumer.
>   Verified live against the real `33e010af` profile's actual Maternity
>   Leave gap entry: confirmed the built `DocumentBlock.text` is now
>   `"Maternity leave — Playkot (Mar 2023 Mar 2024)"`, `locked: true`, no
>   bracket. 5 existing tests updated for the new convention
>   (`structuredDocument.test.ts`, `DocumentExperienceSection.test.tsx`,
>   `PrintExperienceSection.test.tsx`).
> * **A section heading could land alone at the bottom of a page**, with
>   its real content starting fresh on the next page — reported
>   specifically for Skills, and confirmed as a gap in not one but *two*
>   renderers, found in two passes:
>   * `app/cv_docx.py` (`render_docx` and `render_templated_docx`) — Phase
>     16c's `break-after: avoid-page` fix for this exact symptom only ever
>     covered the on-screen/Playwright-PDF path's CSS; python-docx has no
>     CSS at all. Fixed with `heading.paragraph_format.keep_with_next =
>     True` on every section heading — the direct python-docx equivalent
>     of "keep me on the same page as whatever follows." Two new tests
>     confirm the flag is set on a real rendered heading paragraph, for
>     both the plain and templated DOCX paths.
>   * `app/cv_pdf.py` (`render_pdf`) — checked in a second pass after the
>     DOCX fix, since this is the *default* export format ("None
>     (ATS-safe)"), the most likely one actually reported, and a third,
>     completely different layout engine (reportlab's Platypus flowables)
>     with its own gap: `SimpleDocTemplate.build()` breaks pages purely by
>     available space, with no equivalent to either CSS's `break-after` or
>     python-docx's `keep_with_next`. Fixed with reportlab's own
>     `KeepTogether([heading, first_line])` — deliberately just the
>     heading plus its first line, not the whole section (wrapping the
>     whole thing would trade a stranded-heading bug for a worse one: a
>     long section like Experience jumping to a new page as one atomic
>     block instead of flowing naturally — the same reasoning the DOCX fix
>     and Phase 16c's original CSS fix both already settled on). One new
>     unit test (intercepting `SimpleDocTemplate.build`'s flowables list to
>     confirm the `KeepTogether` grouping) plus a real multi-page stress
>     test via a live `/export` call — mirroring Phase 16c's own "real
>     multi-page stress test" precedent — confirmed a genuinely 3-page PDF
>     puts a "Skills" heading and its first skill on the same page.
>
> Separately: the `"[E2E TEST EDIT]"` text in the same report turned out
> to be a real file downloaded during this project's own Phase 20.3
> browser-based verification (clicking Export CV for real, as
> `docs/development_plan.md`'s own verification convention requires,
> triggers a genuine file download, independent of the server-side test
> data that was cleaned up afterward) — not a code bug, and nothing to
> fix, but a reminder that a verification session's real downloads land
> in the same Downloads folder as everything else. A reported
> `"Roadmapping (Expertise)"` skill name was investigated the same way:
> unreproducible from the current, real `33e010af` profile (confirmed via
> both the live database and a fresh real generate — every skill's
> `category`/`proficiency` is `None`), so also most likely a stale
> artifact from an earlier test export rather than a live issue, though
> it does reflect a known, pre-existing, probabilistic risk documented
> since Phase 18's addendum: the LLM occasionally doesn't follow
> `05_rewrite_bullets_v1.md`'s "do not alter any name's spelling" rule
> exactly. Not re-fixed here for lack of a reproducible case — worth
> revisiting with a concrete example if it recurs.
> Full suite: 529 backend passed (up from 526 — 3 new pagination tests
> across the DOCX and PDF renderers), 187 frontend passed (unchanged —
> this addendum only touched existing tests' fixtures, no new frontend
> tests).

> **Addendum — three more UX gaps found using the Profile Explorer.**
> Reported directly, in three separate passes:
> * **`ProfileHeader.tsx`** (Name/Headline/Summary/Seeking) was always
>   shown as an open, editable form — the one Profile Explorer section
>   that never matched the read-only-preview-plus-Edit-button convention
>   every other section (`EntitySection.tsx`, `ExperienceSection.tsx`)
>   already used, and easy to misread as "these fields aren't saved yet."
>   Rebuilt read-only-by-default with a single "Edit" button in the
>   `CardHeader` (via a new `CardAction` — no `+Add`/Delete affordance
>   needed, since it's a singleton record, not a list); Save/Cancel now
>   live inside the form. 5 tests updated/added.
> * **`EntitySection.tsx`** (Skills, Technologies, Languages,
>   Certifications, Awards, Contacts, Projects, Publications, Portfolio
>   Links, Volunteer Experience, Education — all 11 "simple" entity types)
>   only ever let one row be edited at a time, making a multi-item change
>   (e.g. adding proficiency to several skills) a slow one-row-at-a-time
>   Edit/Save loop. Reworked into one section-wide "Edit" toggle that
>   turns every row editable at once, with a single Save writing only the
>   rows that actually changed (a per-row dirty check against the
>   original values) — verified live to fire exactly one `PUT` when only
>   one of nine real skills changed. Delete (per row) and "+ Add X" stay
>   outside edit mode entirely, available immediately regardless of
>   whether the section is mid-bulk-edit — confirmed as the explicit
>   requirement, not just a nice-to-have. A real bug caught before it
>   shipped: the first version reused the bulk-edit form-values object for
>   each row's DOM `id`/`label` association, which isn't keyed by entity
>   id — every row would have collided on the same id. Fixed by threading
>   the entity's real id through explicitly. 6 new tests.
> * **`BulletRowsEditor.tsx`** (Experience's Achievements/Responsibilities
>   list) had no reorder capability at all, in any role — the original
>   Phase 15b-ii design's own comment said so explicitly ("rows are only
>   appended/edited/removed, never reordered"), unlike the A4 CV editor's
>   own bullet lists, which have supported drag-reorder via `@dnd-kit`
>   since Phase 16a. Added the identical `DndContext`/`SortableContext`/
>   `useSortable` mechanism here. `BulletRow` gained a client-side-only
>   `id` (never sent to the backend — `toExperienceRequestBody` never
>   reads it) purely so dnd-kit has a stable identity to track across
>   reorders, generated wherever a row is created (`ExperienceSection.tsx`'s
>   `experienceToValues` flatten step, and this file's own `+ Add`).
>   Reordering the flat list is sufficient on its own to reorder the saved
>   output too: `toExperienceRequestBody`'s per-project/role-level split
>   already preserves relative order via a plain `.filter()`. The actual
>   move logic is extracted into a standalone `reorderBulletRows(rows,
>   fromId, toId)` function, tested directly — jsdom (and, it turned out,
>   this session's own sandboxed browser tooling) can't reliably simulate
>   a real drag gesture, the same limitation `structuredDocument.ts`'s
>   `reorderEntries`/`reorderBullets` already established this precedent
>   for. 4 new tests; drag handles confirmed rendered correctly against
>   the real `33e010af` profile (7 handles for a real role's bullets), but
>   the actual mouse-drag gesture itself wasn't mechanically verified this
>   pass — flagged honestly rather than claimed, on the strength of this
>   being the exact mechanism already proven live for the A4 editor.
>
> Full suite: 529 backend passed (unchanged, no backend touched), 199
> frontend passed (up from 187).

> **Addendum — bullet reorder confirmed working, then extended to all 11
> simple entity sections.** Follow-up report: "It works in Experience
> section, let's add the same in other sections: skills, tools, education,
> languages, certifications, awards, contacts, key projects, publications,
> portfolio, volunteer experience" — the previous addendum's honest
> "not mechanically verified" caveat for `BulletRowsEditor` turned out
> fine in the real app, and the same drag-reorder affordance was missing
> from every `EntitySection.tsx`-backed section too.
> * **Backend**: one generic `CandidateService.reorder_entities(list_field,
>   ordered_ids)` — same "factory, not eleven near-duplicates" precedent
>   `entity_crud.py`'s create/update/remove routes already set. Any
>   existing item missing from `ordered_ids` (stale client, a concurrent
>   add racing the request) is appended at the end in its prior relative
>   order rather than dropped, mirroring `cv_assembler.py`'s
>   `_rank_by_category` fail-safe for an unrecognized name. Wired via a new
>   optional `list_field` param on `register_entity_crud_routes` —
>   registered for all 11 simple entities, deliberately *not* for
>   `experience` (its own nested reorder already lives inside
>   `ExperienceForm.tsx`'s atomic role save). 3 new service-level tests
>   plus a parametrized `test_reorder_round_trip` sweep across all 11
>   reorderable entities in `test_entity_crud.py`, plus one test
>   confirming `experience` has no reorder route (405, not 404 — FastAPI
>   matches the existing `PUT .../experience/{item_id}` path first and
>   rejects the method).
> * **Frontend**: `EntitySection.tsx` gained the identical
>   `DndContext`/`SortableContext`/`useSortable` mechanism
>   `BulletRowsEditor.tsx` already used, scoped to bulk-edit mode only
>   (matching that mode's existing convention — Delete and "+ Add" stay
>   available outside edit mode, drag handles only appear once "Edit" is
>   clicked). New `reorderEntityItems(items, fromId, toId)` pure function,
>   unit-tested directly rather than simulating a drag gesture (same
>   established precedent). New `reorder` mutation on
>   `useEntityMutations`, posting to the new `.../reorder` route and
>   invalidating the candidate query on success.
> * Verified live against the real `33e010af` profile: entered Skills'
>   edit mode and confirmed 9 drag handles render (one per real skill,
>   `aria-label="Drag to reorder skill"`), then round-tripped an actual
>   reorder directly through `POST /candidates/33e010af/skills/reorder`
>   (swapped the first two skills, confirmed the response and a follow-up
>   `GET` both reflected the new order), then reverted it back to the
>   original order via a second reorder call — leaving the real profile's
>   data unchanged.
>
> Full suite: 544 backend passed (up from 529), 203 frontend passed (up
> from 199).

> **Addendum — unified draggable-row styling, and a real concurrent-save
> data-loss bug found while verifying it.**
> * **Visual unification.** Reported directly, with a reference screenshot
>   of what a "unified" draggable row should look like: grip handle, fields,
>   and delete control all inside one bordered card, not floating loosely
>   next to each other. `EntitySection.tsx`'s `SortableEntityRow` and
>   `BulletRowsEditor.tsx`'s `BulletRowItem` both gained a `rounded-lg
>   border bg-card p-2` wrapper (the same treatment `EntityForm`'s "+ Add"
>   box already used), and their Delete/Remove buttons became icon-only
>   (`Trash2`, `variant="ghost"`, `size="icon-sm"`) to fit the tighter card
>   — kept as `aria-label="Delete"`/`"Remove"` specifically so the existing
>   `getByRole("button", { name: "Delete" })`-style tests needed no changes.
> * **Real bug found while verifying the above live**: editing several
>   different Skills rows in one bulk-edit session and clicking Save
>   silently lost some of the edits — only one of them ended up persisted.
>   Root cause: `EntitySection.tsx`'s `handleSaveAll` fired one PUT per
>   changed row through `Promise.all`, but every one of these 11 entity
>   types lives inside the *same* whole-`Candidate` JSON blob row
>   (`CandidateRow.data`) — `CandidateService.update_X` is an independent
>   read-mutate-write-the-whole-blob round trip
>   (`_require_existing()`/`_save()`) with no locking between calls. Two
>   such calls in flight at once race: the second request's read (taken
>   before the first request's write had landed) still reflects
>   pre-first-edit data, so when it saves the whole blob back it silently
>   clobbers the first edit — a classic lost-update race, confirmed live by
>   editing two real skills at once and watching the backend's own GET
>   response show only one edit had survived. Fixed by awaiting each
>   `update.mutateAsync` one at a time instead of `Promise.all`-ing them —
>   every write is fully persisted (a round trip completed) before the next
>   request reads, closing the race. Scoped to `EntitySection.tsx` only:
>   it's the only place in the frontend that ever fires concurrent writes
>   for the same candidate (grepped for other `Promise.all` call sites —
>   none), so this one fix covers all 11 entity sections at once, same as
>   every other EntitySection-rooted fix this session. New regression test
>   asserts the second row's PUT doesn't fire until the first one's
>   response has resolved. The real `33e010af` profile's Skills list had
>   actually been left in a corrupted state by this exact bug during
>   testing (`"Team Management lala"`, `"Roadmapping EDIT2"`) — restored to
>   `"Team Management"`/`"Roadmapping"` via the now-fixed bulk-save flow
>   itself, which also served as the live confirmation that two
>   simultaneous edits now both persist correctly.
>
> Full suite: 544 backend passed (unchanged, no backend touched), 204
> frontend passed (up from 203).

## Phase 21 — Skills/Technologies as category-header groups

Requested directly: make the Skills/Technologies editor look like
Experience's role → nested-bullets structure — a flat, drag-orderable
list where some rows are plain skills and some are "category header" rows,
and a skill's effective category is whichever header is nearest above it
(no header above it = no category). This turns the editor into a live,
editable preview of the exact grouping `app/cv_assembler.py:
_rank_by_category` already computes for export, instead of a free-text
`category` field per row with no visual relationship to how the CV
actually renders. Applied to both Skills and Technologies, kept in
lockstep as every category-related change has been since Phase 12.3.

* **`Skill`/`Technology` gain `is_category_header: bool = False`**
  (`domain/models.py`). A header is a normal entry in the same list —
  `name` holds the label, `category`/`proficiency`/`evidence_ids` stay
  unused — so it's draggable/CRUD'able through the exact same generic
  routes as any other skill, zero new backend route code.
  `add_skill()`/`add_technology()` gained the matching parameter
  (`app/candidate_service.py`) since `entity_crud.py`'s factory builds the
  create-request model straight from that signature.
* **Category becomes derived, not directly edited.** The "Category" input
  is gone from both the per-row bulk-edit form and the "+ Add" form for
  Skills/Technologies (`lib/entityConfigs.ts` — `category` removed from
  `fields`, a new `categoryHeaders: true` flag added). Whenever the list's
  structure changes, `EntitySection.tsx`'s new `deriveCategories`/
  `groupItemsByHeader` (pure functions, unit-tested directly per this
  session's established "don't simulate drag, test the logic" precedent)
  recompute every skill's effective category and a `useEffect` PUTs
  (sequentially — same race-condition reasoning as the bulk-save fix
  above) any skill whose derived category actually changed. Naturally
  idempotent: once a write lands, the next `items` update finds no diff.
* **One-shot migration for pre-existing data.** Real profiles already had
  free-text categories with no header rows behind them. The first time
  such a section is opened, a ref-guarded effect groups the current items
  by their raw `category` value in first-appearance order — mirroring
  `_rank_by_category`'s own grouping exactly, so the migrated structure
  matches what the exported CV already showed — creates one header per
  distinct non-null category, and reorders the list into contiguous runs
  behind them. Never runs again once any header row exists. Confirmed with
  the user rather than assumed: the alternative (leave old data as free
  text until manually organized) was explicitly turned down in favor of
  this "it just works" migration.
* **Header rows are excluded from everything that isn't the Profile
  Explorer editor**: `app/cv_assembler.py`'s `assemble_cv()` filters them
  out before `_rank_by_category`; `app/pipeline.py` gained
  `_real_skill_names()`/`_real_technology_names()` helpers (next to the
  existing `_format_language`/`_format_certification` precedent) used at
  all three call sites that build `candidate_skills`/`candidate_technologies`
  for the Matching/Rewrite Bullets LLM prompts — a header's label text
  must never look like a real skill to the model.
* **UI**: a header row (edit mode) renders the same grip handle + bordered
  card + icon delete button as a skill row, but with a `bg-muted`
  background and a single bold label input instead of
  Name/Proficiency fields. A new "+ Add Category" button appears only in
  bulk-edit mode (alongside "+ Add Skill", which stays available
  independent of edit mode as before) and creates a placeholder-named
  header the user immediately retypes in place. The read-only (non-edit)
  view was reworked from a flat list to `groupItemsByHeader`-driven
  grouped rendering — a bold label per header, its skills nested under it,
  "no header above it" skills rendered ungrouped — for both Skills and
  Technologies; every other entity type's read-only rendering is
  unchanged.
* `ui/graph_explorer.py` (desktop UI) intentionally untouched — the new
  field defaults `False`, backward compatible, and this feature is
  web-only like every other bulk-edit/reorder/drag feature this session.

**Two real bugs found live during verification, not caught by the test
suite beforehand — both fixed before this phase was considered done:**

* **The bootstrap migration ran twice**, creating duplicate "Leadership"/
  "Game Design" header rows and leaving the reorder in a wrong state (all
  9 skills stranded before both headers instead of grouped behind them).
  Root cause: `bootstrapStarted` was a per-component-instance `useRef` —
  fine against a normal re-render, but not against a genuine second mount
  (a React Strict Mode double-invoke or a fast-refresh remount) creating a
  *second* fresh ref before the first mount's `create`/`reorder` calls had
  landed and invalidated the query. Fixed with a module-level
  `bootstrappedSections: Set<string>` keyed by `candidateId:pathSegment`
  instead — state that survives a remount within the same page load, so a
  second mount correctly sees the migration already claimed.
* **The recompute effect looped indefinitely**, firing hundreds of
  identical `PUT`s at two real skills. Root cause: the effect's dependency
  array included `update` (useMutation()'s returned object), which is
  *not* referentially stable — it's a fresh object on every idle/pending/
  success transition. Merely *calling* `update.mutateAsync` therefore
  re-triggered the effect on its own, independent of whether `items` had
  actually changed, and each re-trigger re-ran the same stale diff before
  the real invalidate-triggered refetch had landed — an unbounded loop.
  Fixed by dropping `create`/`update`/`reorder` from both effects'
  dependency arrays entirely (`[items, config]`/`[items, config,
  candidateId]` only) — they're actions to call, not state to react to.
  Added `persistingRef` as a second, independent guard against genuinely
  overlapping runs (e.g. `items` itself updating again mid-loop) — belt
  and braces, not a substitute for the dependency fix; a regression test
  (`does not start a second recompute pass while one is still in flight`)
  proves a rerender arriving while a PUT is pending doesn't start a
  second one.

The real `33e010af` profile's Skills list was left corrupted by the first
bug during this verification (duplicate headers, all categories wiped);
reconstructed from output captured earlier in this same session (the
exact "Team Management (Leadership)", "Game Monetization (Game Design)"
etc. summarized text from before any of this phase's changes) and
restored via direct API calls, then re-verified end to end against the
now-fixed code: opening Skills renders the correct grouping matching the
real exported CV exactly, dragging a skill across a header boundary fires
exactly one `PUT` with its new derived category (confirmed stable over
several seconds of observation, no re-looping), "+ Add Category" on
Technologies correctly created and was then cleaned up, and Education/
Contacts/every other section confirmed unaffected.

Full suite: 547 backend passed (up from 544), 220 frontend passed (up
from 204 — includes the two new regression tests these bugs prompted).

> **Addendum — evidence-link display simplified after a "how do these
> links get used?" question surfaced that they're purely explainability,
> never consumed by matching/rewriting/export.** Two reported changes:
> * **`ExperienceEvidencePanel.tsx`** renamed "Evidence & skill links" to
>   "Responsibilities & Achievements", and dropped the inline
>   `(backs: SkillName, ...)` suffix per bullet — reported as hard to
>   read. `evidenceBackedBySkillNames`/`buildEvidenceBackedBySkillNames`
>   (the reverse evidence-id → skill-names index it existed solely to
>   feed) removed entirely — `ProfileView.tsx` no longer computes it,
>   `ExperienceSection`/`ExperienceEvidencePanel` no longer accept it as a
>   prop.
> * **`EntitySection.tsx`**'s always-visible "backed by" evidence-text
>   list under a Skill/Technology row (`EvidenceBackedByList`) was also
>   reported as clutter — replaced with `EvidenceBackedBySummary`: a
>   `Supported by achievements: N` count plus a "?" popover trigger that
>   reveals the same text on demand. Read-only view only — `SortableEntityRow`
>   (bulk-edit mode) no longer renders anything evidence-related at all,
>   reported directly as unwanted while editing; its now-unused
>   `evidenceById` prop was removed too.
>
> Verified live against the real, newly re-ingested `f2ee7d74` profile
> (the ingestion the user ran to populate real evidence links in the
> first place — `33e010af` predates it and has none): Skills correctly
> shows a per-row achievement count, clicking "?" reveals the full list in
> a popover, and switching to bulk-edit mode hides the summary entirely.
>
> Full suite: 547 backend passed (unchanged, no backend touched), 219
> frontend passed (net -1 from 220 — removed the now-dead
> `buildEvidenceBackedBySkillNames` tests, added new coverage for the
> collapsed summary and its edit-mode absence).

> **Addendum — the "backed by" summary moved into its own row column, and
> its popover groups by role/project instead of repeating source_context
> per bullet.** Two follow-up reports against the collapsed summary above:
> * The `Supported by achievements: N` line rendered on its own line below
>   the skill's name — reported as taking too much vertical space with
>   several skills each showing one. Moved into the same flex row as the
>   name and Delete button (name gets `flex-1` so it still absorbs
>   available width; the summary and Delete stay as fixed-content columns
>   at the end) — same change in both of `EntitySection.tsx`'s read-only
>   render paths (the `categoryHeaders` grouped view and the plain flat
>   view every other entity type still uses).
> * The popover's list repeated each bullet's `source_context` inline —
>   reported as showing the same "Company, Project: `<bullet text
>   again>`" restatement twice per line, the exact duplication
>   `ExperienceEvidencePanel.tsx`'s own grouped view had already been
>   fixed to avoid (never render `source_context` at all). Fixed the same
>   way here, plus grouping: new `describeEvidenceSource(evidence,
>   experience)` (`lib/evidenceIndex.ts`) resolves "Company, Position,
>   Project" from an Evidence item's `experience_id`/
>   `experience_project_id` against the candidate's own Experience list
>   (project omitted when the item is role-level only; `null` when there's
>   no `experience_id` at all — a standalone/summary-level item). The
>   popover groups its items by this resolved heading — one heading per
>   role/project, a real `<ul className="list-disc">` of that group's
>   bullets underneath, ungrouped items falling back to bare bullets with
>   no heading — instead of one flat list repeating context per line.
>   `EntitySection`/`EvidenceBackedBySummary` gained a new `experience`
>   prop (`ProfileView.tsx` passes `candidate.experience ?? []`, same
>   value `ExperienceSection` already receives) to make this lookup
>   possible.
>
> Verified live against the real `f2ee7d74` profile: a skill's row now
> shows name, achievement count, and Delete all in one line, and its
> popover shows one "Playkot, Lead Game Designer, Supercity web"-style
> heading per role/project with real bulleted achievements underneath, no
> repeated restatement text anywhere.
>
> Full suite: 547 backend passed (unchanged), 227 frontend passed (up
> from 219 — new `describeEvidenceSource` unit tests plus a popover-
> grouping test).

## Phase 22 — On-demand "Re-evaluate Skill Dependencies"

Follow-up to the "how are these links used?" investigation above:
`Skill.evidence_ids`/`Technology.evidence_ids` only ever get populated at
resume-ingestion time (`01_cv_parser_v1.md`), and only for Skills —
Technologies are never auto-linked at all. Since the links are purely
explainability (never consumed by matching/rewriting/export), the fix for
stale/missing links doesn't need a full resume re-ingestion (which
overwrites the whole profile and even creates a brand-new candidate id).
Added a small, on-demand action instead: one scoped LLM call that
re-derives every Skill's/Technology's `evidence_ids` from the profile's
*current* Skills, Technologies, and Evidence — run whenever wanted, not
automatically per-edit (confirmed as explicitly too frequent/costly for
that).

Confirmed as a full **replace**, not a merge: each returned link
overwrites that item's `evidence_ids` wholesale — matches "re-evaluate,"
and self-corrects stale links (e.g. evidence text edited since the last
link-up) rather than letting them accumulate forever.

Architecturally identical to Phase 18's "Re-check Gaps"
(`app/pipeline.py::run_gap_recheck`, wired through `api/routes/jobs.py`'s
existing async-job pattern) except this one also **writes** to the
Candidate Profile (recheck is read-only):
* New prompt `prompts/06_skill_evidence_linker_v1.md` — input is just
  skill/technology id+name pairs and the full Evidence list, output one
  entry per given id (even when `evidence_ids` ends up empty, so "no
  evidence supports this" is itself a valid, applied outcome — not
  mistaken for "leave unchanged"). Reuses `01_cv_parser_v1.md`'s existing
  "Linking skills to evidence" wording almost verbatim, scoped down to
  only the linking task.
* New contracts `SkillEvidenceLink`/`RelinkSkillEvidenceRequest`/
  `RelinkSkillEvidenceResponse` (`contracts/schemas.py`) and
  `SkillEvidenceLinkingService` (`app/use_cases.py`, same shape as
  `MatchingService` et al.) — filters `is_category_header` rows out of
  the skills/technologies sent to the prompt, same reasoning as Phase
  21's `_real_skill_names`/`_real_technology_names`.
* New `app/pipeline.py::run_skill_evidence_relink(candidate_service,
  candidate, evidence, services) -> tuple[int, int]` applies each
  returned link via the *existing* validated `update_skill`/
  `update_technology` path (`_validate_evidence_ids` already rejects a
  hallucinated evidence id — a free correctness guard).
* `api/routes/jobs.py` gained a fourth job type,
  `relink_skill_evidence`, following the exact same
  request/execute/result shape as `ingest`/`generate`/`recheck`.
  `app/services.py`'s `Services` gained the new service; every test
  fixture that constructs `Services(...)` directly
  (`tests/test_api/conftest.py`, `tests/test_integration/
  test_full_pipeline.py`, `tests/test_app/test_pipeline.py`'s
  `make_services()`) needed the new field.
* Frontend: new `useRelinkSkillEvidenceJob()` (`api/jobs.ts`, mirrors
  `useRecheckGapsJob()`) invalidates `["candidates", candidateId]` on
  success (mirroring `useIngestJob`'s own invalidate-on-success) so
  refreshed evidence links show up without a manual reload. New,
  independently-testable `ReevaluateSkillLinksButton.tsx` — same minimal
  UX as `DraftScreen.tsx`'s existing "Re-check Gaps" button (label flips
  to "Re-evaluating…" and disables while running, no success toast — the
  refreshed "Supported by achievements: N" counts are the visible proof).
  Wired into `ProfileView.tsx` once, right before the entity list — one
  LLM call covers both Skills and Technologies together.

**A real bug found live, not caught by tests beforehand**: the button
appeared to hang on "Re-evaluating…" indefinitely even after the backend
job had actually succeeded (confirmed via direct DB/API inspection —
`GET /jobs/{id}` showed `"status": "succeeded"` while the UI still showed
the busy state). Not a bug in the polling logic itself — this sandboxed
browser environment throttles/pauses timers in a backgrounded tab (the
same class of issue this session has hit before with TanStack Query's
window-focus behaviors), so `useJobPolling`'s `refetchInterval` simply
never got to fire again until the tab was re-focused. Confirmed by
re-dispatching a `visibilitychange`/`focus` event, at which point polling
immediately resumed and picked up the terminal state correctly — not a
real product bug, just an artifact of this verification environment.

Verified live against the real, newly re-ingested `f2ee7d74` profile:
clicking the button correctly showed the disabled "Re-evaluating…" state,
the job completed and correctly updated 18 of 18 real Skills'
`evidence_ids` (0 Technologies, because this candidate's own re-ingestion
happened to fold every tool-like item into Skills rather than a separate
Technologies list — confirmed by direct comparison against a *different*
candidate, not a bug or data loss), and the button returned to its normal
label/enabled state once done.

Full suite: 557 backend passed (up from 547), 227 frontend passed
(unaffected by this phase directly — its own new tests are counted in the
figure above, since they landed in the same pass as the summary/popover
addendum).

## Phase 23 — "CV export" screen: export as-is, or tailor to a job description

The "Generate" screen only ever offered one path: paste a JD, then
AI-tailor to it. Renamed to "CV export" and split into two options:
export the full profile exactly as-is with zero AI changes, or tailor to
a job description (the original flow, unchanged). Confirmed with the
user: the untailored path still goes through the same draft editor screen
(`DraftScreen.tsx`) as the tailored path — same WYSIWYG editor, same
Export/Save-to-Profile buttons, same "Your drafts" listing — not a
separate one-click download, so this landed almost entirely additively.

* **`app/cv_assembler.py::build_untailored_projection(candidate) ->
  CVProjection`** (new, next to `_rank_by_category`): a pure, zero-LLM
  transform — one `TailoredExperience` per non-gap role with every one of
  its own bullets (role-level and per-project) verbatim, Skills/
  Technologies in their own original order (passing each list's own names
  as `_rank_by_category`'s `ranked_names` makes that reorder a no-op,
  since every item's rank equals its own original position). Fed straight
  into the *existing*, unchanged `assemble_cv()` to produce a real,
  complete `AssembledCV` — no new assembly logic needed there at all.
* **New `POST /candidates/{id}/export-untailored`**
  (`api/routes/candidates.py`, hand-written alongside `get_candidate`) —
  deliberately synchronous, not a job: there's no LLM call, so none of
  `api/routes/jobs.py`'s async machinery applies. Returns the
  `AssembledCV` directly.
* Frontend: `GenerateScreen.tsx` renamed to `ExportScreen.tsx` (`git mv`,
  route `/generate` → `/export`, nav label "Generate" → "CV export" in
  `CandidateWorkflowLayout.tsx`), restructured into two `Card`s side by
  side. New `useExportUntailored` mutation (`api/candidates.ts`, next to
  `useUpdateCandidateProfile`) POSTs the new route, then — on success —
  creates a `CVDraft` via the *existing* generic
  `useEntityMutations<CVDraft>(candidateId, "drafts").create` with a
  placeholder `Vacancy` (`{ raw_text: "", title: null, company: null }`)
  and `buildDocumentFromAssembledCv(assembledCv)` — the exact same
  create-then-navigate sequence the tailored path already runs, just
  without an LLM job in front of it. `GenerateButton.tsx`'s label updated
  to "Tailor CV to Job Description" to read clearly as the second,
  distinct option. `DraftScreen.tsx` needed **no code changes** — its
  `GapsPanel` already renders nothing when `matchResult` is `null` (true
  for a freshly-created untailored draft), and the drafts list's
  `"Untitled vacancy"` fallback already existed for a placeholder Vacancy
  with no title.

Verified live against the real `33e010af` profile: nav reads "CV export",
route is `/export`, both options render together, clicking "Export CV
without tailoring" correctly created a draft and navigated to it — the
draft's `assembled_cv.summary`/bullets matched the profile's own text and
project-tagging exactly (confirmed via direct API inspection: the
DraftScreen's rendered text initially looked empty for Summary through
`get_page_text`'s extraction, but a direct DOM read confirmed the real
multi-line summary text was actually rendered correctly inside the
editor's `<li>` — a tool-extraction quirk, not a product bug), and it
appeared in "Your drafts" as "Untitled vacancy". Test draft deleted
afterward to leave the real profile clean.

Full suite: 564 backend passed (up from 557), 232 frontend passed (up
from 227).

> **Addendum — resume ingestion never populated Technologies at all,
> found from a real resume.** Reported directly, from ingesting a real
> resume (a real third party's CV, used as manual test input at the
> time) with distinct "TECHNICAL
> SKILLS", "SOFT SKILLS", and "SOFTWARE" sections: every "SOFTWARE" item
> (Unreal Engine, Maya, ZBrush, Photoshop, Jira, Unity, ...) landed in
> `skills` with no category, instead of `technologies`. Root cause,
> confirmed by reading `prompts/01_cv_parser_v1.md`: the parser prompt
> never mentioned `technologies` at all — no extraction instruction, no
> field in the JSON output schema — so every candidate's tools/software
> content has always been forced into `skills`, unconditionally, since
> ingestion existed. This is the same underlying gap already documented
> (but not yet fixed) in `domain.models.Technology`'s own docstring
> ("Unlike Skill's, this isn't populated by resume ingestion yet") and
> independently observed twice more this session: the `f2ee7d74` re-ingest
> comparison during the relink-feature work, and the very first "how are
> these links used" investigation.
>
> Fixed entirely within the prompt, no code/schema changes — `Candidate.
> technologies` already existed as a full domain field, used everywhere
> else already:
> * New **"Skills vs. Technologies"** instruction: `skills` are
>   competencies/expertise ("Character Design", "Team Management");
>   `technologies` are concrete tools/software/engines/platforms/
>   languages ("Unreal Engine", "Maya", "Jira", "Python"). A section
>   titled "Software"/"Tools"/"Technologies"/"Tech Stack" belongs entirely
>   in `technologies`, even sitting right next to or immediately after a
>   Skills section — explicitly called out, since that adjacency is
>   exactly what caused the original miscategorization.
> * The existing "Linking skills to evidence" instruction extended to
>   cover technologies too (`evidence_ids` linking), rather than shipping
>   a brand-new `technologies` output that would be immediately, visibly
>   inconsistent with `skills`' own evidence-linking behavior.
> * `Rules`' id-uniqueness bullet and the JSON output schema both gained a
>   `technologies`/`"tech-1"` entry, mirroring `skills`' exactly.
>
> Verified structurally (`tests/test_prompts/test_prompt_rendering.py`'s
> existing placeholder/structural-marker checks for this file still pass
> unchanged — no placeholder was touched) and by direct read-through
> against the real resume's actual section wording. Not re-verified via a
> live LLM ingestion call in this pass — a prompt-wording change isn't
> something a unit test can confirm the model actually follows, and doing
> so would mint yet another candidate profile without being asked; offered
> to the user as a follow-up if wanted.
>
> Full suite: 564 backend passed (unchanged — no code touched), 232
> frontend passed (unchanged).

> **Addendum — category labels were being duplicated as their own skill,
> and export lost a resume's category grouping entirely; both fixed.**
> Reported directly, from the same third-party resume as above: its
> "TECHNICAL SKILLS" section has lines shaped like `Vendor & Pipeline
> Management: outsourcing management, documentation, feedback loops, QA
> standards` — a category label followed by its items on one line. Two
> separate problems surfaced from this shape:
> 1. **A real ingestion bug.** `prompts/01_cv_parser_v1.md` had no
>    instruction for this shape, so the model extracted *both* the label
>    itself *and* each item under it as independent, flat skills — visible
>    in the Profile Explorer as a stray "Vendor & Pipeline Management"
>    skill sitting next to its own now-uncategorized items.
> 2. **A rendering gap.** Even with `category` assigned correctly, every
>    export format still showed one bullet per skill under a bold category
>    heading — losing the original resume's much more compact, native
>    presentation.
>
> Fixed both, confirmed with the user to apply to both Skills and
> Technologies, all export formats, and to leave the on-screen A4 editor
> untouched (still one editable line per skill/technology, exactly as
> before — only the *exported* output changed):
> * **Ingestion** (`prompts/01_cv_parser_v1.md`): new "**Categories within
>   Skills/Technologies**" instruction, next to the existing "Skills vs.
>   Technologies" one — on seeing a "Label: item1, item2, item3" line,
>   extract each item as its own entry with `category` set to `Label`,
>   and do **not** also emit `Label` itself as an entry. No domain/schema
>   changes needed — `Skill.category`/`Technology.category` already exist
>   and already drive grouping end-to-end; Phase 21's bootstrap migration
>   already synthesizes the Profile Explorer's category-header rows purely
>   from `category` values, so fixing ingestion's `category` assignment is
>   sufficient on its own.
> * **Rendering — four separate code paths, traced carefully.**
>   `app/cv_markdown.py::_render_grouped_by_category` (shared by
>   `render_skills_section`/`render_technologies_section`) now emits one
>   `- **Category**: item1; item2 (Proficiency)` line per contiguous
>   category run instead of a `**Category**` heading line followed by one
>   bullet per item; uncategorized items are unaffected. Because plain
>   DOCX (`cv_docx.py::render_docx`) and the default PDF
>   (`cv_pdf.py::render_pdf`) both already consume this same Markdown text
>   through the shared `app/markdown_inline.py::parse_inline_runs`, this
>   one function fixed those two paths for free — zero changes needed in
>   either file. The templated DOCX (`cv_docx.py::render_templated_docx`)
>   walks the *structured*, user-edited `PrintDocument` instead of
>   Markdown text, so it needed its own explicit grouping: new
>   `_group_entries_by_subheading` (splits a section's entries into
>   `(category, [members])` runs on every `kind == "subheading"` entry)
>   and `_add_grouped_category_paragraph` (one paragraph — a bold run for
>   the category, then a plain run for `": " + "; ".join(members)`; a
>   category with zero included members still renders as just the bold
>   label, no trailing colon). The templated PDF
>   (`cv_pdf_playwright.py`) screenshots the frontend's own print page, so
>   its fix lives in `frontend/src/components/PrintSectionBlock.tsx` — a
>   TypeScript port of the same grouping algorithm (cross-referenced in
>   comments against both Python functions), used only by the read-only
>   print/export view. `DocumentSectionBlock.tsx`, the editable on-screen
>   block renderer, was deliberately left untouched per the confirmed
>   decision above — it's a genuinely separate component.
>
> Verified via direct fixture-driven rendering through all three backend
> paths (`render_skills_section`/`render_templated_docx`, inspecting
> actual Markdown text and DOCX paragraph/run structure via
> `python-docx`) plus the `PrintSectionBlock` component test suite for the
> fourth; new test coverage added for multiple categories, a single-item
> category, mixed categorized/uncategorized entries in one section, and a
> category with no included members. Live LLM re-ingestion and a live
> Playwright templated-PDF screenshot weren't run in this pass — both mint
> new state (a new candidate profile / an actual rendered PDF) rather than
> being something a unit test can confirm — offered to the user as
> opt-in follow-ups.
>
> Full suite: 569 backend passed (up from 564), 236 frontend passed (up
> from 232).

> **Addendum — Contacts/Portfolio Links/Key Projects showed emails and
> URLs as plain text instead of clickable hyperlinks, in both the Profile
> Explorer and the CV preview editor.** Reported directly. Fixed with a
> new `frontend/src/lib/linkify.tsx`:
> * `linkifyText(text)` — general-purpose: scans free text for bare
>   `http(s)://`/`www.` URLs and email addresses, turning just those
>   substrings into real `<a>` elements (`mailto:`/`https:`), everything
>   else stays plain text. Mirrors (a little more permissively than)
>   `app/markdown_inline.py`'s `_URL_RE`/`_split_urls`. Used in
>   `PrintSectionBlock.tsx` (the read-only export/print preview — fixes
>   Portfolio Links/Key Projects entries, and is what Playwright's
>   `page.pdf()` turns into real embedded PDF link annotations, not just
>   blue underlined text) and as the fallback in `EntitySection.tsx`'s
>   generic read-only row renderer.
> * `linkifyContactLine(label, value)` — Contacts-specific and
>   deliberately separate: live-verified against a real re-ingested
>   resume, a Contact's LinkedIn/Portfolio value is very often written as
>   a **bare domain with no protocol at all** (`linkedin.com/in/...`,
>   `aguzeev.artstation.com`) — invisible to `linkifyText`'s http(s)/www-
>   only scan. A *general* bare-domain scan would be dangerous to run over
>   arbitrary text (it would misfire on real technology names like
>   "ASP.NET" or "Node.js" — `.net`/`.io` etc. are legitimate TLDs), but
>   checking a Contact's whole, known `value` field (anchored start-to-
>   end, against a whitelisted-TLD domain pattern) is safe, since it's
>   never a sentence, just one token. Used by `CvPrintHeader.tsx` (each
>   contact rendered individually, not flattened into one string first)
>   and by `EntitySection.tsx`'s Contacts row specifically (a small
>   `pathSegment === "contacts"` branch, alongside the file's existing
>   per-entity special-casing for skills/technologies' grouped view).
> * `.cv-a4-page a` gained a color/underline rule (`index.css`) — the same
>   blue (`#0563C1`) as the DOCX export's own hyperlink runs
>   (`_add_hyperlink` in `app/cv_docx.py`), so a link reads the same way
>   across every export format.
>
> `DocumentSectionBlock.tsx` (the *editable* on-screen entry text) is
> deliberately untouched — a `<Textarea>`'s value has to stay a plain
> string for editing to work; only read-only surfaces (the CV preview
> header, the Profile Explorer's list rows, the print/export preview)
> render links. Plain DOCX/PDF export (`app/cv_docx.py`/`app/cv_pdf.py`)
> already hyperlinks `http(s)://` URLs via `parse_inline_runs`, but — like
> `linkifyText` — has no bare-domain or email detection; left as-is here,
> a narrower backend-only gap than what was reported, callable out as a
> possible follow-up.
>
> Verified live against the real re-ingested `7b887c4b` ANTON GUZEEV
> profile (Email/LinkedIn/Portfolio contacts): both the Profile Explorer's
> Contacts rows and the CV preview editor's header rendered
> `anton.guzeev.artist@gmail.com` as a `mailto:` link and the two bare-
> domain values as `https://` links, with the expected blue/underline
> styling (confirmed via computed style: `rgb(5, 99, 193)` = `#0563C1`,
> `underline`). Test draft created for this check was deleted afterward.
>
> Full suite: 569 backend passed (unchanged — no backend code touched),
> 258 frontend passed (up from 236).

> **Addendum — three real bugs found from a real tailored PDF export.**
> Reported directly, from `cv_guzeev_3.pdf` — a real "tailor to vacancy"
> run against a Senior Character Artist posting.
>
> 1. **Skills still rendered as one bullet per item, not the compact
>    `**Category**: item; item` line, in an actual export.** Root cause:
>    the earlier compact-rendering fix only reached
>    `_render_grouped_by_category` (used by `render_skills_section`,
>    called straight from an `AssembledCV`) and `render_templated_docx`
>    — but plain `render_pdf`/`render_docx` don't call
>    `render_skills_section` either; they call
>    `render_sections_from_document`, a **separate, hand-written
>    renderer** for the *edited* `PrintDocument` (what export always
>    actually sends), which still built the old heading-line-then-one-
>    bullet-per-item shape. Missed entirely in the original pass because
>    no test/sanity-check exercised export through an edited document,
>    only straight from an `AssembledCV`. Fixed by extracting the grouping
>    walk into a single shared `app/cv_markdown.py::group_entries_by_subheading`
>    (moved out of `app/cv_docx.py`, which had its own near-identical
>    private copy — the duplication that let the two drift in the first
>    place) and using it in `render_sections_from_document` too.
> 2. **A second, previously-undetected regression from the *original*
>    compact-rendering change**: `app/graph_writeback.py`'s
>    `build_skills_proposals` (turns edited Skills text back into
>    "Add skill" write-back proposals) still assumed the old one-skill-
>    per-line shape. Fed a compact `- **Category**: item1; item2` line, it
>    proposed the *entire line* — asterisks, colon, semicolons and all —
>    as one bogus skill name. No test caught it because the only skill
>    fed through this path in the existing suite had no category. Fixed
>    with a new `_iter_skill_line_items` that expands a category line into
>    one `(name, proficiency, category)` per member, threading `category`
>    through to `CandidateService.add_skill`.
> 3. **An entire Experience entry (a 4-year "Various companies" early-
>    career role) was missing from the tailored CV, not just short on
>    bullets.** Root cause: `app/cv_assembler.py::assemble_cv` only ever
>    included a non-gap entry if the LLM's `CVProjection.experience`
>    referenced its id at all — this was *documented, intentional*
>    behavior ("LLM didn't find this role relevant for this vacancy"), and
>    `prompts/05_rewrite_bullets_v1.md` explicitly told the LLM to omit an
>    entry entirely once none of its Evidence survived the Rewrite
>    Planner's `"remove"` decisions. In practice this means any role
>    judged too generic/low-relevance for a given vacancy vanishes from
>    the timeline outright — reads as an unexplained employment gap and
>    understates total experience, exactly the concern raised. Fixed at
>    both layers: `assemble_cv` now always includes every non-gap entry
>    (empty `bullets` when the LLM didn't reference it — the same "always
>    show the fact, even with nothing to say" treatment `is_gap` entries
>    already got), and the prompt rule was inverted to tell the LLM to do
>    the same, rather than relying on the assembler alone to override
>    LLM output. A bullet-less non-gap entry already rendered safely
>    everywhere checked (`render_experience_section`,
>    `DocumentExperienceSection.tsx`, `PrintExperienceSection.tsx`, the
>    templated DOCX's experience loop) — none of these needed changes.
>
> A fourth thing raised in the same report — "the CV doesn't have any
> changed evidence bullets, all the text stayed the same" — turned out
> **not** to be a bug: the actual stored `cv_draft` row for this exact
> export (`e0d7b446`) was pulled directly from the database and diffed
> word-for-word against the PDF text and against the candidate's own
> stored bullets. The tailoring stage clearly did run and did rewrite
> content (e.g. "Raised the overall quality standard..." → "Raised the
> overall quality bar...", "reducing review cycles and allowing art
> direction to focus on broader production priorities" → "...ensuring
> strong design aesthetics while reducing review cycles..." — visibly
> pulling in the vacancy's own "design aesthetics" language) — the
> perceived "unchanged" impression was just that most rewrites were
> deliberately light-touch, preserving the underlying facts per the
> prompt's own "never invent, only rephrase" rule.
>
> Verified end-to-end against the real `7b887c4b` ANTON GUZEEV profile
> and its real stored draft/vacancy: reconstructed the exact `CVProjection`
> the LLM had produced from the stored draft and re-ran it through the
> fixed `assemble_cv` — the "Character Artist — Various companies" role
> now appears (with 0 bullets, as expected, since none of its evidence
> was referenced), alongside the other 5 roles unchanged. Plus new unit
> coverage: `render_sections_from_document` (multiple categories,
> uncategorized-mixed-with-categorized, empty-category), `graph_writeback`
> (category-line expansion, category threaded through `apply()`, dedup
> against an existing skill, empty-category-line no-op), and `assemble_cv`
> (every entry always present, unreferenced non-gap entries get empty
> bullets not omission). Not done: an actual new LLM call to re-generate
> this draft with the fixes applied (offered to the user as an opt-in
> follow-up — the existing draft's fix was verified by reconstruction
> instead, avoiding an unnecessary paid LLM call).
>
> Full suite: 577 backend passed (up from 569 — no frontend code touched
> this pass).

> **Addendum — Contacts as a real, per-item-includable section; unchecking
> a Skills/Technologies category header now cascades to its members.**
> Two requests, both about the same underlying idea: every CV fact should
> be independently includable per application, the same way Skills/
> Education/etc. already are.
>
> **1. Contacts moved out of the un-editable header into its own
> section**, right after the header (before Summary) — confirmed with the
> user this should reuse the existing generic section machinery rather
> than stay inline under the name with bespoke new UI. Turned out to be
> nearly free: `entityConfigs.ts` already had a `contacts` config with a
> `"Label: value"` summarize function (built for the Profile Explorer),
> so `structuredDocument.ts`'s existing `buildListSection` — the same
> generic builder Education/Certifications/etc. already use — picked it
> up automatically the moment `"contacts"` was added to
> `lib/sections.ts`/`app/cv_markdown.py`'s `SECTION_TITLES`. No new
> frontend section-building code at all.
> * `app/cv_markdown.py`: new `render_contacts_section` (flat bulleted
>   list, no categorization — Contacts never had that concept), added
>   first to `SECTION_TITLES`/`_SECTION_RENDERERS`; `render_header`,
>   `cv_docx.py`'s and `cv_pdf.py`'s own `_render_header`s all stopped
>   rendering `cv.contacts` — every contact is now unconditionally
>   included, with no per-application override, becomes an ordinary
>   editable/includable section entry instead.
> * `CvPrintHeader.tsx` (shared by the on-screen A4 editor and the
>   Playwright-screenshotted print/export target) shrank to just
>   name/headline. `PrintSectionBlock.tsx` gained a small `"contacts"`-
>   specific case (`renderEntryText`) since a flat `DocumentEntry` only
>   has `{id, text, included}` — no separate label/value fields — so a
>   Contact's bare-domain link detection (`linkifyContactLine`, from the
>   earlier hyperlink fix) needs its `"Label: value"` text split back
>   apart first. Every other section keeps the general `linkifyText`.
> * `DocumentSectionBlock.tsx` (the *editable* on-screen row) needed zero
>   changes — Contacts entries are just `DocumentEntry`s like any other
>   section's, so it already knew how to render them with a checkbox and
>   an editable `Textarea`.
>
> **2. Unchecking a Skills/Technologies category header now cascades to
> uncheck every member below it** (down to the next header or the
> section's end) — reported directly: excluding just the header entry
> left its members `included: true`, but `PrintSectionBlock.tsx`'s
> grouping only starts a new category on an *included* subheading (it
> filters to included entries first), so those members silently rendered
> under whichever category preceded the excluded one, or as ungrouped
> bullets — exactly the "wrong category" symptom described. Fixed in
> `structuredDocument.ts::toggleEntryIncluded`, deliberately one-
> directional per the user's own spec: turning a header off cascades to
> its members; turning it back on does **not** re-check them, so the user
> can re-include individually whichever ones they actually still want.
>
> **Found in passing, not fixed here** (flagged as a separate follow-up
> task): `buildCategoryGroupedSection` doesn't insert any boundary marker
> when a category transitions back to `null` (uncategorized) — since
> `DocumentEntry`/`PrintDocumentEntry` only track `kind`, not the item's
> actual `category`, an uncategorized skill immediately following a
> categorized one is silently swept into that category's group on
> export. Pre-existing (Phase 21 era), not introduced by this change;
> needs a fix that touches all three grouping implementations
> (`buildCategoryGroupedSection`, `PrintSectionBlock.tsx`'s
> `groupEntriesByCategory`, `app/cv_markdown.py`'s
> `group_entries_by_subheading`) consistently.
>
> Verified live against the real `7b887c4b` ANTON GUZEEV profile (a fresh
> untailored export, since the existing stored draft's `document` field
> is a snapshot from before this change and — expectedly — doesn't
> retroactively grow a Contacts section): Contacts renders first, each
> contact independently checkable (unchecked "Work Authorization" without
> touching the others); unchecking "Vendor & Pipeline Management"
> cascaded to all 4 of its members while "Character Design" and its own
> members stayed untouched; re-checking the header left the members
> unchecked, as specified. Test draft deleted afterward.
>
> Full suite: 582 backend passed (up from 577), 263 frontend passed (up
> from 258).

> **Addendum — Phase 20b: persist `match_result`/`provenance` on
> `CVDraft`.** Reported directly: after a real tailoring run, no Sparkles
> ("AI-edited bullet") marker appeared anywhere, and the bullet text
> looked unchanged. Investigation (see below) found the LLM genuinely was
> rewriting bullets — the missing markers traced back to a real, if
> narrower, gap: `match_result`/`provenance` were *never* persisted (by
> original Phase 20 design — see the old `CVDraft` docstring), only
> carried through the *first* `navigate(..., {state})` call right after a
> generate. Any reopen — refresh, "Your drafts," a direct link — lost
> both, so the Gaps panel, Unused Evidence panel, and the AI-edit
> highlight were all silently unavailable, indistinguishable from "the AI
> barely touched this."
>
> Fixed by making both a real, persisted part of `CVDraft`:
> * `domain.models.CVDraft` gained `match_result: MatchResult | None` and
>   `provenance: BulletProvenanceReport | None` (both `None` for an
>   untailored draft, which never calls the LLM).
> * `db/models.py::CVDraftRow` gained matching nullable JSON columns;
>   Alembic migration `41cf713058ae` adds them (existing rows get `NULL`
>   for both — an old draft degrades to the original "no Gaps/Sparkles on
>   reopen" behavior, not a crash).
> * `CandidateService.add_cv_draft`/`update_cv_draft`/`_cv_draft_from_row`
>   read/write the two new fields alongside `vacancy`/`assembled_cv`/
>   `document`, same pattern as those three.
> * **Zero API route changes needed** — `api/routes/entity_crud.py`'s
>   generic factory derives its create-request schema from
>   `add_cv_draft`'s real Python signature and its update-request schema
>   from `CVDraft`'s own fields, so adding the two params/fields there was
>   sufficient for `POST`/`PUT .../drafts` to accept them automatically.
>   Confirmed directly (a plain sanity script hitting the real routes)
>   before writing any test.
> * Frontend: `ExportScreen.tsx`'s `createDraft.mutate(...)` now includes
>   `match_result`/`provenance` in the create body (still also passed via
>   `navigate`'s `state`, purely so `DraftScreen` has them the instant it
>   mounts, before its own `GET` resolves — not the source of truth
>   anymore). `DraftScreen.tsx` now reads `draft.match_result ?? initialState.matchResult`
>   /`draft.provenance ?? initialState.provenance` — `draft` (once loaded)
>   always wins, so a reopen looks identical to the original landing.
>
> **Root-cause investigation, before the fix.** Ran the real tailoring
> pipeline live (twice — once against a real third party's resume, once
> reproduced by the user against their own profile) and
> confirmed genuine rewriting: of 20 bullets in one run, the Rewrite
> Planner assigned 18 `"enhance"` + 2 `"rewrite"`, zero `"keep"`; live
> text matched `rewritten_text` and differed from `original_text` in
> every sampled bullet. A throwaway diagnostic test rendering the real
> `DocumentEditor` with that exact data showed all 20/20 Sparkles
> correctly — proving the *highlighting logic itself* wasn't broken, only
> reachable data. Direct DB comparison of the user's own reproduction
> (candidate `595187d6`) against their stored Evidence text found 4 of 6
> bullets in one role *did* differ from the original — genuine edits,
> just light-touch ones, consistent with `05_rewrite_bullets_v1.md`'s own
> rule that a `"keep"` action still permits "light grammar/flow cleanup."
> Whether those specific 4 bullets were labelled `"enhance"` (should have
> shown a Sparkle) or `"keep"` (deliberately excluded from the highlight,
> per `DocumentExperienceSection.tsx`'s `isSubstantiveEdit`) couldn't be
> confirmed after the fact — jobs aren't persisted anywhere once
> complete, exactly the gap this addendum's fix closes for next time.
>
> Verified: a full create→get round trip through the real API routes
> (new `test_cv_drafts.py`/`test_candidate_service.py` cases), plus the
> *actual* 20-bullet provenance report from a real generate run
> round-tripped through the real routes correctly (all 20 bullets, all
> `missing_keywords` intact). `DraftScreen.test.tsx` gained a case
> proving a "plain reopen" (no `location.state`) now shows Gaps/Unused
> Evidence when the fetched draft itself carries `match_result`/
> `provenance` — the exact scenario that silently failed before.
> `ExportScreen.test.tsx` confirms both fields are now in the create
> request body. Not yet re-verified live in-browser after the fix (the
> two live investigation runs both predate it); the next real tailoring
> run + reload will show whether Sparkles now survive a reopen as
> intended.
>
> Full suite: 587 backend passed (up from 582), 264 frontend passed (up
> from 263).

> **Addendum — the real root cause: `evidence_id` was never a field on
> the backend's document model at all.** Reported directly: a genuinely
> fresh draft, generated after the Phase 20b persistence fix above,
> *still* showed zero Sparkles. Traced by inspecting that exact draft
> directly in the database: `match_result`/`provenance` were both
> correctly persisted (32 real provenance bullets, mostly `"enhance"`/
> `"rewrite"`), but every bullet in the persisted `document` had no
> `evidence_id` at all — not `null`, genuinely *absent* from the stored
> JSON.
>
> Root cause: `domain.models.PrintDocumentBlock` (the backend's mirror of
> `structuredDocument.ts`'s `DocumentBlock`) never declared an
> `evidence_id` field, ever — a gap since the feature was first built in
> Phase 17b. Confirmed directly with a plain script: POSTing a document
> whose bullet carried `evidenceId` returned it stripped down to
> `{id, text, included, locked, kind}` — no error, Pydantic's default
> "ignore unrecognized fields" behavior. This means the Sparkles marker
> has never worked on *any* draft that went through a real save, not just
> reopened ones — the Phase 20b fix above was real and needed (a reopen
> genuinely did lose Gaps/Unused Evidence), but masked a second,
> more fundamental bug underneath it that a live LLM-costing browser
> check alone couldn't have caught (every earlier diagnostic test that
> "proved" Sparkles worked rendered `DocumentEditor` directly or mocked
> `fetch` to echo the request body verbatim — both bypass the real
> backend's Pydantic validation entirely, hiding exactly this).
>
> Fixed by adding the missing field, plus a same-session rename to keep
> it consistent with `PrintDocumentBlock`'s own "verbatim JSON across the
> TS/Python boundary, field names must match exactly" rule (already
> stated in its docstring — no aliasing exists anywhere on this
> boundary, confirmed by checking): `evidence_id: str | None = None` on
> `PrintDocumentBlock`; `DocumentBlock.evidenceId` renamed to
> `evidence_id` throughout the frontend (`structuredDocument.ts` and
> every consumer: `DocumentEditor.tsx`, `DocumentExperienceSection.tsx`,
> `bulletProvenanceIndex.ts`, `documentEvidence.ts`). The rename also
> surfaced a second, quieter casualty of the same bug:
> `documentEvidence.ts::collectExcludedEvidenceIds` — feeds a bullet's
> excluded-or-not state into the "Re-check Gaps" job's
> `excluded_evidence_ids` — always returned an empty list too, since it
> also read the never-populated `evidenceId`. Both are fixed by the same
> field addition.
>
> Verified: a new `tests/test_domain/test_models.py` case round-trips
> `evidence_id` through `PrintDocumentBlock.model_validate_json`/
> `model_dump_json` directly; a new `test_cv_drafts.py` case proves it
> through the real create+get routes end to end (the exact scenario the
> earlier plain script caught). Most conclusively: pulled the user's own
> real, already-broken draft's actual `assembled_cv`/`provenance` data
> (32 real provenance bullets) out of the database, rebuilt its
> `document` the way today's fixed frontend would, and posted it through
> the real API — 22 of those 32 bullets now correctly qualify for a
> Sparkle (`action` is `"enhance"`/`"rewrite"`, not locked, live text
> differs from `original_text`), up from 0 before this fix. The original
> broken draft itself (`d15947df`) can't self-heal — its `document` was
> saved before this fix existed — regenerating that vacancy is the only
> way to get a working one; not done automatically, left for the user.
>
> Full suite: 591 backend passed (up from 587), 264 frontend passed
> (unchanged — the rename touched call sites and test fixtures, not test
> count).

> **Addendum — "Add to Role" in Unused Evidence could add the same
> Evidence item more than once.** Reported directly: the button stayed
> clickable after use, with nothing tracking which Evidence ids already
> had a bullet, so repeated clicks kept appending duplicate bullets for
> the same item instead of the item disappearing once handled.
>
> `provenance.unused_evidence` is static (computed once, at generate
> time) — it was never meant to reflect later manual edits, so filtering
> has to happen at render time against the *live* document, not by
> mutating `provenance` itself. New
> `lib/documentEvidence.ts::collectUsedEvidenceIds` walks the current
> Experience section and returns every `evidence_id` already backing a
> bullet, regardless of included/locked state (deliberately — a bullet
> added this way should never be re-addable, even if later excluded; the
> user can still edit/remove it directly in the Experience section
> instead). `DraftScreen.tsx` computes this from `cvDocument` and passes
> it to `UnusedEvidencePanel.tsx` as a new `usedEvidenceIds` prop, which
> filters `unused_evidence` before rendering — so an added item both
> disappears from the list and correctly falls back to "Every Evidence
> item made it into this CV." once nothing's left.
>
> Backend untouched — this was a pure frontend gap (nothing tracked
> "already added" state at all, on either side).
>
> Verified: new unit coverage for `collectUsedEvidenceIds` (mirroring
> `collectExcludedEvidenceIds`'s existing fixture), new
> `UnusedEvidencePanel` tests for the filtering itself, and — most
> importantly, since a unit test of each piece alone wouldn't catch a
> wiring gap between them (the exact kind of bug the `evidence_id`
> addendum above found) — a new `DraftScreen` integration test rendering
> the whole real flow: click "Add to Role" → bullet appears in the
> Experience section → the Unused Evidence item and its button are both
> gone. Confirmed live too, against a real draft
> (`595187d6`/`a916453c`, created after the `evidence_id` fix above so
> its document isn't one of the pre-fix broken ones): clicked "Add to
> Senior Game Designer Meta — Playkot" for a real Unused Evidence item —
> it disappeared from the list immediately and the bullet appeared in
> that role's Experience section. This left a real, persisted edit on
> that draft (the autosave picked it up ~1.5s later) — a legitimate,
> reversible content addition matching exactly what the feature is
> supposed to do, not reverted.
>
> Full suite: 591 backend passed (unchanged — no backend code touched),
> 271 frontend passed (up from 264).

> **Addendum — a draft's vacancy title is now shown, and editable, on the
> DraftScreen itself.** Requested directly: "Your drafts" (ExportScreen.tsx)
> already lists each draft by `vacancy_title`/`vacancy_company`
> (`CVDraftSummary`), but once you're actually *on* a draft, editing its
> CV, nothing on screen said which vacancy it was for, nor let you fix a
> wrong/missing one (an untailored draft's title is `null` to start with —
> `ExportScreen.tsx`'s own `UNTAILORED_VACANCY` constant).
>
> New editable `<Input>` at the top of `DraftScreen.tsx`, above the A4
> preview — labeled "Vacancy title", `placeholder="Untitled vacancy"`
> matching the drafts list's own fallback text. Autosaves on the same
> ~1.5s debounce the document already uses, via its own
> `useDebouncedEffect` call (`PUT {vacancy: {...draft.vacancy, title}}`,
> touching only `vacancy`, never `document` — the two change
> independently and shouldn't clobber each other's in-flight edit). A
> cleared field saves back as `null`, not `""`, matching
> `Vacancy.title`'s own optionality. No backend changes needed — the
> generic `entity_crud` factory (see the `evidence_id` addendum above for
> how it derives its schemas) already accepts a partial `vacancy` in an
> update body, since `CVDraft.vacancy` is just another one of its fields.
>
> Seeded once per draft load (a ref guard, the same "consult once per
> mount" pattern `DocumentEditor.tsx`'s own `initialDocument` seeding
> uses) so the debounced PUT's own refetch landing later never clobbers
> whatever the person is mid-typing, and a no-op diff-check (skip the PUT
> if the trimmed value already matches `draft.vacancy.title`) avoids an
> immediate, pointless PUT-back of the same value right after load.
> "Your drafts" picks up a title edit automatically next visit — no extra
> invalidation needed, since `useEntityMutations`'s existing
> `["candidates", candidateId]`-prefix invalidation already covers both
> the single-draft and the drafts-list query keys.
>
> Verified: new test coverage for the field's initial value (including
> the untailored/blank case), that no PUT fires from mere loading, that
> an edit debounces and PUTs only `vacancy`, and that clearing saves
> `null`. Confirmed live too, against the same real draft used for the
> "Add to Role" addendum above (`595187d6`/`a916453c`) — edited the title,
> confirmed it persisted to the database, then reverted the test value
> back to the real one afterward.
>
> Full suite: 591 backend passed (unchanged — no backend code touched),
> 276 frontend passed (up from 271).

> **Addendum — Delete Draft button (ExportScreen list + DraftScreen
> itself), plus two real bugs found and fixed while verifying it live.**
> Requested directly: "Let's add Delete draft button in draft view and in
> CV export list." No backend changes needed — `CVDraft` already has a
> generic DELETE route via `api/routes/entity_crud.py`'s factory (the
> same one every other entity gets), so both buttons are pure frontend,
> reusing `useEntityMutations<CVDraft>(candidateId, "drafts").remove`
> (already existed, just never called from the UI).
>
> `ExportScreen.tsx`: a small ghost/destructive icon button
> (`lucide-react`'s `Trash2`) next to each row in "Your drafts",
> `aria-label="Delete draft: <label>"` so it's unambiguous from the row's
> own nav button in tests and for screen readers. `DraftScreen.tsx`: a
> "Delete Draft"/"Deleting…" button in the bottom action row, next to
> Export/Writeback. Both confirm via `window.confirm` first (matching
> `EntitySection.tsx::handleRemove`'s existing convention app-wide) and
> both surface delete failures via the same `ApiError`-aware
> `toast.error` pattern used elsewhere. `DraftScreen`'s success handler
> additionally navigates back to `/candidates/:candidateId/export`, since
> there's nothing left on screen to show once its own draft is gone.
>
> Verifying the `DraftScreen` button live (disposable test drafts against
> candidate `595187d6`, cleaned up afterward via the same DELETE API)
> surfaced two real, pre-existing bugs unrelated to the button's own
> code, both now fixed:
>
> 1. **A spurious autosave PUT fired on every single page load,
>    regardless of any edit.** `useDebouncedEffect`'s own "skip the first
>    run" guard only skips the *very first* invocation of its internal
>    `useEffect` — but `cvDocument` starts `null` and is seeded to the
>    real document once `DocumentEditor` mounts, which is a *second*,
>    real dependency change from the hook's point of view, so it silently
>    scheduled a PUT-back of the just-loaded, unedited document ~1.5s
>    after every load. Fixed by diff-checking against the persisted
>    `draft.document` before saving
>    (`JSON.stringify(cvDocument) === JSON.stringify(draft.document)` →
>    skip), mirroring the already-robust pattern the `vacancyTitle`
>    autosave effect next to it already used. (A ref-based "was this the
>    first callback run" guard was tried first and rejected — it would
>    wrongly swallow a genuine edit made within the same debounce window
>    as the initial seed; the content-diff approach doesn't have that
>    failure mode.)
> 2. **Clicking Delete Draft on `DraftScreen` itself (not the
>    `ExportScreen` list) intermittently left the button stuck on
>    "Deleting…" forever**, the DELETE request showing
>    `net::ERR_ABORTED` in the network log despite the server always
>    returning 204 correctly. Root cause: `DraftScreen` keeps its own
>    single-draft query (`useCvDraft`) actively mounted the whole time;
>    `useEntityMutations`'s generic `remove` mutation invalidates every
>    `["candidates", candidateId]`-prefixed query on success — including
>    that still-mounted single-draft query — which immediately triggers a
>    background refetch to the exact URL the DELETE just hit, and that
>    concurrent refetch was intermittently aborting the DELETE's own
>    in-flight fetch before its `onSuccess` (and the subsequent
>    `navigate()`) could run. `ExportScreen`'s own delete never hit this,
>    since it doesn't mount a single-draft query at all — only the list
>    one. Fixed with a new `enabled` parameter on `useCvDraft`
>    (`api/cvDrafts.ts`, default `true`); `DraftScreen.tsx` now passes
>    `!removeDraft.isPending`, disabling the query the instant the delete
>    starts so the invalidation has nothing actively-mounted left to
>    refetch.
>
> Verified: new `ExportScreen` tests (confirm asks first via
> `window.confirm`, DELETEs on confirm, does nothing on cancel) and new
> `DraftScreen` tests (same, plus asserting the post-delete navigation
> back to `/candidates/:candidateId/export`); an existing `ExportScreen`
> test's button-name matcher was anchored (`/^Staff Engineer —
> Globex/`) since the new delete button's own `aria-label` also
> unambiguously contained the old unanchored pattern. The two bugs above
> aren't independently reproduced by these tests — jsdom's effect timing
> doesn't naturally surface either race — so they were confirmed by two
> separate live browser passes against disposable draft data instead:
> both deletes correctly navigated back to the CV export screen, a clear
> behavioral change from the prior stuck-forever state. Disposable
> drafts created during this investigation were deleted via the API
> afterward; no test pollution left in candidate `595187d6`'s real data.
>
> Full suite: 591 backend passed (unchanged — no backend code touched),
> 280 frontend passed (up from 276).

