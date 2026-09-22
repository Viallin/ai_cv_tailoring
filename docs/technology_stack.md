# Technology Stack

> **Revised for Version 2** (`docs/development_plan.md`, Phases 13-23,
> shipped). This file was originally drafted at the concept stage, before
> the app's actual shape (single-user, local, no hosting for this stage —
> see `docs/PROJECT_CONTEXT.md`'s Product Stages) was settled. The
> frontend stack below is unchanged from that draft; the Database and
> Deployment sections are revised to match single-user/local scope
> instead of the originally-assumed multi-tenant SaaS target. Revisit
> both sections again when a hosted "marketable" stage is actually
> planned. Version 3 (Phases 24-31, shipped) added one frontend
> dependency this file went a while without reflecting: Tiptap
> (rich-text editor, landed Phase 26, gained selection-level rich
> formatting in Phase 31) — its own section is below now. Version 4
> prototyped a Tauri-packaged desktop installer as a deployment target;
> that packaging was later dropped (see the Tauri section below), and the
> app runs as local dev servers (`dev.bat`) again.

The technology stack is selected to support the project's core architectural goals:

- AI-provider independence
- Strong separation of concerns
- Type safety across the application
- Easy testing
- Incremental scalability from MVP to SaaS
- Modern developer experience
- Maintainable long-term architecture

---

# Frontend

## React

Responsible for building the user interface.

Used for:

- Resume editor
- Career Graph explorer
- AI suggestions
- Vacancy analysis workflow
- CV builder
- Settings and configuration

Chosen because:

- component-based architecture
- large ecosystem
- excellent support for complex interactive applications
- easy integration with TypeScript

---

## TypeScript

Provides static typing for the frontend.

Benefits:

- early error detection
- improved IDE support
- safer refactoring
- shared data models with backend contracts

---

## Vite

Frontend build tool.

Responsible for:

- development server
- production builds
- hot module replacement

Chosen because it offers a significantly faster development experience than traditional bundlers.

---

## Tailwind CSS

Utility-first CSS framework.

Responsible for:

- application styling
- responsive layouts
- design consistency

Benefits:

- minimal custom CSS
- rapid UI development
- maintainable styling system

---

## shadcn/ui

Reusable UI component library.

Provides:

- dialogs
- forms
- tables
- dropdowns
- navigation
- inputs
- buttons

Chosen because components remain fully customizable instead of being locked into a UI framework.

---

## Tiptap (ProseMirror)

Rich-text document editing for the A4 CV editor (`frontend/src/components/DocumentEditor.tsx` and
`frontend/src/lib/tiptap/`, `frontend/src/components/tiptap/`).

Used for:

- one real, prerendered `contentEditable` document (section → entry → bullet), replacing a stack of
  independent `<Textarea>`/`<Input>` fields (Phase 16-23) that never behaved like a unified document
- structural drag-to-reorder of sections/entries/bullets (native ProseMirror node dragging, Phase 27)
- checkbox/Sparkles-AI-edit-trigger chrome positioned via NodeViews, not template markup (Phase 26,
  reworked into a floating-in-page-margin gutter in Phase 28)
- a manual "start this section/entry on a new page" toggle honored by every export path (Phase 30)
- selection-level rich formatting — a BubbleMenu for bold/italic/underline/alignment/links, plus a
  link edit/hover card, across every section (Phase 31)

Packages: `@tiptap/core`, `@tiptap/react`, `@tiptap/pm`, `@tiptap/extension-text`,
`@tiptap/extensions`, `@tiptap/extension-bold`, `@tiptap/extension-italic`,
`@tiptap/extension-underline`, `@tiptap/extension-link` (Phase 31). Deliberately not
`@tiptap/starter-kit` — this is a fully custom, minimal schema (no headings/lists baked in; see
`lib/tiptap/schema.ts`).

Chosen over hand-rolled `contentEditable` diffing or Slate for schema-enforced custom node types
(sections/entries/bullets stay structural, not arbitrary text), NodeViews for embedding React inside
the document, a BubbleMenu for selection-triggered formatting, and native browser cursor/selection
behavior for free. `@dnd-kit/*` stays in the project for unrelated profile-CRUD lists
(`EntitySection.tsx`/`BulletRowsEditor.tsx`) — only the CV document editor's own drag-reorder moved to
Tiptap's native mechanism.

---

## TanStack Query

Server state management.

Responsible for:

- API communication
- request caching
- background refetching
- loading and error states

Benefits:

- eliminates most manual API state management
- improves application responsiveness

---

## React Hook Form

Form management library.

Used for:

- resume editing
- settings
- vacancy input
- profile editing

Benefits:

- minimal re-rendering
- simple validation integration
- excellent TypeScript support

---

## Zod

Runtime validation library.

Responsible for validating:

- user input
- API payloads
- imported data

Provides additional safety before requests reach the backend.

---

# Backend

## Python

Primary backend language.

Chosen because of its mature ecosystem for:

- AI
- document processing
- PDF generation
- natural language processing
- data manipulation

---

## FastAPI

Backend web framework.

Responsible for:

- REST API
- request routing
- dependency injection
- OpenAPI generation
- job-status endpoints for long-running LLM calls (ingest/analyze/
  generate) — an in-process async job pattern (`POST /jobs` + `GET
  /jobs/{id}`, polled by TanStack Query), not a separate task queue.
  Replaces the `QThread`/`PipelineWorker` pattern the current desktop UI
  uses to keep multi-second Gemini calls off the blocking thread. No
  Celery/Redis: a single local user doesn't need a distributed queue.

Chosen because it integrates naturally with Pydantic and provides excellent performance for API-based applications.

---

## Pydantic

Data validation library.

Responsible for:

- request validation
- response validation
- configuration models
- typed contracts

Pydantic forms the foundation of the application's Contracts Layer.

---

## SQLModel

ORM built on SQLAlchemy and Pydantic.

Responsible for:

- database models
- persistence
- querying
- mapping database records to domain objects

Chosen because it combines ORM capabilities with Pydantic validation while reducing boilerplate.

---

## Alembic

Database migration tool.

Responsible for:

- schema versioning
- database upgrades
- rollback support

Ensures database evolution remains predictable throughout the project.

---

# Database

## SQLite

Primary persistent storage for Version 2 (revised from the original
PostgreSQL proposal).

Stores:

- Candidate
- Career Graph
- Claims
- Variants
- Skills
- Vacancies
- CVDrafts (persisted generated documents, Phase 20)
- Application metadata

Chosen over PostgreSQL because Version 2 is single-user and local: no
concurrent-write contention to manage, no separate DB server to install
or run, and the whole dataset backs up as one file. Accessed through the
same SQLModel/Alembic layer PostgreSQL would have used, so migrating to
PostgreSQL later (once a hosted, multi-tenant stage is actually planned)
is a connection-string and Alembic-target change, not a rewrite — record
that migration as its own ADR (`docs/adr-template.md`) when it happens
rather than pre-building for it now.

---

# AI Layer

The AI architecture remains provider-independent.

Supported providers include:

- Gemini
- OpenAI
- Claude
- Ollama

The AI layer consists of:

- Prompt Builder
- LLM Gateway
- Provider Registry
- Response Validator
- Provider Implementations

This architecture allows replacing AI providers without changing business logic.

---

# Export

## HTML + CSS

Resume templates are generated as HTML documents.

Benefits:

- easy template customization
- modern layout capabilities
- separation between content and presentation

---

## PDF Renderer

`app/cv_pdf.py`, built on `reportlab`. Both the plain/ATS-safe export
(`render_pdf`) and the templated export (`render_templated_pdf`) share
one flowable-building implementation, parameterized by a `PdfTemplate`
(font/bullet-char/section-spacing) — the only thing that differs between
"plain" and "classic"/"modern" is which template's values get used.

Through Phase 16b–4.8, templated PDF instead worked by having Playwright
(headless Chromium) screenshot a live print-preview route the frontend
served — pixel-perfect with the on-screen A4 preview "by construction."
Version 4, Phase 4.9 replaced that: a packaged Tauri build can't
reasonably bundle a browser, and its frontend isn't reachable over real
HTTP for an external process to navigate to anyway (Tauri serves it via
its own asset protocol, not localhost). `render_templated_pdf` instead
reuses `app/cv_markdown.py`'s `render_sections_from_document` — the same
edited-document-to-text bridge the plain PDF/DOCX paths already use — so
it inherits that function's grouping/subheading/page-break handling for
free. The trade-off, accepted deliberately: templated PDF is now a
genuinely separate implementation from the on-screen preview that has to
be kept visually in sync by hand, the same trade-off templated DOCX
already lived with. Playwright itself (and the Python `playwright`
package) is no longer a dependency of this codebase at all.

Cyrillic support (Version 4, Phase 4.4, Sans family swapped post-4.9):
reportlab's Base-14 Helvetica has zero Cyrillic glyphs. `app/cv_fonts.py`
vendors and registers Noto Sans + DejaVu Serif (both SIL OFL/Bitstream
Vera-derived licenses, `assets/fonts/`) — Noto Sans for the plain export
and the "Modern" template, DejaVu Serif for "Classic." Originally DejaVu
Sans (matplotlib's bundle) was used for Sans too, but that build had no
true bold face, so `<b>` markup silently fell back to the regular
weight — real testing surfaced this as a visible bug (the "Modern"
template's role headers rendered bold on-screen but plain in the
exported PDF), fixed by swapping to Noto Sans, whose four static weight
instances (generated locally via `fonttools varLib.instancer` from
Google Fonts' own variable-font source) include a genuine bold face.

DOCX export stays on the existing `python-docx`-based `app/cv_docx.py` —
not unified with the PDF path, since DOCX is a genuinely different
format — but is template-aware (Phase 16b), applying the same
font/bullet/spacing choices directly via `python-docx`'s own styling.
Cyrillic support here (Phase 4.4) works differently: Word silently
substitutes an unavailable font with no error surfaced, so rather than
gamble on Georgia's/Geist's uncertain Cyrillic coverage,
`app/cv_templates.py`'s `resolve_docx_template` substitutes both
templates' fonts to Calibri (ships with every modern Word install, full
Cyrillic coverage) whenever the candidate's `language != "en"`.

Responsible for:

- PDF generation
- DOCX generation
- layout consistency
- export quality

---

# Testing

## pytest

Backend testing framework.

Used for:

- unit tests
- integration tests
- contract tests

---

## Vitest

Frontend testing framework.

Used for:

- component tests
- utility tests
- frontend business logic

---

# Deployment

Versions 1-3 ran entirely on the local machine (FastAPI + SQLite serving
a built React app, or `vite dev` + `uvicorn` in development) with no
production deployment target — the sections below on Docker/Nginx/etc.
still don't apply, since none of them are about *distributing* a local
app, only about *hosting* one as a network service.

## Tauri (Version 4 — desktop distribution, prototyped then dropped)

Version 4 explored a distributable **desktop installer**: wrapping the
existing React frontend + FastAPI backend unchanged in a native Tauri
window, with the backend frozen via PyInstaller and bundled as a Tauri
resource. It reached a working NSIS installer, verified end-to-end, but
the packaging (`frontend/src-tauri/`, `packaging/`) was later removed
from the codebase — see `docs/development_plan.md`'s Version 4 section
for the full history. Running the backend + frontend dev servers
(`dev.bat`) is the supported way to run the app now.

## Docker (optional dev convenience)

Not required to run Version 2 locally. Worth adding later only if
one-command local startup becomes a real friction point — not a blocking
deliverable of any Phase 13-20 item.

## Docker Compose — deferred

Only relevant once there's more than one service to orchestrate (e.g. a
real PostgreSQL server after a future hosted-stage migration). Nothing in
Version 2 needs it: SQLite is an embedded file, not a service.

## Nginx — deferred

A reverse proxy/TLS terminator matters once the app is reachable over a
network. Version 2 is localhost-only, so this has no role until a hosted
stage exists.

---

# Overall Philosophy

Each technology serves a single well-defined responsibility.

The stack prioritizes:

- simplicity over novelty
- maintainability over short-term convenience
- scalability without premature complexity
- strong typing across application boundaries
- clear separation between UI, business logic, AI infrastructure, and persistenceD