# Documentation Index

> This index was out of date against the actual `docs/` contents (listed
> `ai-pipeline.md`/`prompts.md`/`storage.md`/`export.md`, none of which
> exist, and omitted several files that do). Corrected as of the Version 2
> planning pass, refreshed 2026-08-07 alongside the development-plan
> archive split and a full staleness pass over every doc here
> (contracts.md/domain-model.md were significantly out of date — both
> covered through Phase 25 at that point), and refreshed again
> 2026-09-04 when Version 3 (Phases 24-31) shipped and its own detail was
> archived the same way. Refreshed again 2026-09-15: development_plan.md
> caught up with six commits landed since its last entry ("Post-4.10
> fixes, round 4" — a Gemini 3.x compatibility break, Matching-stage
> Contacts visibility, headline tailoring/PDF link ingestion/company-
> project links/ingest UX, two rounds of JD-keyword accuracy fixes, and
> the candidate-navigation redesign), and contracts.md/domain-model.md
> got targeted fixes for fields those commits (and the still-unreflected
> Phase 4.9 print-session removal) had left stale — still not a full
> re-pass of either.

## Product & planning
- PROJECT_CONTEXT.md — product vision, scope, current Product Stage
  (Version 1, 2 & 3 shipped; Version 4 — the distributable desktop app —
  in progress, Phases 4.1-4.10 done, 4.11 "Friend rollout" not started)
- development_plan.md — phased roadmap. Shipped versions (V1: Phases
  0-12.3, V2: Phases 13-23, V3: Phases 24-31) are each collapsed to a
  retrospective summary here, with their full unabridged phase detail
  moved to `archive/`; the file's active-version section (split out
  2026-08-07, once the plan passed ~3500 lines, and again 2026-09-04 for
  V3) now carries Version 4's own phase-by-phase detail in full, kept
  current as of 2026-09-15
- archive/development_plan_v1.md, archive/development_plan_v2.md,
  archive/development_plan_v3.md — full phase-by-phase detail for shipped
  versions, linked from development_plan.md
- archive/phase_8_wireframes_spec.md — dead Qt/PySide6 wireframes for a UI
  paradigm the product no longer has (moved out of `docs/` 2026-08-07;
  see the file's own header note)

## Core documents
- architecture.md
- domain-model.md

These two core documents should evolve together with development_plan.md:
1. Architecture (how the system works)
2. Domain Model (what the system knows)
3. Development Plan (in what order it gets built)

An "AI Pipeline" doc covering how information flows through the LLM
stages was planned here but never written — that flow is currently
documented inline in architecture.md's "5 Data Flow" section and
contracts.md's "Tailoring" section instead.

## Supporting documents
- contracts.md — contracts that exist in code today, updated through
  Phase 25 (structured document model, TextRun, CVDraft, BulletProvenance,
  the HTTP API layer) plus targeted later additions through Phase 31
  (`page_break_before`, `kind: "compact"`, widened `runs` scope) and,
  refreshed 2026-09-15, several Version 4 fields (`CVProjection.headline`,
  `Experience.company_url`/`ExperienceProject.url`, `Requirement.priority`,
  `MatchRequest.candidate_contacts`) plus the Phase 4.9 print-session
  removal — not a full re-pass past Phase 25
- adr-template.md
- technology_stack.md — revised for Version 2's single-user/local scope;
  its Tiptap section covers through Version 3/Phase 31

"prompts.md" and "storage.md" were planned as dedicated docs but never
written. Prompts are reasonably well covered without one
(architecture.md section 6, plus the `prompts/` directory's own files);
storage is only covered thinly (a few scattered mentions in
architecture.md and contracts.md) — a dedicated doc there is still a real
gap. "export.md" is largely covered now by contracts.md's structured
document model / HTTP API sections and technology_stack.md's Export
section, though nothing pulls those together into one place yet.
