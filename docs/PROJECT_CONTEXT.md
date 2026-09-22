# AI CV Builder
AI CV Builder helps users quickly create and tailor CVs to specific job openings using LLM.

The app's primary goal is to transform the CV preparation process from hours of manual effort into a series of small steps, where the user makes decisions and AI handles most of the routine work.

The application is designed to be LLM-agnostic: working with a specific model (Gemini, OpenAI, Claude, Ollama, etc.) should not impact the application's business logic.

The system is a platform for semantic CV creation. Users do not manually create structured data. Instead, source resumes are processed and transformed into a semantic career graph.

## Product Stages

**Version 1 (shipped, Phases 0-12.3 of `docs/development_plan.md`):** a
PySide6 desktop app, single window. Proved the ingest → analyze → match →
tailor → assemble → export pipeline end-to-end, including real Gap
Analysis and write-back. Output was functionally correct but not
pleasant to use — plain editable text fields, no preview of the actual
export, no visibility into what the AI changed. Superseded by Version 2;
see `docs/archive/development_plan_v1.md` for the full phase detail.

**Version 2 (shipped, Phases 13-23):** replaced the desktop app with a
single-user, local web app (no auth/hosting — see Non-goals below).
Shifted focus from pipeline capability to product feel: a WYSIWYG A4
preview of the real export with configurable export templates, a
candidate profile page with cross-links between skills and the experience
that backs them, visible/explainable AI edits with one-click revert, a
re-run-able gap check after manual edits, bullet locking, persisted CV
drafts, and advisory checks. See `docs/archive/development_plan_v2.md`
for the full phase detail and `docs/technology_stack.md` for the stack.

**Version 3 (shipped, Phases 24-31):** reworked the A4 editor from a
stack of `<Textarea>` fields into a real rich-text document (Tiptap-based)
— structural drag-to-reorder, selection-level bold/italic/underline/
links/alignment via a BubbleMenu, a floating gutter for controls, an
on-screen page-break guide with manual pagination control. Net result as
of this version: a local web application that can ingest a plain-text
CV, let the user edit the profile and save the data, and generate a
tailored, ATS-friendly CV in English with gap analysis and highlights of
the skills the user already has for a given job description. See
`docs/archive/development_plan_v3.md` for the full phase detail and
`docs/development_plan.md` for the retrospective summary.

**Version 4 (prototyped, later dropped):** explored turning the app into
something distributable — a real, installable Windows desktop app
(Tauri-wrapped, no console, no API key setup) a few non-technical friends
could actually run, plus CV generation in the candidate's own language
(Russian first). The Tauri packaging was later removed; running the
backend + frontend dev servers is the supported way to run the app. See
`docs/development_plan.md`'s Version 4 section for the full
phase-by-phase history.

## Vision
The initial core idea: Help professionals tailor a high-quality CV to any job opening in minutes, while maintaining full control over the final text.

Potential expansion: transform the app into a full-fledged job hunting database with status tracking for each opening, assistance with responses, and interview preparation.

## Problem Statement
Job hunting nowadays requires multiple CV versions for different positions, as you often need to tailor your experience for different job descriptions and present the same information under different angles. Manually rewriting a CV based on your master CV  is extremely time-consuming.
Furthermore, users are constantly copying the same experience between different CV versions, and after several iterations, it's difficult to determine which version has become the primary one.

Possible marketing statement:
- Build your Career Memory once. Generate every application from it.
- A personal knowledge base for your professional experience.

## Product Goals
* Loading a CV document into a structured data model
* Extracting specific career achievements claims from the document
* Improving the wording of career achievements claims without changing the meaning
* Generating multiple variations of achievement claims wording
* Analyzing job requirements using AI
* Generating complete CVs from a candidate's knowledge base, selecting the most appropriate career point variations.
* Allowing the user to fully manually edit the CV
* Exporting the CV  to PDF in a well-designed, ATS-readable format with compression (<2 MB)
* Editing can be quickly saved to the master resume

## Non-goals (for MVP)
> Status of each item as of Version 2 planning — most were MVP-only
> exclusions, not permanent ones. Still-excluded items carry into Version 2
> deliberately (see `docs/development_plan.md`'s Version 2 intro) and stay
> Non-goals until a later "marketable" stage.
* Multiple options for importing your initial resume — **resolved**
  (Version 4, Phase 4.5: file upload accepts PDF/DOCX/RTF/TXT/MD via a
  new `POST /jobs/ingest-upload` route and a file input alongside the
  existing paste box)
* Convenient manual entry of experience directly through the UI —
  **resolved** (Phase 12.3 Graph Explorer; Phase 15 replaces it with an
  inline-editable profile page)
* Support for multiple users — still excluded in the multi-tenant sense:
  no shared backend serving many people, no auth, no hosting. Version 4's
  distributable desktop app is a different thing — each friend runs
  their own separate install, still single-user/local per install, not a
  multi-tenant server
* User-side API selection — still excluded; Version 4 goes the other
  way (an app-embedded key, so friends set up nothing)
* CV translation into other languages — **in scope for Version 4**
  (Phases 4.2/4.3), but as "generate in the candidate's own profile
  language" (detected at ingestion, or chosen for an empty profile), not
  an on-demand translate-this-CV feature — a different target language
  means creating a new candidate profile, by design
* Monetization — still excluded
* Version history — still excluded
* Export templates — **in scope for Version 2** (Phase 16)
* Previews of the result — **in scope for Version 2** (Phase 16, WYSIWYG
  A4 preview)
* Cover Letter generation — still excluded
* LinkedIn profile generation — still excluded
* Portfolio generation — still excluded


## Target Audience
Professionals who regularly apply for job openings and want to:
- Maintain a unified experience profile;
- Quickly adapt their resume to different job openings;
- Control the final text instead of relying on fully automated generation;
- Use different AI models without changing the interface.
  
Primary audience:
* Product Managers
* Game Designers
* Software Engineers
* Quality Assurance
* Data Engineers
* Analysts


## User Journey
1. The user uploads their master CV to the service, and the service remembers it.
   1. User uploads PDF
   2. CV is parsed into a structured data model
   3. Each career achievement claim is transformed into a "fact, metrics, context, action" statement 
   4. LLM gereates different angles for these career claims and proposes wording for these angles
2. Building CV variants:
   1. User pastes job description into the service
   2. AI analyzes the JD
   3. AI finds the gaps into the existing experience and career claims and proposes adding extra angles for it.
   4. AI builds the tailored CV using the best matching angles of career claims for this particular JD
   5. User can manually edit the end result
   6. User exports the CV into PDF (ATS-friendly)
   7. Optional: User saves the new added career claims into the master CV database

## Core Features
1. Importing CV into a structured CV database
2. Generation of diifferent angles for each career claim
3. Job desription analysis
5. Building tailored CV
6. Manual CV editing
7. CV export

## Future Ideas
> "Export templates" and "Visually pleasant CV previews" moved out of this
> list into Version 2 scope (Phase 16) — see Product Stages above. Bullet-
> variant reuse via similarity/embedding search was considered for Version
> 2 and deliberately deferred (Phase 19 ships only exact-match bullet
> locking); revisit once that phase's cost/latency logging shows whether
> it's actually worth the added infrastructure.
* General
  * Monetization
  * Version history
  * Auth / multi-user / hosting
* CV
  * Сover Letter generation
  * LinkedIn profile generation
  * Portfolio generation
  * Bullet-variant reuse via similarity search (see note above)
* AI
  * Agent workflows
  * RAG
  * Local models
* Job hunting board: 
  * Kanban
  * Interview preparation
  * Interview notes
  * Reminders

## Guiding Principles

* The user retains control over the final result.
* AI suggests options, the user makes a decision.
* Prioritizes local data.
* Transparent AI output.
* LLM-independent architecture.
* Structured data instead of free text.
* Reusability of the main CV.
* Incremental improvements instead of a complete rewrite.

## Success Metrics
* For the user:
  * The user creates a customized CV in less than 15 minutes.
  * At least 80% of AI suggestions are accepted by the user without significant edits.
  * The user can reuse the master CV without manually copying information.
* For the product:
  * The full cycle (job analysis → export) is error-free.
  * The exported PDF meets ATS requirements and is less than 2 MB in size.
  * The architecture allows for replacing the AI ​​provider without changing the business logic.

## Competitors
https://tailored-cv.com/
https://tailoredcv.ai/
https://www.grammarly.com/a/resume-builder