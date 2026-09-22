# Development plan

> This file tracks the **active** version in full phase-by-phase detail.
> Completed versions are collapsed to a short retrospective below and their
> full, unabridged phase detail is archived verbatim in `docs/archive/`:
> [`development_plan_v1.md`](archive/development_plan_v1.md) (Phases 0–12.3),
> [`development_plan_v2.md`](archive/development_plan_v2.md) (Phases 13–23),
> [`development_plan_v3.md`](archive/development_plan_v3.md) (Phases 24–31).
>
> Version 3 shipped 2026-09-04 (see its retrospective below). **Version 4
> was later discontinued** (2026-09-22): the project moved to a private/
> open-source model, and the Tauri desktop-installer packaging it
> describes below (`frontend/src-tauri/`, `packaging/`) was removed from
> the codebase. The phase-by-phase detail below is kept as historical
> record of that work, not a description of the current app — running
> the backend + frontend dev servers (`dev.bat`) is the supported way to
> run it now.

## Version 4 — Friend-testable Desktop App (Phases 4.1–4.11, DISCONTINUED)

Goal: turn the local-first web app into something a few non-technical
friends can actually install and use, to validate the product beyond the
author's own testing. Built on the `tauri-desktop-prototype` branch,
which already proved the underlying local-first architecture (per-user
SQLite, no centralized database — see that branch's
`frontend/src-tauri/PROTOTYPE_NOTES.md`) before this version's work
began.

Phases, in build order — packaging (4.1, 4.8) de-risked first,
deliberately, ahead of the feature-facing phases (4.2-4.7): it's both the
highest-uncertainty work (would PyInstaller even freeze this dependency
set? would a real installer actually work?) and the literal gatekeeper
for "can a friend install this at all," so proving it early meant the
rest of the plan wasn't designed around an untested assumption:

- **4.1 — Packaging spike: DONE.** Proved the backend's full dependency
  set (FastAPI, uvicorn, SQLModel, Alembic, ReportLab, python-docx,
  pypdf, google-genai) freezes cleanly via PyInstaller, verified against
  the actual frozen binary (not just "it compiled") — migrations, every
  export format, real HTTP traffic. Also fixed a real bug this surfaced:
  `frontend/src/api/client.ts` used a relative `/api` path that only
  resolves via `tauri dev`'s Vite proxy, never caught before because
  nothing had run a real `tauri build` yet. Full detail:
  `packaging/PACKAGING_NOTES.md`.
- **4.2 — Language field: DONE.** `Candidate`/`AssembledCV` got a
  `language` field (ISO 639-1, defaults `"en"` — no migration needed,
  `CandidateRow.data` is a schemaless JSON column). Resume ingestion
  detects it (`prompts/01_cv_parser_v1.md`); empty-profile creation takes
  it as an explicit request field. Threaded through all four generation-
  stage prompts (Matching, Rewrite Planning, Bullet Rewriting, Quality
  Recheck) via a new `language` field on each `contracts/schemas.py`
  request — every one always follows the candidate's own profile
  language, never the job description's. Live-verified against a real
  Gemini call, not just unit tests: ingested an actual Russian-language
  sample resume (`language` correctly detected as `"ru"`), then generated
  a tailored CV against an **English** job description — the resulting
  summary, bullets, and rewrite-provenance text all came back in Russian
  (confirmed programmatically: 694 Cyrillic characters vs. only expected
  Latin-script technology names like "Python"/"Docker"), proving the
  "candidate's language wins over the JD's language" behavior actually
  holds against a real model, not just the prompt text asking for it.
  7 new tests added across `test_candidate_service.py`,
  `test_cv_assembler.py`, `test_pipeline.py`, `test_api/test_candidates.py`
  (670 backend + 463 frontend tests passing).
- **4.3 — Header localization table: DONE.** A hand-synced EN/RU
  section-title mapping (`app/cv_locales.py` + `frontend/src/lib/sections.ts`),
  mirroring the existing `SECTION_TITLES` dual-implementation convention.
  Wired into every render surface that used to hardcode English titles:
  plain Markdown/PDF/DOCX export, the on-screen A4 preview/export document
  builder (`structuredDocument.ts`), and every Profile Explorer section
  (`EntityConfig.title` refactored to `EntityConfig.sectionKey`, resolved
  per-candidate by `ProfileView.tsx` since the config table itself is
  built once at module load, before any candidate/language is known).
  `ProfileHeader.tsx` and `ExportScreen.tsx` both show the profile's
  language (2.2's "state it plainly, no in-place translate" requirement).
  Found and confirmed correct rather than assumed: plain PDF export
  can't render Cyrillic at all (Base-14 Helvetica has no glyphs for
  it — confirmed by generating one and extracting the text, every
  Cyrillic character came back as a tofu box), a real, separate
  Phase 4.4 problem, *not* introduced by this phase — DOCX has no such
  limitation (OOXML text is just encoded XML, confirmed rendering
  correctly). Live-verified in the actual running app (Browser pane
  against the Tauri window's own dev server, not just unit tests): every
  one of the 13 section headings, the Profile page's "Language: Russian"
  line, and the Export page's language notice all render correctly for a
  real Russian-language candidate. 11 new backend tests, 9 new frontend
  tests. 681 backend + 472 frontend tests passing.
- **4.4 — Cyrillic font fixes: DONE** (implemented alongside 4.9 — the
  two turned out to be the same body of work once 4.9's browser-free PDF
  redesign meant touching `app/cv_pdf.py` directly anyway). Plain PDF
  export's Base-14 Helvetica (zero Cyrillic glyphs) replaced with vendored,
  registered DejaVu Sans (`app/cv_fonts.py`, `assets/fonts/` —
  Bitstream Vera-derived license, sourced from an ephemeral `matplotlib`
  install rather than adding matplotlib itself as a dependency); applied
  unconditionally, not just for Russian. Templated DOCX's Georgia/Geist
  fonts substitute to Calibri (ships with every modern Word install, full
  Cyrillic coverage) whenever `language != "en"`
  (`app/cv_templates.py::resolve_docx_template`) — Word silently
  substitutes an unavailable font with no error surfaced, so this doesn't
  gamble on Georgia's/Geist's actual Cyrillic coverage. Templated PDF's
  Cyrillic handling is 4.9's own job, since that phase rebuilt templated
  PDF's rendering entirely. Live-verified: generated real Cyrillic-content
  PDF/DOCX exports (all 3 PDF variants, all 3 DOCX variants) via direct
  API calls and extracted/inspected the actual output — every one
  round-trips Cyrillic text correctly, and templated DOCX confirmed using
  Calibri specifically. New tests in `test_cv_templates.py` and
  `test_cv_docx_templated.py` — combined backend test count for 4.4+4.9
  together noted at the end of 4.9's own entry below.
- **4.5 — File-upload ingestion: DONE.** `app/resume_reader.py` extended
  from txt/md/pdf to also accept DOCX (`python-docx`, already a
  dependency) and RTF (new `striprtf` dependency). RTF needed its own
  care: the raw bytes are decoded with `latin-1` (a lossless 1:1
  byte↔codepoint mapping) before handing the string to `striprtf`, so
  `\'XX` hex escapes survive intact for `striprtf` to decode per the
  file's own `\ansicpg` codepage declaration (e.g. `\ansicpg1251` for
  legacy Cyrillic Windows RTF) — verified against a real
  `\ansicpg1251`-declared sample, not assumed. New
  `POST /jobs/ingest-upload` route (`api/routes/jobs.py`, needed the new
  `python-multipart` dependency for FastAPI's `UploadFile`) extracts text
  synchronously in-request, then hands off to the exact same job/polling
  machinery `POST /jobs {"type": "ingest"}` uses — an extraction failure
  (unsupported type, unreadable file, no extractable text) surfaces as an
  immediate error response, not a "failed" job, since it's a
  request-validation problem rather than a mid-LLM-call failure.
  `IngestPanel.tsx` gained a second, independent path alongside paste —
  "Upload a file" opens a hidden file input (`accept=".txt,.md,.pdf,.docx,.rtf"`)
  wired to a new `useIngestUploadJob` hook (mirrors `useIngestJob`, but
  posts `FormData` via a new `apiFetchUpload` — deliberately does *not*
  set `Content-Type` itself, since the browser must compute the
  multipart boundary from the `FormData` body). `CandidateHomeScreen.tsx`
  runs both jobs side by side, each with its own status/error effects, so
  a failed upload never clobbers pasted text still sitting in the
  textarea or vice versa. Caught during test-writing, not live: jsdom's
  `userEvent.upload` itself enforces an `<input accept>` filter and
  silently refuses to attach a file whose extension isn't in the accept
  list — so a "server rejects this file" test has to use an
  accepted-looking extension (e.g. `.pdf`) and rely on the mocked
  backend response for the actual rejection, matching what a real OS
  file picker would do too. Live-verified against the real running
  backend and a real Gemini call (not just unit tests): uploaded a real
  `.docx` sample via `curl -F`, ingested correctly; uploaded a real
  `\ansicpg1251` `.rtf` sample with genuine Cyrillic content, both the
  extracted name/headline text and Phase 4.2's language auto-detection
  came back correctly as `"ru"`; an unsupported extension (`.xyz`)
  correctly 502'd with `ParsingError` before any job was created. Both
  test candidates deleted afterward, dev DB left exactly as found. 8 new
  backend tests (6 in `test_resume_reader.py`, 2 in `test_api/test_jobs.py`,
  plus reworking a test that used to assert `.docx` was unsupported), 11
  new frontend tests (2 in `client.test.ts`, 2 in `jobs.test.tsx`, a new
  `IngestPanel.test.tsx`, 2 in `CandidateHomeScreen.test.tsx`). 689
  backend + 483 frontend tests passing.
- **4.6 — Start screen, navigation, deletion: DONE.** The start screen's
  `CandidatePicker` dropdown replaced with a new `CandidateTable.tsx`
  (Name/Role/Language/Open/Delete — a table scales better than a dropdown
  once a friend has several profiles); `CandidatePicker` itself untouched,
  still backing `CandidateWorkflowLayout`'s compact header dropdown, where
  a table wouldn't fit. Backend prerequisite: `CandidateProfileSummary`
  (`app/candidate_registry.py`) gained `headline`/`language` fields (free
  reads off each row's own JSON blob, no extra query), `frontend/src/api/types.ts`
  regenerated against the live OpenAPI schema as its own step so `tsc -b`
  would catch any drift. Delete uses a grey button + `window.confirm(...)`
  — the codebase's existing convention (`EntitySection.tsx`'s
  `handleRemove`), no new dialog primitive — backed by a new
  `useDeleteCandidate()` hook; `DELETE /candidates/{id}` already existed
  end-to-end server-side, so this needed zero backend route changes. A
  second profile-creation path (3.2.2) — `CreateProfilePanel.tsx`, a
  name field plus a language dropdown limited to what `app/cv_locales.py`
  actually has labels for — calls the existing `POST /candidates` route
  with Phase 4.2's `language` field via a new `useCreateCandidate()` hook;
  no LLM call, so this is a plain mutation, not a job. "New Candidate"
  reachable from anywhere (4.1): `CandidatePicker` gained a
  `+ New Candidate` sentinel item (`NEW_CANDIDATE_OPTION`), and
  `CandidateWorkflowLayout`'s header dropdown branches on it to
  `navigate("/")` instead of to a candidate profile — reachable from any
  candidate-scoped screen (Profile, CV export), not just the start
  screen. Delete-loaded-profile (4.2): `ProfileHeader.tsx` gained a grey
  "Delete" button next to "Edit," same hook/confirm convention,
  `navigate("/")` on success since there's no "current" profile to fall
  back to once it's gone. Live-verified in the actual running app
  (Browser pane): created a real empty profile in Russian via the new
  form, confirmed it appeared in the table with the right Role/Language,
  confirmed "+ New Candidate" in the header dropdown navigates back to
  the start screen from a loaded profile, confirmed the table stays in
  sync after a delete. `window.confirm` itself can't be driven
  interactively in the sandboxed Browser pane (dialogs are silently
  auto-dismissed, a known limitation of automated browser testing, not an
  app bug) — the click-through confirm→DELETE flow relies on the unit
  tests' mocked `window.confirm` instead, and the DELETE route itself was
  confirmed live via a direct API call, with the table verified to drop
  the row on the next load. Test candidate cleaned up afterward, dev DB
  left exactly as found. 3 new backend tests, 21 new frontend tests
  (2 new component files — `CandidateTable.test.tsx`,
  `CreateProfilePanel.test.tsx`, `CandidatePicker.test.tsx` — plus
  additions to `ProfileHeader.test.tsx`, `CandidateHomeScreen.test.tsx`,
  `candidates.test.tsx`). 692 backend + 504 frontend tests passing.
- **4.7 — API key embedding: DONE.** The mechanism itself
  (`OBFUSCATED_GEMINI_KEY`/`decode_gemini_key()`/`XOR_PAD` in
  `frontend/src-tauri/src/lib.rs`, `packaging/obfuscate_key.py`, the
  `base64` crate dependency) was actually built during Phase 4.8's larger
  packaging restructuring — `resolve_backend_env()` already resolves
  `Some(decode_gemini_key())` in release mode and `None` in dev mode
  (falling through to a real developer `.env`), and
  `spawn_release_backend()` already sets it on the sidecar's env. This
  phase's real remaining work was closing a gap `packaging/PACKAGING_NOTES.md`
  flagged during 4.8: the obfuscate/decode round-trip itself was
  completely untested. Deliberately not called "encrypted" anywhere in
  the comments — a client-embedded secret can't be truly protected, since
  the app itself has to decode it at runtime and the decode logic ships
  in the same binary either way; real protection is a dedicated API key
  with a spend/quota cap set in Google AI Studio, outside this codebase.
  Added tests on both sides of the XOR+base64 scheme: 5 new Python tests
  (`tests/test_packaging/test_obfuscate_key.py`, invoking
  `packaging/obfuscate_key.py` via subprocess rather than importing it —
  this repo's `packaging/` directory isn't an installed package and would
  collide with the real, already-installed PyPI `packaging` library used
  by pip/setuptools) and 2 new Rust unit tests (`cargo test`, a
  `#[cfg(test)]` module in `lib.rs`) — one pair cross-checks the exact
  same known input produces the exact same output on both sides (proving
  Python and Rust still agree on `XOR_PAD` and the base64 alphabet — if
  they ever drifted, a shipped build's embedded key would silently decode
  to garbage instead of failing loudly), the other pair is a
  scheme-level round-trip independent of any hardcoded value. The
  embedded key is still the placeholder value (obfuscated from the
  literal `"REPLACE_WITH_REAL_GEMINI_API_KEY"`) — this session has never
  had, asked for, or handled a real Gemini API key, by design; before
  distributing a real build, run
  `packaging/obfuscate_key.py YOUR_REAL_KEY` yourself and paste the
  output into `OBFUSCATED_GEMINI_KEY`, with a spend/quota cap set on that
  key in Google AI Studio first. So friends never touch a console or
  paste a key. 5 new backend tests, 2 new Rust tests. 697 backend + 504
  frontend tests passing.
- **4.8 — Installer + uninstaller: DONE.** A real `tauri build` producing
  a working NSIS installer (chosen over MSI — MSI's default per-machine
  install requires admin elevation, confirmed by testing, a worse fit
  for non-technical friends), the full install → launch → real API
  traffic → close → uninstall → reinstall cycle verified on a real
  install, not just "the build succeeded." Five real bugs found live
  during this phase (an Alembic logging footgun that looked exactly like
  a hang, a dev-mode env-var regression, a wrong API base URL, missing
  CORS support for the packaged build's genuinely cross-origin requests,
  and an NSIS uninstall-hook context bug) — full forensic detail in
  `packaging/PACKAGING_NOTES.md`.
- **4.9 — Templated PDF, browser-free: DONE — scope changed from the
  original plan, with the user's explicit sign-off.** The plan assumed
  the only obstacle was bundling a Chromium binary; investigating turned
  up a second, deeper blocker the plan hadn't accounted for:
  `app/cv_pdf_playwright.py` worked by having headless Chromium navigate
  to the frontend's own print-preview page over HTTP
  (`http://localhost:5173/print/{id}` in dev) — but a packaged Tauri
  build serves its frontend via Tauri's own internal asset protocol, not
  real HTTP, so even a bundled Chromium would have had nowhere reachable
  to navigate to. Researched two no-browser HTML-to-PDF alternatives
  before deciding against both: wkhtmltopdf is archived (Jan 2023, no
  releases since 2020, an unpatched critical CVE, a Qt WebKit fork frozen
  around 2012-era CSS); WeasyPrint is actively maintained but still needs
  native Pango/Cairo/GDK-PixBuf libraries on Windows with no established
  PyInstaller-bundling precedent found — trading the Chromium-bundling
  problem for a different, equally uncertain one. Presented the actual
  choice to the user (defer the phase / bundle Chromium + a local static
  server / download Chromium on first use / go browser-free by extending
  the existing reportlab renderer) — chose browser-free.

  `app/cv_pdf.py` now has one shared flowable-building implementation
  (`_render_pdf`) parameterized by a `PdfTemplate` (font/bullet-char/
  section-spacing); `render_pdf` (plain) and the new `render_templated_pdf`
  both just supply different template values. `render_templated_pdf`
  reuses `app/cv_markdown.py`'s `render_sections_from_document` — the
  same edited-document-to-text bridge the plain PDF/DOCX paths already
  use — rather than re-walking `PrintDocument`'s grouping/subheading/
  page-break logic a second time the way templated DOCX's own
  `render_templated_docx` has to (DOCX needs real Word-native paragraph
  objects; reportlab's markup-based Paragraph model can already consume
  the same text shape the plain path does). This is what kept the actual
  addition small despite `render_templated_docx`'s own ~500 lines of
  accumulated grouping logic — none of it needed reimplementing.

  Removed entirely as dead weight once no longer needed: `playwright`
  (the Python package — `@playwright/test` was never actually added as a
  frontend dependency, despite `docs/technology_stack.md` describing an
  E2E-testing role for it that was never built), `app/cv_pdf_playwright.py`,
  the server-side print-session stash in `api/routes/export.py`,
  `domain.models.PrintSessionPayload`, `frontend/src/components/PrintPreview.tsx`
  (+ its boot-time route in `main.tsx`), and — found to be dead code once
  `PrintPreview.tsx` was gone, their only remaining consumer —
  `PrintExperienceSection.tsx`, `PrintSectionBlock.tsx`, and
  `lib/textRuns.tsx`. `app/config.py`'s `frontend_url` field (only ever
  used by the removed Playwright path) removed too. `CvPrintHeader.tsx`
  (still genuinely shared with the on-screen A4 preview) kept, with its
  stale Playwright-era comments corrected.

  A packaging-specific bug caught by review, not live testing (this
  machine's dev environment can't distinguish the two): `app/cv_fonts.py`
  initially resolved `assets/fonts/` via `Path(__file__)` — the one
  module in `app/`/`api/`/`domain/` that did, everywhere else already
  uses a CWD-relative path (`app/config.py`'s `prompts_dir`) specifically
  because PyInstaller's onedir freeze may bundle pure-Python modules into
  a compressed archive rather than loose files, where `__file__` isn't
  guaranteed to resolve to a real path. Fixed to match the established
  convention, and `packaging/build_sidecar.ps1` gained its own
  `--add-data "assets;assets"` PyInstaller flag (the actual, tracked
  source of truth — `cv-ai-backend.spec` is PyInstaller's own generated
  build artifact, gitignored, rewritten fresh by this script every build)
  so the packaged sidecar actually has the fonts to find.

  Live-verified against the real running backend (not just unit tests):
  generated all 6 real export combinations (plain/classic/modern × PDF/DOCX)
  for a Cyrillic-content candidate via direct API calls, extracted and
  inspected every one's actual text/font content — every PDF's bullet
  character matched its template exactly, every DOCX's Calibri
  substitution fired correctly; then repeated the classic-PDF export
  through the actual browser UI (DraftScreen's Export CV button, no
  gating/mocking) and confirmed a clean `200 OK` with no console errors.
  Test candidate/draft cleaned up afterward, dev DB left exactly as found.
  New tests in `test_cv_pdf_templated.py` and `test_cv_fonts.py`, plus
  additions to `test_cv_pdf.py`/`test_export.py`; net frontend test count
  *dropped* by 59 (510 → 451) — entirely from deleting genuinely dead
  test files for the removed Playwright-only components (`PrintPreview`,
  `PrintExperienceSection`, `PrintSectionBlock`, `textRuns`) and reverting
  the `VITE_TEMPLATED_PDF_ENABLED` gating this phase briefly added and
  then made unnecessary, not from losing real coverage. 4.4+4.9 combined:
  697 → 714 backend (+17), 510 → 451 frontend (-59, all dead-code
  removal). 714 backend + 451 frontend tests passing overall.
- **Post-4.9 fixes — found via the user's own live testing with a real
  Russian CV, both DONE.** Two real regressions Phase 4.9 introduced
  without either being caught by that phase's own (real, but not
  exhaustive-enough) live verification:
  1. **A bullet could split mid-sentence across a page boundary.**
     reportlab's default pagination lets a Paragraph tall enough to wrap
     onto two lines have *those lines* land on different pages — visible
     in a real export as a sentence cut off mid-word at the bottom of
     one page, continuing alone at the top of the next. Fixed by
     wrapping every bullet/line Paragraph (except the one already glued
     to its section heading) in its own single-item `KeepTogether`
     (`app/cv_pdf.py::_protect_lines_from_page_splits`) — matches the
     CSS `break-inside: avoid` rule the on-screen prediction already
     assumed held. Verified against the *exact* real sentence that broke
     (reconstructed from the reported PDFs), confirmed intact afterward;
     2 new structural tests plus the existing pagination suite.
  2. **The on-screen page-break guide's predictions were no longer
     accurate for anything** (worse for Cyrillic, but not exclusive to
     it) — its own code comment said plainly why it used to be valid:
     "calibrated against the exact same CSS Playwright's page.pdf()
     applies." That was true through 4.8; Phase 4.9 replaced templated
     PDF with a genuinely separate ReportLab renderer using different
     fonts (DejaVu vs. the on-screen preview's Geist/Georgia), so
     measuring the live DOM started measuring the wrong thing entirely —
     a real gap this session should have flagged when 4.9 shipped and
     didn't. Presented three fix options to the user (an honest
     disclaimer / re-measure using the real export fonts / ask the
     backend for real page breaks); chose the most accurate, most
     invasive one.

     Rebuilt as: `app/cv_markdown.py::iter_section_lines_with_ids` — a
     deliberately separate, parallel walk from `render_sections_from_document`
     (same convention as this codebase's other dual-implementation
     tables) that additionally tracks which `PrintDocumentEntry`/`Block`
     id(s) produced each line, for the sections where that's reliably
     single-valued (Summary, Experience, compact Skills/Technologies,
     every section's own heading) — the generic grouped-line sections
     (Contacts, Education, Certifications, Awards, Publications,
     Volunteer Experience, Portfolio Links) get section-level tracking
     only, since `SubheadingGroupMember` carries no id by design and a
     joined/grouped line can legitimately fuse several source entries
     with no single correct "owner." `app/cv_pdf.py::compute_page_breaks`
     builds the exact same flowables a real export would (tagged with
     those ids), runs them through a `SimpleDocTemplate` subclass that
     records which page each tagged flowable actually lands on
     (`afterFlowable`, confirmed empirically that it fires on a
     `KeepTogether`'s *inner* flowable, not the wrapper), then reports
     every point where the page number increases. New
     `POST /export/page-breaks` route exposes it.

     Frontend: `PageBreakGuide.tsx` rewritten to call that route
     (debounced 400ms, not on every keystroke) instead of approximating
     from `getBoundingClientRect()` measurements — `data-entry-id`/
     `data-bullet-id`/`data-section-key` attributes added to
     `EntryNodeView.tsx`/`BulletNodeView.tsx`/`SectionNodeView.tsx` so a
     returned element id can be found and positioned on screen. The old
     DOM-measurement module (`lib/tiptap/pageBreaks.ts`) is gone —
     nothing else depended on it. One deliberate scope cut from the old
     version: no more visual distinction between a *manual*
     `page_break_before` break (used to render solid, labeled "manual")
     and a predicted one — every break renders the same dashed style
     now; the backend has what's needed to restore that distinction
     later if it's missed.

     Live-verified two ways: (a) through the real running app — created
     a real 23-bullet Russian draft via the actual UI (real Gemini
     tailoring call, not seeded data), confirmed the on-screen guide
     showed exactly one break with a real, sensible computed pixel
     position; (b) closed the loop completely — fetched that *exact*
     draft's data via the API, called `/export/page-breaks` and
     `/export` (format=pdf) against it directly, and confirmed the
     predicted break element's bullet text ("...номер 12") is the
     *literal first line of page 2* in the real exported PDF, with page
     1 ending cleanly after "...номер 11" — an exact match, not an
     approximation. Test candidate/draft cleaned up afterward.

     714 → 735 backend tests (+21: `test_cv_markdown_line_ids.py`,
     `test_cv_pdf_page_breaks.py`, plus additions to `test_cv_pdf.py` and
     `test_api/test_export.py`). 451 → 431 frontend (net *-20*: deleting
     `lib/tiptap/pageBreaks.test.ts` — the old DOM-measurement module's
     own extensive test suite, no longer applicable — removed more tests
     than the 8 new ones added across `DocumentEditor.test.tsx`/
     `api/export.test.tsx` replaced it with; not a coverage loss, the
     same "dead code, dead tests" shape 4.9's own cleanup already had).
     735 backend + 431 frontend tests passing overall.
  3. **"Modern" template's role headers rendered bold on-screen but
     plain in the actual exported PDF** — reported after the page-break
     fix above, via a screenshot of a real export with the mismatch
     annotated. Root cause: `app/cv_fonts.py`'s DejaVu Sans (vendored
     from an ephemeral `matplotlib` install, Phase 4.4) only had
     Regular + Oblique faces available from that source — no true bold,
     so reportlab's `<b>` markup silently resolved to the regular face
     rather than erroring (confirmed directly via `reportlab.lib.fonts.
     tt2ps`). DejaVu Serif ("Classic" template) was never affected — its
     matplotlib bundle does ship a full four-weight family — which is
     why this went unnoticed until someone actually used the "Modern"
     template. Fixed by replacing DejaVu Sans with **Noto Sans**: Google
     Fonts ships it only as a variable font, so four static instances
     (Regular/Bold/Italic/BoldItalic, wght=400/700 wdth=100) were
     generated locally via `uv run --with fonttools fonttools varLib.
     instancer --update-name-table` from Google's own `google/fonts`
     GitHub source (SIL OFL 1.1, `assets/fonts/LICENSE_NOTO_SANS.txt`).
     `--update-name-table` turned out not to be optional: a first pass
     without it produced 4 files with correct, distinct weight/italic
     *axis* values but an unchanged internal PostScript name (inherited
     from the base variable font) — reportlab's own font-registration
     cache keys on that internal name, not the registered name or
     filename, so `NotoSans-Bold` silently aliased the exact same font
     object as `NotoSans` (Regular) underneath a distinct-looking
     registration. Caught by inspecting `pdfmetrics.getFont("NotoSans-
     Bold").face.filename` directly (it pointed at the Regular file) —
     `tt2ps('NotoSans', 1, 0)` resolving to the string `'NotoSans-Bold'`
     had looked like proof but only confirmed the family-table wiring,
     not that the underlying glyph data actually differed. Regenerated
     with the flag; confirmed via each file's `OS/2.usWeightClass`/
     `post.italicAngle`/internal PostScript name that the 4 instances
     are now genuinely distinct, and the exported "Modern" PDF's own
     content stream embeds `NotoSans-Bold` as its own subsetted
     `/BaseFont` (not a repeat of `NotoSans-Regular`) with different
     glyph advance widths. Both the
     plain/ATS-safe export and the "Modern" template now use it
     (`app/cv_fonts.py::register_pdf_fonts`, `app/cv_pdf.py`'s
     `PDF_TEMPLATES["modern"]`/`_PLAIN_TEMPLATE`); DejaVu Serif
     ("Classic") is untouched. Noto Sans's Cyrillic coverage was
     re-confirmed the same way DejaVu Sans's was originally. This also
     answered a second, related observation from the same report — that
     the exported PDF's font *family* looks different from the on-screen
     editor's (Geist Variable) — which is not a bug: templated PDF has
     been a genuinely separate, browser-free renderer since Phase 4.9
     (see fix 2 above), so it was never going to share the on-screen
     preview's exact webfonts; only the bold-*weight* gap was a real
     regression, now closed. Existing tests updated for the new font
     name (`test_cv_fonts.py`, `test_cv_pdf_templated.py`'s bold-markup
     test now asserts a real bold face resolves rather than documenting
     the fallback); 735 backend tests passing, no net count change
     (existing tests updated in place, not added).
- **4.10 — App stabilization: DONE.** Found entirely via the user's own
  live testing — generating real Russian-language drafts against real
  vacancies and reviewing every summary/bullet against the original
  Evidence text, one draft at a time, across many rounds in one sitting.
  Two categories of finding: localization/fabrication quality in the four
  tailoring prompts, and a UI bug plus three small features that came up
  along the way.

  **Localization and fabrication-by-keyword, `prompts/02_jd_parser_v1.md` /
  `04_rewrite_planner_v1.md` / `05_rewrite_bullets_v1.md` /
  `07_bullet_quality_recheck_v1.md`.** The recurring pattern across every
  round: a Requirement keyword forced into a bullet or the summary in a
  way that either fabricated a fact the Evidence never stated, or just
  read as unnatural, keyword-stuffed prose a person wouldn't write. Fixed
  the mechanism at its root rather than patching symptoms one at a time:

  1. **JD keywords forced into English regardless of the vacancy's own
     language.** `02_jd_parser_v1.md`'s keyword-extraction rule mandated
     English-style "Title Cased" output with only English examples, no
     language directive — so a fully Russian vacancy produced English
     canonical keywords ("Monetization Mechanics" instead of
     "Монетизационные механики"), visible directly in the frontend's own
     "Hard Skills" chip row (`JobDescriptionSummary.tsx`) sitting next to
     an otherwise all-Russian JD summary. Fixed to write keywords in the
     JD's own language and capitalization convention, with a carved-out
     exception for genuine industry English terms (LiveOps, Core Loops).
  2. **A taxonomy of seven fabrication-by-keyword variants**, found one
     real instance at a time and generalized into explicit rules (with
     concrete before/after examples) in both the Rewrite Planning and
     Bullet Rewriting prompts, each capped by "follow the Evidence instead
     of the `new_angle` every time": over-specific detail (a keyword
     asserting more precision than Evidence states), an invented
     collaborator/stakeholder, an invented genre/classification (including
     a genre generalization hedged as "often"/"typically" — exactly as
     much an unconfirmed assertion as "if applicable"), an invented
     systemic relationship (a feature framed as "part of" a larger system
     the Evidence never connects it to), an invented preceding method
     (crediting an unstated analytical process, or a specific tool/
     technology, for a result the Evidence only states the outcome of —
     found live via a fabricated "Excel" claim on a bullet that never
     mentioned it, sourced from the candidate's own Technologies list
     having zero Evidence backing), an invented job title/role (the worst
     offender: "Feature Owner" asserted as the candidate's own title
     across six bullets in three different roles, traced to the planner
     assigning a title-shaped Requirement keyword as an ordinary
     `target_keyword` with no cap — fixed by banning a title-shaped
     keyword from `target_keywords` entirely, not just capping its reuse),
     and collapsing ongoing/recurring work into a one-time creation (a
     Russian imperfective verb — "разрабатывала", ongoing/repeated —
     rewritten into a perfective one plus "from idea to launch," changing
     the claim from "iterated on this recurring mechanic" to "built this
     once").
  3. **Wording-quality issues distinct from outright fabrication**: a
     keyword-shaped "self-explaining tail" restating a categorical
     membership no reader needed spelled out (generalized past its first,
     too-narrow example — "part of the development lifecycle" — to the
     general test "does this clause say anything beyond confirming
     category membership," after the same shape recurred as "as part of
     feature development"); a same-concept tautology when a keyword's
     translation shares a root with a word already in the sentence
     ("мета-прогрессия" + "Meta Loops"); near-synonym list-padding that
     adds no real information ("игровых механик" → "игровых концептов и
     механик"); a keyword splitting one compound predicate sharing an
     object into two verb-object pairs, inventing a second deliverable
     ("developed [game concepts] and launched [format]" from a single
     "developed and launched [format]"); a misplaced modifier clause
     landing next to the wrong noun phrase; and forcing an already-correct
     idiomatic phrase into an awkward derived grammatical form to fit a
     restructured sentence ("анализ воронок" → "воронкового анализа").
     Also fixed a summary switching to third person with no rule against
     it (matching neither the candidate's own consistently first-person
     original nor the "About Me" convention the section header implies —
     far more conspicuous in a language with person-marked verb
     conjugation than in English).
  4. **The summary is structurally more fabrication-prone than a bullet**,
     since it's synthesized freely from the whole Evidence/Requirements
     set with no single `evidence_id` anchoring one claim the way a
     bullet has — found via a summary asserting a specific Unity
     prototyping skill (from a bare, evidence-less Technologies entry), a
     "cooperative games" genre claim (from one cooperative *event* inside
     a single title), and an invented "game scripts" mention traced
     straight to a Requirements keyword with zero Evidence anywhere. Root
     cause in the prompt's own wording: "grounded in the Evidence/
     Requirements" let a Requirement mentioning something read as half the
     grounding a claim needed — fixed by removing Requirements from the
     grounding list entirely (they select/emphasize among grounded facts,
     they never supply one) and adding the explicit checklist "for every
     tool/technique/genre named in the summary, ask which Evidence item
     says this, not whether the vacancy wants it."
  5. **`07_bullet_quality_recheck_v1.md` generalized past English-only
     pattern-matching** (its suspect-phrase list and every example were
     English, so it was structurally blind to the Russian-language version
     of the same tells) and gained two new defects as a safety net
     mirroring the fixes above: outcome buried behind the method (reorder
     to lead with the concrete result, not the mechanism), and repeated
     bullet openers within one role (the same keyword-derived phrase
     opening two different bullets, reading as duplicated content).

  **UI bug, `CvPrintHeader.tsx`.** The on-screen editable role-title field
  was a plain `<input>` — fundamentally single-line, so a long headline
  clipped/scrolled its overflow invisibly past the box instead of
  wrapping, while the read-only fallback and the server-side export (which
  never goes through this component) both wrapped correctly. Fixed by
  switching to a `<textarea rows={1}>` with `field-sizing-content` (grows
  to fit wrapped lines with no manual resize handler) and an Enter-key
  guard so it stays one logical line that happens to wrap.

  **New feature: the summary gets the same AI-edit affordance as a
  bullet.** Reported directly — a rewritten bullet shows a Sparkles
  button with original text/rationale/"Revert to original," but the
  summary (also freshly written every generation) gave no sign it wasn't
  copied verbatim from the profile. New `SummaryProvenance`
  (`domain/models.py`) alongside `BulletProvenanceReport`, populated only
  when there's a genuine, non-trivial edit to show; `EntryNodeView.tsx`
  gained the same Popover the bullet NodeView already had, gated to the
  one `summary` entry. One accepted, documented tradeoff: the gutter's
  Sparkles slot and its page-break-toggle slot share one visual position
  (previously never simultaneously occupied by any one row) — the summary
  is the first entry that can have both, and Sparkles wins the slot while
  showing.

  **New feature: real generation timing, live step progress, and a
  vacancy-reparse cache.** Asked for directly, after "how long does
  generation actually take" turned out to be unanswerable from existing
  data — the app only ever logged to stdout (never captured), and a
  `CVDraft`'s `created_at`/`updated_at` gap conflates editing time with
  generation time. Added `GenerationTiming` (`domain/models.py`), timing
  each of `run_cv_generation`'s five LLM stages plus the total, persisted
  onto `CVDraft.timing` the same durable way `provenance` already is.
  Live-measured against the real Gemini API (this repo's own configured
  key, run directly rather than through the separately-built desktop app):
  a full cold generation took **263.9s (~4.4 min)** — Rewrite Planning
  (66.7s), Bullet Rewriting (71.5s), and Quality Recheck (66.4s) together
  accounted for 77% of it, a direct, measured correlation with exactly the
  three prompts this phase's fabrication fixes grew the most; Matching
  (41.6s, untouched this phase) and JD Analysis (17.8s, touched lightly)
  were the two fastest stages. Also added `on_stage` progress reporting
  (`app/pipeline.py`) surfaced through `JobStatus.stage`/`stage_number`/
  `stage_count` (`api/routes/jobs.py`) to a live "Step N/6: <stage>" label
  on the Generate/Regenerate buttons, replacing a bare unexplained
  "Generating…" for the full multi-minute wait. Finally, `run_cv_generation`
  gained an `existing_vacancy` parameter: a Regenerate/Regenerate as New
  already has its own draft's previously-parsed Vacancy on hand, so JD
  Analysis is skipped entirely (reported as a distinct "Reusing previous
  job description analysis" stage label) whenever the vacancy text is
  unchanged — cutting one of the six stages from the common "re-tailor
  against the same JD" case. Deliberately not cached across an *edited*
  vacancy text, and deliberately caches unconditionally rather than
  invalidating on prompt changes (the user's explicit choice, made aware
  that a `02_jd_parser_v1.md` improvement won't retroactively affect a
  Regenerate against unchanged text).

  735 → 748 backend tests, 431 → 435 frontend tests. 748 backend + 435
  frontend tests passing overall.
- **Post-4.10 fixes — found via the user's own live testing, continuing
  the same real-draft review process, both DONE.** One implementation bug
  in 4.10's own new timing feature, and a second, deeper round of
  fabrication-by-keyword findings in the tailoring prompts — this time
  surfaced by deliberately testing a genuinely poor-fit vacancy (a
  Technical Game Designer role, Unity/scripting-heavy, against an
  economy/monetization-focused candidate profile), which put far more
  pressure on the anti-fabrication rules than the earlier, better-matched
  test vacancies had.

  1. **`GenerationTiming` was silently never persisted**, despite 4.10
     adding the field to `CVDraft` and having it work correctly in the
     in-memory `JobStatus` progress display. Root cause, found by tracing
     the write path rather than guessing at a stale build: `cv_draft` is
     one column per field (not a JSON blob), and `CVDraftRow` (`db/
     models.py`) never got a `timing` column; `CandidateService.
     add_cv_draft`/`update_cv_draft`/`_cv_draft_from_row` never read or
     wrote it either. Worse, `api/routes/entity_crud.py`'s generic
     factory builds a create-request's Pydantic schema from `add_cv_draft`'s
     own Python *signature*, not from the `CVDraft` domain model — so a
     real POST body's `timing` was dropped before it ever reached that
     method, silently, no error raised. Fixed all three layers (new
     Alembic migration `129f21ad6b02` adding the column; `add_cv_draft`
     gained an explicit `timing` parameter; the row↔model mapping copies
     it both ways) and added tests at both the service layer and the real
     HTTP create-route layer specifically — the latter is what would have
     caught the actual bug, since the service-layer fix alone can't prove
     the generated request schema accepts the field.
  2. **A live-testing distinction that mattered**: live progress on the
     Generate button (in-memory `JobStatus`, no persistence involved)
     working correctly was initially mistaken for proof the whole backend
     was rebuilt and current, when only the persisted `timing` value was
     actually stale — a reminder that partial evidence of "the new code
     is running" isn't evidence every piece of it reached the same code
     path.
  3. **Requirements matched only by Education were always a Gap.** Same
     class of bug 4.2's "candidate_skills/technologies/languages/
     certifications" fix (Phase 8.4, predates this version) already
     closed for those four — Education was simply never added when the
     other four were. A Requirement like "higher technical, mathematical,
     or economic education" was reported missing regardless of the
     candidate's real Education entries, because the Matching stage
     (`03_cv_jd_matcher_v1.md`) was never given them at all. Fixed
     symmetrically: `MatchRequest.candidate_education` (`contracts/
     schemas.py`), a new `_format_education` helper mirroring `ui/
     graph_explorer.py`'s own `_summarize_education` convention
     (`app/pipeline.py`, wired into both call sites — `run_cv_generation`
     and the standalone `run_gap_recheck`), and the prompt's own grounding
     rules and Input section updated to match.
  4. **A widespread, previously-undocumented tail pattern**: "в рамках X"
     ("as part of X"/"within the framework of X") turned up on 7 of 31
     bullets (23%) in one draft — the same self-explaining-tail failure
     4.10 already fixed, just generalized too narrowly (specific example
     wordings, not the underlying construction). Generalized the rule in
     both `05_rewrite_bullets_v1.md` and `07_bullet_quality_recheck_v1.md`
     to treat the construction itself as a default-suspect signal.
     Reduced to 1 of 30 bullets on the next generation, and that one
     instance traced to a genuinely-stated fact from the original Evidence
     phrased slightly differently, not a fabricated tail.
  5. **A deeper root cause, once traced through the planner's own stated
     reasoning**: two Evidence items about calculation-pipeline automation
     and balance-validation tooling both got a fabricated "...by writing
     scripts" claim attached, and the Rewrite Planning stage's own
     `reason` text admitted why — "rephrasing to explicitly indicate
     script writing, **to fill a gap in requirements**." Traced to
     `04_rewrite_planner_v1.md`'s own general instruction that Evidence
     backing a Gap "is a good rewrite candidate if the underlying fact
     could be **reframed to address that gap**" — technically already
     qualified elsewhere in the prompt, but vague enough at the point it's
     first stated that the model read it as license to invent the missing
     skill rather than only reframe an already-grounded one. Fixed by
     drawing that line explicitly in the rule itself: reframing changes
     emphasis on a fact Evidence already grounds; asserting a new skill/
     tool/technique because a Gap exists for it is fabrication, not
     reframing, regardless of which Evidence item it's attached to.
  6. **The most severe finding, and the reason for testing a poor-fit
     vacancy deliberately**: the tailored summary asserted "quickly
     prototypes in Unity" in the very same generation whose own Matching
     stage had just written "no explicit mention of fast Unity
     prototyping" for that identical Requirement — one pipeline stage
     directly contradicting the honest assessment another stage in the
     same run had already produced. Root cause: the Bullet Rewriting
     stage never received the Matching stage's own Gaps at all, so it had
     no way to know a claim was already flagged unconfirmed. Fixed
     architecturally, not with another wording example: `MatchResult.gaps`
     now flows into `RewriteBulletsRequest` (`contracts/schemas.py`,
     `app/pipeline.py`, `app/use_cases.py`), and `05_rewrite_bullets_v1.md`
     gained a new rule at the very top of its Rules section (overriding
     every instruction below it, including a `target_keyword`/`new_angle`
     that points toward a Gap) — plus the explicit principle that a poor
     overall fit calls for *more* discipline, not less, since the pressure
     to compensate by fabricating is highest exactly when the fit is
     worst. Re-tested against the same poor-fit vacancy afterward: the
     Unity/scripting/PC-platform fabrications were gone; one softer,
     single-word residual ("...which included creating prototypes," on an
     unrelated bullet, echoing an open Gap's topic in generic wording
     rather than its exact phrasing) survived, added as a further example
     to the same rule.
  7. **A meta-level fix once the same failure recurred under a new
     name**: with "в рамках X" banned, the model reached for a *different*
     generic connective phrase serving the same function ("используя
     технический дизайн для X") across three unrelated bullets. Rather
     than adding a third named-phrase example to an endless list,
     generalized the detection itself in both `05_rewrite_bullets_v1.md`
     and `07_bullet_quality_recheck_v1.md`: the signal is *any* connective
     phrase the model reused verbatim across 3+ otherwise-unrelated
     bullets, not a match against a fixed list of previously-seen
     phrasings — self-checking for one's own repetition generalizes to a
     phrase this document never happened to name. Confirmed working on an
     independent re-test: zero repeated-phrase patterns detected across
     32 bullets (checked programmatically, not just by eye).

  748 → 754 backend tests (new coverage: the `timing` round-trip at both
  the service and real-HTTP-route layers, `candidate_education` reaching
  the Matching stage from both call sites, and `gaps` reaching the Bullet
  Rewriting stage). No frontend changes this round. 754 backend + 435
  frontend tests passing overall.
- **Post-4.10 fixes, round 2 — generation latency: DONE.** Started from a
  direct complaint (~5 minutes per generation, 40-90s per stage with no
  sense of progress) and a question of whether the six prompts should be
  split per output language — they shouldn't, and weren't: each already
  uses one constant prompt template with a `$language` substitution
  (`app/use_cases.py` → `app/prompt_loader.py`), not per-language
  duplicates, so that wasn't the lever. `providers/gemini_provider.py`'s
  per-call logging (added this round, numbers-only per its own rule) is
  what turned "5 minutes, no idea why" into real, stage-by-stage evidence
  for everything below — and also durable for the first time: logs now
  also land in a rotating file under `data_dir/logs/app.log` (`app/
  logging_setup.py`), not just an ANSI console nothing captures.

  1. **`response_schema` (constrained decoding)** now goes to Gemini
     alongside `response_mime_type` instead of relying solely on each
     prompt's own "Output format" prose — the installed `google-genai`
     SDK converts a Pydantic response model directly. Zero regenerations/
     transient retries observed across every real generation run this
     round (new `regenerations`/`transient_retries` log fields exist
     specifically to keep tracking this going forward, not just for this
     round's own before/after).
  2. **The real latency driver, once `thoughts_token_count` was logged
     alongside prompt/response tokens**: gemini-2.5-flash's thinking
     budget was unset (`AUTOMATIC`/unbounded), and every one of the six
     stages was spending more tokens *thinking* than writing their
     actual, much shorter output — up to 6x, on the Bullet Rewriting
     stage. `generate_structured()` gained an optional `thinking_budget`
     parameter (`providers/base.py`, `providers/gemini_provider.py`) for
     callers to cap it per stage. JD Parsing and Quality Recheck — the
     two most mechanical stages — got `thinking_budget=0` outright:
     ~13-24s → ~5-10s and ~34-43s → ~6-10s respectively, confirmed
     consistently across five separate live regenerations, no quality
     regression found (Quality Recheck's one job — trimming
     self-explaining tails — kept working with thinking off).
  3. **Rewrite Planning and Bullet Rewriting** (the two reasoning-heaviest
     stages — Bullet Rewriting's own prompt, `05_rewrite_bullets_v1.md`,
     walks through seven separate fabrication-failure variants it must
     actively check for) needed real trial and error, not a single
     `0`. First try: both capped at 4096. Rewrite Planning showed no
     harm (its own `reason`/`new_angle`/`target_keywords` output looked
     no different) and kept that value. Bullet Rewriting at 4096
     produced two real regressions on a real generation, both confirmed
     by comparing the *same* Evidence item's output against the
     `auto`-budget run: a case-agreement grammar error ("когортного
     **анализе**, воронк**ах**" instead of "анализа, воронок") in a
     light-touch `"enhance"` bullet, and a genuine fabrication — "...
     учитывая принципы сетевых взаимодействий и синергии для
     кооперативных игр" added to a cooperative-event bullet whose
     Evidence never mentions networking or synergy at all, chasing an
     open Gap the Rewrite Planning stage's own `new_angle` admitted was
     "to close a gap" (exactly the situation `05_rewrite_bullets_v1.md`'s
     Rules section already says to follow the Evidence over the angle
     for — with only 4096 tokens of thinking room, it didn't). Bullet
     Rewriting alone moved up to a separate, higher budget — 8192 — and
     neither defect reproduced on a fresh generation against the same
     vacancy (one much milder, arguable case surfaced instead: tagging
     "Big Fish Games" as a "(ПК)" platform, a reasonable but
     Evidence-unstated classification). Settled: `_REWRITE_PLANNING_
     THINKING_BUDGET = 4096`, `_BULLET_REWRITING_THINKING_BUDGET = 8192`
     (`app/use_cases.py`). Matching stayed on `auto` throughout — see
     finding 4 below for why touching its budget wasn't attempted this
     round.
  4. **A real Matching-stage content-quality bug, found independently of
     the thinking-budget work while reviewing generation quality**: every
     freeform string field across a whole `MatchResponse` (`requirement_
     text`/`description`/`suggested_action`/`keyword`, 17 matches + 7
     gaps + 18 skills-to-add in one real generation) came back as the
     literal two-character placeholder `", "`, while the `strength`/
     `severity`/`evidence_ids` fields right next to them were genuine —
     `model_validate()` alone can't catch this, since a short non-empty
     string is a perfectly valid `str`. Added a generic, schema-agnostic
     detector (`_find_degenerate_placeholder_string`,
     `providers/gemini_provider.py`) keyed on nothing but "a non-empty
     string with zero letters/digits in it" — true of no legitimate
     content in any of this app's fields — wired into the same
     malformed-output retry loop `response_schema` mismatches already
     use. Applied to every stage, not just Matching, since the check is
     this cheap and this unlikely to false-positive on real content.
  5. **An unrelated live crash, found while stress-testing on a harder
     vacancy**: `IndexError` in `app/cv_pdf.py`'s `_render_body`,
     surfaced via the export screen's page-break calculation. Root
     cause: `CVProjection.summary` came back from Gemini with four
     leading newlines (`"\n\n\n\n Опытный..."`); every renderer downstream
     assumes one of these fields renders as exactly one line, and
     `compute_page_breaks`'s join-then-split-on-"\n" roundtrip turned
     that one summary into five lines against a `line_ids` list sized
     for one. Fixed at the boundary where the LLM's raw string becomes a
     validated domain object, not at each renderer: `CVProjection.summary`/
     `TailoredBullet.text` (`domain/models.py`) now collapse any run of
     whitespace (embedded newlines included) into a single space via a
     `field_validator`, so `AssembledCV`/`PrintDocument` — both always
     built from an already-validated `CVProjection` — never see the bad
     value in the first place.

  Net effect on the real, harder "Technical Game Designer" vacancy this
  round tested against throughout (see Post-4.10 fixes' own note on why
  that vacancy specifically): total generation time on the settings this
  round landed on (~242s) vs. the original all-`auto` baseline (~318s) on
  the same vacancy — about 24% faster overall, with JD Parsing and
  Quality Recheck individually 4x+ faster. Matching's own timing (84-340s
  across different runs on this vacancy, much higher than the 60-100s
  seen on an easier-fit vacancy) stayed unexplained variance, not
  something this round's changes touched or fixed.

  754 → 769 backend tests (new coverage: `response_schema`/`thinking_
  budget` plumbing through every provider layer, the degenerate-
  placeholder detector against both a synthetic schema and the real
  `MatchResponse`, and the two whitespace-collapsing domain validators).
  No frontend changes this round either.
- **Post-4.10 fixes, round 3 — re-check ignoring document edits, and
  severity blind to "nice to have": DONE.** Both found via the user's own
  live testing on a real draft (candidate `595187d6`, vacancy `25ef70cd`).

  1. **Re-check gaps never saw a hand-edited bullet's rewritten text, or a
     Skill/Technology added or deleted straight in the draft.** The user
     rewrote two Experience bullets by hand to cover a Competitor
     Analysis/Product Deconstruction/Market Research gap, re-ran Re-check
     Gaps, and watched the same gap resurface with the Hard Skills chip
     row still unhighlighted. Root cause: `run_gap_recheck`
     (`app/pipeline.py`) always matched against the stored Candidate
     profile's Evidence/Skills/Technologies, never the A4 document's own
     current content — `excluded_evidence_ids` (Phase 18) only let a
     toggled-*off* bullet drop out of matching, with no path at all for a
     bullet that stayed on but got its *text* rewritten, a hand-typed
     bullet with no `evidence_id` to key off of, or a Skills/Technologies
     line added/removed in the draft without touching the profile.
     `JobDescriptionSummary`'s Hard Skills highlighting (`lib/
     vacancySummary.ts`) derives from that same stale `missing_keywords`,
     so it inherited the bug for free.

     Fixed by carrying the document's own state into the recheck request:
     `frontend/src/lib/documentEvidence.ts` gained
     `collectEditedBulletText`/`collectManualBulletText`,
     `frontend/src/lib/structuredDocument.ts` gained
     `collectDocumentSkillNames` (reading back the flat name list from the
     Post-31 compact Skills/Technologies shape, with a defensive fallback
     for the pre-migration one-entry-per-skill shape), all wired into
     `DraftScreen.tsx`'s Re-check click and a new `RecheckDocumentContext`
     on `useRecheckGapsJob` (`api/jobs.ts`). `RecheckJobRequest`
     (`api/routes/jobs.py`) carries them to `run_gap_recheck`, which
     overrides each edited Evidence item's `.text` via `model_copy` (the
     stored Evidence itself is never mutated), folds hand-typed bullets in
     as synthetic, unpersisted Evidence items, and swaps in the document's
     own skill/technology name lists when given — falling back to the
     profile exactly as before when they're omitted, so no existing
     caller broke.

  2. **A "will be a plus" requirement could still be reported as a `"high"`
     severity Gap.** Same draft: "Active use of AI tools..." sat under the
     vacancy's own "Will be a plus:" heading, yet the Matching stage rated
     it `"low"` on the original generate and `"high"` on a later re-check
     with the requirement's own text completely unchanged — nothing
     grounded the severity call at all. Root cause: `Requirement`
     (`domain/models.py`) never captured whether the JD's own structure
     marked an item optional — an earlier, now-archived parser prompt
     (`prompts/archive/02_jd_parser.md`) had a `nice_to_have` list, but the
     current `02_jd_parser_v1.md` flattens every item into one
     undifferentiated `requirements` list, and `03_cv_jd_matcher_v1.md`'s
     severity rule only ever carved out stakeholder/relational and
     personality/disposition Requirements from `"high"` — nothing for an
     explicitly optional one.

     Fixed by adding `Requirement.priority` (`"required"` default |
     `"nice_to_have"`, defaulting to `"required"` so an already-persisted
     `Vacancy` never has a real Gap silently softened), teaching
     `02_jd_parser_v1.md` to set it only from the JD's own explicit
     framing (a "Nice to have"/"Bonus points"/"Will be a plus"/"Preferred"
     heading or equivalent inline phrasing — never from an item merely
     sounding less important), and adding a third severity carve-out to
     `03_cv_jd_matcher_v1.md`: a `"nice_to_have"` Requirement is capped at
     `"medium"` regardless of how unaddressed it is, independent of the
     two existing carve-outs. No `MatchRequest`/prompt-variable changes
     needed — `priority` rides along inside the same serialized
     Requirement object the matcher already receives.

  772 → 782 backend tests, 435 → 451 frontend tests. 782 backend + 451
  frontend tests passing overall.
- **Post-4.10 fixes, round 4 — Gemini 3.x compatibility, Matching-stage
  Contacts, headline tailoring, PDF link ingestion, and further JD-keyword
  accuracy: DONE.** Five more fixes on top of round 3's, spanning an
  external-API break, a further gap in what the Matching stage can see,
  and continued fabrication/precision cleanup in the JD parser.

  1. **`gemini-2.0-flash` (the old fallback default in `app/config.py`)
     was shut down by Google on 2026-06-01**, breaking any install with no
     `LLM_MODEL` set — including the packaged Tauri build, which ships
     with no `.env`. Bumped the fallback to `gemini-3.6-flash`, the model
     a fresh AI Studio project is currently steered to. That model also
     dropped the integer `thinking_config.thinking_budget` parameter (used
     by Rewrite Planning/Bullet Rewriting, the two stages with a nonzero
     budget — see round 2's finding 3 above) in favor of a `thinking_level`
     enum, which broke both stages with a bare `400 INVALID_ARGUMENT`.
     `GeminiProvider._generate_content_with_retry` now detects that
     specific rejection and retries once with `thinking_config` omitted
     entirely, falling back to the model's own default reasoning level
     rather than guessing a budget→level mapping for values that were
     tuned against `gemini-2.5-flash` specifically.
  2. **Matching stage still couldn't see Contacts** — the same class of
     gap Phase 8.4/round 3's Education fix already closed for four other
     flat profile fields. Reported directly: a vacancy requiring
     relocation, stated in the description, was flagged as a Gap even
     though the candidate's own Contacts held a directly on-point
     "Relocation" entry. Fixed with `MatchRequest.candidate_contacts`
     (`contracts/schemas.py`), wired from both `run_cv_generation` and
     `run_gap_recheck`, and `02_jd_parser_v1.md` now folds an adjacent
     relocation/visa/work-authorization sentence into the same
     `Requirement` as the location clause it qualifies, instead of
     silently dropping it. Follow-up privacy fix in the same commit: every
     raw Contact (email, phone included) was being sent to the LLM on
     every Matching call/recheck with no matching benefit for those two
     fields — `app/pipeline.py`'s new `_matching_contacts`/
     `_is_sensitive_contact_value` filter out any Contact whose *value*
     looks like an email address or phone number before the rest reach
     the prompt (matched on shape, not label); Resume Ingestion is
     unaffected and still sees the real values, since extracting them is
     genuinely its job.
  3. **Headline tailoring, PDF link ingestion, company/project links, and
     ingest UX** — one bundled commit spanning several related gaps:
     - `CVProjection.headline` is now generated fresh per vacancy by the
       Bullet Rewriting stage, grounded in the candidate's own evidenced
       seniority and never fabricated from the vacancy title alone —
       replacing the old behavior of copying `Candidate.headline`
       verbatim into every export regardless of fit.
     - `app/resume_reader.py` now reads a PDF's `/Link` annotations, so a
       hyperlink whose visible label isn't the URL itself (a company name,
       "LinkedIn," "Figma") is no longer silently lost; the parser resolves
       these onto new `Experience.company_url` / `ExperienceProject.url`
       fields and, with a description, `PortfolioLink` entries. Both
       render as real hyperlinks across plain Markdown/PDF/DOCX export, the
       live document editor (via a `TextRun`, since Markdown syntax embedded
       in plain text doesn't render on the frontend), and the Profile
       Explorer. `graph_writeback.py` strips a hyperlinked company/project
       name back to plain text before writing back, so hand-editing a
       linked entry can't corrupt it with literal `[text](url)` syntax.
     - Every PDF's extracted text is now flagged with a caveat about silent
       trailing-character truncation, and the parser refuses to guess a
       missing digit in a date/number from it — a dropped digit had
       previously been fabricated into a wrong, internally-inconsistent
       employment date.
     - `IngestPanel` supports real drag-and-drop (both a plain browser drop
       and Tauri's own native drag-drop event, which bypasses the DOM
       entirely) instead of falling through to the browser's default
       "open this file" handling; upload extraction now runs off the event
       loop so a pathological file can't block the whole server; the
       ingest/upload busy state moved onto the button actually clicked
       instead of a page-top status line.
     - Editor bug fix: `LinkHoverCard`/`FormattingBubbleMenu` now read
       editor state via `useEditorState` instead of a direct
       `editor.getAttributes()`/`.isActive()` read at render time —
       Tiptap's BubbleMenu doesn't necessarily re-render its children when
       the cursor moves between two spots that both keep it visible, so
       these were showing stale formatting/href from wherever the cursor
       last happened to force a re-render.
  4. **Two further rounds of JD-keyword accuracy fixes**, both rewriting
     `02_jd_parser_v1.md`'s keyword-extraction rule with concrete
     Accept/Reject examples instead of abstract descriptions (this stage
     runs with thinking disabled — see round 2 — so it needs examples to
     pattern-match against rather than open-ended judgment calls):
     - The parser was pulling company-side facts (a benefit like
       "relocation support," a bare location like "Berlin") into the Hard
       Skills keyword list as if they were candidate skills, and letting
       vague bare-word fragments ("Influence") through despite the
       existing skill-name-quality rule. Also fixed the matcher's
       relocation/location matching, which only recognized Contacts
       entries literally labeled "Relocation"/"Work Authorization" with no
       geographic-containment reasoning, so a "Location: ..., open to
       relocation within Germany" entry never satisfied an on-site-in-
       Berlin requirement even though Berlin is in Germany.
     - That first fix let a qualifier exempt an outcome word from
       rejection ("Stakeholder Influence" is fine) — the parser exploited
       the loophole by padding the bare "Influence" it kept extracting
       into "Direct Influence"/"Game Influence"/"Development Process
       Influence," still not something anyone would list as its own
       Skills-line entry, since almost any responsibility can be reworded
       as "influences X." Rejected the whole outcome/effect-word family
       (Influence, Impact, Ownership, Drive, Results) regardless of
       qualifier, contrasted explicitly with genuinely named practices
       like "Stakeholder Management" that describe what you do rather
       than the effect of doing it well.
  5. **Navigation redesign, three rounds of UI/UX feedback addressed
     together**: `CandidateWorkflowLayout`'s old Profile/CV-export tabs and
     buried "+ New Candidate" picker replaced with a sticky breadcrumb
     trail (Home / profile / draft title); the profile picker is inlined
     into the breadcrumb itself (a name link to Profile, plus a separate
     switcher chevron, since Radix `Select` doesn't fire `onValueChange`
     when reselecting the already-active value). The standalone CV export
     screen is gone entirely — its content ("Export without tailoring,"
     "Tailor to a job description," "Your drafts") now lives in a new
     `ProfileExportPanel`, a sticky rail next to the profile (the same
     pattern `DraftScreen`'s own action rail already used) so drafts are
     always visible instead of hidden behind an unlabeled "Export CV"
     button; the old `/export` route redirects to `/profile`. "Tailor to a
     job description" moved from an inline sidebar textarea into a modal
     (`TailorToJobDialog`) that always runs against one snapshot of the
     profile, blocking closing for the whole generation so an in-flight
     job can't get lost. Also fixed `VacancyPanel`'s textarea growing
     unbounded when a long JD is pasted (now a fixed height with its own
     scrollbar, in a wider dialog), and `DraftScreen`'s action rail sticky
     offset, which used to pin behind the new breadcrumb bar instead of
     clearing it.

  782 → 815 backend tests, 451 → 464 frontend tests (all passing). 815
  backend + 464 frontend tests passing overall.
- **4.11 — Friend rollout:** not started.

Two things worth carrying forward once this version ships: the embedded
`GEMINI_API_KEY` in the current build is a placeholder (no real key was
ever available during 4.1/4.8's work) and must be replaced before
distributing a build to anyone; the packaging build script has one
machine-specific hardcoded path (`packaging/PACKAGING_NOTES.md` has the
exact line) worth generalizing before a fresh clone elsewhere needs to
build it.

## Guiding approach

The full architecture (Career Graph, Evidence/Claim/Variant layers, multi-provider
gateway, structured-output validation, ATS-ready PDF export, etc.) is the target
end-state described in `architecture.md` and `domain-model.md`. Building all of it
before anything runs end-to-end is too much surface area for a first prototype.

Each version below thickens the working slice one layer/stage at a time rather than
building the target architecture up front. Phase detail for whichever version is
currently active lives in this file; once a version ships, its detail moves to
`docs/archive/` and this file keeps only the retrospective summary — see the three
summaries below for the pattern.

---

# Version 1 — Desktop Prototype (Phases 0–12.3)

**Shipped:** a working PySide6 desktop app running the full pipeline —
ingest → match/gap-analyze → plan → rewrite → assemble → export — end to
end against a single LLM provider (Gemini), with flat-JSON storage,
Markdown/DOCX/PDF export, and full CRUD over the Candidate Profile via a
Graph Explorer panel.

Built as a thin vertical slice first (Phases 0–6: single provider, flat
non-graph Candidate model, Markdown-only export, one-window UI), then
thickened one layer at a time: a real Organization→Role→Project→Evidence
graph for Experience (Phase 7, scoped to Project-nesting only —
`Organization` stayed a plain string), an explicit Matching + Gap Analysis
stage split out of the original one-shot generation call (Phase 8),
multiple Candidate Profiles (8.1), severity-ranked actionable gaps (8.2),
edit write-back from the generated CV into the graph (8.3), a Provider
Registry + fallback strategy (Phase 9, though no second concrete provider
was ever registered alongside Gemini), DOCX/PDF export (Phase 10), and a
polish pass (Phase 12) covering error-handling coverage, test-pyramid
gaps, the Graph Explorer UI itself, and several domain-model gap-fills
(Portfolio Links, Awards/Publications/Volunteer Experience/Technologies,
category-grouped AI-ranked Skills export).

**Deliberately deferred past this version:** Claims/Competencies/per-Evidence
Variants (a "semantic layer" domain concepts never needed to prove the
core loop), an AI Suggestions panel depending on it, and conflict handling
for write-back when the same Evidence diverges across CV versions.

Full phase-by-phase detail: [`docs/archive/development_plan_v1.md`](archive/development_plan_v1.md).

---

# Version 2 — Web App & WYSIWYG UX (Phases 13–23)

**Shipped:** replaced the desktop app with a browser-based single-user
local web app — React/TypeScript/Vite/Tailwind/shadcn/TanStack Query
frontend, FastAPI backend reusing `contracts/schemas.py` directly as
request/response models, SQLite via SQLModel/Alembic in place of flat
JSON — and rebuilt the editing experience from a flat "one Textarea per
CV section" form into a real WYSIWYG document.

Sequence: a backend-first migration with zero user-visible change (Phase
13: FastAPI routes, SQLite storage, async job-status endpoint replacing
`QThread`), then a feature-parity React shell proving the new stack end
to end (Phase 14), then an inline-editable, cross-linked Candidate
Profile page — Skill/Technology↔Evidence linking, split backend-then-frontend,
then split again into simple-entity CRUD vs. the novel Experience/bullet
cross-link interaction (Phase 15, 15a/15b-i/15b-ii). The core UX work
followed: an A4 print-CSS WYSIWYG document editor with drag-reorder and
section/bullet include-toggles, replacing the structured-document model
underneath (Phase 16); AI-edit transparency — inline diff/rationale
popovers on every LLM-edited block, with "revert to original" (Phase 17);
a re-evaluation loop letting a user re-run Matching against their *edited*
document and dismiss acknowledged gaps instead of them resurfacing (Phase
18); write-back, bullet locking, and LLM cost instrumentation (Phase 19);
persisted `CVDraft`s plus deterministic advisory checks — page-length,
bullet-count outliers, empty sections (Phase 20); a live, editable
drag-orderable Skills/Technologies category-header editor mirroring
Experience's structure (Phase 21); on-demand re-evaluation of stale
Skill/Technology↔Evidence links without a full resume re-ingestion (Phase
22); and a "CV export" screen offering export-as-is alongside the
original tailor-to-a-job-description flow, sharing one draft editor
(Phase 23).

Scope for this version was deliberately single-user/local throughout — no
auth, no multi-tenant storage, no hosting infrastructure.

Full phase-by-phase detail: [`docs/archive/development_plan_v2.md`](archive/development_plan_v2.md).

---

# Version 3 — Rich Text Document Editor (Phases 24-31)

**Shipped:** a local web application that can ingest a plain-text CV,
let the user edit the profile and save the data, and generate a
tailored, ATS-friendly CV in English with gap analysis and highlights of
the skills the user already has for a given job description — now edited
on screen through one real rich-text document instead of a stack of
independent `<Textarea>`/`<Input>` fields wearing CV styling.

Reworked the A4 editor's rendering/editing substrate onto Tiptap
(ProseMirror), keeping the structured-document model (section → entry →
bullet, `included`/`locked`/`kind` toggles) and the export pipeline's
overall shape unchanged underneath. Sequence: an exclude-to-stash panel
for manually-removed content (Phase 24), a rich-run (`TextRun`)
content model added to the backend/contract layer with no UI yet (Phase
25), the Tiptap adoption itself — one prerendered `contentEditable`
document functionally equivalent to the old editor (Phase 26), native
ProseMirror structural drag-to-reorder for sections/entries/bullets
(Phase 27, the largest real-bug hunt of the version — five rounds of
drag/scroll/cursor fixes only findable via live-instrumenting a real
running editor), a floating in-page gutter for the checkbox/Sparkles
AI-edit controls, several rounds refined against real user feedback
(Phase 28), an on-screen dotted page-break guide approximating the real
PDF export's pagination (Phase 29), a manual "start this section/entry
on a new page" override honored by every export path (Phase 30), and
selection-level rich formatting — a BubbleMenu for bold/italic/
underline/alignment/links across every section, plus a link
edit/hover card (Phase 31). A long tail of post-31 follow-ups closed
real gaps found through live use: Skills/Technologies collapsed into
compact, already-grouped entries as the stored (not just exported)
shape; several WYSIWYG mismatches between the on-screen editor and the
real PDF/DOCX export (font size, bullet markers, section spacing) found
and fixed; the AI-edit provenance popover repositioned to anchor
correctly against its own bullet; and per-draft CV headline editing in
place, directly on the A4 page.

Scope stayed single-user/local throughout, same as Version 2 — no auth,
no multi-tenant storage, no hosting infrastructure.

Full phase-by-phase detail: [`docs/archive/development_plan_v3.md`](archive/development_plan_v3.md).
