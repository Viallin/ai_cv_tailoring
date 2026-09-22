# Domain Model

## Purpose

The Domain Model defines the business entities that represent a candidate's professional experience independently of any AI provider, resume format, or export template.

The application's primary business asset is the **Career Graph**—a semantic representation of a candidate's professional history. Every generated resume is a projection of this graph rather than a standalone document.

The Domain Layer contains only factual career information and business rules. AI-generated interpretations, prompts, and provider-specific logic belong to the AI Layer.

> **Note:** this file describes the full target model; "Prototype scope
> note" / "Implemented" / "Version N addition" callouts throughout mark
> where today's code deviates. Phase references below to Phases 0-12.3
> point to detail now archived in `docs/archive/development_plan_v1.md`;
> references to Phases 13-23 point to `docs/archive/development_plan_v2.md`;
> references to Phase 24+ are in `docs/development_plan.md` directly.

---

# Design Principles

## Career Graph is the Source of Truth

The Career Graph is the authoritative representation of the candidate's professional experience.

Resumes, cover letters, and LinkedIn profiles are generated from the graph rather than being stored as independent documents.

---

## Structured Data First

Whenever possible, professional information is represented as structured entities instead of free text.

---

## Facts Before Interpretation

The domain stores objective career facts.

Higher-level interpretations (matching, semantic enrichment, AI recommendations) are derived from these facts and may be regenerated at any time.

---

## Reusability

Every piece of career information should be reusable across multiple resumes, job applications, and future product features.

---

# Core Entities

## Candidate

Represents the person whose professional experience is stored in the system.

Contains:

* personal information
* contacts
* location
* work authorization
* relocation preferences
* languages
* education
* certifications
* portfolio
* references

A Candidate owns a single Career Graph.

> **Prototype scope note (Phase 2):** the full CareerGraph/Organization/Role/
> Project hierarchy below is deferred. The current `domain.models.Candidate`
> is a flatter interim shape — `name`, `headline`, `summary` (the candidate's
> own, often-untitled "about me" paragraph from the resume — see below), a
> flexible `contacts` list (label+value pairs — Email/Phone/LinkedIn/
> Location/Work Authorization/etc, not fixed named fields, since what
> belongs on a CV header varies by role and location), plus flat
> `experience` / `education` / `skills` / `languages` / `certifications` /
> `projects` lists (no separate Organization/Role/Project nesting yet — and
> `projects` here means the standalone "Key Projects" portfolio section, not
> the graph's future per-Role Project nodes). It is populated two ways:
> 1. **Resume ingestion** (`01_cv_parser_v1.md` → `IngestResumeResponse.candidate`)
>    extracts it automatically from an uploaded resume — see `docs/contracts.md`.
> 2. **Manual CRUD** (`app/candidate_service.py`) lets the person add to or
>    correct it afterward.
>
> This Candidate Profile is intentionally a *separate* layer from Evidence
> below: Evidence is atomic, semantically reusable career facts meant for
> future Claim/Variant generation and vacancy matching, while the Candidate
> Profile is the structural record a person edits directly and expects to
> see mirrored back (like a normal profile form). They currently do not
> sync with each other — a resume re-import overwrites the Candidate Profile
> wholesale but does not touch previously extracted Evidence, and Evidence
> generation does not read from or write to the Candidate Profile.
>
> An `experience` entry can also represent an employment gap
> (`is_gap=True` — parental leave, sabbatical, career break) rather than a
> role. Gaps have no Evidence and are never selected/tailored by the CV
> generation LLM call; `app/cv_assembler.py` always includes them in the
> exported CV so a real gap in the candidate's timeline is never silently
> dropped. See `docs/development_plan.md` Phase 5 notes.
>
> `projects` (Key Projects) is deterministic like Education, not AI-tailored
> per vacancy like Experience — see `docs/development_plan.md` Phase 5 notes
> for the reasoning and how to upgrade this later if needed.
>
> `summary` is a Candidate *fact* (captured close to verbatim at ingestion)
> — distinct from `CVProjection.summary`, which is AI-generated fresh per
> vacancy. The latter may use the former as tone/positioning context but
> must not just copy it. Before this field existed, a resume's untitled
> intro paragraph had nowhere to go in the schema and was getting dropped
> or inconsistently absorbed elsewhere — a symptom of a missing field, not
> something prompt wording alone could fix. See `docs/development_plan.md`
> Phase 5 notes.
>
> `headline` (the Candidate's own current title, e.g. "Character Art
> Supervisor") used to be this same kind of untouched fact, copied verbatim
> into every tailored CV regardless of vacancy — reported directly:
> tailoring for "Senior 3D Character Artist" still showed the untouched
> profile headline. `CVProjection.headline` (Post-4.10 follow-up) now gets
> the same "fresh per vacancy, grounded in Evidence" treatment as
> `CVProjection.summary` — see `docs/contracts.md`'s RewriteBulletsRequest/
> RewriteBulletsResponse notes for the grounding rules (seniority and any
> specialization qualifier must be evidenced, never just lifted from the
> vacancy's own title).
> per vacancy like Experience — see `docs/development_plan.md` Phase 5 notes
> for the reasoning and how to upgrade this later if needed.

---

## SourceDocument

Represents an imported source of professional information.

Examples:

* Resume (PDF/DOCX/TXT)
* LinkedIn export
* Portfolio
* Future supported formats

A SourceDocument is immutable after import and serves only as an input for building the Career Graph.

---

## CareerGraph

The central business object of the application.

The Career Graph stores structured professional knowledge and relationships between entities.

The graph is continuously enriched as new source documents are imported or the user manually edits their experience.

Business rule:

* The Career Graph is the single source of truth.
* Generated resumes never modify the graph directly.

---

## Organization

Represents a company or institution where the candidate worked.

Contains:

* company name
* location
* industry (optional)

An Organization may contain multiple Roles.

---

## Role

Represents a position held within an organization.

Examples:

* Senior Product Manager
* Lead Game Designer
* Software Engineer

Contains:

* title
* employment type
* start date
* end date

A Role may contain multiple Projects and multiple Evidence items.

---

## Project

Represents a specific initiative or product within a role.

Projects are optional.

Examples:

* Mobile Launch
* LiveOps Overhaul
* Internal Analytics Platform

Projects group related Evidence items.

---

## Evidence

Evidence is the smallest reusable unit of professional experience.

An Evidence object represents a concrete responsibility, achievement, or measurable outcome.

Examples:

* Increased D30 retention by 12%.
* Led a team of five designers.
* Designed a LiveOps pipeline.
* Reduced production time by one week.

Evidence is attached to a Role or Project.

Business rules:

* Evidence should describe a single career fact.
* Evidence should remain independent of resume wording.
* Multiple wording variants may exist for the same Evidence.

---

## Variant

Represents an alternative textual expression of an Evidence object.

Variants allow the same professional fact to be presented differently depending on the target role.

Examples:

* ATS-friendly
* Executive
* Technical
* Concise

Business rules:

* Variants must preserve the meaning of the original Evidence.
* Variants never introduce unsupported information.

---

## Claim

A Claim represents a higher-level professional statement supported by one or more Evidence objects.

Unlike Evidence, a Claim is an interpretation rather than a directly imported fact.

Examples:

* Experienced people leader
* Expert in LiveOps optimization
* Strong cross-functional collaborator
* Data-driven product manager

Claims are used for semantic matching and AI reasoning.

Business rules:

* Claims are supported by one or more Evidence objects.
* Claims do not replace Evidence.
* Claims may be regenerated as AI capabilities improve.

---

## Skill

Represents a professional skill demonstrated by the candidate.

Examples:

* Product Management
* System Design
* Economy Design
* SQL

Skills are linked to supporting Evidence.

The application should always be able to explain why a skill exists by referencing supporting Evidence.

> **Implemented (Phase 15a):** `domain.models.Skill.evidence_ids: list[str]`
> — ids into the sibling Evidence[] list. Many-to-many: one Evidence item
> can back several skills, one skill can be backed by several Evidence
> items (a list on Skill, not a single id on Evidence — the only shape of
> the two that can express "backed by multiple items" at all). Populated
> automatically at resume ingestion (`prompts/01_cv_parser_v1.md`) where
> a bullet clearly demonstrates a skill — most skills, especially ones
> from a bare "Skills:" line with no supporting bullet, will have none,
> which is expected. Also settable manually via
> `CandidateService.update_skill()` / `PUT /candidates/{id}/skills/{id}`,
> which validates every id actually exists for that candidate (raises
> `ValidationError` otherwise) — unlike `Evidence.experience_id`, which is
> never eagerly cross-validated (see `docs/archive/development_plan_v2.md`'s
> Phase 15a notes for why the two links are treated differently). The
> symmetric UI (click a skill, highlight the bullets that back it, and
> vice versa) shipped in Phase 15b-ii.
>
> **Implemented (Phase 21):** `is_category_header: bool` turns a normal
> `Skill` row (same CRUD as any other, no separate entity) into a category
> header rather than a real skill — the Profile Explorer's editor is a
> flat, drag-orderable list where a skill's effective category is derived
> client-side from the nearest preceding header row and written back onto
> it. This makes the editor a live, editable preview of the same grouping
> `app/cv_assembler.py:_rank_by_category` already computes for export
> (category grouping stays deterministic from the Candidate's own list
> order; only the ranking *within* each category comes from the AI — see
> `docs/contracts.md`'s CVProjection/AssembledCV notes), instead of a
> free-text `category` field with no visible connection to it.

---

## Technology

Represents tools, frameworks, platforms, or technologies used by the candidate.

Examples:

* Unity
* Python
* AWS
* Jira

Technologies are linked to Roles, Projects, or Evidence.

> **Implemented (Phase 15a), partially:** `domain.models.Technology.
> evidence_ids: list[str]` exists (identical shape and validation to
> `Skill.evidence_ids` above), but resume ingestion never populates it —
> `prompts/01_cv_parser_v1.md` doesn't extract `technologies` at all
> today (a pre-existing gap, not introduced by Phase 15a); Technology
> entries only ever exist via manual creation
> (`add_technology`/`update_technology`), so the link is only ever set
> manually too, via the same `update_technology()` API.
>
> **Implemented (Phase 21):** `is_category_header: bool` — identical
> mechanism and reasoning to `Skill.is_category_header` above.

---

## Portfolio Item

Represents externally visible work.

Examples:

* Published application
* Game
* GitHub repository
* Presentation
* Technical article

Portfolio items may reference Projects and Evidence.

---

## Vacancy

Represents a target job opportunity.

Contains:

* metadata
* requirements
* constraints

Vacancies are temporary business objects used during resume generation.

---

## Requirement

Represents an individual requirement extracted from a vacancy.

Examples:

* Experience leading cross-functional teams
* SQL proficiency
* Mobile game experience

Requirements are matched against Claims and supporting Evidence.

> **Version 4 addition (Post-4.10 fixes round 3):** `Requirement` gains a
> `priority: "required" | "nice_to_have"` field, set only from the JD's
> own explicit framing ("Nice to have"/"Bonus points"/"Will be a plus").
> A `"nice_to_have"` Requirement caps its Gap at `severity: "medium"`
> regardless of how unaddressed it is — see `docs/contracts.md`'s
> Requirement section for the literal shape.

---

## Gap

Represents a mismatch between vacancy requirements and the candidate's current Career Graph.

Examples:

* Missing evidence
* Weak supporting experience
* Missing terminology

Gaps are used to generate recommendations and rewrite plans.

> **Prototype scope note (Phase 8):** implemented as `domain.models.Gap`
> (`requirement_text` + `description`), produced per-vacancy by the
> Matching stage (`03_cv_jd_matcher_v1.md`) as part of a `MatchResult`
> alongside `RequirementMatch`es — not yet a persistent Career Graph node
> the way the full model above describes. It *is* used to generate a
> rewrite plan, per this entity's own description: `RewritePlannerService`
> (`04_rewrite_planner_v1.md`) takes the `MatchResult` as input. See
> `docs/development_plan.md` Phase 8 notes.
>
> **Version 2 addition (Phase 18):** `Gap` gains a `status: "open" |
> "skipped"` field so a user can acknowledge-and-dismiss a gap after
> manual edits instead of it resurfacing every time Matching is re-run —
> Version 2 makes Matching re-invokable against the current edited
> document, not just a one-time pre-tailoring step.

---

## Resume Projection

Represents a generated resume for a specific vacancy.

A Resume Projection contains:

* selected Evidence
* selected Variants
* ordering
* formatting information

Business rules:

* Resume Projections are disposable outputs.
* They never become the source of truth.
* User edits may optionally be promoted back into the Career Graph.

> **Prototype scope note (Phase 5):** this full model (Evidence/Variant
> selection) is deferred to Phase 8. Today, this concept is split into two
> pieces in `domain/models.py`:
> 1. **`CVProjection`** — the AI-tailored *content* only (summary, per-role
>    bullets, skills). No identity, contacts, education, dates, or company
>    names.
> 2. **`AssembledCV`** — the actual exportable resume: Candidate facts merged
>    deterministically with `CVProjection`'s content by
>    `app/cv_assembler.py:assemble_cv()`, with no LLM involved in that merge.
>
> This split exists so identity/dates/companies — real facts — are never at
> risk of LLM hallucination, matching the "Facts Before Interpretation"
> principle above. See `docs/contracts.md`'s "Tailoring: Matching ->
> Rewrite Planning -> Bullet Rewriting" section and `docs/development_plan.md`
> Phase 5/8 notes.
>
> **Version 2 additions:**
> * **Provenance (Phase 17):** each tailored bullet retains
>   `{original_text, rewritten_text, rationale}`, not just the final text —
>   needed for the UI to explain an AI edit and offer one-click revert. A
>   bullet can also be marked `locked` (Phase 19): the rewrite stage then
>   skips the LLM call and reuses the locked text verbatim for any
>   vacancy, the cheap alternative to embedding-based variant reuse (see
>   `docs/PROJECT_CONTEXT.md`'s Future Ideas note on that).
> * **`CVDraft` (Phase 20):** unlike the disposable Resume Projection
>   described above, Version 2 persists generated documents keyed by
>   candidate + vacancy, so previous drafts for a given job description can
>   be reopened instead of regenerated. This does not change the "never
>   becomes the source of truth" rule — a `CVDraft` is a saved output, not
>   a Career Graph node; only explicit write-back (Phase 8.3/19) promotes
>   its content back into the graph.
>
> **Version 3 additions:**
> * **The structured document model (Phase 16, extended 21/24/25):** what
>   `CVDraft.document` actually holds isn't `CVProjection`/`AssembledCV`
>   directly — it's `domain.models.PrintDocument`, an ordered
>   sections → ordered entries → (for Experience) ordered bullets tree, a
>   structural mirror of the frontend's live A4-editor state
>   (`frontend/src/lib/structuredDocument.ts`). Every entry/bullet carries
>   its own `included` flag (the section/bullet exclude-toggle — Phase 24
>   builds a "restore excluded content" panel entirely on top of this
>   existing flag, no schema change) and, for Experience bullets, an
>   `evidence_id` link back to its `BulletProvenance`. See
>   `docs/contracts.md`'s "structured document model" section for the
>   literal shape — it's presentation/editing state (ordering, inclusion,
>   formatting), not a new semantic layer, so it stays out of this file's
>   entity list rather than becoming a first-class Domain entity of its
>   own.
> * **`TextRun` (Phase 25, editor-producible since Phase 31):** optional
>   inline bold/italic/underline/link spans within a block's text,
>   authoritative over the block's plain-text fallback when present.
>   Phase 25 added the field to the backend/contract layer only, with no
>   producing UI; Phase 31 added a Tiptap BubbleMenu (selection →
>   bold/italic/underline/link/alignment) that writes real ProseMirror
>   marks, from which `runs` is derived — across every section, not just
>   Summary/Experience, though a grouped/joined Skills-or-Technologies
>   line still doesn't carry per-member `runs` (see `docs/contracts.md`'s
>   TextRun section for the exact scope).
> * **`page_break_before` (Phase 30):** a manual "start this section/entry
>   on a new page" override on `PrintDocumentSection`/`PrintDocumentEntry`,
>   honored by every export path with a real page concept. Presentation/
>   editing state, same as `included` above — not a new Domain entity.

---

# Entity Relationships

```text
Candidate
│
├── Source Documents
│
└── Career Graph
     │
     ├── Organizations
     │      │
     │      └── Roles
     │             │
     │             ├── Projects
     │             │      │
     │             │      └── Evidence
     │             │             │
     │             │             └── Variants
     │             │
     │             └── Evidence
     │
     ├── Claims
     │      │
     │      └── Supported by Evidence
     │
     ├── Skills
     │      │
     │      └── Proven by Evidence
     │
     ├── Technologies
     │
     └── Portfolio Items
```

---

# Business Rules

* The Career Graph is the single source of truth.
* Source Documents are immutable.
* Evidence represents factual career information.
* Variants change wording but never meaning.
* Claims are semantic interpretations supported by Evidence.
* Skills must always be backed by supporting Evidence.
* Resume Projections are generated outputs and are never edited as the master record.
* AI-generated interpretations may be regenerated without modifying the underlying Career Graph.

---

# Future Extensions

The model is intentionally extensible and may later include:

* Interview preparation
* Career timeline visualization
* Job application tracking
* Cover letter generation
* LinkedIn profile generation
* Semantic search
* Retrieval-Augmented Generation (RAG)
* Local embedding index
* Multi-language support
