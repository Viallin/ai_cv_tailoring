# AI CV Builder

AI CV Tailoring Builder — create and manage a master CV, then tailor
different versions of it to specific job descriptions, in the CV's
target language. Currently supported languages: English and Russian.

See `docs/PROJECT_CONTEXT.md` for the product vision and
`docs/architecture.md` / `docs/domain-model.md` for the architecture.

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** — manages the Python environment and dependencies (no separate `pip install` needed)
- **Node.js 20+** and npm — for the frontend
- **A Gemini API key** — free, from [Google AI Studio](https://aistudio.google.com/apikey)

## Quick start (Windows)

```bash
git clone <this-repo-url>
cd cv-ai
uv sync --extra dev
cp .env.example .env
# open .env and paste your key into GEMINI_API_KEY=
uv run alembic upgrade head
cd frontend && npm install && npm run gen:types && cd ..
dev.bat
```

`dev.bat` opens two terminal windows (backend on :8000, frontend on
:5173) and launches `http://localhost:5173` once it's ready — that's the
app. Every step above only needs to be run once; after that, `dev.bat` is
the day-to-day way to start it.

On macOS/Linux (no `dev.bat` equivalent yet), do the same setup, then run
the two commands under "Getting started" below in separate terminals
instead of the last step.

## Features

- **Master CV**: ingest a resume (paste text, or upload a PDF/DOCX/RTF/TXT/MD file) into a structured Candidate Profile — a semantic career graph of experience, skills, education, and the evidence behind every bullet.
- **Tailor to a job description**: match the profile against a job posting, get a gap analysis, and AI-rewritten bullets — every edit stays visible and explainable, with one-click revert and the ability to lock bullets you don't want touched.
- **Rich-text editor**: a WYSIWYG A4 CV preview/editor (Tiptap-based) with drag-reorder, selection-level formatting, and an on-screen page-break guide.
- **Export**: plain ATS-safe or templated (Classic/Modern) PDF and DOCX, in the CV's target language — English and Russian currently supported.
- **Local-first**: single-user, runs entirely on your machine (SQLite, no hosting or account required).

Backend uses a single Gemini provider; the multi-provider registry/
fallback plumbing is wired up but OpenAI/Claude/Ollama implementations
aren't added yet. See `docs/development_plan.md` for the full
phase-by-phase development history.

## Getting started

The same setup as Quick start above, broken into individual commands —
useful on macOS/Linux, or if you want to run pieces separately (just the
API, just the tests, etc.) instead of `dev.bat`.

Backend:
```bash
uv sync --extra dev
cp .env.example .env   # fill in GEMINI_API_KEY
uv run alembic upgrade head            # create/migrate the local SQLite DB
uv run python -m scripts.migrate_json_to_sqlite  # one-time: import any data/candidates/ profiles from before Phase 13
uv run python main.py                  # legacy desktop UI — frozen since before Phase 13, not the maintained app
uv run uvicorn api.main:app --reload   # HTTP API — see /docs for OpenAPI
uv run pytest
```

Frontend (`frontend/`, needs the backend running for the type-gen step):
```bash
cd frontend
npm install
npm run gen:types   # regenerate src/api/types.ts from the running backend's OpenAPI schema
npm run dev          # Vite dev server on :5173, proxies /api/* to :8000 (see vite.config.ts)
npm run test         # Vitest
```

Once both are set up once (dependencies installed, `.env` filled in,
`src/api/types.ts` generated), `dev.bat` (repo root, Windows) starts both
dev servers in their own windows and opens `http://localhost:5173` once
Vite is ready — the day-to-day way to run the app, no need to repeat the
two blocks above every time.

## Layout

| Folder       | Purpose                                          |
| ------------ | ------------------------------------------------- |
| `api/`       | FastAPI HTTP layer (Phase 13) — routes only, no business logic |
| `app/`       | Config, logging, errors, prompt loader, use cases, resume reader, Candidate Profile, CV assembler |
| `contracts/` | Request/response schemas for LLM-backed use cases  |
| `db/`        | SQLModel table definitions + engine/session helpers (Phase 13) |
| `domain/`    | Core business entities (prototype scope)           |
| `frontend/`  | React/TS/Vite web UI (Phase 14+) — the actively developed UI, replaces `ui/`'s role |
| `prompts/`   | Version-controlled prompt templates                |
| `providers/` | LLM provider implementations behind `ILLMProvider`  |
| `scripts/`   | One-time ops scripts (e.g. the JSON->SQLite migration) |
| `ui/`        | Legacy PySide6 desktop UI (Phase 6) — frozen since before Phase 13, kept for reference only |
| `tests/`     | Unit / contract / provider / API tests (Python); `frontend/src/**/*.test.tsx` for the web UI |
| `docs/`      | Project documentation                              |

## Contributing

Bug reports, feature ideas, and PRs are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md) for how to get set up and run the
tests.

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
