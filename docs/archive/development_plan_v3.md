# Version 3 — Rich Text Document Editor (Phases 24-31): full phase detail

> Archived from `docs/development_plan.md` on 2026-09-04 when Version 3
> shipped, following the same split `development_plan_v1.md`/
> `development_plan_v2.md` already established — see
> `docs/development_plan.md` for the current summary and links to the
> other archives. This is the verbatim, unabridged Version 3 detail. (The
> heading below still says "Phases 24-30" as originally written when the
> version's own plan text was drafted; the version ultimately grew through
> Phase 31, plus several post-Phase-31 follow-up fixes, without the
> heading being updated at the time — same situation `development_plan_v2.md`'s
> own archive note already records for its own heading.)

# Version 3 — Rich Text Document Editor (Phases 24-30)

Phases 13-23 (Version 2) got the on-screen preview functionally complete
— toggle/reorder, AI-edit transparency, gaps, write-back — but the
editing surface itself is still a stack of independent `<Textarea>`/
`<Input>` fields wearing CV styling, not a real document. Confirmed
directly against the actual code, not just reported symptoms: no unified
cursor/selection across the page (`DocumentSectionBlock.tsx`/
`DocumentExperienceSection.tsx` render one form field per row);
checkboxes and the Sparkles AI-edit trigger sit inside the text flow
instead of an outside gutter; unchecking a block only strikes it through
in place instead of removing it from the page — and only AI-dropped
Evidence (`provenance.unused_evidence`) ever surfaces in a side panel
today, not manually-excluded content, which has no stash mechanism at
all; no visible page-break guide on screen (the pagination CSS from
Phase 16c is only ever exercised inside the headless-Playwright PDF
export, never the live editor); and no way to bold/italicize/link part
of a bullet — `DocumentBlock.text` is one plain string end to end, and
every renderer (`cv_docx.py`, `cv_pdf.py`, the templated Playwright
export) treats it as such.

**What stays:** `DocumentModel`/`PrintDocument*`'s section→entry→bullet
shape (`structuredDocument.ts`/`domain/models.py`), the
include-toggle→Unused-Evidence pipeline (extended, not replaced — see
Phase 24), the Sparkles provenance-popover concept, the export
pipeline's overall shape (Playwright screenshot for templated PDF/DOCX,
`cv_markdown.py`/`cv_docx.py`/`cv_pdf.py` for plain).
**What changes:** the rendering/editing substrate — one real,
prerendered, contentEditable document instead of N independent form
fields — and `DocumentBlock.text` grows an optional rich-runs
representation.

**Engine choice: [Tiptap](https://tiptap.dev/) (ProseMirror).**
Schema-enforced custom node types (sections/entries/bullets stay
structural, not arbitrary text), NodeViews for embedding React inside
the document (gutter icons anchored to real positions), a BubbleMenu for
selection-triggered formatting, and native browser cursor/selection/
Home/End/Ctrl+Arrow/PageUp-PageDown behavior for free — the two
next-most-obvious paths (hand-rolled `contentEditable` diffing, or
Slate) would mean building most of that from scratch. New frontend
dependency (`@tiptap/*`) — nothing in `frontend/package.json` currently
does rich-text editing; `@dnd-kit/*` stays for now (Phase 24 still uses
it) and is retired in Phase 26/27 once Tiptap's own drag primitives
replace it.

## Phase 24 — Exclude → stash panel (done)
Unchecking any block/entry/bullet removes it from the rendered A4 page
entirely (not struck-through in place, as before) and surfaces it in a
generalized side panel with a "restore" action. Sequenced first and
independent of every phase after it — no schema change (`included`
already existed on every `DocumentBlock`/`DocumentEntry` and already
persisted via the existing autosave), no new rendering engine needed,
shipped against the existing dnd-kit-based editor.

* New `frontend/src/lib/excludedContent.ts::collectExcludedContent`
  walks a `DocumentModel` and returns every individually-excluded entry
  or bullet by its own text — deliberately *not* keyed off Evidence
  (unlike `lib/documentEvidence.ts`'s Experience-only helpers), since
  most sections have no Evidence behind their entries at all (Skills/
  Education/Contacts/etc. were never Evidence-linked). Two scoping
  choices, both because the alternative already has a working restore
  path elsewhere: a fully-excluded *section* (`section.included ===
  false`) is skipped — its own checkbox stays visible right next to its
  heading regardless of `included` — and an excluded top-level entry
  (e.g. a whole Experience role) is listed once, not walked into; its
  nested bullets keep whatever `included` they already had and simply
  reappear alongside it once the entry itself is restored, since
  `toggleEntryIncluded` never touches them.
* New `ExcludedContentPanel.tsx` (new `Card` in `DraftScreen.tsx`,
  titled "Excluded from CV", next to Gaps) renders `collectExcludedContent`'s
  list with a "Restore" button per item; distinct from
  `UnusedEvidencePanel.tsx`, which still only ever covers Evidence the
  AI never put into the document at generation time.
* `DocumentSectionBlock.tsx`/`DocumentExperienceSection.tsx` now filter
  to `entry.included`/`bullet.included` before rendering — an excluded
  row no longer renders at all, and the `line-through`/`!included`
  styling paths in `SectionEntryRow`/`ExperienceEntryRow`/`BulletRow`
  were deleted outright rather than left dead. Each row's own checkbox
  is now always rendered checked (`checked={true}`), since an unchecked
  row is, by construction, no longer on screen to show a checkbox for.
  The section-level heading+checkbox is unaffected — still gated on the
  section's raw `entries.length`, not the filtered count, so a section
  stays visible (and toggleable) even once every one of its entries is
  individually excluded.
* `DocumentEditorHandle` (the existing ref-based escape hatch
  `UnusedEvidencePanel`'s "Add to Role" already used) gained
  `restoreContent(sectionKey, entryId, bulletId?)`, implemented by
  reusing the existing `toggleEntryIncluded`/`toggleBulletIncluded` —
  restoring is always flipping a currently-false flag back on, exactly
  what the toggle already does; no new mutation path. `DraftScreen.tsx`
  wires `ExcludedContentPanel`'s `onRestore` to it the same way it
  already wires `UnusedEvidencePanel`'s `onAddToRole`.

Verified: new unit coverage for `collectExcludedContent` (flat-section
entry, Experience bullet, excluded-role-not-walked-into, fully-excluded-
section-skipped) and `ExcludedContentPanel` (empty state, listing,
Restore click); `DocumentSectionBlock`/`DocumentExperienceSection` tests
updated to reflect the new filtering (excluded rows assert absent, not
struck through) plus new cases confirming the section heading survives
an all-excluded section; `DocumentEditor` gained two round-trip tests —
exclude via a real checkbox click, restore via the ref handle, for both
an entry and a bullet. Most conclusively, two new `DraftScreen`
integration tests drive the real component tree: unchecking a rendered
entry's checkbox removes it from the page and it appears in "Excluded
from CV" with a Restore button; clicking Restore on an already-excluded
item brings it back into the document and the panel returns to "Nothing
excluded from this CV." `npm run lint` and `tsc -b && vite build` both
clean. No backend changes, so the backend suite is untouched.

A live browser click-through (the usual final confirmation step for a
user-visible change) wasn't completed this pass — the Browser pane's
`navigate` action was intermittently unavailable during this session
(a tool-side condition, confirmed by retrying against the already-
running dev servers on repeated attempts, all denied before any page
loaded). Given the change is pure, deterministic DOM-rendering logic
with no LLM/network non-determinism involved, and the `DraftScreen`
integration tests above exercise the exact same component tree and
interaction sequence a live click-through would, this is left as an
opt-in follow-up rather than blocking the phase.

Full suite: 591 backend passed (unchanged — no backend code touched),
301 frontend passed (up from 280).

## Phase 25 — Rich-run content model (backend + contract), no UI change (done)
* New `domain.models.TextRun {text, bold=False, italic=False,
  underline=False, link: str|None}`; `PrintDocumentBlock` (and its TS
  mirror, `structuredDocument.ts`'s `DocumentBlock`) keep `text: str` as
  a plain-text fallback (search, ATS parsing, every draft saved before
  this phase) and gain optional `runs: list[TextRun] | None` —
  authoritative over `text`, and over any *default* block-level styling
  (an Experience role's automatic bold, a gap/project-heading's
  automatic italic), when present. Also added a per-block `alignment`
  attr (`"left"|"center"|"right"`), paragraph-level not a run, mirroring
  `python-docx`'s own `paragraph.alignment`.

> **Scoped to Summary + Experience this phase — every other section stays
> text-only in every export path, on purpose.** `render_templated_docx`'s
> Experience branch and `render_sections_from_document`'s Summary/
> Experience branches are the only places a `PrintDocumentBlock` maps
> 1:1 to its own paragraph; every other section (Education, Certs,
> Contacts, and Skills/Technologies' category lines) routes through the
> shared `group_entries_by_subheading` helper (used by *both*
> `render_sections_from_document` and `render_templated_docx`'s generic
> branch), which only ever carries plain `.text` — extending it to
> thread `runs` through a *concatenated* multi-entry line ("Category:
> item1; item2") is a materially harder problem than "render this one
> block's own runs," and nothing can produce a `runs`-bearing entry
> there yet anyway (no UI exists until Phase 31). The frontend
> (`PrintSectionBlock.tsx`) deliberately mirrors this exact scope rather
> than doing more just because it's cheap there (every ungrouped entry
> already renders as its own `<p>`) — `render_templated_docx` not
> supporting it for those sections would otherwise make the
> Playwright-screenshotted templated PDF visually diverge from templated
> DOCX for the same document, the recurring class of bug this codebase
> has repeatedly caught and fixed (see Phase 23's several addenda).

* Every renderer updated to honor `runs`/`alignment` within that scope,
  falling back to today's flat-string behavior otherwise:
  * `app/markdown_inline.py`: `InlineRun` gained `underline`; the
    `**bold**`/`*italic*`-only grammar gained `__underline__` and
    `[text](url)` — still no nesting, per the module's own stated scope.
  * `app/cv_markdown.py`: new `_serialize_runs`/`_block_markdown_text`
    turn a Summary/Experience block's `runs` back into that same tiny
    dialect (one-way only — nothing parses it back), so the plain
    DOCX/PDF path picks it up for free through the existing
    `parse_inline_runs` pipeline. Found from a real hand-crafted
    export, not anticipated in planning: two adjacent runs whose
    wrapped text meets at a bare `*`/`_` boundary (e.g. a bold run
    immediately followed by an italic one) concatenates into an
    ambiguous `***`-style sequence — fixed by inserting a zero-width
    space at exactly that boundary, invisible in every rendered output.
    Documented, deliberate limitation: a run with more than one of
    bold/italic/underline collapses to the highest-priority one
    (bold > italic > underline) *only* on this flat-text bridge, since
    `parse_inline_runs` has no nested-span support — the templated paths
    below have no such limit.
  * `app/cv_docx.py`: `_add_runs` (plain path) threads `underline`
    through; new `_add_paragraph_with_runs` (Experience-only in
    `render_templated_docx`) renders each run as its own real docx run —
    full simultaneous bold+italic+underline+hyperlink fidelity, since it
    consumes `TextRun` objects directly and never goes through text.
  * `app/cv_pdf.py`: `_runs_to_markup` wraps `<u>` for `run.underline`
    (skipped when the run is already a link, which gets its own `<u>`).
  * `frontend/src/lib/textRuns.tsx` (new): `renderBlockText` — the one
    shared renderer for both `PrintExperienceSection.tsx` (Experience,
    full support) and `PrintSectionBlock.tsx` (Summary only, via a
    `section.key === "summary"` branch in `renderEntryText`).
* `frontend/src/api/types.ts` regenerated (`npm run gen:types`) for the
  new `TextRun` schema; `api/models.ts` re-exports it.
* Verified: a hand-crafted `PrintDocument` (Summary + Experience role +
  bullet, mixing bold/italic/underline/a hyperlink) posted to the real
  running `/export` endpoint for all three non-Playwright formats —
  `.md` (raw dialect text, confirmed the zero-width-space fix directly
  in the byte output), plain `.docx` (via `python-docx`: correct
  bold/underline runs, single-priority italic+bold collapse exactly as
  documented, and a real hyperlink relationship), templated `.docx` (via
  `python-docx`: full simultaneous bold+italic on one run, confirming
  the templated path's fuller fidelity), and plain `.pdf` (via `pypdf`
  text + link-annotation extraction) — all four produced correct real
  files. The templated-PDF path (Playwright screenshotting
  `PrintExperienceSection.tsx`/`PrintSectionBlock.tsx`) was **not**
  live-verified this pass — the Browser pane's `navigate` action was
  intermittently unavailable for the whole session (a tool-side
  condition, not a code issue); its component-level test coverage
  (`PrintExperienceSection.test.tsx`/`PrintSectionBlock.test.tsx`)
  exercises the identical rendering logic, but a real Playwright
  screenshot hasn't confirmed pixels. Left as an opt-in follow-up.

Full suite: 616 backend passed (up from 591), 317 frontend passed (up
from 301).

## Phase 26 — Tiptap adoption: one prerendered document, functionally equivalent to today (done)
New dependencies: `@tiptap/core`, `@tiptap/react`, `@tiptap/pm`,
`@tiptap/extension-text`, `@tiptap/extensions` (v3's `UndoRedo` — the
`@tiptap/extension-history` package from v2 is now a thin deprecated
shim over it). Deliberately not `@tiptap/starter-kit` (bundles Heading/
Bold/lists/its own Document/Paragraph/Text — none belong this phase).
`@dnd-kit/*` stays in `package.json` — `EntitySection.tsx`/
`BulletRowsEditor.tsx` still use it for unrelated profile-CRUD lists;
only `DocumentEditor`'s own usage is retired.

* New minimal custom schema (`frontend/src/lib/tiptap/schema.ts`):
  `doc` (`section*`) → `section` (`entry*`) → `entry`
  (`entryHeading bullet*`) → `entryHeading`/`bullet` (`text*`).
  `entryHeading` is a 5th node beyond the four the phase's own plan text
  named — forced by a real ProseMirror constraint, not preference: a
  node's `content` expression can't mix inline text and block children
  directly, so `entry` needs a dedicated textblock child to hold its own
  heading/role-name text before its (optional) nested bullets, the same
  problem `prosemirror-schema-list`'s `list_item` solves with
  `content: "paragraph block*"`. `kind: "subheading"` stayed an **attr**
  on `entry`/`bullet` (not a distinct node type) — already an attr on
  `DocumentBlock`, and structurally a subheading is identical to a plain
  entry/bullet; only styling and the exclude-cascade rule differ.
* `frontend/src/lib/tiptap/converter.ts`: `documentModelToTiptapJSON`/
  `tiptapJSONToDocumentModel` — a total, lossless bijection with no
  per-section/per-kind special-casing (every optional `DocumentBlock`
  field maps 1:1 to a same-named node attr; empty text maps to
  `content: []`, since a ProseMirror text node can't hold `""`). One
  accepted, documented deviation: an entry's explicit `bullets: []`
  round-trips as an absent `bullets` key — functionally identical
  everywhere both are consumed, confirmed by a dedicated test.
* `frontend/src/lib/tiptap/commands.ts`: Enter inside a bullet creates a
  fresh sibling bullet (reset attrs — never a continuation of a
  subheading/evidence-linked/locked one); Enter inside an entryHeading
  splits the parent entry, modeled on `splitListItem` from
  `@tiptap/pm/schema-list`. Found empirically, not anticipated in
  planning: `splitListItem`'s own default is a plain positional split —
  content strictly *after* the cursor (which includes every bullet, not
  just trailing heading text) moves to the new node — the wrong default
  here, since a role's bullets still belong to the role *above* the
  cursor, not the new, still-untitled one below it; the command
  explicitly moves any bullets the library left on the new entry back
  onto the original. Backspace at the start of a bullet/entryHeading
  reuses ProseMirror's own `joinBackward` unmodified except two guards:
  never merge across a section boundary or into the entry's own heading
  line (bullet→heading), and never merge into/out of a `locked` (Gap)
  entry.
* `frontend/src/lib/tiptap/plugins.ts`: `idIntegrityPlugin` (an
  `appendTransaction` plugin — split commands deliberately leave
  `id: null` on a fresh node, this is the one place that mints the real
  `crypto.randomUUID()`) and `excludedSelectionGuardPlugin`. Excluded
  content (`included: false`) stays a real node in the ProseMirror doc
  rather than being deleted — `ExcludedContentPanel`/
  `collectExcludedContent` still walk the *full* `DocumentModel` — made
  invisible/unreachable by two layers: the NodeView hides it
  (`display:none` + `contentEditable=false`, best-effort — browsers
  refuse a native caret inside `display:none`, but that's a DOM
  convention, not something ProseMirror's own selection model enforces)
  and this plugin is the authoritative backstop, relocating any
  selection that still resolves inside an excluded node (or an excluded
  ancestor entry/section) just outside its range.
* NodeViews (`frontend/src/components/tiptap/*NodeView.tsx`) reuse
  `PrintExperienceSection.tsx`/`PrintSectionBlock.tsx`'s exact classes
  (`.cv-print-entry`, `.cv-print-bullet`) so on-screen typography matches
  the export target via the same `.cv-a4-page` CSS custom properties —
  closes the "not pixel-real" gap. `DocumentRow.tsx` is the one shared
  checkbox+text(+Sparkles) row both `EntryHeadingNodeView`/
  `BulletNodeView` use, mirroring `DocumentSectionBlock.tsx`'s old
  `SectionEntryRow` "one generic row" shape. `EntryNodeView` also grew
  the "+ Add Bullet" button (a real Tiptap-era regression risk avoided:
  it's easy to reproduce the read-only Print* rendering and forget the
  one piece of write-side chrome that has no Print* equivalent at all).
* A real, load-bearing architectural finding, not anticipated in
  planning: **React Context does not nest through NodeView boundaries.**
  The first pass had `SectionNodeView`/`EntryNodeView` each re-provide an
  ambient `sectionKey`/`entryId` via a nested
  `DocumentEditorNodeViewContext.Provider` for their own children — this
  silently never worked (`ctx.sectionKey` always read the top-level
  placeholder), because Tiptap's `ReactNodeViewRenderer` mounts *every*
  NodeView in the document as its own portal into one editor-wide React
  tree; a NodeView nested inside another NodeView's `contentDOM` at the
  DOM level is not a descendant of that other NodeView's own React
  component subtree. Found from two real failing tests ("+ Add Bullet"
  never rendering; toggling an entry's checkbox silently doing nothing).
  Fixed by deriving section/entry identity per-NodeView from the live
  ProseMirror document instead (`frontend/src/lib/tiptap/useNodeAncestry.ts`,
  walking ancestors from `editor.state.doc.resolve(getPos())`) — the
  shared context (`context.tsx`) now only carries genuinely
  editor-wide, non-positional data (`provenanceByEvidenceId`, the
  toggle/add-bullet/revert callbacks).
* `DocumentEditor.tsx` rewritten around two write paths into the same
  `DocumentModel` mirror: free-text edits (typing) are owned entirely by
  the live ProseMirror `EditorState`, read back via `onUpdate`; every
  other mutation (checkbox toggle, "+ Add Bullet", Sparkles "Revert to
  original", the `addBulletFromEvidence`/`restoreContent` imperative
  handle) still runs through the existing, untouched pure helpers in
  `structuredDocument.ts`, then gets pushed into the editor via
  `setContent(..., { emitUpdate: false })` — safe because these are all
  button-driven, no live cursor to preserve at that instant. Keeps
  `structuredDocument.ts` (and its existing test suite) the sole owner
  of the toggle/exclude-cascade/add-bullet business rules, fully
  untouched this phase. External `DocumentEditorProps`/
  `DocumentEditorHandle` interface unchanged — `DraftScreen.tsx` needed
  zero changes. Old dnd-kit-based `DocumentSectionBlock.tsx`/
  `DocumentExperienceSection.tsx` (and their tests) deleted, superseded.
* Deliberately scoped to whole-block text editing only — no
  partial-selection formatting (Phase 31), no structural drag-to-reorder
  (Phase 27; the `DndContext`/drag handles are gone along with the old
  row components, a real, expected regression until Phase 27 restores it
  with Tiptap's own drag primitives), checkboxes/Sparkles stay in their
  current inline position (Phase 28 moves them to a floating gutter).

Testing under jsdom needed a second real finding: Tiptap's
`ReactNodeViewRenderer` mounts each node's actual React content via a
*queued* portal, not synchronously within the triggering render — a raw
`contentDOM` placeholder briefly exists first (tagged
`data-node-view-content-react`, distinct from the real
`data-node-view-content` `<NodeViewContent>` itself sets). A synchronous
`getBy*` right after `render()`/`rerender()`/an `act()`-wrapped mutation
can catch that placeholder; every such query in `DocumentEditor.test.tsx`/
`DraftScreen.test.tsx` was changed to `findBy*` (which polls) for its
first touch of freshly-(re)mounted content. Separately, jsdom has no
`document.elementFromPoint`, which ProseMirror's own click-to-position-
cursor handling depends on — a raw `userEvent.click()`+type into the
contentEditable crashes; the one test that needed this
(`DraftScreen.test.tsx`'s autosave-debounce test) was rewritten to
trigger its edit via a checkbox toggle instead, which exercises the
identical debounce timing without depending on jsdom's contentEditable/
layout support at all. New dedicated schema/command/converter tests
(`frontend/src/lib/tiptap/{converter,commands}.test.ts`) drive a
**headless** `new Editor({extensions, content})` directly (no DOM event
synthesis needed — pure ProseMirror state transitions), calling the
exported command functions (`splitBulletSibling`/
`splitEntryHeadingSibling`/`handleBackspace`) directly rather than
simulating keystrokes; this is where every boundary rule and both guard
plugins actually get exercised.

Full suite: 616 backend passed (unchanged — no backend code touched,
this is a frontend editing-substrate swap only), 319 frontend passed (up
from 317; two files' worth of old row-component tests replaced by new
converter/command/DocumentEditor coverage). `npm run lint` and
`tsc -b && vite build` both clean (the production bundle grew to ~889 kB
gzipped 273 kB with Tiptap/ProseMirror included — noted, not addressed;
no code-splitting infrastructure exists in this app yet and setting one
up is out of scope for this phase).

Live-verified against a real draft (not just a fixture) via the Browser
pane: typed real text into a bullet (a genuine `execCommand('insertText')`
in a live Chromium tab, confirmed to land correctly), clicked "+ Add
Bullet" and confirmed a real empty bullet appeared, toggled a section's
checkbox off and back on and confirmed its content actually disappeared/
reappeared (and that a fully-excluded section, correctly, never appears
in the "Excluded from CV" panel — only its own header checkbox
represents that state), confirmed zero console errors and every autosave
PUT round-tripped 200 OK throughout. This exercised the real backend/DB,
not a mock — the draft used for this pass (`a916453c`) was left with one
harmless test bullet ("Verified live Tiptap typing.") under its first
Experience role from this verification pass; delete it from the UI if
undesired.

## Phase 27 — Structural drag-to-reorder, hover-only handles (done)
Native ProseMirror node dragging, not a redraggable-row library:
`section`/`entry`/`bullet` NodeSpecs (`lib/tiptap/schema.ts`) gained
`draggable: true`. The browser only *starts* a drag from an element
that itself carries the real HTML `draggable` attribute — set only on a
small hover-revealed handle (new `components/tiptap/DragHandle.tsx`,
`GripVertical` from `lucide-react`, same icon the old dnd-kit rows
used), never the NodeView's own root, so grabbing text elsewhere still
just selects it. The `dragstart` event bubbles to the editor root,
where ProseMirror's own handler resolves which node to grab from the
drag position, walking up to the nearest ancestor whose *type* has
`draggable: true` — `entryHeading` deliberately never gets it, so
grabbing anywhere inside an entry (including its heading) always drags
the whole entry, heading and bullets together. `Dropcursor` (from
`@tiptap/extensions`, already an installed dependency since Phase 26 —
no new one needed) renders the drop-position line, added to
`DocumentEditor.tsx`'s extension list configured with `var(--primary)`
to match the checkbox's own checked-state color.

Hover-only via Tailwind's `group`/`group-hover:opacity-100 opacity-0`
(space always reserved, never conditionally unmounted, so hovering
never shifts layout) — `DocumentRow.tsx` gained an optional `dragHandle`
slot alongside its existing `sparkles` one (`EntryHeadingNodeView.tsx`/
`BulletNodeView.tsx` both pass one); `SectionNodeView.tsx`'s header row
gets its own, since it has no entry/bullet text row to share that
layout with. The CV header (name/contacts,`CvPrintHeader.tsx`) needed
no handling at all — it's plain React rendered as a sibling of
`<EditorContent>`, never part of the ProseMirror doc, so it was already
unreachable by drag logic before this phase touched anything.

New `dragScopeGuardPlugin` (`lib/tiptap/plugins.ts`, same
`appendTransaction`-revert style as Phase 26's `idIntegrityPlugin`/
`excludedSelectionGuardPlugin`) enforces the one restriction the schema
alone doesn't know about: entries stay within their own section,
bullets within their own entry — same restriction the pre-Phase-26
dnd-kit editor enforced ("cross-section drags unsupported"), since a
section's entries and another section's entries hold structurally
different kinds of content. Compares every existing entry's/bullet's
parent identity before and after a transaction; if any changed (only
possible via a drag — every split/join path in `commands.ts` already
stays within-section/within-entry by its own Backspace guards), reverts
the transaction wholesale (`tr.replaceWith(0, size, oldState.doc.content)`).
Section-level drags have no such guard at all — reordering sections
relative to each other is this phase's actual new capability; confirmed
first that section order is genuinely meaningful end-to-end, not
cosmetic — `app/cv_markdown.py::render_sections_from_document`,
`app/cv_docx.py::render_templated_docx`, and `PrintPreview.tsx` all
iterate `document.sections` in array order, not a fixed `SECTION_KEYS`
order.

`reorderEntries`/`reorderBullets` (`structuredDocument.ts`, dead code
since Phase 26 dropped their only caller) deleted along with their
`moveItem` helper and their two tests — a drag is a live, continuous
native interaction with no discrete `fromIndex`/`toIndex` call site to
make, so (like keystrokes already do) ProseMirror performs the move
directly and `DocumentEditor.tsx`'s existing `onUpdate` reads the
result back; no array-splice helper is needed at all anymore.

New `lib/tiptap/plugins.test.ts` drives a headless `Editor` (same
pattern as `commands.test.ts`) with hand-built delete+insert
transactions standing in for what a real native drag would dispatch —
the plugin only ever inspects the resulting document, not how a
transaction was produced, so this is a faithful, DOM-free test of the
actual guard logic: same-section entry moves and same-entry bullet
moves are allowed, cross-section/cross-entry ones are reverted
wholesale, and a whole-section reorder (the new capability) is allowed
unconditionally.

Full suite: 616 backend passed (unchanged — no schema/API change this
phase), 322 frontend passed (up from 317: 2 tests removed with
`reorderEntries`/`reorderBullets`, 7 added — 5 in `plugins.test.ts`, and
2 stale comments elsewhere updated to stop citing the now-deleted
functions). `npm run lint` and `tsc -b && vite build` both clean.

**The first verification pass here was wrong to call this done** — the
Browser pane couldn't compose a real trusted drag (`computer`'s
`screenshot`/`left_click_drag` failed outright, and a JS-dispatched
`DragEvent` never populates `dataTransfer` — real browsers gate native
DnD behind `isTrusted: true`), so this shipped on unit tests plus
structural checks (handles present, zero console errors) alone. The
user then tried it for real and reported it precisely: dropcursor shows
while dragging, cursor never becomes a grab hand, and releasing does
nothing — for *every* level, bullets included.

What followed was four rounds of real bugs, found by combining the
user's own screen recordings/console logs from real gestures (this
tooling still can't perform a trusted native drag) with direct
instrumentation of the real running editor instance (temporarily
exposed as `window.__dbgEditor`, removed again once this phase was
actually done) — mousedown/dragstart/drop dispatched as real (untrusted)
DOM events against it, which exercises the app's and ProseMirror's own
code faithfully even though the *browser's* native drag-initiation
itself can't be triggered this way:

1. **`display: contents` broke coordinate resolution.**
   `EntryNodeView.tsx`'s `NodeViewWrapper` used `className="contents"`
   (chosen in Phase 26 purely to avoid one extra `<div>` layer) — a
   `display: contents` element generates no box at all, and
   `view.posAtCoords()` (which the native drop handler depends on
   entirely to find where to insert the dragged node) relies on rect
   comparisons to decide which child NodeView a point falls inside; with
   a zero-rect ancestor in the way it couldn't descend past the entry
   level, so every drop computed the same (already-correct, for a
   same-entry move) position and inserted nothing. **Fix:** dropped
   `display:contents` — `NodeViewWrapper` is a plain, box-generating
   `<div>` now. Necessary, not sufficient — the user retested and it
   still didn't work, for any level.
2. **A mousedown landing on the icon, not the handle.** The `GripVertical`
   SVG's own `<circle>` primitive was absorbing the mousedown target
   instead of the wrapping `<span>`. **Fix:** `pointer-events-none` on
   the icon.
3. **Missing `data-drag-handle`.** Tiptap's own `NodeView.stopEvent()`
   (`@tiptap/core`) only recognizes a `[data-drag-handle]` element as a
   legitimate custom handle at all. Real, required — but adding it alone
   produced a byte-for-byte identical failure log, so it wasn't the
   actual blocker for what the user was seeing.
4. **The real blocker, for entry/section drags specifically: ProseMirror's
   own `nearestDesc`-based position resolution stops at the *nearest*
   NodeView ancestor of a click and never continues further up if that
   one isn't `draggable`.** An entry-level handle physically living
   inside `EntryHeadingNodeView`'s own DOM always resolved to
   "entryHeading, not draggable" and ProseMirror silently gave up
   (`view.input.mouseDown.mightDrag` never populated — confirmed via a
   diagnostic script the user ran during a real gesture and pasted back).
   **Fix, first attempt:** an explicit `onDragSelect` prop on
   `DragHandle.tsx`, called from `onMouseDown`, wired by every caller to
   `editor.commands.setNodeSelection(pos)` for *their own* correct
   draggable ancestor — this exploits `handlers.dragstart`'s own priority
   order (it checks the *current selection* against the click position
   before ever falling back to nearestDesc-based guessing). Fixed bullet-
   and section-level dragging outright (confirmed via a full simulated
   mousedown→dragstart→dragover→drop sequence against the live editor,
   each immediately undone).

**Entry-level dragging then destructively corrupted a real draft during
this same verification pass** — worth recording plainly rather than
folding into the bullet list above. `onDragSelect` alone wasn't enough
for `entry`, and the two-bug chain behind it is why the entry-level
handle no longer lives inside `EntryHeadingNodeView.tsx` at all (see
`schema.ts`'s `TiptapEntryHeading` and `EntryNodeView.tsx`'s own
comments for the full mechanism):

- Tiptap's `stopEvent()` only tracks the mousedown→dragstart handoff
  that keeps it from swallowing the `dragstart` event for a NodeView
  whose *own* node type is draggable — `entryHeading` wasn't, so
  `dragstart` never reached ProseMirror's real handler at all.
- Separately, and worse: `@tiptap/react`'s `NodeViewWrapper`
  unconditionally wires *every* NodeView's own `onDragStart` (used to
  build the native drag image) to the DOM's `onDragStart` prop, no way
  to opt out. That handler bails out only if the event target is inside
  *that NodeView's own* `contentDOM` — true for `entry` (the handle,
  nested inside entryHeading, is inside entry's contentDOM) but false
  for entryHeading itself (the handle sits in *its* chrome, outside its
  own much-smaller contentDOM) — so entryHeading's onDragStart ran
  unconditionally, calling `NodeSelection.create(doc, this.getPos())`
  and silently overwriting the correct whole-`entry` selection with one
  scoped to just entryHeading, moments before the real drop handler read
  it.

The resulting drop was captured as one transaction combining a delete of
the (now wrong, narrow) selection with an insert of the slice captured
*before* the corruption — net effect: the dragged entry's own heading
text got deleted in place, and a duplicate copy (with a freshly
regenerated id, courtesy of Phase 26's `idIntegrityPlugin`) landed at
the drop target. This happened against the user's real, live draft
during a live-instrumentation test in this session and autosaved before
being caught. **It was fully repaired** — the exact original heading
text was recovered from an earlier successful fetch in the same
session, the duplicate entry (identifiable by its fresh non-`exp-N` id
and empty bullet list) was deleted, both applied as one transaction and
confirmed against a fresh page reload — but it's recorded here because
it's a real lesson, not just a bug: **live-instrumenting a running app
against a user's actual data is not risk-free**, even when every
individual step looks read-only or reversible; a "move" that turns out
to secretly be "delete + insert-a-stale-copy" is exactly the kind of
failure that doesn't show up until you check the *content*, not just
the *shape*, of the result.

**Fix:** restructure, not patch — the entry-level checkbox + drag handle
moved out of `EntryHeadingNodeView.tsx` entirely and into
`EntryNodeView.tsx`'s own chrome (a sibling of `<NodeViewContent>`,
absolutely positioned to overlay where the heading row visually starts;
`EntryHeadingNodeView.tsx`'s own `<p>` gets a matching `pl-12` to
reserve the same space). This is exactly how `SectionNodeView.tsx`
and `BulletNodeView.tsx` already had their own handles — chrome for a
draggable node has to live inside *that node's own* NodeView, never a
child's, for either of Tiptap's drag mechanisms (`stopEvent()`,
`onDragStart`) to behave correctly. `entryHeading` no longer needs (and
no longer has) `draggable: true` or any chrome of its own at all — both
failure modes traced to the same structural cause, and moving the
handle fixes both simultaneously rather than patching each symptom.
One accepted UX tradeoff: the entry's own `group` hover-scope now spans
the whole entry (all its bullets), not just the heading row — hovering
any bullet reveals the entry's own handle floating at the top, since
scoping hover strictly to the heading row would need a `:has()`-based
cross-branch query (the handle and heading text are now siblings in
different DOM subtrees, not parent/child). Three existing tests
(`DocumentEditor.test.tsx` x2, `DraftScreen.test.tsx` x1) queried the
entry's checkbox `within(heading)` — updated to query from the entry
container's parent instead, matching the new DOM shape.

Re-verified end to end after the fix, via the same live-instrumentation
technique (mousedown→dragstart→dragover→drop, each immediately
followed by `undo()`, against the same real draft): bullet, entry, and
section drags all now set the correct `NodeSelection` at mousedown,
correctly populate `view.dragging` (previously `null`/`undefined` for
entry) at dragstart, and produce a genuine, non-destructive move on drop
— an entry moved to a new position with its full heading text and all
bullets intact, confirmed both against the live document and, after
reload, against the persisted server-side state. Full suite: 322
frontend passed, `tsc -b` and lint both clean.

**A real mouse-driven drag in an actual browser is still the one thing
this session's tooling can't perform** — the Browser pane still can't
composite frames for `computer`'s coordinate actions, so every fix above
is confirmed via direct instrumentation of the real running editor
(measured against live DOM/ProseMirror state, including a genuine
document mutation and its correctness, not just a structural check)
rather than an actual recorded mouse gesture.

**Follow-up, reported once dragging itself finally worked:** no way to
scroll while a drag was held, making it impossible to drop anything
before/after a long section (Experience) whose target position was
off-screen. Root cause: a browser's own built-in "auto-scroll near the
viewport edge during a drag" behavior is tied to the *default* action of
the `dragover` event — and `prosemirror-view`'s own core `dragover`
handler unconditionally calls `event.preventDefault()` (required for a
drop to be accepted at all), which silently disables it. New
`createDragAutoScrollPlugin`/`DragAutoScroll` (`lib/tiptap/plugins.ts`,
added to `DocumentEditor.tsx`'s extensions) drives `window.scrollBy`
directly via a `handleDOMEvents.dragover` hook (returns `false`, so
ProseMirror's own handler — and Dropcursor's positioning — still run
afterward) — scrolls the *window*, not an inner container, since this
app has none for the editor itself (`DraftScreen.tsx`'s only
`overflow-y-auto` is the sidebar). A `requestAnimationFrame` loop, keyed
off the last known `clientY` rather than re-triggered per `dragover`
event, keeps scrolling smooth even though `dragover` doesn't fire at a
guaranteed rate; `dragend`/`drop` stop it, and the Plugin's own `view()`
`destroy()` hook stops it on unmount too. A factory
(`createDragAutoScrollPlugin()`), not a module-level singleton like the
three guard plugins above — this one holds real mutable state (the
in-flight frame handle) that must not leak across separate `Editor`
instances.

Verified two ways: `computeAutoScrollDelta` (the pure "how close to
which edge, how fast" math) directly unit-tested (`plugins.test.ts`, 4
new cases — zero in the middle, correct sign/magnitude near each edge,
zero exactly at the threshold). The full `dragover`→scroll mechanism
verified live against the running editor: a real `dragover` DOM event
correctly invokes the handler and schedules a frame (confirmed via
`requestAnimationFrame` call interception) — but the frame itself never
fires in this environment, since the Browser pane's "not compositing
frames" limitation (the same one blocking `computer`'s `screenshot`)
applies to `requestAnimationFrame` too, not just `screenshot`. Worked
around by capturing the scheduled callback and invoking it manually,
standing in for "the next real frame": confirmed `window.scrollBy`
fires with the correct sign and magnitude near both edges, and that
`dragend` correctly leaves a still-queued frame as a no-op (doesn't
reschedule) rather than only preventing *future* scheduling. Full
suite: 326 frontend passed (up from 322), `tsc -b` and lint clean.

**Follow-up #2, reported once edge-hover auto-scroll worked:** mouse
wheel still didn't scroll at all while a drag was held — a second,
separate instance of the same class of bug, not a leftover part of the
first one. Chromium fires `wheel` normally during an active native
drag session (confirmed live — unlike `mousemove`, which stops firing
in favor of `dragover`), but doesn't apply the scroll that would
normally follow it. `createDragAutoScrollPlugin`'s `handleDOMEvents`
gained a `wheel` hook, gated on a `dragActive` flag (set by `dragover`,
cleared by `dragend`/`drop` — separate from `lastClientY`/`frame`,
which drive the edge-hover loop specifically): while a drag is held, it
manually replays the scroll via `window.scrollBy(0, event.deltaY)` —
scaled by 16 for `deltaMode === 1` (`DOM_DELTA_LINE`, some
mice/trackpads' native unit) — and calls `preventDefault()` so nothing
double-applies it if some browser/OS combination *does* still handle it
natively too. Verified live against the running editor: a wheel event
dispatched before a drag starts is correctly a no-op, one dispatched
mid-drag calls `window.scrollBy` exactly once with the event's own
`deltaY` (and the window's `scrollY` genuinely changes), and one
dispatched after `dragend` goes back to a no-op — plus the
`deltaMode === 1` ×16 scaling checked directly. Full suite still 326
passed, `tsc -b` and lint clean (no new pure-function surface here
worth a dedicated unit test — the gating logic is a couple of boolean
reads, exercised directly against the live plugin instead, the same
tier the edge-hover loop itself already gets).

**Follow-up #3, requested once dragging and scrolling both worked:**
visual scope feedback — dim out illegal drop targets, turn the drop
line red with an explanatory tooltip over an illegal spot, so the
restriction (entries stay within their section, bullets within their
entry — `dragScopeGuardPlugin`'s own rule) is visible *during* the drag
instead of only discoverable by attempting an illegal drop and having
it silently revert.

New `createDragScopeFeedbackPlugin`/`DragScopeFeedback`
(`lib/tiptap/plugins.ts`) replaces `@tiptap/extensions`' stock
`Dropcursor` outright in `DocumentEditor.tsx`'s extensions — running
both would draw two independent, conflicting cursor lines, and this
plugin already needs everything Dropcursor computes (the actual drop
position, via the same `dropPoint` helper from `prosemirror-transform`)
to decide the color. Architecture ported from
`prosemirror-dropcursor`'s own `DropCursorView` (MIT-licensed, adapted
under `DragScopeFeedbackView`): a raw `view()` plugin with native
`dragstart`/`dragover`/`dragend`/`drop`/`dragleave` listeners on
`editorView.dom`, manually positioning a couple of plain DOM elements —
no decorations, no meta-transaction dance to force a redraw, since nothing
about the document changes while just hovering. Only the block-level
rect math survived the port; this project never drags inline content,
so the original's thin-vertical-line (inline-drop) branch was dropped
entirely.

A `DragScope` (`{ nodeType, scopeId, scopeLabel }`) is computed once, at
`dragstart`, from `state.selection` — already the correct `NodeSelection`
by then, via `DragHandle.tsx`'s own `onDragSelect` — not recomputed per
`dragover`, since what's being dragged can't change mid-drag.
`scopeId` is the id/key of the ancestor (section for an entry, entry
for a bullet) a drop has to land back inside; `null` means "no
restriction" (a section can be dropped anywhere). Three pure functions
factor out of the view class and are unit-tested directly
(`plugins.test.ts`, 12 new cases): `computeDragScope` (what's being
dragged, and its scope), `isPositionInScope` (does a given document
position still sit inside that scope — walks up from the position the
same way `computeDragScope` walked up from the drag's own origin, so a
mismatch here is exactly what `dragScopeGuardPlugin` would revert if
the drop actually happened), and `invalidDropMessage` (the tooltip
text, polished per node type: `Can only be reordered within the
"Experience" section.` for an entry — naming the actual section, read
from its own `title` attr, reads far better than a bare key — or `Can
only be reordered within its own entry.` for a bullet, which doesn't
get a name since "its own entry" is unambiguous without one).

Dimming: at `dragstart`, every entry/bullet node whose *parent*'s
key/id doesn't match the drag's own scope gets `opacity: 0.28;
pointer-events: none` set directly on its DOM (also preventing an
accidental hover-interaction with a dimmed item's own checkbox mid-drag),
cleared on `dragend`/`drop`. A genuine gotcha found live: `editorView.
nodeDOM(pos)` returns Tiptap's own outer portal-mount `<div>` for a
React NodeView, not the `<p>`/whatever tag the NodeView's own JSX
renders — setting `opacity` there still visually dims the whole node
correctly (opacity composites across all descendants), but a
verification check that queries the *inner* rendered tag directly and
reads its own `style.opacity` will wrongly read `""`/unset, since
opacity doesn't propagate as an inline style to descendants, only as a
compositing effect — worth remembering for any future NodeView-DOM
introspection in this codebase.

Cursor color: `var(--primary)` (matches the checkbox's own checked-state
accent, same choice the original Dropcursor config made) over a legal
position, `var(--destructive)` over an illegal one — same CSS variable
`index.css` already defines for the app's own error/destructive UI
elsewhere, not a new color.

Verified live against the running editor (same technique as every other
drag fix this phase — this environment can't perform a real trusted
drag gesture): a bullet drag hovering within its own entry shows a
primary-colored line, no tooltip, and leaves other entries' bullets at
full opacity; the *same* drag hovering a different entry's bullets
shows a destructive-colored line, the correct tooltip text, and dims
every bullet outside its own entry (confirmed via the wrapper-div
opacity, not the inner tag, per the gotcha above) while leaving its own
entry's bullets undimmed; an entry drag hovering a different section
shows the tooltip correctly naming its own section ("Experience");
`dragend` cleans up the cursor, tooltip, and every dimmed element; and,
unchanged from before this follow-up, an actual legal drop still
performs a genuine move (confirmed via `undo()` restoring the exact
original bullet order). Full suite: 338 frontend passed (up from 326),
`tsc -b` and lint clean.

**Follow-up #2's own "confirmed" claim was wrong.** Retested by the
user: wheel-during-drag still didn't scroll, even after that fix. The
live verification behind that fix dispatched a *synthetic* (untrusted)
`wheel` event mid-drag and watched it reach the handler — which proves
the handler's own logic is correct, but not that a real mouse-wheel
gesture ever produces a trusted `wheel` event on this page during a
drag at all; an untrusted `dispatchEvent` always reaches an
`addEventListener`-registered handler regardless of what the browser's
actual native input routing does mid-drag, the exact gap that's made
"confirmed via dispatchEvent" not equivalent to a real gesture at
several other points in this same phase.
Widened the listener one step further as a good-faith second attempt —
a second, raw `wheel` listener directly on `window` with
`capture: true` (fires before `view.dom`'s own bubble-phase one;
`stopPropagation()` on a hit there skips the redundant one, verified
live to scroll exactly once per event, not double) — but the honest
likely explanation, worth recording plainly rather than chasing further
without a way to confirm it: on Windows, Chrome's native drag-and-drop
runs through the OS's own modal `DoDragDrop` loop, documented to only
pump a limited set of input messages back to the page for the drag's
duration (mouse move, Escape-to-cancel) — `WM_MOUSEWHEEL` isn't
necessarily one of them, which would mean the browser never dispatches
a `wheel` DOM event to *any* part of the page while a drag is held, not
just to whatever element the cursor happens to be over. If that's what's
actually happening, no listener placement fixes it — there's nothing
for JS to intercept, since the event never reaches the page's own event
queue at all. Full suite still 338 passed, `tsc -b` and lint clean (no
behavior change worth new test coverage — the pure `applyWheelScroll`
logic was already covered by the earlier follow-up's own live checks,
and the new window-level listener is wiring, not new logic). The
edge-hover autoscroll from follow-up #1 remains the one scroll
mechanism actually confirmed working by the user during a drag, and is
the fallback if wheel genuinely can't be reached from here.

**The widened listener didn't fix it either — and this time it's
settled, not just suspected.** Rather than keep guessing from
synthetic-event checks that can't tell "the browser suppresses this"
apart from "my code is wrong," asked the user to run a small diagnostic
directly in DevTools during a real drag: plain `wheel` listeners on
`window` and `document` (capture and bubble phase both), a running
count, logged at `dragstart`/`dragend`. Result: `dragstart` fired,
then — despite spinning the mouse wheel repeatedly while holding the
drag — **zero** `wheel` events reached the page for the entire drag,
confirmed by `dragend`'s own count. This is airtight: not a matter of
which element the listener was on, since `window`-level capture-phase
listeners see every event that reaches the page at all. On Windows,
Chrome's native drag-and-drop runs through the OS's own modal
`DoDragDrop` loop, which only pumps a limited set of input back to the
page while a drag is held (mouse move, Escape-to-cancel) — mouse wheel
isn't one of them, so the event never reaches the page's own queue for
any element, at any point during the drag. No JS listener placement can
fix that; there's nothing here to intercept. Recorded plainly in
`lib/tiptap/plugins.ts`'s own comment rather than left as the earlier,
now-known-wrong "confirmed" claim. The wheel-handling code itself
stays (harmless when inactive, and untested whether every browser/OS
suppresses this the same way) — but it's the edge-hover mechanism that
gets the investment from here, since it's the one actually confirmed
working.

Widened it accordingly: `AUTO_SCROLL_EDGE_PX` 72px → 140px,
`AUTO_SCROLL_MAX_SPEED_PX` 18 → 26 — a bigger hot zone (less precise
hovering needed near the top/bottom of the screen) and a faster top
speed (less time spent waiting for a long section like Experience to
scroll into reach). `computeAutoScrollDelta`'s own exact-threshold test
updated to match (140/139, was 72/71); the near-edge/at-edge direction
tests didn't need changes — they don't hardcode the threshold itself.
Verified live: a `dragover` at a Y position that was outside the *old*
72px zone (and would previously have been a no-op) now correctly
triggers a scroll under the new 140px one. Full suite: 338 passed
(unchanged — no new pure-function surface, just retuned constants and
their existing tests), `tsc -b` and lint clean.

**Follow-up #3's own dimming logic had a real gap**, found the same
session it shipped: it only walked nodes of the *exact same type* as
whatever was being dragged — only other bullets for a bullet drag, only
other entries for an entry drag — which left every *other* section's
own header, and (for a bullet drag) every other role's own heading row,
reading as available when neither actually was. Reported precisely,
against three cases: a section drag correctly dims nothing (sections
have no restriction, expected); an entry drag left other sections'
headers undimmed despite a drop landing near one being illegal; a
bullet drag dimmed other roles' bullets but left whole other sections
(Contacts, Key Projects, Skills) untouched despite the bullet being
unable to land in any of them.

**Fix:** `applyDim` rewritten to dim whole out-of-scope *subtrees*
top-down (`doc.forEach` over sections, not `descendants` over every
node) rather than same-type nodes one at a time — dimming a single
ancestor's own DOM root is enough, since CSS `opacity` composites
across all of an element's descendants at once (the same fact behind
the `nodeDOM()`-returns-the-portal-div gotcha noted earlier in this
file). For an entry drag: every section whose key doesn't match the
drag's own scope gets dimmed *whole* (header included), the source
section untouched. For a bullet drag: a section that doesn't contain
the bullet's own entry at all gets dimmed whole; a section that does
gets its *other* entries dimmed individually (whole entry, heading
included — not just their bullets), leaving only the bullet's own
entry, and only its own siblings within it, undimmed. Verified live
against the running editor for both moved cases (entry drag: source
section and its sibling entries undimmed, every other section — header
and content — dimmed; bullet drag: the bullet's own section and entry
undimmed down to its sibling bullets, every other entry within that
section dimmed *and* every unrelated section dimmed whole) plus
`dragend` cleanup (confirmed zero elements left with a stray inline
opacity anywhere in the document afterward). No test suite changes —
`applyDim`'s own behavior is DOM-mutation-driven, same as the rest of
this view class, verified live rather than via jsdom per this whole
phase's established precedent; full suite still 338 passed, `tsc -b`
and lint clean.

**Follow-up #4**, once the drop line's own color/tooltip worked:
reported as too thin/narrow a target to comfortably land the mouse on.
`updateCursorOverlay` widened via two new named constants —
`CURSOR_HEIGHT_PX` (2px → 3px, a thicker line) and
`CURSOR_HORIZONTAL_OVERHANG_RATIO` (0.25 — the line now extends 25%
past the underlying row's own left/right edges, split evenly on both
sides, rather than exactly matching its width). Verified live: for a
657.6px-wide row, the rendered line measured exactly 822.0px — 1.25×,
confirming the math. No test changes (this view class's DOM-mutation
behavior is verified live throughout, not via jsdom — same precedent as
every other follow-up here); full suite still 338 passed, `tsc -b` and
lint clean.

**Follow-up #5**, reported once the wider line was confirmed working:
the drag handle's own `cursor: grab` had stopped showing on hover —
hovering showed the text/I-beam caret instead, as if the handle didn't
have a `cursor` style at all, despite `DragHandle.tsx` clearly setting
one. First guess (missing `user-select: none` — a real, separate, and
also-fixed gap, since Chrome does sometimes fall back to a text cursor
for anything it still considers text-selectable inside a
`contentEditable` region) didn't fix it either; the user re-confirmed
the bug survived a hard reload with `select-none` in place, ruling out
both "stale bundle" and "text-selectability" as the actual cause.

Diagnosed with the user's help, the same way real-gesture-only bugs
throughout this whole phase have been: a console script logging
`document.elementFromPoint` + computed `cursor` on every `mousemove`,
pasted into DevTools. The log confirmed the handle itself was correct
in every way that could be checked — right element under the cursor,
`cursor: grab`, `user-select: none` — yet the *browser* was still
painting an I-beam. The genuinely useful part: **the bug vanished for
the rest of that page load, the moment the diagnostic script's own
`mousemove` listener was attached**, and came back on the next reload
once it was gone. That's not a coincidence — it's a real, documented
Chromium quirk: the browser can skip re-running its cursor hit-test for
a spot that only becomes interactive via a CSS-only transition (exactly
`DragHandle.tsx`'s own `opacity-0` → `group-hover:opacity-100` reveal,
no JS involved) *unless* the page has an actual `mousemove` listener
registered somewhere, which keeps that recompute path active on every
move. Fixed by adding exactly that, permanently: a no-op `mousemove`
listener in `DocumentEditor.tsx`, mounted/cleaned up via `useEffect`
scoped to the component's own lifecycle — the handler body does
nothing at all, its only job is to exist. Confirmed by the user working
correctly afterward, without DevTools open. Full suite: 338 passed
(unchanged — nothing here is a pure function to unit test, it's a
browser-rendering-pipeline workaround, verified live), `tsc -b` and
lint clean.

The user's own hands-on retry across all of this phase's follow-ups
(edge-scroll, scope-dimming, wider drop line, grab-cursor) came back
positive — Phase 27, including its structural dragging feature and
every piece of feedback/polish reported afterward, is genuinely done.
Wheel-during-drag remains the one known, accepted exception: a real
platform limitation on Windows Chrome, not a bug to keep chasing.

## Phase 28 — Floating gutter: checkboxes & Sparkles move outside the page (done)
Checkboxes (section/entry/bullet include-exclude) and the Sparkles
AI-edit trigger moved out of the text flow into `DocumentGutter.tsx` — a
single overlay rendered as a flex sibling of `A4Page` inside
`DocumentEditor.tsx` (not a child of it, and not per-row CSS offsets),
laid out in two fixed-x lanes: Sparkles (outer) then checkbox (inner,
nearest the page), so every row's checkbox lines up in one vertical
column regardless of section/entry/bullet nesting depth — confirmed live
(see below), not just intended. Drag handles explicitly stayed put
(inline, hover-only, inside the page's own padding) — deliberately out of
scope, not an oversight: Phase 27's `[data-drag-handle]` mechanism is
DOM-position-sensitive (`stopEvent()`, `nearestDesc()`) and took five
rounds of real bugs to stabilize, including one that briefly corrupted a
real draft; hoisting it into an externally-positioned gutter risked
reopening exactly that class of bug for no real benefit, so this phase
left it exactly where Phase 27 finished it.

* **Registration is bottom-up** (every NodeView → one shared overlay),
  which plain React Context can't do on its own for the same reason
  Phase 26 already found (`context.tsx`'s docstring): Tiptap's
  `ReactNodeViewRenderer` mounts every NodeView as its own portal into
  one editor-wide React tree, so nesting a *new* Provider inside a
  NodeView is invisible to NodeViews mounted under it. That finding was
  about *providing new values* top-down, though — reading two stable
  functions off the *existing* top-level Provider works fine (exactly
  like `onToggleBullet` already did), so `registerGutterItem`/
  `unregisterGutterItem` just rode along on it. New
  `lib/tiptap/gutterRegistry.ts::GutterRegistry`, a plain external store
  (Map + `Set<Listener>`, `register`/`unregister`/`subscribe`/
  `getSnapshot`) is the actual mutable state those two functions write
  into — one instance per `DocumentEditor` (`useMemo`), read by
  `DocumentGutter.tsx` via `useSyncExternalStore`. New
  `lib/tiptap/useGutterItem.ts` is the one hook `Section`/`Entry`/
  `BulletNodeView` all call instead of rendering their own checkbox/
  Sparkles — re-registers (a cheap Map upsert) on every render with no
  dependency array (checked/disabled/Sparkles-popover-content are all
  fresh most renders anyway), unregisters once on real unmount.
* **A real, load-bearing finding, not caught until live verification**:
  a child NodeView whose own node is unchanged isn't guaranteed to
  re-render just because an *ancestor's* attrs changed (excluding a whole
  section doesn't touch any of its entries' own ProseMirror nodes) — so a
  value like "is my ancestor section excluded" computed inside a NodeView
  at its own render time can silently go stale, since Tiptap/ProseMirror
  can reuse an unchanged child NodeView wholesale across a `setContent`
  call without ever calling into it again. Found by a test written
  *for* this phase (excluding a section should hide its entries' gutter
  checkboxes too — they're rendered outside the page's own DOM subtree
  now, so the CSS-cascade hiding that used to do this for free no longer
  reaches them), not anticipated in the design above. **Fix:** moved
  entirely out of each NodeView's own render and into `DocumentGutter`'s
  own remeasure, which *is* reliably driven by `editor.on("update")` —
  tied to the editor's document actually changing, not to whether any
  particular child NodeView re-rendered. `useNodeAncestry.ts` split its
  walk-the-doc logic out into a standalone `computeNodeAncestry(doc, pos)`
  (the hook is now a thin wrapper over it); `GutterItem` gained a
  `getPos: () => number | undefined` field — Tiptap's own live-bound
  closure (`() => this.getPos()`, from `@tiptap/react`'s
  `ReactNodeView.mount()`), not a value captured once — so
  `DocumentGutter` can call `computeNodeAncestry(editor.state.doc,
  item.getPos())` fresh on every remeasure and skip any item whose
  ancestor entry/section is excluded, independent of whatever the
  registering NodeView's own last render happened to compute. Each
  NodeView's own registration now only gates on *its own* `included`/
  `hasEntries` (reliable — a node's own attr change always re-renders
  that same node); cascading exclusion is `DocumentGutter`'s job alone.
* **Visibility rule, made uniform across all three levels**: a row's
  gutter checkbox shows iff it, and every one of its ancestors, has
  `included !== false` — "content still in the document," matching this
  phase's own framing. This is a deliberate behavior change for entries
  specifically: the pre-Phase-28 inline chrome (`EntryNodeView`'s
  absolutely-positioned overlay) rendered its checkbox unconditionally,
  regardless of the entry's own `included` — a workable-by-accident
  quirk while the checkbox lived inside the page's own content flow next
  to a hidden `NodeViewContent`, but never a documented, deliberate
  design choice, and one Phase 28 would otherwise have had to
  special-case around forever. Made consistent with bullets instead
  (whose checkbox already disappeared on exclusion): excluded content's
  only restore path is `ExcludedContentPanel` (Phase 24), not a second,
  redundant checkbox floating in the gutter next to nothing.
* **Layout**: `DocumentEditor.tsx`'s `A4Page` no longer self-centers via
  its own CSS (`margin: 0 auto`, still in `index.css`, still exercised by
  `PrintPreview.tsx`, which has no gutter) — a new `relative flex w-fit`
  row wraps `<DocumentGutter>` and `<A4Page>` together as one centered
  unit, so there's real reserved horizontal space for the gutter rather
  than relying on incidental whitespace that only exists on wide
  viewports. No `items-start` on that row — default `align-items:
  stretch` gives the gutter the same height as `A4Page` for free.
* **A genuine fidelity win, not just relocation**: removing the checkbox
  from each row's own inline flow freed the horizontal space it used to
  reserve — `EntryHeadingNodeView.tsx`'s `pl-12` (handle + gap + checkbox
  + gap) shrank to `pl-6` (handle + gap only, the drag handle being all
  that's left inline), and `BulletNodeView`'s own row (inlined directly
  now that `DocumentRow.tsx` — deleted, its only remaining job before
  this phase — had nothing left to share with anything else) lost its
  checkbox-sized gap the same way. On-screen text now starts closer to
  the page's actual print margin, closing more of the "not pixel-real"
  gap against `PrintExperienceSection.tsx`/`PrintSectionBlock.tsx` that
  Phase 26 didn't fully close.
* **Aria-labels made content-specific**, a needed fix, not a nice-to-have:
  every entry/bullet checkbox used to share one generic label ("Include
  this entry"/"Include this bullet") — harmless when a screen reader user
  or a test could rely on DOM proximity to disambiguate which one, both
  of which stopped being true once every checkbox in the document became
  a sibling in one shared gutter. Now `Include this entry: ${heading
  text}` / `Include this bullet: ${bullet text, truncated to 60 chars}` —
  entry heading read directly off `node.firstChild` (always the
  `entryHeading` per `schema.ts`), locked Gaps get `Career gaps can't be
  excluded: ${heading text}`.

Verified: new `lib/tiptap/gutterRegistry.test.ts` (register/unregister/
upsert/publish-notifies-subscribers/fresh-snapshot-identity/unsubscribe
cleanup) exercises the store directly, headless — same tier as
`commands.test.ts`/`plugins.test.ts`. Existing `DocumentEditor.test.tsx`/
`DraftScreen.test.tsx` checkbox interactions updated from DOM-containment
queries (`within(row).getByRole("checkbox")`, no longer meaningful once
the checkbox isn't a descendant of its row) to content-specific
aria-label queries; two new `DocumentEditor.test.tsx` cases added —
a section/entry/bullet's checkbox renders outside `.cv-print-entry`/
`.cv-a4-page` entirely (guards against the relocation silently not
happening even if every interaction test still passed), and excluding a
whole section hides its entries' gutter checkboxes too (the cascading-
exclusion fix above, written *as* the regression test that first caught
it broken). Full suite: 616 backend passed (unchanged — no backend code
touched), 347 frontend passed (up from 338). `npm run lint`, `tsc -b`,
and `vite build` all clean.

Position (the actual `top` a checkbox renders at) is the one thing here
that stays a live-verification-only concern, same precedent as every
Tiptap-era phase — `getBoundingClientRect()` is always a zero rect under
jsdom, so the visibility *rule* was deliberately kept independent of
measurement (explicit `included` booleans, not "is the measured rect
zero-height") specifically so correctness stayed unit-testable; only
positioning itself couldn't be. Live-verified against a real draft (not a
fixture) via the Browser pane's `javascript_tool` (the pane still can't
composite frames for `computer`'s screenshot/click actions in this
environment, per every prior phase's own note) against the same draft
Phase 26 used (`a916453c`): every checkbox in a real, full CV (90 of 96
structural rows — the other 6 are the 5 genuinely-empty sections plus one
already-excluded duplicate bullet already in that draft's own data,
correctly *not* registering a gutter item for either reason) lands at
`left: 61`, one consistent column, `pageLeft: 97` confirming it's
genuinely outside the page; Sparkles at `left: 29`, left of the checkbox
as specified. Found and fixed one real misalignment this way: the
Sparkles trigger and Checkbox landed 6px out of vertical sync (a leftover
`mt-1.5` on the Checkbox alone, nothing on Sparkles) — moved to the
shared row wrapper instead. Excluding the real "Education" section live
correctly hid its entry's gutter checkbox immediately, confirming the
ancestor-staleness fix above against real React re-render timing (not
just jsdom); restoring it, confirmed via both the DOM and a direct
read of `data/cvai.db` afterward, round-tripped correctly with no
persisted side effect left behind. The Sparkles popover (rationale,
original text, Revert button) opened with correct real content.
Drag handles confirmed unaffected — all 96 still present inside
`.cv-a4-page`, `opacity: 0` by default, `cursor: grab`, same as Phase 27
left them. Zero console errors throughout.

**Follow-up, reported once the always-visible gutter was tried for
real**: a checkbox on every single row, all the time, made it hard to
tell which bullets were even there — the checkboxes themselves became the
dominant visual signal, competing with the CV text they were annotating.
The expected use case is "leave what the AI chose alone, exclude is the
rare action" — so the checkbox itself shouldn't earn permanent screen
space for a rarely-used action. Two changes, reported together but
genuinely separate:

1. **Checkboxes go hover/edit-only**, the same "reveal near the content
   it belongs to" idea `DragHandle.tsx` already established for the drag
   handle (Phase 27) — except a gutter item and its own row live in two
   different DOM subtrees (the whole point of this file), so plain CSS
   `group-hover` can't reach across on its own; `DocumentGutter.tsx` now
   tracks hover/selection in JS instead. **Sparkles deliberately stays
   always-visible** — not folded into this, on purpose: it's a passive,
   useful-while-scanning signal ("this bullet was AI-edited"), not a
   rarely-used action like exclude.
   * `hoveredId`/`activeSelectionId` state in `DocumentGutter`, combined
     as `checkboxVisible = id === hoveredId || id === activeSelectionId`.
     Hover comes from two independent sources feeding the same state: a
     native `mouseenter`/`mouseleave` listener attached directly to each
     item's `anchorEl` (imperative — `anchorEl` belongs to a NodeView,
     entirely outside this component's own JSX, so there's no React prop
     to hang a handler off), and a plain `onMouseEnter`/`onMouseLeave` on
     the gutter's own rendered row for that same id. Needed both: the row
     (in the page) and its checkbox (in this gutter) are physically
     separate hover targets with a real gap between them.
   * **A short grace period before hiding** (`HOVER_HIDE_DELAY_MS`,
     150ms), not an immediate clear on `mouseleave` — without it, moving
     the mouse from the row toward its checkbox reads as "left" and hides
     the checkbox before the pointer ever arrives, since leaving the row
     and entering the gutter aren't the same instant. A pending hide is
     cancelled if the *same* id's hover fires again (from either source)
     before the timeout elapses.
   * `activeSelectionId` (the "or when I'm editing it" half) is computed
     via new `computeActiveGutterItemId(doc, pos)`
     (`lib/tiptap/useNodeAncestry.ts`) on every `editor.on("update"/
     "selectionUpdate")` — walks up from the resolved position the same
     way `computeNodeAncestry` does, returning the nearest bullet/entry/
     section's own gutter id (an entryHeading position falls through to
     its parent entry, since entryHeading has no gutter item of its own —
     mirrors `computeNodeAncestry`'s own `entryId` lookup).
2. **A bullet whose text is fully deleted auto-excludes itself**,
   reported in the same pass: with the checkbox no longer visible by
   default, "select all, Backspace" is now the natural way to remove a
   bullet, and leaving it included-but-empty would be a silent, confusing
   dead end — a blank line with no obvious way back to a checkbox to
   exclude it properly. New `emptyBulletExclusionPlugin`
   (`lib/tiptap/plugins.ts`, same `appendTransaction`-guard style as
   `idIntegrityPlugin` alongside it) compares bullet ids that had real
   text *before* a transaction against which of those are empty *after*
   it — deliberately not "is newState's bullet empty" alone, which would
   also catch a freshly-created blank bullet ("+ Add Bullet", or a fresh
   sibling from pressing Enter) and exclude it the instant it's created,
   before the user types anything. Neither creation path's id exists in
   the *old* state at all (both mint a fresh id — `addBullet` via
   `crypto.randomUUID()`, a split via `idIntegrityPlugin`), so neither is
   ever touched. Registered *before* `excludedSelectionGuardPlugin` in
   `DocumentGuards`' plugin list (order matters here — ProseMirror's own
   `appendTransaction` chaining applies each plugin's returned
   transaction before calling the next, so this ordering is what lets the
   selection-guard plugin see, and relocate the cursor out of, a bullet
   that was just excluded by deleting all its text, in the same pass
   rather than a visibly separate one).

Verified: 5 new `plugins.test.ts` cases for `emptyBulletExclusionPlugin`
(excludes on full deletion; leaves a partially-deleted bullet alone;
never excludes a freshly-inserted blank bullet; no-op for an
already-excluded bullet; confirms the selection-relocation ordering with
`excludedSelectionGuardPlugin`), same headless-`Editor` technique as
`dragScopeGuardPlugin`'s own tests in the same file. New
`useNodeAncestry.test.ts` (didn't exist before this follow-up) covers
`computeNodeAncestry`'s own default/cascading-exclusion cases directly
plus `computeActiveGutterItemId`'s three resolution cases (bullet,
entryHeading-falls-through-to-entry, section). Three new
`DocumentEditor.test.tsx` cases cover the hover mechanism itself:
starts hidden and becomes visible on hovering the row; hides again after
the grace period, not immediately, on leaving; hovering the gutter's own
row (not just the page row) also counts — using `vi.useFakeTimers({
shouldAdvanceTime: true })` (the same pattern `DraftScreen.test.tsx`'s
autosave-debounce tests already established) and `fireEvent.mouseEnter`/
`mouseLeave` dispatched directly at the relevant element, wrapping
`vi.advanceTimersByTime` in `act()` — a state update from inside a raw
`setTimeout` callback (not a React event handler) needs that to flush
synchronously before the next assertion. The "stays visible while the
cursor is inside it" half of the visibility rule is *not* covered at the
component level — real caret placement isn't reliable under jsdom (no
`document.elementFromPoint`, same gap noted throughout this file's own
`DocumentEditor.test.tsx`), and `DocumentEditor` doesn't expose its
editor instance externally the way `lib/tiptap`'s own headless-editor
tests do; `computeActiveGutterItemId` itself has direct coverage instead,
and the wiring from a real selection change to checkbox opacity is left
as a live-verification-only concern. Full suite: 616 backend passed
(unchanged), 361 frontend passed (up from 347). `npm run lint`, `tsc -b`,
`vite build` all clean.

Live-verified against the same real draft (`a916453c`) via the Browser
pane: every checkbox starts `opacity-0`; dispatching a real `mouseenter`
on a row's own chrome div reveals its checkbox (`opacity-100`); leaving
keeps it visible immediately, then hides it once the fake-timer-free real
grace period elapses; clicking a checkbox while hover-revealed still
toggles it correctly (confirmed, then reverted, with a follow-up DB read
confirming no persisted side effect and an unchanged `updated_at`);
Sparkles confirmed unaffected — still `opacity-100` unconditionally.
One real mistake caught and fixed *during* this verification pass, worth
recording: an early check reused a checkbox element reference captured
*before* triggering the hover, and read `false` for "now visible" —
looking like the mechanism was broken. Re-querying the checkbox fresh
*after* dispatching the hover event showed it was `opacity-100` all
along; the stale DOM reference was an artifact of the verification
script, not a bug in the app. A reminder that this same class of mistake
(trusting a DOM reference captured before an async-ish update) is exactly
what `findBy*`-over-`getBy*` and re-querying-after-mutation already guard
against in this file's own component tests — worth applying the same
discipline to ad hoc live-verification scripts, not just test code.
**`emptyBulletExclusionPlugin` itself was deliberately not live-tested
against the real draft** — unlike the drag mechanics Phase 27 had no
choice but to live-instrument (and which, in that phase, briefly
corrupted a real draft), this plugin's logic is fully deterministic
document-transaction handling with no native-DOM-event dependency at
all, well within what the 5 headless-editor tests above already exercise
faithfully; given Phase 27's own hard-won lesson about the real risk of
live-instrumenting a user's actual data, spending that risk on a plugin
that's already soundly covered by direct unit tests wasn't worth it.

**Follow-up — reported directly, with a mockup: pulling checkbox/
Sparkles out to a separate column outside `.cv-a4-page` was itself a
mistake**, not just missing hover-only visibility. Losing proximity to
the actual text made it hard to tell which bullets were even there — the
fix needed was "don't let the chrome push the exported text around,"
never "move the chrome off the page." A second, related report in the
same message: the drag handle's cursor showed the text/I-beam caret
again instead of `grab`, the exact symptom Phase 27 (follow-up #5)
already fixed once.

Reverted the external-column layout and rebuilt it *inside* the page:
new `lib/tiptap/gutterLayout.ts` is the shared coordinate system — 0 =
the text's own left edge (flush with the real print margin), negative
`left` offsets extend into `.cv-a4-page`'s own blank left padding (18mm,
currently unused space) rather than reserving any inline flow width.
Mockup's own left-to-right order: checkbox, Sparkles, handle, text.

* `DocumentGutter.tsx` now renders as a plain extra child *inside*
  `<A4Page>` (alongside `CvPrintHeader`), not a flex sibling reserving
  its own layout column — `observeRef` prop dropped, it self-observes
  its own `containerRef` instead (now sized via `position: absolute;
  inset: 0` against `.cv-a4-page`, which gained `position: relative` for
  this — a no-op for `PrintPreview.tsx`, which never renders this child
  at all). `pointer-events: none` on this root, `pointer-events: auto`
  per item, so the overlay never blocks clicking/selecting the real text
  it sits on top of.
* **The drag handle deliberately did *not* move into DocumentGutter** —
  Tiptap's drag mechanics (`stopEvent()`, `nearestDesc()`) require
  `[data-drag-handle]` to live inside the *dragged node's own* view DOM
  (schema.ts's TiptapEntryHeading comment has the two real bugs, one
  destructive, that came from getting this wrong even while the handle
  stayed inside the page) — moving it to a separately-rendered overlay
  risked reopening exactly that class of bug for a purely cosmetic gain.
  It stays rendered by each NodeView's own chrome, repositioned from
  `left: 0`/a normal-flow flex child (both of which reserved or shifted
  space) to `position: absolute` at gutterLayout.ts's `HANDLE_LEFT_PX` —
  same technique as checkbox/Sparkles, independently rendered, visually
  aligned via the shared constants. `BulletNodeView`'s wrapping `<span>`
  changed from `flex` to `block` for this specifically — an inline
  `position: relative` ancestor can fragment across line boxes when its
  content wraps, leaving an absolutely-positioned child's anchor point
  ambiguous; `block` guarantees one single box regardless of how many
  lines the bullet's own text wraps onto.
* All three reserved-space remnants from earlier in this phase are gone
  now, not just shrunk: `EntryHeadingNodeView.tsx`'s `pl-6` (entry
  headings) and `BulletNodeView`'s flex `gap` (bullets) — text starts
  flush with the real print margin in every case, matching
  `PrintExperienceSection.tsx`/`PrintSectionBlock.tsx` exactly, confirmed
  by measurement (see below), not just by inspection.
* **A real fit bug caught by live measurement, not anticipated in the
  design**: the checkbox+Sparkles+handle cluster's total width (with 4px
  gaps) summed to exactly 68px against an 18mm (≈68.03px) padding —
  zero breathing room, one rounding error from visibly clipping at the
  page's own outer edge. Gaps tightened to 2px (`gap-0.5`), leaving a
  real ~6px margin; documented directly in gutterLayout.ts so the exact
  math (and why 4px failed) isn't lost.

Verified: full suite unchanged in count (616 backend, 361 frontend) —
this follow-up moved *where* existing chrome renders and *how* it's
positioned, not the registration/visibility logic itself, so no new
pure-logic surface needed new tests; existing hover/visibility/
cascading-exclusion tests all kept passing unmodified, confirming the
DOM relationships they depend on (`.closest(".group")`,
`.previousElementSibling`, etc.) survived the restructuring. `npm run
lint`, `tsc -b`, `vite build` all clean.

Live-verified against the same real draft (`a916453c`): every row's
actual text (`Summary`'s own paragraph, an Experience bullet, an entry
heading) measures exactly 68px from the page's own left edge — identical
to `getComputedStyle(page).paddingLeft` (68.0315px) — regardless of
whether that row has any chrome nearby, confirming the core ask (text
position genuinely untouched) directly rather than by inspection. All 90
checkboxes correctly hidden by default post-fix; hovering a row's own
chrome div (dispatched `mouseenter`) correctly reveals its checkbox. One
false alarm caught and corrected *during* this pass: a checkbox appeared
stuck visible across several follow-up checks — traced (via a temporary
`console.log` of `hoveredId`/`activeSelectionId`, removed once done) to
an earlier test in this same session having dispatched `mouseenter`
without ever dispatching the matching `mouseleave`, correctly latching
`hoveredId` exactly as designed — not a product bug, a gap in the
verification script itself, the same class of mistake as the stale-
DOM-reference one caught in the previous follow-up.

**The reported cursor bug could not be conclusively verified either way
in this environment** — confirmed directly, deliberately, not assumed:
Phase 27's own `mousemove`-listener fix is untouched by any change in
this pass, and the handle's structural position/computed `cursor: grab`
are both correct, but a dispatched (untrusted) `MouseEvent("mouseenter")`
does not set the browser's real `:hover` pseudo-class state (confirmed
directly this session, both before and during this follow-up) —
`group-hover:opacity-100` (pure CSS, unlike the checkbox's own JS-driven
visibility) never toggled from a dispatched event even when the
mechanism was otherwise working correctly, so this genuinely can't be
distinguished from "the fix still holds" using this tooling. Left for
the user to reconfirm live — plausible either way: the fix's own
mechanism (a permanent global `mousemove` listener) doesn't depend on
any specific element's DOM position, so restructuring the handle
shouldn't have disturbed it, but Chromium's underlying cursor-repaint
heuristic was never fully documented even when Phase 27 first chased it.

**The above was wrong to call verified — reported back immediately by
the user (screenshot + a screen recording): checkboxes weren't visible
at all, Sparkles floated in what was clearly blank space outside the
actual page, and both disappeared entirely at a narrower window width.**
A real, load-bearing bug, not a variant of the false alarms above.

**A genuine wrong turn along the way, worth recording plainly.** The
first response to "still broken, and it reproduces in incognito and a
second browser" reached for the wrong root cause: the frontend dev
server process had in fact been running continuously for two days, long
enough to plausibly accumulate corrupted Vite/Fast-Refresh state across
every edit made in this session — a real, independent issue (a genuine
bogus React "hook count changed" console error had already surfaced once
and gone away on its own, consistent with exactly this). Restarting it
seemed to confirm the fix: a diagnostic script run in the user's own
browser afterward reported numbers that matched this phase's own design
constants exactly. **That confirmation was an illusion, not evidence of
correctness** — `getBoundingClientRect()`-based diffs are internally
consistent *regardless of which coordinate frame a constant is
misapplied in*, so "the measured offset matches the constant" was always
going to be true whether or not that constant meant what it was assumed
to mean in that particular container. "Incognito and a second browser
both show it" was, correctly, evidence against *client-side* caching —
but never evidence against *server-side* staleness, which affects every
client identically regardless of browser or cache state; conflating the
two is what made the restart look like a plausible, confirmed fix when
it had fixed nothing.

**The real bug, found from the user's own annotated screenshot** (magenta
boxes marking a hard-edged, unreachable-by-scrolling void where the
checkbox/Sparkles column should have been) **and confirmed by direct
measurement**: `DocumentGutter`'s own container is `position: absolute;
inset: 0` against `.cv-a4-page` *itself* — and CSS resolves `inset: 0`
against the nearest positioned ancestor's *padding box*, i.e.
`.cv-a4-page`'s own outer edge, not the text's (68.03px further in, past
its padding). `gutterLayout.ts`'s offsets were derived, correctly, in a
*text-relative* frame (0 = text start) — exactly right for the drag
handle, whose own `position: relative` ancestor sits in normal document
flow and genuinely does start where the text does — but applying that
same text-relative constant directly as DocumentGutter's own `left`
value put the checkbox 62px to the *left of the page's own edge*,
genuinely outside `.cv-a4-page` entirely, not merely deep in its padding.
Confirmed exactly this way by the user's own diagnostic numbers from the
*previous* round, re-read correctly this time: page edge at `x=90.15`,
sparkle measured at `x=46.15` — 44px to the *left of the page*, not 44px
into its padding as assumed. The two rounds of "still broken" reports
(magenta-boxed screenshot, "hidden if you shrink the page") are both
explained by the same root cause: a scrollable ancestor's
(`overflow-x-auto`, wrapping `.cv-a4-page`) default scroll range does not
extend to content overflowing in the *negative* direction the way it
does for positive overflow, so this content wasn't just visually
misplaced, it was often genuinely unreachable by scrolling at all.

**Fix:** `gutterLayout.ts` gained `PAGE_EDGE_CHECKBOX_ROW_LEFT_PX` —
the same physical offset, re-expressed in the *other* coordinate frame
by adding `.cv-a4-page`'s own known, fixed `padding-left` (18mm, computed
via `96/25.4` — never templated, confirmed against `index.css` directly
rather than assumed). `DocumentGutter.tsx` uses this one specifically;
`HANDLE_LEFT_PX` (consumed by each NodeView's own chrome, a different
positioning container) was never wrong and stays as-is. The underlying
`CHECKBOX_ROW_LEFT_PX` constant that caused this is no longer exported —
kept module-private now that there's exactly one (correct) way to
consume it, precisely to stop a future caller from reaching for the
convenient-looking-but-wrong text-relative value directly against a
page-anchored container again.

Verified by direct measurement against the same real draft (`a916453c`):
checkbox now `+6.03px` from the page's own left edge, Sparkles
`+24.03px`, the drag handle `[50.03, 66.03]`, text starting at `68.03px`
— every one of them now provably *inside* `.cv-a4-page`'s own bounding
box (`rect.left >= pageRect.left`, checked directly, not inferred), with
consistent 2px gaps between each and before the text. Re-checked at a
narrow 900px viewport specifically to address "hidden if you shrink the
page" — checkbox still measures exactly `+6.03px` from the page's own
edge, no clipping, because nothing renders outside the page's own box at
any width anymore. Checkbox hover-reveal, click-to-toggle (confirmed via
DOM then reverted, with a follow-up `data/cvai.db` read confirming no
persisted side effect), and the drag handle's computed `cursor: grab`
all reconfirmed working after the fix. Full suite unaffected (616
backend, 361 frontend — this fix changed one constant's value and where
it's consumed, no new logic branch to test beyond what already covers
the render path), `npm run lint`, `tsc -b`, `vite build` all clean.

**Follow-up — three more reports once the layout itself was confirmed
fixed**, all genuinely separate issues:

1. **Checkbox/Sparkles/handle didn't share a common vertical center** —
   Checkbox (`size-4`, 16px) and the Sparkles trigger (`icon-xs`, 24px)
   are two different sizes; `items-start` (used throughout this whole
   phase) aligns their *top* edges, not their icons' visual centers, so
   Sparkles reading as always-lower than Checkbox was that 8px size
   difference, not a positioning bug. `DocumentGutter.tsx`'s row switched
   to `items-center` (auto-centers regardless of the size difference) and
   its own base offset from `mt-1.5` to `mt-0.5` — Checkbox, centered
   within Sparkles' taller box, lands exactly 4px lower than the row's
   own top either way, so dropping the row's base margin by that same 4px
   keeps Checkbox's own final position unchanged from the earlier fix
   while lifting Sparkles up to match it. The drag handle (rendered
   independently — still deliberately not folded into DocumentGutter, see
   gutterLayout.ts's own docstring) is `size-4` like Checkbox, so it only
   ever needed the plain `mt-1.5` `DragHandle.tsx` already defaults to;
   `SectionNodeView.tsx`'s own `mt-0` override — a leftover from the old
   flex-*centered* header row, never revisited when that row became
   `position: absolute` — was the one real mismatch, removed. Verified by
   direct measurement against the real draft: Sparkles/Checkbox/handle's
   own `getBoundingClientRect()` centers now land on the exact same Y
   coordinate for a real bullet (`969.583...`, identical to the
   sub-pixel, not just visually close).
2. **A locked (career-Gap) entry's checkbox was grey/disabled —
   "we don't throw gaps away during generation, but we shouldn't forbid
   the user from doing it, it's their decision."** Two separate places
   enforced the old, now-unwanted invariant, both fixed:
   `EntryNodeView.tsx`'s own checkbox `disabled`/aria-label (from the
   *previous* follow-up's "no longer visible at all" pass, which kept
   this pre-existing behavior unexamined); and, found only once the UI
   layer stopped blocking it and the click still silently did nothing —
   `structuredDocument.ts::toggleEntryIncluded`'s own guard
   (`target.locked` short-circuited the whole function, independent of
   any UI state). Fixed at the data layer, not just the UI — the
   `DocumentBlock.locked` field's own docstring updated to stop claiming
   "can't be excluded," since that's no longer true; `locked` still means
   something everywhere else (commands.ts's backspace-merge guard,
   EntryHeadingNodeView's italic styling, and a *different* locked
   concept — Skills/Technologies subheading members — in this same
   function's own cascade logic a few lines down, deliberately left
   untouched since it wasn't what was reported). `structuredDocument.test.ts`'s
   existing "no-op on a locked entry" case inverted into "also flips a
   locked entry — locked no longer blocks the toggle," asserting
   `locked` itself stays `true` (the flag survives) while `included`
   correctly flips. Verified live: clicking the "Maternity leave" gap's
   checkbox now genuinely excludes it (confirmed by its own gutter item
   disappearing, the uniform Phase 28 visibility rule doing exactly what
   it does for any other entry) and restoring it via `ExcludedContentPanel`
   round-trips correctly, confirmed against `data/cvai.db` directly
   (`included: true`, `locked: true` — both correct).
3. **The drag handle's cursor wasn't `grab` at all — reported with a
   direct, specific hint: a quote of this exact codebase's own Phase 26
   history**, where entry/bullet handles missing `contentEditable={false}`
   left them inheriting `contentEditable="true"` from the ProseMirror
   root, and a plain `<span draggable>` inside a genuinely editable
   region is exactly the case browsers won't reliably start a native drag
   from (the same mousedown is also a caret-placement gesture, which
   wins) — section's handle "worked by accident" back then because it
   already sat inside a `contentEditable={false}` div. **The same
   asymmetry, reintroduced by this phase's own restructuring**: Entry/
   SectionNodeView's chrome lives in a `contentEditable={false}` div that's
   a *sibling* of `NodeViewContent`, but this phase's BulletNodeView
   nests chrome and content together inside one shared `<span>`
   (`gutterLayout.ts`'s HANDLE_LEFT_PX positioning needed a single
   `position: relative` box that doesn't fragment across wrapped lines —
   see this phase's earlier own note) — and that wrapping span never got
   its own `contentEditable={false}`, relying solely on DragHandle's own
   self-directive, which this same investigation's own history already
   showed isn't reliably sufficient on its own. Fixed by adding it to the
   span directly (`NodeViewContent`'s own explicit `contentEditable=
   {included}` still creates a normal editable island for the text
   itself, unaffected by its ancestor's). Verified structurally against
   the real draft — `anchorSpan.isContentEditable`/`handle.isContentEditable`
   both `false`, `cursor: grab` computed correctly, `draggable="true"` —
   the same properties Phase 26 confirmed fixed the identical bug by; the
   actual native drag gesture itself is, as throughout this whole
   version, outside what this environment's tooling can perform or
   observe pixels for, left for the user to reconfirm.

Full suite: 616 backend passed (unchanged), 362 frontend passed (up from
361 — `structuredDocument.test.ts`'s locked-entry case split into two,
net one new assertion). `npm run lint`, `tsc -b`, `vite build` all clean.

**Follow-up #1's own vertical-alignment fix was incomplete — reported
back with five screenshots**: alignment only actually held for a bullet
that has Sparkles; every other case (a section header, an entry heading,
a bullet the AI never rewrote) was still visibly off. Two distinct causes,
both found by direct measurement against the real draft rather than
guessed at from the screenshots alone:

1. **`items-center`'s own centering target disappears when Sparkles
   isn't rendered.** The previous fix relied on Sparkles' taller 24px box
   giving `DocumentGutter`'s flex row something to center Checkbox
   against; a row with *only* Checkbox in it collapses to Checkbox's own
   bare 16px, so `items-center` has nothing to center against and
   Checkbox loses the 4px offset that kept it level with the handle —
   true for every section and entry (Sparkles never applies to either)
   and most bullets (only an AI-rewritten one gets one at all). Fixed
   with `min-h-6` on the row (24px, matching Sparkles' own size)
   unconditionally, whether or not `item.sparkles` is actually present
   this render — not decorative, load-bearing for every sparkle-less row.
2. **The entry-level drag handle's own `mt-1.5` had no visual effect at
   all — a real, separate bug, not the same root cause.** `DragHandle`
   renders a `<span>` — `display: inline` by default — and CSS ignores
   vertical margins on inline-level boxes entirely. Bullet/SectionNodeView
   both already passed `className="absolute top-0"` to `DragHandle`
   *itself* (forcing block-level box generation, a side effect of
   `position: absolute` regardless of the element's own `display` —
   incidentally why their handles were never affected), but
   `EntryNodeView` put `position: absolute` on the *wrapping div* instead
   and left `DragHandle` itself as a plain, still-inline span — so its
   `mt-1.5` was silently a no-op and the handle rendered flush with the
   row's own top, 6px out of sync with Checkbox next to it. Fixed by
   moving the positioning onto `DragHandle` itself here too, matching the
   other two NodeViews' own established pattern exactly; the wrapping div
   now only carries `group` (hover scope) and the `anchorRef` DocumentGutter
   measures, no positioning of its own — collapses to zero height, which
   is fine, only its own `top` is ever read.

Verified by direct measurement against the real draft, all four row
kinds in one pass: a section header, an entry heading, a bullet *with*
Sparkles, and a bullet *without* — Checkbox/Sparkles/handle's own
`getBoundingClientRect()` centers land on the exact same Y coordinate in
every one of the four cases (down to the sub-pixel), not just the one
case the previous fix happened to be verified against. Click-to-toggle
re-confirmed working (via the Contacts section checkbox, reverted after,
confirmed against `data/cvai.db`). Full suite unaffected (616 backend,
362 frontend — a `min-h-6` class and moving which element carries
`position: absolute`, no new logic branch), `npm run lint`, `tsc -b`,
`vite build` all clean.

**The drag-cursor bug — STILL OPEN as of this writing, deliberately
deferred rather than fixed.** The `contentEditable={false}` fix above
was real and confirmed structurally correct, but the user reconfirmed
live afterward that the cursor still doesn't show `grab` on hover. Two
follow-on hypotheses tried, both live-diagnosed with the user directly
(same technique as every other real-gesture-only bug in this phase —
this environment still can't observe actual cursor painting):

* **Phase 27's own repaint-recompute quirk, resurfacing.** Removed
  `{ passive: true }` from `DocumentEditor.tsx`'s existing permanent
  no-op `mousemove` listener (the fix Phase 27 originally shipped for
  the identical symptom), on the theory that Chromium's own recompute
  heuristic might specifically key off a listener that *could* call
  `preventDefault()`, which a passive one, by contract, never will.
  **Reconfirmed still broken even after a genuine hard reload with no
  diagnostic script running** — ruling this out as the (whole)
  explanation this time, not just an untested guess.
* **A live DevTools diagnostic, run directly by the user**: a
  `mousemove` listener logging `document.elementFromPoint` + computed
  cursor on every move confirmed, while hovering a real handle, that the
  browser resolves the exact point to the handle's own `<span
  data-drag-handle>`, with `cursor: grab` computed correctly,
  `isContentEditable: false`, `draggable: "true"` — structurally
  identical to what Phase 26's own fix for this exact symptom checked
  and confirmed by. Separately, forcing `:hover` via DevTools' Elements
  panel on that same span shows the `.cursor-grab { cursor: grab; }`
  rule cleanly winning the cascade, nothing overriding it. Also
  confirmed: cursor rendering works correctly elsewhere on the same page
  (buttons, checkboxes) — not an OS/environment-level cursor issue — and
  the wrong cursor reproduces on *every* handle (section/entry/bullet
  alike), not just some.

**Net effect: every individual piece checked out correct — right
element, right computed style, right cascade winner, right
`draggable`/`contentEditable` state, environment renders cursors fine in
general — yet the real, physical cursor still doesn't paint `grab`.**
That combination doesn't match either of this codebase's two prior
explanations for this exact symptom (Phase 26's missing
`contentEditable={false}`; Phase 27's repaint-recompute-needs-a-
mousemove-listener quirk) — something about this specific instance is
still unaccounted for. Left open at the user's own explicit direction
("let's leave it for the last polish change") rather than pursued
further via more guessing; whether dragging *itself* still works despite
the wrong cursor icon (a purely cosmetic bug) or is also broken (a
functional one) was not yet re-confirmed either way when this was
paused. Next session picking this up should start from a fresh live
diagnostic rather than assume either prior theory still applies.

## Phase 29 — On-screen dotted page-break guide (done)
Resolved the plan's own open spike question in favor of (a): a JS
measurement pass over the live on-screen DOM, approximating the same
break rules `index.css`'s `@media print` block already encodes for the
real export. (b) — reusing the real Playwright print session — was
rejected outright: Chromium's print pagination has no live API exposing
*where* its breaks land short of actually rendering a PDF and parsing it
back, so it would mean a debounced network round-trip (a real templated
render) on every edit just to draw a guide line, for something scoped as
"purely visual — doesn't change export." (a) is self-contained and
recomputes instantly, the same "measure the real live DOM" call
DocumentGutter.tsx (Phase 28) already made for its own positioning.

* New `lib/tiptap/pageBreaks.ts` — pure, DOM-free logic, fully unit
  tested against synthetic rects (`pageBreaks.test.ts`). `PAGE_CONTENT_HEIGHT_PX`
  mirrors `index.css`'s `@page { size: A4; margin: 18mm 16mm; }` exactly
  (297mm − 2×18mm), not the on-screen `.cv-a4-page`'s own roomier
  20mm/18mm padding — the guide is meant to agree with the thing it
  represents, not with itself. `computePageBreaks` is a single greedy
  pass: a unit that would straddle a page boundary moves whole to a
  fresh page (mirrors `break-inside: avoid` on `.cv-print-entry`/
  `.cv-print-bullet`) unless it's taller than one whole page by itself,
  in which case it falls back to splitting at its own `leaves` (entry
  heading + each bullet paragraph) instead — never below that, so a
  single bullet's own text is never split. `mergeKeepWithNext` folds a
  section `<h2>` into the unit immediately after it before packing
  (mirrors `break-after: avoid-page`), so a heading can never be
  stranded alone at a page's bottom with its own content pushed to the
  next page.
* New `components/tiptap/PageBreakGuide.tsx` — walks the page's real
  rendered DOM (`header, h2, .cv-print-entry`, one combined
  `querySelectorAll` so results come back in true document order) rather
  than re-deriving structure from the DocumentModel/ProseMirror doc,
  same "measure reality" call as DocumentGutter.tsx. A fully-excluded
  section still shows its own `<h2>` on screen (`SectionNodeView.tsx`'s
  toggleable-header rule) but the real export drops the whole section —
  detected here via that heading's `<ul>` sibling carrying `hidden` in
  exactly that case, and treated as not worth `keepWithNext` protecting
  (nothing real follows it either way). Renders one absolutely-positioned
  dashed line per break, `left/right: 0` against `.cv-a4-page` itself (a
  physical page-width line, not just the text column) with a small
  "Page N" label, `pointer-events: none` throughout — decorative only,
  never intercepts a click/selection meant for the real editor content.
* **A real, live-measurement-only bug, not caught by the type checker or
  the test suite**: the page element was first threaded down as a plain
  `useRef` (`A4Page` gained a `forwardRef`, `DocumentEditor.tsx` created
  the ref and handed it to both `A4Page` and `PageBreakGuide`) — and
  `pageRef.current` read from `PageBreakGuide`'s own mount-time
  `useLayoutEffect` was reliably `null`, every time. Root cause: `A4Page`
  (the ref's owner) is `PageBreakGuide`'s own *ancestor*, and React
  attaches a host node's ref bottom-up, in the same per-fiber commit step
  as layout effects — a descendant's own `useLayoutEffect` fires
  *before* an ancestor's ref gets attached. `DocumentGutter.tsx` never
  hit this because its equivalent ref target is a div *it renders
  itself* (a child of its own fiber, not an ancestor) — refs work
  "downward" from a component's own render, not "upward" from a prop
  passed into it. **Fix:** lifted the node into `DocumentEditor.tsx`'s
  own React state instead (`useState<HTMLDivElement | null>`, set via
  `ref={setPageEl}` on `A4Page`) — the state update that callback
  triggers schedules a real re-render, so `PageBreakGuide` picks up the
  real node on its next pass regardless of commit order. Confirmed live
  (a synthetic 10-role/60-bullet document, matching Phase 16c's own
  stress-test shape) rather than assumed fixed once it compiled.
* **A second live-only finding, once the above was fixed**: the guide's
  primary remeasure trigger was originally `editor.on("update")`/
  `"selectionUpdate")` alone — which never fires for
  `DocumentEditor.tsx`'s own `applyModel` (every checkbox toggle, "+ Add
  Bullet", and critically the *initial* seed from a freshly-generated
  CV all call `setContent(..., { emitUpdate: false })`, deliberately
  silent). A live check showed the guide stuck at its very first
  (near-empty) measurement, never updating once real content loaded.
  **Fix:** `PageBreakGuide` now also takes the same `GutterRegistry`
  instance `DocumentGutter` already reads, and depends on its
  `useSyncExternalStore` snapshot the same way — registration happens on
  every NodeView render regardless of `emitUpdate`, since NodeView
  mount/unmount is driven by ProseMirror's own view reconciliation, not
  by the "update" event. `editor.on("update"/"selectionUpdate")` stayed
  too (a real keystroke changes a leaf's own text length in place, with
  no node registering/unregistering), and the pre-existing ResizeObserver
  stayed as a last catch-all for reflow neither one causes directly
  (font load, template swap).
* Purely visual — doesn't touch the export path, which already
  paginates correctly (Phase 16c); an approximation of Chromium's real
  pagination engine, not a port of it — the one known gap is `orphans`/
  `widows: 3` for a single very long paragraph (mainly Summary), which
  this guide currently doesn't split mid-block at all where the real
  export eventually would. Accepted as out of scope, consistent with the
  rest of this phase's approximations.

> **Post-29 fix: reported directly — editing/adding lines didn't move
> the separators.** Live reproduction (a synthetic short CV, typed past
> the first-page boundary) initially showed the *opposite* of the
> report — every edit re-triggered `remeasure()` correctly and the guide
> stayed accurate — until a break appeared in a visibly wrong spot: a
> line landing mid-way through an *earlier*, otherwise-untouched entry,
> nowhere near the actual overflow. Root cause, in `measureUnits`
> (`PageBreakGuide.tsx`): a *structurally* empty section (zero entries at
> all, e.g. unused "Certifications"/"Projects"/etc. — most real CVs carry
> several) hides its whole `<section>` wrapper (`SectionNodeView.tsx`'s
> `!hasEntries` rule), `<h2>` included, whose `getBoundingClientRect()`
> then collapses to a meaningless `display:none` position. The heading-
> protection check only looked at the section's `<ul>` sibling's own
> `hidden` class (correct for the *other* empty case — every entry
> individually toggled off, entries still exist) and missed this one
> entirely, so the check read this heading as a normal, visible,
> `keepWithNext` unit — `mergeKeepWithNext` then fused its garbage
> position with the real, visible unit right after it, corrupting that
> merged unit's own top and throwing off the whole page's packing math
> from there on. Explains the original report too: with the wrong break
> already planted from an empty section earlier in the document, further
> edits recomputed a *consistent* result around that same corruption, not
> a visibly moving one — reading as "not recalculating" even though it
> was, just always wrong the same way. **Fix:** skip the h2 entirely (not
> just its `keepWithNext` flag) whenever its own `<section>` ancestor
> carries `hidden` — the structurally-empty and all-entries-toggled-off
> cases now check the right element each. Verified live: the same
> synthetic-CV growth test that surfaced this now produces a break at
> exactly the real page-1 capacity boundary (right before the next
> section's heading), with no regression against the earlier 10-role/
> 60-bullet stress-test shape (still 3 clean breaks, unchanged positions).

> **Post-29 fix: reported directly — the on-screen guide's first break
> landed after "Maternity leave," but the real PDF export split one
> entry earlier (right after Key Projects), and the DOCX export
> disagreed with both.** Investigated by generating a real PDF for the
> reporter's own draft and extracting exact text positions with
> `pdfminer` (ground truth), then comparing against this same content's
> live on-screen measurements. Two separable findings:
>
> * **The guide vs. the real PDF: a genuine, confirmed WYSIWYG bug, not
>   a calibration nit.** `BulletNodeView.tsx`'s bullet `<p>` carried
>   `text-sm` (14px/20px line-height) — but neither `.cv-print-bullet`
>   nor `.cv-print-entry` carry any font-size rule of their own
>   (index.css only ever touches them for `break-inside: avoid`), and
>   `PrintExperienceSection.tsx`/`PrintSectionBlock.tsx` — the components
>   Playwright's `page.pdf()` actually screenshots — never applied
>   `text-sm` on their own equivalent element either. A bullet's real
>   exported size was always the inherited base 16px/24px; only the
>   on-screen editor rendered it smaller. Ruled out font-availability
>   first (measured identical `canvas.measureText()` widths for Georgia
>   in both the interactive browser and Playwright's own headless
>   Chromium — a byte-for-byte match), which pointed at a CSS-class gap
>   rather than a rendering-engine difference; grepping both component
>   trees for `text-sm` confirmed BulletNodeView.tsx was the only place
>   it appeared, and it had no counterpart on the print-target side.
>   **Fix:** dropped `text-sm` from BulletNodeView.tsx — bullets now
>   render on screen exactly as they've always actually exported.
>   Verified live: a real Experience entry's on-screen height went from
>   292px (22% short of the real PDF's 376px-equivalent) to 388px (~3%
>   over, ordinary rounding/approximation noise) for the identical
>   content — no algorithm change in pageBreaks.ts at all, since the
>   guide already measures the live DOM; fixing the DOM fixed the guide.
> * **The guide vs. the real DOCX: not a bug, a different rendering
>   engine entirely.** `python-docx` (app/cv_docx.py) never computes
>   page breaks at all — pagination only happens later, whenever
>   something opens the file (Word/LibreOffice/Google Docs), using that
>   program's own independent text-layout engine. There is no "real DOCX
>   break position" to read or approximate at export time short of
>   actually rendering the DOCX through a real Word-layout engine (e.g.
>   LibreOffice headless) on every edit — the same heavy per-edit
>   round-trip this whole guide was built to avoid (see this phase's own
>   top-of-file docstring), now for a second format. Discussed directly
>   with the user, who confirmed: keep PDF pagination as the one thing
>   this guide claims to represent (real, native, ATS-parseable DOCX
>   output was a deliberate Phase 16b/16c choice, not worth trading away
>   for pixel parity a screenshot-derived DOCX still couldn't fully
>   guarantee), and make the guide honest about that scope instead of
>   silently wrong for the other two formats.
>
> New: `format`, the export-format choice, is lifted from ExportButton's
> own local state up into DraftScreen — the same "one lifted choice
> drives both the preview and the export" move `templateId` already went
> through (Phase 16c) — and threaded down through DocumentEditor into
> PageBreakGuide as a new required prop. PageBreakGuide now only
> measures/renders the real dashed-line guide when `format === "pdf"`
> (skipping the DOM walk entirely otherwise, not just its render, since
> there's no point re-measuring on every keystroke for a format it can't
> speak to); `"docx"` gets a plain disclaimer ("Page breaks are
> approximate for Word — the exact split depends on what opens it.")
> pinned near the page's top-right instead of dashed lines; `"md"`
> renders nothing at all — a plain-text export was never paginated to
> begin with, so even a disclaimer would imply a concept that doesn't
> apply. Verified live: switching the Format select between all three
> values while watching `.cv-a4-page`'s own DOM confirmed each renders
> exactly the intended one of {dashed lines, disclaimer, nothing}, with
> no leftover node from a previous selection.

> **Post-29 fix #2: reported directly, with an annotated screenshot of a
> real exported PDF — bullet markers and inter-section spacing were both
> missing from the on-screen editor entirely**, on top of the font-size
> gap the first fix already closed. Two more real, confirmed WYSIWYG
> gaps, same root shape as the first: something the print-target
> components (PrintExperienceSection.tsx/PrintSectionBlock.tsx) always
> rendered that the Tiptap NodeViews never did.
>
> * **Bullet markers.** Every real export prefixes an ungrouped entry/
>   bullet with `{bulletChar} ` (app/cv_pdf.py/cv_docx.py's own literal-
>   character convention, see Phase 16c) — `BulletNodeView.tsx` and
>   `EntryHeadingNodeView.tsx` never rendered it at all, so the on-screen
>   page showed bare paragraphs. **Fix:** `DocumentEditorNodeViewContextValue`
>   gained a `bulletChar` field (DocumentEditor.tsx already resolves the
>   current template two ways — `A4Page`'s `template` prop and now also
>   this context value, both from the same `templateId`); both NodeViews
>   render `{ctx.bulletChar} ` as a plain `aria-hidden` sibling *outside*
>   `NodeViewContent` — never part of the actual ProseMirror-managed text,
>   confirmed live by reading the `contenteditable="true"` span's own
>   `textContent` directly (no dash) vs. the row's full `textContent`
>   (dash present) — so it can never leak into the persisted document or
>   get double-prefixed by export. Skipped for an Experience role heading
>   or a `subheading` (Skills/Technologies category label), matching
>   PrintExperienceSection.tsx/PrintSectionBlock.tsx's own branches
>   exactly. Known, accepted residual gap: an ordinary member row export
>   would compact under a preceding subheading category (Skills-with-
>   grouping) still shows a marker here, since on screen it's still its
>   own individually-editable row regardless — the compacting itself is a
>   pre-existing, out-of-scope structural difference, untouched.
> * **Inter-section spacing.** `.cv-a4-page > * + *` (index.css) only
>   reaches `.cv-a4-page`'s own *direct* children — exactly what every
>   section is in PrintPreview.tsx (each `<PrintExperienceSection>`/
>   `<PrintSectionBlock>` renders straight into `<A4Page>`) but not in the
>   live editor, where `EditorContent` inserts one `.tiptap.ProseMirror`
>   contentEditable div between `.cv-a4-page` and every actual `<section>`
>   — making every section a *grandchild*, invisible to a `>` combinator
>   scoped one level up (confirmed live: every `<section>`'s own
>   `margin-top` computed to `0px`, and consecutive sections' boundaries
>   measured exactly adjacent, zero gap). **Fix:** a second rule,
>   `.cv-a4-page .tiptap > section + section`, mirroring the same
>   `var(--cv-section-spacing, 1.5rem)` one level deeper — not a DOM
>   restructure, since ProseMirror requires that one content div (Phase 26).
>
> Both fixes are pure CSS/rendering — no pageBreaks.ts/PageBreakGuide.tsx
> change needed, since the guide already measures the live DOM; fixing
> what the DOM actually shows fixed the guide's own accuracy again for
> free. Live verification at the time read as an exact match (break at
> 907.6px, within 1px of "Experience"'s own measured top) — **later shown
> to be a coincidence, not a real fix; see the very next note.**

> **Post-29 fix #3: reported directly, with a screenshot — the bullet-
> marker fix rendered each dash alone on its own line, with the row's
> real text starting on the line below it.** Not a wrapping-indent
> quirk, a genuine block-level split, and investigating it uncovered
> that the *previous* note's "907.6px, matches almost exactly" verdict
> had been a coincidence: two independent bugs happened to cancel out,
> not a real fix landing.
>
> * **The visible bug.** Found by inspecting the live `outerHTML`:
>   Tiptap's `NodeViewContent` always wraps its real text in an inner
>   `<div data-node-view-content-react>`, regardless of the outer tag its
>   own `as` prop requests (`as="span"` here) — and a bare `<div>`
>   defaults to `display: block`. Invisible before the bullet-marker fix
>   (nothing else ever shared that line, so a block box spanning the same
>   width as an inline one looked identical); adding a real inline
>   sibling right before it surfaced the mismatch. Confirmed a stable,
>   intentional Tiptap marker before relying on it in a selector —
>   `@tiptap/react`'s own `ReactNodeViewRenderer.spec.ts` asserts against
>   this exact attribute. **Fix:** `.cv-a4-page p [data-node-view-content-react] { display: inline; }`
>   — scoped to `<p>` specifically (EntryHeadingNodeView/BulletNodeView,
>   both `as="p"`), not `.cv-print-entry` (EntryNodeView's own `<div>`,
>   which never has an inline sibling to align with in the first place).
>   Verified via `getClientRects()` (not `getBoundingClientRect()` — a
>   wrapping inline element's bounding box is the union of *every* line
>   fragment, misleadingly making "same line" and "stacked on two lines"
>   look almost identical at a glance): the prefix's own fragment and the
>   text's *first* fragment now share the same `top` and are
>   horizontally adjacent (text starts exactly where the prefix ends).
> * **What that bug's *height* was quietly doing, and why fixing it
>   exposed the second bug.** Every bulleted/entry row was silently
>   ~24px taller than it should have been (one whole spurious extra line
>   per row, for the stranded prefix) — enough, summed across Contacts'
>   5 rows + Key Projects' 4, to closely resemble the *missing*
>   section-spacing gap fix #2 was supposed to add. Fixing the block/
>   inline bug removed that accidental padding — and with it, the
>   9-section-boundaries-worth of section spacing the guide had
>   (wrongly) looked like it had. Re-checking live confirmed every
>   section boundary back to a real `0px` gap: fix #2's own selector,
>   `.cv-a4-page .tiptap > section + section`, matched nothing at all.
>   Root cause: `.tiptap.ProseMirror`'s own direct children are each
>   *another* Tiptap-internal wrapper, `<div class="react-renderer
>   node-section">` (auto-generated from the ProseMirror node's own
>   `name: "section"`, schema.ts) — a `<section>` is a
>   great-grandchild of `.cv-a4-page`, not a grandchild as fix #2
>   assumed. **Fix:** retargeted the same rule at
>   `.cv-a4-page .tiptap > .node-section + .node-section` instead (margin
>   on the wrapper is visually indistinguishable from margin on the
>   `<section>` it exists solely to contain).
>
> Verified live against the reporter's own real draft, for real this
> time: every section boundary now measures a genuine 24px gap
> (`1.5rem`), and the first break lands at 739.6px, within 1px of
> "Experience"'s own measured top (740px) — matching the real PDF's
> actual split (page 1 ends right after Key Projects) via the spacing
> and bullet-marker fixes actually working together correctly, not
> coincidentally offsetting each other.

> **Post-29 fix #4: reported directly — the line still looked like it
> sat one heading too low, even after fix #3.** This time genuinely not
> a data bug: asked the reporter to run a small diagnostic snippet
> directly in their own browser's console (not reproducible in this
> environment's own browser session, so a live measurement from theirs
> specifically was the only way to be sure) — it came back with the
> *exact* same numbers this environment already had (`experienceH2.top:
> 740`, break line at `739.578px`, `ulHidden: false`), in a different
> browser, hard-refreshed, even in Incognito. The math was already
> correct in both places; what wasn't was how easy the result was to
> *read*. A bare 1px dashed line sitting within a pixel of the very
> heading it separates gives a person nothing to visually anchor which
> side that heading is on — and the label used to make it worse, sitting
> *above* the line (a negative offset reaching back into whatever
> content precedes it) when it's actually announcing what comes after.
> **Fix:** moved the label below the line instead, added a `↓`, and gave
> the line itself more visual weight (`border-t-2`, higher-contrast
> label). Deliberately not an attempt to fabricate real blank space
> between the two pages — this overlay is purely decorative
> (`pointer-events-none`) and has no way to actually carve space out of
> the real content flow underneath it without restructuring how
> ProseMirror owns that DOM; disambiguating by reading direction instead
> was the safer fix.

> **Post-29 fix #5: reported directly, insisted on (correctly) against
> an initial dismissal — a real, exact 24px coordinate-frame bug, not a
> legibility issue like fix #4 and not the reporter's environment.** The
> reporter measured the DOM directly (a `.node-section` div and a
> heading in different parent containers, an explicit 24px gap) and
> pushed back hard on an initial "already verified this is correct"
> response instead of accepting it — this time rightly: a live check of
> the line's own `getBoundingClientRect()` against `.cv-a4-page`'s
> confirmed every line rendered a real, consistent 24px *below* its own
> computed position.
>
> Root cause: `measureUnits` computes every position relative to
> `.cv-a4-page`'s own `getBoundingClientRect()` — but `.cv-a4-page > *
> + *` (index.css) gives every child but the *first* a `margin-top:
> 1.5rem`, and `PageBreakGuide`'s own overlay is `.cv-a4-page`'s fourth
> child (after `<header>`, DocumentGutter's own overlay, and the Tiptap
> content div), not its first. Left uncancelled, that stray margin
> shifted the whole overlay — and every line positioned inside it via
> `top` — 24px below the frame `measureUnits` actually measured against.
> `DocumentGutter.tsx` hit this identical pitfall first (Phase 28) and
> already cancels it on its own overlay (`style={{ marginTop: 0 }}`,
> with its own docstring explaining why) — this component just never
> carried that same fix over. **Fix:** the same `marginTop: 0` on both
> of this component's own root divs (the real guide and the `"docx"`
> disclaimer alike, both equally non-first children).
>
> Why every earlier check in this phase missed it: each one compared the
> computed `top` *value* against a heading's measured position in the
> same frame — never the line's own final *rendered* position against
> it, which is the one comparison that actually exercises this bug.
> Verified this time by measuring the rendered gap directly: `line.
> getBoundingClientRect().top - page.getBoundingClientRect().top` now
> equals 740, exactly matching "Experience"'s own measured top (740),
> zero px apart — not the ~1px-apart *value* comparison every prior
> check relied on.

## Phase 30 — Manual pagination control (done)
Resolved after Phase 29 shipped: tuning the automated CSS/JS pagination
heuristics further was the wrong direction entirely. Raised directly —
the on-screen guide shows *where* a break will land, but never *why*, so
a user who dislikes a given split has no way to understand or change it
short of adding/removing content until the heuristic happens to agree.
The fix isn't a better heuristic; it's handing the decision to the user.
Chosen mechanism (over a freeform "insert a page-break block" node):
a toggle on the section/entry itself — "start this section/entry on a
new page" — mirroring the include/exclude checkbox already sitting in
the same gutter, and confirmed explicitly over the freeform alternative.
Scope, also confirmed explicitly: every export path with a real page
concept honors it — templated PDF, plain/ATS-safe PDF, and templated
DOCX alike — not just the templated ones. Markdown export is exempt; it
has no page concept at all.

* `domain/models.py` — `page_break_before: bool = False` on both
  `PrintDocumentSection` and `PrintDocumentEntry` (not
  `PrintDocumentBlock` — bullets never get the toggle, matching the
  gutter UI). `structuredDocument.ts` gained matching
  `toggleSectionPageBreak`/`toggleEntryPageBreak` mutation helpers;
  `tiptap/schema.ts`/`tiptap/converter.ts` thread the attr through the
  editor's own node schema and JSON round-trip.
* Gutter UI: a `SeparatorHorizontal` icon button next to the existing
  checkbox (`DocumentGutter.tsx`, `SectionNodeView.tsx`/
  `EntryNodeView.tsx`), same hover-reveal/`aria-pressed` pattern Phase 28
  established. Label flips between "Start … on a new page" and "Remove
  the forced page break before …" — not just a visual toggle state, a
  real accessible-name change.
* On-screen guide (`pageBreaks.ts`/`PageBreakGuide.tsx`): a forced break
  is checked *first*, ahead of the natural greedy-pack logic, and always
  wins — even against a unit that would otherwise fit on the current
  page. Rendered visually distinct from a predicted break (solid vs
  dashed border, `"· manual"` suffix on the page label) so the guide
  itself teaches the difference between "the algorithm decided this" and
  "you decided this."
* Templated PDF (`PrintSectionBlock.tsx`/`PrintExperienceSection.tsx`): a
  plain `cv-print-page-break-before` class resolving to `break-before:
  page` inside `index.css`'s `@media print` block — Playwright's
  `page.pdf()` already honors `@media print` natively, so this is a
  three-line change once the class exists on the right elements
  (section, entry, and — for the Skills/Technologies category-grouped
  path — the subheading entry's own compact line).
* Templated DOCX (`app/cv_docx.py::render_templated_docx`) — the direct
  analogue: `paragraph_format.page_break_before = True` on the section
  heading, the Experience entry's own role-header paragraph, and (via
  `app/cv_markdown.py`'s now attribute-carrying `SubheadingGroup`/
  `SubheadingGroupMember`, replacing the old bare-tuple
  `group_entries_by_subheading` return shape) the grouped-category
  paragraph or plain member paragraph for every other section. Word
  composes this natively with the existing `keep_with_next` heading fix
  (Phase 16b) — no extra bookkeeping needed for the ordinary case.
* Plain/ATS-safe PDF and DOCX (`app/cv_pdf.py::render_pdf`,
  `app/cv_docx.py::render_docx`) — the harder case: both consume an
  *already-flattened* `dict[str, str]` of markdown-ish text
  (`render_sections_from_document`), with no structured objects left to
  read `page_break_before` off by the time they run. Solved with two
  sentinel marker lines `render_sections_from_document` emits inline —
  `SECTION_PAGE_BREAK_MARKER` (a section's own flag, always the literal
  first line of its body) and `ENTRY_PAGE_BREAK_MARKER` (an entry/
  category's own flag, wherever it falls in the body) — two markers, not
  one, because a section's *first entry* being flagged (section itself
  not flagged) also lands on body's first line, and the two cases render
  differently: a section-level break pushes the heading itself to the
  new page; an entry-level break on the section's first entry leaves the
  heading behind alone. Each renderer's own `_render_body` line-parser
  turns `ENTRY_PAGE_BREAK_MARKER` into a real `PageBreak()` flowable
  (reportlab) or a deferred `paragraph_format.page_break_before = True`
  on the next real paragraph (python-docx); the section-level marker is
  stripped and handled by the caller, one level up, before the heading
  even exists.

> **Debugging note, not a code bug: hours of live-verification results
> looked wrong (a forced entry-level break silently failing — the
> flagged entry stayed put at the bottom of the "wrong" page) even
> though every direct unit test, `TestClient` call, and adhoc
> `python -c` invocation of the exact same code produced the correct
> result.** Traced to three separate `uv run uvicorn --reload` processes
> left running simultaneously on the same machine from earlier in this
> session (a stale one from a prior day, two more from earlier restarts
> today) — since only one process can truly hold a listening TCP socket,
> curl/httpx requests were non-deterministically landing on whichever
> process's accept() loop happened to win, including one running code
> from *before* this phase's changes existed. `--reload`'s file-watcher
> was never the problem; leftover sibling processes from a long session
> were. Fixed by enumerating and killing every stray `python`/`uvicorn`
> process bound to the port and starting exactly one fresh instance —
> after which the same request that "failed" moments earlier succeeded
> immediately, byte-for-byte matching the already-passing unit tests.
> Verified live end to end afterward: a section toggle and an entry
> toggle both landed correctly in the real templated PDF (Playwright), the
> real plain/ATS PDF (reportlab), and the real templated DOCX
> (python-docx) exports, not just in the on-screen guide.

> **Post-30 fix: reported directly, from a real export — page 2 started
> right at "Experience" even though page 1 had a visibly empty trailing
> third.** Root cause, confirmed by measuring both the on-screen guide and
> a real Playwright PDF (they agreed, so this wasn't a guide/export
> mismatch like the Post-29 fixes — a genuine shared design issue):
> `.cv-print-entry { break-inside: avoid }` (index.css) treated a *whole*
> Experience entry — role header plus every one of its bullets,
> PrintExperienceSection.tsx's own wrapping `<div>` — as one indivisible
> block. An entry that easily fit within one full page on its own but
> didn't fit the *remaining* space on the current page moved whole to a
> fresh page rather than splitting (the "taller than a whole page" leaves
> fallback never even triggers for a unit that comfortably fits *a* page,
> just not *this* one), wasting whatever was left behind. Asked directly
> whether to narrow the block to per-bullet, keep it and lean on the
> manual toggle, or drop the automatic keep-together rules entirely;
> narrowing to per-bullet was the confirmed choice — a long entry's
> bullets now flow/split across a page boundary like ordinary lines, the
> same as any other section's, while still never splitting a single
> line's own text and still never stranding a heading completely alone.
>
> Scoped via a tag selector, no new class needed: `p.cv-print-entry`
> (PrintSectionBlock.tsx's genuinely-single-line entries) keeps
> `break-inside: avoid`; `div.cv-print-entry` (PrintExperienceSection.tsx's
> multi-child wrapper) doesn't, since it's never a `<p>`. In its place,
> `div.cv-print-entry > p:first-child` (the role header — always the
> entry's first child, schema.ts) and a new `.cv-print-subheading` marker
> class (a project-name bullet, e.g. "Supercity web") both get
> `break-after: avoid-page` — glued only to their own immediately-
> following line, not to the whole entry. `pageBreaks.ts`'s
> `mergeKeepWithNext` (the on-screen guide's mirror of the same rule) had
> to become a genuine transitive fold (rewritten to walk backward,
> folding into `merged[0]` at each step) rather than a single forward
> pass, since a role header immediately followed by a project subheading —
> two `keepWithNext` units back to back, no plain bullet between them — is
> a real, common shape the old single-pass version would have silently
> under-glued.
>
> A second, independent bug surfaced verifying the guide fix live: the
> new on-screen prediction didn't move at all after the first pass of
> changes, still landing at the exact same position as before. Traced to
> `measureUnits` reading `el.children` directly on `.cv-print-entry` to
> find each bullet — but `NodeViewContent` (EntryNodeView.tsx's own
> `<NodeViewContent as="div" className="cv-print-entry">`) always inserts
> its own inner `data-node-view-content-react` wrapper div around its
> real children, the exact same Tiptap behavior index.css's Post-29 fix #3
> already documented for a *different* component's `NodeViewContent` —
> missed here because it was a different file. `el.children` was always
> exactly one element (that wrapper), so `children.length > 1` was never
> true and every entry silently fell through to the single-unit branch,
> Experience included. Confirmed by dumping the live `outerHTML` before
> trusting the fix a second time, then fixed by reading `el.children[0]
> .children` instead. Verified afterward against the same real export: the
> entry that used to jump whole now splits mid-bullet, the role header and
> its own subheading still travel together, and the page count for that
> exact draft dropped from 5 to 4.

> **Post-30 polish, three more asks in one pass: Summary shouldn't be a
> bulleted list, a categorized Skills/Technologies group should read as
> "Header: item1, item2, ..." (confirmed already working in real
> export — the gap was the on-screen editor never mirroring it, a
> pre-existing, deliberately-out-of-scope divergence, not a regression),
> and an uncategorized skill list eats too much page for what it says.**
>
> Summary getting a bullet character traced to `EntryHeadingNodeView.tsx`'s
> `showBulletChar` (on screen), `PrintSectionBlock.tsx`'s unconditional
> `{bulletChar} ` prefix (templated PDF), and `render_templated_docx`'s
> `else` branch always passing `bullet=True` (templated DOCX) — the plain/
> ATS bridge (`cv_markdown.py::render_sections_from_document`) already had
> a dedicated no-bullet Summary branch, so only three of four paths needed
> the fix. Summary entries still render as separate paragraphs (not
> joined) — it's prose, sometimes a few paragraphs, not a single line.
>
> The uncategorized-list ask ("Skill 1 · Skill 2 · Skill 3 · …", confirmed
> over keeping one bullet per skill) is the same "compact single line"
> treatment a *categorized* group already got, minus the category label —
> implemented as a new `EntryGroup`/`SubheadingGroup` branch scoped to
> `section.key in ("skills", "technologies")` across all four renderers
> (`PrintSectionBlock.tsx`'s new `renderFlatGroup`, `render_templated_docx`,
> and `render_sections_from_document`, whose output both plain PDF and
> plain DOCX inherit unchanged). Only the *first* member's own
> `page_break_before` has anywhere left to apply once every member fuses
> onto one line — mirrors a category's own flag; a later member's flag is
> silently absorbed.
>
> Two real bugs found chasing this one down:
> - `app/graph_writeback.py`'s `_iter_skill_line_items` (the write-back
>   feature's "propose adding this new skill" diffing) only understood
>   the plain-line and category-grouped-line shapes — the exact same class
>   of bug its own docstring already warns about for the category case
>   ("Add skill: **Vendor & Pipeline Management**: outsourcing management;
>   documentation" as one bogus item), resurfacing for the new joined-flat
>   shape ("Add skill: Python · Go" as one bogus item, confirmed by a real
>   failing test — `test_apply_only_writes_back_selected_proposals` and
>   its siblings). Fixed with a second split, on the joined line's own
>   separator, checked only once the category shape doesn't match.
> - The separator itself: chose `" • "` (U+2022) first, matching the
>   request's own wording — worked fine in the templated PDF (Chromium)
>   and both DOCX paths, but round-tripped through the plain/ATS PDF
>   (reportlab, base-14 Helvetica, no embedded font) as `0x7f`, garbled —
>   confirmed with an isolated reportlab+pypdf round-trip check, not just
>   eyeballing it. The exact same class of problem `_render_body`'s own
>   comment already documents for list bullets ("a plain hyphen, not a
>   '•' glyph — base-14 Helvetica's WinAnsi encoding doesn't map U+2022
>   cleanly"), just newly relevant here since this is the first *inline*
>   (not list-marker) use of a bullet-like character in that path. Fixed
>   by switching to `" · "` (U+00B7, MIDDLE DOT) everywhere — confirmed
>   round-tripping correctly (`0xb7`, itself) in the same isolated check —
>   rather than special-casing just the reportlab path, so all four export
>   formats stay visually consistent with each other.
>
> The on-screen editor still shows each Skills/Technologies entry as its
> own individually-editable row, in both the categorized and flat cases —
> confirmed with the user as accepted, pre-existing scope (the live
> Tiptap editor never mirrored export's compact grouping, even before this
> phase), not something this pass changed either way. Making the on-screen
> editor itself show the compact grouped/joined view, while keeping each
> skill individually toggleable/draggable, is a real UI design question
> (inline editable chips vs. something else) left for a follow-up
> discussion, not decided here.

> **Post-31 redesign — compact Skills/Technologies as the stored shape.**
> The above Post-30 polish pass left a real gap: every export already
> collapsed Skills/Technologies onto compact lines, but the on-screen
> editor still stored (and showed) one individually-editable row per
> skill, plus a separate `kind: "subheading"` row per category. Confirmed
> with the user this wasn't worth preserving — skills only ever get
> *sorted*, never selectively dropped one at a time — so the fix moves
> the grouping earlier: a Skills/Technologies section's `entries` now
> store one already-compact `DocumentEntry` per category (or per
> uncategorized run), marked `kind: "compact"`, and that paragraph is the
> unit that gets checked out, dragged, or pushed onto a new page — the
> same generic per-entry editor UI every flat section already has, no new
> UI code needed.
> - `frontend/src/lib/structuredDocument.ts` gained `buildCompactSkillEntries`
>   (shared by fresh generation and migration), `needsSkillsCompaction`,
>   `deriveSkillGroupsFromLegacyEntries`, and
>   `collapseSkillsSectionIfNeeded`/`collapseSkillsAndTechnologiesIfNeeded`.
>   A category entry's `runs` reuse Phase 25's rich-text mechanism (bold
>   label, plain `": members"` run); a flat run is plain text joined with
>   `" · "`, no bullet.
> - Existing drafts migrate on load: `DraftScreen.tsx` runs
>   `collapseSkillsAndTechnologiesIfNeeded` over `draft.document` before
>   handing it to `DocumentEditor` as `initialDocument`. No explicit
>   write-back trigger was needed — `DocumentEditor.tsx`'s existing
>   `useEffect(() => { onModelChange?.(model); }, [model])` already fires
>   on the silent initial seed, so the normal autosave path persists the
>   migrated shape for free. Verified live: reopening the same draft
>   stays collapsed, no re-migration loop.
> - `EntryHeadingNodeView.tsx`'s `showBulletChar` was extended to also
>   suppress the bullet for Skills/Technologies (alongside the earlier
>   Summary exclusion) — a migrated/fresh compact entry is otherwise an
>   ordinary single-child entry, so checkbox/drag/page-break-toggle apply
>   with zero new NodeView code. Known, accepted gap: the on-screen editor
>   still doesn't render `runs` at all (no rich-text rendering exists in
>   Tiptap yet), so a category's bold label is invisible on screen even
>   though it exports bold — same pre-existing limitation `runs` already
>   had for Summary/Experience.
> - Two real bugs surfaced during implementation, both self-caught before
>   reaching the user:
>   - **Already-compact entries getting re-joined.** The legacy
>     `groupEntriesByCategory`/`group_entries_by_subheading` grouping logic
>     has no concept of "already grouped" — two separate compact category
>     entries with no `kind: "subheading"` marker between them would be
>     treated as one flat run and joined together with `" · "`, corrupting
>     the output. Fixed by short-circuiting on `kind === "compact"` /
>     `entry.kind == "compact"` in `PrintSectionBlock.tsx`, `cv_markdown.py`,
>     and `cv_docx.py`, rendering each compact entry standalone before the
>     legacy grouping path ever runs.
>   - **Bold run swallowing the colon, breaking write-back detection.**
>     `buildCompactSkillEntries` initially bolded `"Category: "` (label
>     plus colon) as a single run. Re-serialized to markdown by
>     `_serialize_runs`, that produces `**Category: **members` — the
>     colon *inside* the closing `**` — which `app/graph_writeback.py`'s
>     `_CATEGORY_LINE_RE` (built around the legacy `**Category**: members`
>     shape) does not match, silently breaking "propose adding this new
>     skill" write-back for every migrated/fresh compact category line.
>     Caught by directly exercising `_iter_skill_line_items` against a
>     real serialized compact line, not by a failing test or a user
>     report. Fixed by narrowing the bold run to just the category name
>     (`{text: category, bold: true}, {text: ": " + members, bold: false}`),
>     matching `PrintSectionBlock.tsx`'s own long-standing
>     `<strong>{category}</strong>: ` convention exactly.
> - Backend needed no renderer changes beyond what Post-30 already
>   shipped — `render_sections_from_document`/`render_templated_docx`
>   gained one new "is this section fully compact?" branch each that
>   renders every entry's own `runs`/text directly (no grouping, no
>   bullet), falling back to the untouched legacy grouping path for any
>   document that reaches a renderer before/without frontend migration
>   (e.g. a stale in-flight request). `app/graph_writeback.py` needed no
>   further changes beyond the Post-30 `" · "`-split fix — it parses
>   rendered text, not structured fields, and a migrated section's
>   emitted text is identical in shape to what Post-30 already produced.
> - Verified: backend 649/649, frontend 417/417, `tsc`/lint/build clean;
>   live browser check of an existing draft collapsing and staying
>   collapsed across reload; direct backend payload check of all four
>   export formats; direct `_iter_skill_line_items` check confirming the
>   write-back fix.

## Phase 31 — Selection-level rich formatting (done)
Phase 25 added `runs[]`/`alignment` to `DocumentBlock` and every export
renderer, but scoped consumption to Summary + Experience only, and
nothing could *produce* a `runs`-bearing block yet — no UI existed to
apply bold/italic/underline/a link to part of a line. This phase closes
that gap, and — confirmed explicitly, widened from the original plan
text above — across **every section that's part of the actual
document**, not just Summary/Experience: Contacts, Education,
Certifications, Awards, Publications, Volunteer Experience, Portfolio
Links, and Skills/Technologies all get the same BubbleMenu. The one
genuine exclusion is the name/headline in `CvPrintHeader.tsx` — not a
scope choice, a structural fact: `PrintDocument` has no header fields at
all, that component always renders straight from `AssembledCV`, never
user-edited.

**Design choice: marks are authoritative, `runs[]` is derived, not
stored state a user could edit out of sync with it.** Selecting text and
clicking Bold applies a real ProseMirror mark to that span, the same
mechanism Tiptap uses for any rich-text feature; `runs[]` is computed
fresh from the live marks whenever the document is read back out
(`tiptapJSONToDocumentModel`), never trusted as an independent attr.
This is the inverse of how the attr already behaved for one existing
producer — Phase Post-31's Skills/Technologies auto-compaction
(`buildCompactSkillEntries`) sets `runs` directly, with no marks in the
node's actual content, since it's built programmatically, never typed.
Both mechanisms coexist deliberately: BubbleMenu-produced runs come from
real marks; Skills/Technologies' own bold category label stays
attr-only, since a user never edits that node's raw text through this
UI.

* **New deps** (pinned to `3.29.2`, matching every other `@tiptap/*`
  package): `@tiptap/extension-bold`, `@tiptap/extension-italic`,
  `@tiptap/extension-underline`, `@tiptap/extension-link`.
  `@tiptap/extension-bubble-menu` — already present as an optional
  transitive dep of `@tiptap/react` — promoted to a direct dependency;
  its React wrapper (`BubbleMenu` from `@tiptap/react/menus`) needed no
  separate package. No schema change: `entryHeading`/`bullet`
  (`lib/tiptap/schema.ts`) don't restrict `marks`, so these attach
  without touching NodeSpecs.
* `lib/tiptap/converter.ts` gained `runsFromContent`/`contentFromRuns` —
  walks a text node's marks, groups consecutive runs sharing an
  identical mark set into `TextRun[]`, returns `undefined` when nothing
  carries a mark (keeps every untouched draft byte-identical); wired
  into `bulletToJSON`/`bulletFromJSON`/`entryToJSON` (heading)/
  `entryFromJSON`, with no per-section special-casing. The `runs` node
  *attr* (`blockAttributes()` in schema.ts) was deleted outright, not
  left as a redundant fallback — marks in the actual text content are
  now the only representation. One genuine, useful side effect of
  making marks authoritative: a Skills/Technologies compact category's
  bold label (`buildCompactSkillEntries`, Post-31) now renders bold
  *on screen* too, not just in every export — it used to be a documented
  "known accepted gap" (see the Post-31 section above) purely because
  the attr and the actual text content were two disconnected things;
  routing it through the same marks pipeline fixed that for free,
  without anyone asking for it specifically.
* `components/tiptap/FormattingBubbleMenu.tsx` (new) — `shouldShow`
  requires a non-empty selection that isn't inside a `locked` (Gap)
  entry or anything excluded (`computeNodeAncestry`, Phase 26/28's
  ancestor-walk helper). No section-key check at all — confirmed with
  the user the BubbleMenu should work everywhere, so the gate is purely
  structural. Buttons: Bold/Italic/Underline (`toggleX()`/`isActive()`),
  Align-left/center/right (not a mark — `updateAttributes` against
  *both* `entryHeading` and `bullet` node types in one chain, since a
  real text selection can span an entry's heading and its bullets — a
  single-type update would silently miss whichever type wasn't
  selected), Link (opens `LinkEditPopover` for a fresh selection with no
  existing link mark, toggles `unsetLink()` directly when the selection
  is already linked).
* Link UX ended up as two separate `BubbleMenu` instances (distinct
  `pluginKey`s, both reusing the same underlying `@tiptap/react/menus`
  component — simpler than the hand-rolled `coordsAtPos` positioning
  originally sketched above, and free floating-ui positioning either
  way), mutually exclusive by construction (empty vs. non-empty
  selection), matching the Google Docs reference from planning:
  * `components/tiptap/LinkEditPopover.tsx` — a small URL `Input` +
    Apply/Cancel, shared by "insert a new link" and "edit an existing
    one." Deliberately plain markup, not a Radix `Popover` — it renders
    as an ordinary DOM child of whichever `BubbleMenu` hosts it, so
    `@tiptap/extension-bubble-menu`'s own default `shouldShow`
    ("`element.contains(document.activeElement)`" keeps the menu open
    once focus moves into this input) just works; a Radix Popover's own
    portal/focus-trap would have fought that instead.
  * `components/tiptap/LinkHoverCard.tsx` (new) — shown for a
    *collapsed* cursor resting inside an existing link (never overlaps
    FormattingBubbleMenu, which requires a real selection): the URL,
    Open (new tab, matching `textRuns.tsx`/`linkify.tsx`'s existing
    `target="_blank" rel="noreferrer"` convention), Copy
    (`navigator.clipboard`, best-effort — a rejected promise isn't
    surfaced as an error, the raw URL is right there to copy by hand),
    Edit (swaps in `LinkEditPopover`), Remove (`extendMarkRange("link")`
    + `unsetLink()`). Clicking into link text edits its display text
    normally (`Link.configure({ openOnClick: false })` on
    `DocumentEditor.tsx`'s extension list) — no navigation on click.
  * Both components' `shouldShow` logic is a standalone exported
    function (`formattingBubbleMenuShouldShow`/`linkHoverCardShouldShow`,
    taking `(params, menuElement)`), not inlined in the JSX — the same
    "pure function, unit-testable without mounting anything" move Phase
    27's `plugins.ts` made for `computeDragScope`/`isPositionInScope`.
    Necessary here for the same reason: jsdom has no real layout, so a
    mounted `BubbleMenu`'s own floating-ui positioning can't be
    exercised in tests, but the predicate itself can, against a real
    headless `Editor`'s state.
* `components/DocumentEditor.tsx` — `EDITOR_EXTENSIONS` gained `Bold`,
  `Italic`, `Underline`, `Link.configure({ openOnClick: false, autolink:
  false, HTMLAttributes: { target: "_blank", rel: "noreferrer" } })`
  (`autolink: false` deliberately — a bare URL typed into a bullet only
  becomes a real link mark via an explicit BubbleMenu action, not
  silently as you type); renders `FormattingBubbleMenu`/`LinkHoverCard`
  alongside `EditorContent`.
* Backend — Phase 25 already consumed `runs`/`alignment` for Summary and
  Experience; this phase extended the same handling to the generic path
  both `cv_markdown.py` and `cv_docx.py` use for every other section —
  with one real structural surprise along the way. `group_entries_by_
  subheading`'s *ungrouped* branch doesn't hand renderers a full
  `PrintDocumentEntry`, only a slimmer `SubheadingGroupMember` (just
  `text`/`page_break_before`, added for Phase 30) — calling
  `_block_markdown_text`/`_add_paragraph_with_runs` on one threw
  `AttributeError: 'SubheadingGroupMember' object has no attribute
  'runs'` immediately, caught by the test suite before reaching a real
  user. Fixed by extending `SubheadingGroupMember` with `runs`/
  `alignment` (threaded through in `group_entries_by_subheading`,
  carried from the source entry the same way `page_break_before`
  already was) and introducing `RunsRenderable`, a `typing.Protocol`
  both `PrintDocumentBlock` and `SubheadingGroupMember` satisfy
  structurally — `_block_markdown_text`/`_add_paragraph_with_runs` both
  now accept that instead of a concrete class. Deliberately *not*
  extended to the grouped-category/Skills-flat-join branches
  (`group.category is not None`, and the flat `" · "`-join) — several
  members still fuse onto one line there, the same "materially harder
  problem" Phase 25 originally cited, and harmless in practice since
  `collapseSkillsAndTechnologiesIfNeeded` migrates every loaded
  Skills/Technologies draft to standalone `kind: "compact"` entries
  before the BubbleMenu could ever reach a grouped one anyway.
  * `app/cv_markdown.py::render_sections_from_document`'s final `else`
    branch (`- {member.text}`) now calls `_block_markdown_text(member)`.
  * `app/cv_docx.py::render_templated_docx`'s matching generic branch
    switched from `_add_styled_paragraph(member.text, ...)` to
    `_add_paragraph_with_runs(member, ...)`.
  * A second, independent bug found in the same pass, not anticipated in
    planning: **Summary's own templated-DOCX branch was still
    `.text`-only**, despite Phase 25's own text above explicitly
    claiming "Summary + Experience" runs support in every export path.
    `render_templated_docx`'s `elif section.key == "summary":` branch
    had never actually been switched to `_add_paragraph_with_runs` —
    only Experience and (later) compact-Skills had. Fixed the same way,
    confirmed via a new dedicated test
    (`test_summary_entry_with_runs_is_honored`) rather than assumed
    correct because a docstring said so elsewhere.
  * Plain PDF/DOCX needed no separate change — both already consume
    `render_sections_from_document`'s markdown-ish text through
    `parse_inline_runs`, the same bridge Phase 25 built.
  * Templated PDF is a Playwright screenshot of the frontend, not a
    separate Python renderer — covered by the frontend change below.
* `frontend/src/components/PrintSectionBlock.tsx`'s `renderEntryText`
  used to call the runs-aware `renderBlockText` only for
  `section.key === "summary"` or `entry.kind === "compact"`. Rewritten
  to call `renderBlockText` unconditionally, with the per-section
  default (Contacts' "Label: value" auto-split, or plain `linkifyText`)
  passed in as `renderBlockText`'s own fallback — `renderBlockText`'s
  existing "authoritative runs, else this fallback" rule subsumed the
  old special-casing for free, so an untouched entry in every section
  keeps behaving exactly as before. A new `alignmentStyle` helper
  mirrors `PrintExperienceSection.tsx`'s existing inline `textAlign`
  style, applied to the same three standalone-entry render sites
  (Summary, the generic per-member branch, compact Skills) — matches
  what `_add_paragraph_with_runs` now applies unconditionally on the
  DOCX side, avoiding a templated-PDF/DOCX visual divergence for the
  same document (the exact class of bug this codebase has repeatedly
  caught and fixed, per Phase 23's own addenda).
* Testing: `lib/tiptap/converter.test.ts` gained runs↔marks round-trip
  cases (including one documented, harmless behavior change — an
  explicit `bold: false` alongside other formatting normalizes to
  *absent* on round-trip, since marks have no way to represent an
  explicitly-false flag; every consumer already treats the two as
  identical). New `lib/tiptap/marks.test.ts` (headless `Editor`,
  `commands.test.ts`'s own pattern): toggle/compose/`setLink`/
  `extendMarkRange`+`unsetLink`, including one case where two
  overlapping toggle ranges produce four runs, not the naively-expected
  three — real ProseMirror mark-composition behavior, not a bug, just a
  wrong first guess corrected before merging. New
  `FormattingBubbleMenu.test.tsx`/`LinkHoverCard.test.tsx` (6 cases
  each) drive the exported `shouldShow` predicates against a real
  headless `Editor` — shown/hidden per selection emptiness, locked/
  excluded ancestry, and the `isChildOfMenu` focus-fallback that keeps
  the menu open once `LinkEditPopover`'s `<input>` has focus (`view.
  hasFocus()` mocked directly rather than fighting jsdom's detached-view
  focus semantics). Backend: `test_education_entry_runs_are_honored`
  (rewritten from a Phase-25-era test that asserted the *old*
  scope-cut behavior), plus two new `cv_docx_templated` tests covering
  the generic-branch and Summary-branch fixes above directly against a
  real rendered `.docx`, not just the markdown bridge.
  Final suite: 651 backend passed (up from 649), 437 frontend passed
  (up from 420).
* Live-verified against the user's own real, in-use draft (`5ae5c13f`)
  via the Browser pane — this session's Browser pane couldn't composite
  frames for `computer`'s `screenshot`/coordinate actions (the same
  "not displayed" limitation Phase 26/27 hit), so verification leaned on
  `read_page`/`read_console_messages`/`read_network_requests` plus a
  handful of `ref`-targeted real (trusted) clicks rather than
  screenshots: a genuine double-click inside the **Languages**
  section (deliberately not Summary/Experience, to confirm the widened
  scope) produced a real text selection, which correctly surfaced
  `FormattingBubbleMenu` with all seven buttons in the live accessibility
  tree; clicking Bold applied a real `<strong>` to the selected text
  (confirmed via a live DOM query), autosaved (`PUT .../drafts/5ae5c13f`
  → 200), clicking it again removed the mark and autosaved a second
  time, and a fresh page reload confirmed the persisted document matched
  its original state exactly (5 `<strong>` elements — only the
  pre-existing Skills category labels — same as before any edit). Zero
  console errors throughout. Because this was real, load-bearing user
  data (not a disposable fixture), the test was deliberately scoped to
  one small, exactly-reversible round-trip rather than exploring every
  button. Link insertion/editing, the LinkHoverCard's own actions, and
  the alignment buttons were **not** live-clicked this pass — word-level
  text selection via `computer`'s `double_click` landed wherever the
  browser's own double-click-to-select-word logic happened to fall
  (once selecting a single "(" character), with no reliable way to
  aim at a specific word without coordinate/screenshot support; left as
  an opt-in follow-up, resting on the headless-editor test coverage
  above for those paths in the meantime — the same trade-off Phase 25/26
  made under an identical tooling limitation.

**Follow-up, reported directly after real use: "1. Bubble menu doesn't
appear in the experience bullets. 2. I don't see that alignment buttons
do anything to the text in the editor."** Both real bugs, found by going
back into the live draft rather than guessing from code alone.

1. **BubbleMenu missing in Experience bullets — a genuine ProseMirror
   selection-mapping bug, not a `shouldShow` logic error.** Confirmed by
   reaching the live `Editor` instance directly (Tiptap attaches it to
   the `.ProseMirror` DOM node as a plain `.editor` property — simpler
   than the fiber-walking this session tried first) and comparing it
   against the browser's own `window.getSelection()` after a real
   double-click: the native browser selection was correct
   (`"across "`), but `editor.state.selection` was an `AllSelection`
   spanning the *entire* document (`from: 0, to: 5981`), not a
   `TextSelection` over the clicked word — so `shouldShow` never had a
   real range to work with. Selecting inside an Experience entry's own
   *heading* (role title) worked correctly throughout, isolating the bug
   to `BulletNodeView.tsx` specifically. Root cause: that NodeView wrapped
   `<NodeViewContent>` *inside* one shared `contentEditable={false}`
   `<span>` alongside `DragHandle` and the bulletChar marker — chrome as
   an ancestor of the real editable content, not a sibling.
   `EntryNodeView.tsx` (Phase 27) already established the correct shape
   for this — a `contentEditable={false}` chrome element as
   `NodeViewContent`'s *sibling*, never its wrapper — but that fix was
   understood at the time as being specifically about drag mechanics
   (`stopEvent()`/`onDragStart` hijacking). It turns out to be the same
   underlying rule regardless of feature: ProseMirror's DOM↔position
   mapping — used for reading a native `Selection` back into document
   positions, not just drag/drop hit-testing — breaks when a node's real
   editable content sits inside a `contentEditable={false}` ancestor
   within its own NodeView wrapper.

   Fixed the same way EntryNodeView already had it: `group`/`relative`
   moved from the old inner `<span>` onto the outer `<p>`
   (`NodeViewWrapper`) — a real block box, immune to the "inline ancestor
   fragments across line boxes" problem the old forced-`display:block`
   span existed to work around in the first place; a `<p>` never needed
   that workaround. `anchorRef` (DocumentGutter's own measurement point)
   stays on a small dedicated `<span>` rather than moving to
   `NodeViewWrapper` itself — confirmed against `@tiptap/react`'s own
   type signature that `NodeViewWrapper` is a plain `React.FC`, not built
   with `forwardRef`, so a `ref` passed to it isn't guaranteed to reach
   the underlying DOM node. That dedicated span now holds only
   `DragHandle`, sibling to (not wrapping) `NodeViewContent`; the
   bulletChar marker span is also now a sibling, with its own explicit
   `contentEditable={false}` (previously inherited from the removed
   wrapper). No hover-scope regression — `group` living on the outer
   `<p>` now covers the whole row (chrome *and* text), actually a closer
   match to the pre-fix behavior than EntryNodeView's own accepted
   "handle-only" hover scope.

   Verified live, directly against `editor.state.selection`: the same
   double-click that used to produce `AllSelection` now produces a
   correct `TextSelection` (`from`/`to` matching the browser's own
   selection exactly), and `FormattingBubbleMenu` appears with all seven
   buttons. Full suite: 437 frontend passed (unchanged — no existing test
   asserted on the old DOM nesting), `tsc`/lint clean.

2. **Alignment buttons visibly did nothing — a real gap, not a timing
   issue.** `FormattingBubbleMenu`'s `updateAttributes` calls correctly
   wrote `alignment` onto the node (confirmed by every export path and
   by the `DocumentModel` itself, both already covered by this phase's
   own tests) — but no NodeView ever *read* that attr back into a visual
   style. `alignment` only ever reached the read-only Print*/export
   renderers (`PrintExperienceSection.tsx`, and this phase's own
   `PrintSectionBlock.tsx::alignmentStyle`); the live, editable Tiptap
   surface itself never rendered it. Fixed by adding
   `style={{ textAlign: node.attrs.alignment || undefined }}` to both
   `EntryHeadingNodeView.tsx` and `BulletNodeView.tsx`'s own
   `NodeViewWrapper` (`|| undefined`, not a bare attr read — the unset
   value is `null`, and `undefined` is the more honest way to say "no
   explicit value" for a React `style` prop, though both are treated
   identically).

   Verified live: selected text in a bullet, clicked Align Center,
   confirmed via a direct DOM query that the bullet's own `<p>` gained
   `text-align: center` (inline and computed) — then reverted to Align
   Left and confirmed the visual state matched the original. One
   accepted, not-yet-solved gap surfaced by this revert: there's no
   button to *clear* alignment back to "no explicit value" once set,
   only to set it to left/center/right explicitly — functionally and
   visually identical to unset (left is the template default either
   way), but not byte-identical in the persisted document. Left for a
   future pass; not blocking, and not something this live-verification
   round-trip could avoid once alignment had been touched at all.

   Full suite after both fixes: 437 frontend passed, 651 backend passed,
   `tsc`/lint clean.

**Second follow-up, reported directly after the fixes above shipped:
"Alignment doesn't work in summary, contacts, key projects, headers of
the roles... Basically, it works only for project names and experience
bullets."** Two more real, distinct bugs — the first fix above was
correct as far as it went (it fixed a bullet's own alignment, which is
why bullets/project-name subheadings visibly worked), but never actually
reached an *entry's own heading* text (Summary, Contacts, Key Projects,
Education, Skills, Tools & Technologies, Languages, and an Experience
role's own title line — everything rendered by `EntryHeadingNodeView`,
not `BulletNodeView`).

1. **Wrong schema target — `entryHeading` has no `alignment` attr at
   all.** `entryHeading` (schema.ts) carries no attrs of its own
   whatsoever; `id`/`included`/`locked`/`kind`/`evidence_id`/`alignment`
   all live on the *parent* `entry` node instead (confirmed directly
   against `converter.ts`'s own `entryToJSON`: the `entryHeading` JSON
   node has only `type`/`content`, no `attrs` key). `bullet` nodes *do*
   carry their own `alignment` (`blockAttributes()`), which is exactly
   why that path alone ever worked. `FormattingBubbleMenu.tsx`'s
   `setAlignment` was calling `editor.commands.updateAttributes
   ("entryHeading", {alignment})` — a schema attr that plainly doesn't
   exist, a silent no-op every time. Fixed by targeting `entry` instead
   of `entryHeading` (`ALIGNABLE_NODE_TYPES`), and by adding
   `entryAlignment` to `useNodeAncestry`'s own `NodeAncestry` shape —
   the walk-to-parent-entry lookup `EntryHeadingNodeView` already used
   for `sectionKey`/`entryLocked`, extended to also read the entry's own
   `alignment` attr, since this node's own `node.attrs.alignment` can
   never exist to read directly.

2. **A second, independent bug, found immediately after fixing the
   first — data updated correctly, but the screen still didn't change.**
   Confirmed directly against the live editor's own JSON
   (`editor.getJSON()`) that clicking Align Center on Summary text
   *did* correctly set `alignment: "center"` on the entry — but the
   on-screen `<p>` kept `text-align: ""`. Root cause: `entryAlignment`
   comes from the *parent* `entry` node's attrs, and a transaction that
   only changes an ancestor's attrs leaves `entryHeading`'s own node
   object referentially unchanged — so Tiptap's NodeView reconciliation
   has no reason to re-render `EntryHeadingNodeView` at all. This is
   exactly the "stale ancestor fact" pitfall `useNodeAncestry.ts`'s own
   docstring already documented for `DocumentGutter`'s remeasure (written
   during Phase 28, well before this bug existed) — a NodeView whose own
   node didn't change isn't guaranteed to re-render when an ancestor's
   did. That docstring's own fix (read fresh from the live doc, driven
   by an explicit `editor.on("update")` subscription rather than trusting
   the natural render cycle) applies here too, just via a local
   force-re-render (`useState` bumped from an `editor.on("update", ...)`
   listener) instead of an external store, since only this one NodeView
   instance's own render needed to react. Confirmed the *initial-mount*
   case (a fresh page load) never needed this — every NodeView gets
   fresh ancestry at mount time regardless; only a *live*, in-session
   `updateAttributes` transaction hit the gap, which is exactly the new
   scenario this phase introduced.

   Bullets never needed this fix — a bullet's own `alignment` change *is*
   a change to its own node, which Tiptap's default reconciliation
   already re-renders correctly on its own.

New tests: `useNodeAncestry.test.ts` gained direct coverage of
`entryAlignment` (resolved from the parent entry, not the entryHeading
node it's textually inside; `null` when unset). `marks.test.ts` gained a
dedicated `describe` block driving the exact commands
`FormattingBubbleMenu.tsx` now issues — including one test that
deliberately calls `updateAttributes("entryHeading", ...)` (the
original, wrong target) and asserts it's a no-op, documenting the actual
bug rather than just testing around it — plus confirmation that a
bullet's own alignment stays independent of its parent entry's.

Live-verified end to end, twice, against the same real draft
(`5ae5c13f`): selected Summary text, clicked Align Center — confirmed via
`editor.getJSON()` that the model updated *and*, this time, via a direct
DOM query that the on-screen `<p>` gained `text-align: center`
immediately, with no reload needed; reverted to Align Left the same way,
confirmed the autosave round-tripped (`PUT` → 200 twice), and confirmed
via a fresh reload that the draft's persisted state matched its original
exactly (5 `<strong>` elements, Summary and the earlier-tested bullet
both back to `text-align: left`). Zero console errors throughout. Full
suite: 443 frontend passed (up from 437), 651 backend passed (unchanged
— no backend code touched, this was a frontend schema-targeting and
NodeView-reactivity bug only), `tsc`/lint clean.

**Post-31 — removed the page-count and empty-section advisory chips.**
Unrelated to rich formatting — flagged directly from a screenshot of the
real app: the chip row below the A4 page (`AdvisoryChips.tsx`, Phase 20)
claimed "~2 pages (estimate)" for a document that visibly ran 4 pages
("↓ Page 4" and beyond, right there in the same screenshot), and the
chip row itself read as stray, unlabeled floating text with no visual
connection to the page above it.

Root cause of the wrong count, found by reading `lib/advisories.ts`
directly: `estimatePageCount` was a crude `chars ÷ 95-per-line ÷
55-lines-per-page` arithmetic guess — no awareness of headings, spacing,
margins, or real line-wrapping — dating to Phase 20, before Phase 29's
`lib/tiptap/pageBreaks.ts` existed. That later system does real DOM
measurement (`getBoundingClientRect()` on every heading/entry/bullet
against the actual CSS page-break rules) and is what draws the "↓ Page
N" markers the user was comparing against — the two were simply never
reconciled once the more accurate one existed.

Presented the option to wire `AdvisoryChips` into that same real
measurement instead of removing the count outright (a bigger change —
`pageBreaks.ts` needs the actual rendered page DOM, not just the
`DocumentModel` this component receives) — confirmed directly with the
user that the count isn't worth having at all, and the empty-section
chips ("'Portfolio' is included but has nothing in it.") should go too,
in the same pass: an included-but-empty section is exactly what export
already silently skips (`app/cv_markdown.py`'s own `if lines:
sections[key] = ...`), so flagging it added noise without changing what
to do about it.

* `lib/advisories.ts` — deleted `estimatePageCount`/`estimateLines`/
  `CHARS_PER_LINE`/`LINES_PER_PAGE` and `findEmptySections`/
  `isEffectivelyEmpty` outright, not left as unused dead code.
  `buildAdvisoryChips` is now a thin pass-through to the one surviving
  check, `findBulletCountOutliers` (a role with zero or notably more
  bullets than its peers) — the one that actually points at something
  worth fixing, not just a fact to note.
* `components/AdvisoryChips.tsx` — with the count gone, the row can
  legitimately have nothing to show; renders `null` in that case instead
  of an empty flex container. Gained a small "Worth a look" label above
  the chips for when there *is* something, directly addressing the
  second half of the report — the row no longer reads as unexplained
  floating text.
* Tests updated to match: `advisories.test.ts` lost the
  `estimatePageCount`/`findEmptySections` describe blocks entirely
  (deleted, not skipped) and `buildAdvisoryChips`'s own test now just
  confirms the delegation; `AdvisoryChips.test.tsx` replaced its
  page-count assertion with an empty-render case and added coverage for
  the new label.

Verified: full suite 437 frontend passed (down from 443 — net removal of
dead test coverage, no regressions), 651 backend passed (unchanged, no
backend code touched), `tsc`/lint clean. Live-verified against the same
real draft used throughout this phase's own verification: reloaded, the
"~2 pages"/empty-section chips are gone, the two real bullet-count
outliers still show correctly under a "Worth a look" label, zero console
errors in a fresh tab (a stale "estimatePageCount is not defined" error
briefly appeared mid-edit in the tab that had been open across the
file save — confirmed to be a one-time Vite HMR artifact from patching a
module that had just lost an export, not a real bug: a fresh tab loaded
the same URL with zero errors, and grep confirmed no remaining reference
to the deleted export anywhere in the source).

**Post-31, immediate follow-up — moved the chip row into the action
rail.** Shown a screenshot of a *different* real draft: even with the
count/empty-section noise gone, the remaining "Worth a look" chips
still sat as a bare, unlabeled row directly under the A4 page, easy to
miss. Confirmed directly: move it into the right-hand action rail, as
its own Card, below Gaps — "it would be much more noticeable this way."

* `components/AdvisoryChips.tsx` rewritten from a self-contained,
  document-computing component into a plain presentational one — `chips:
  AdvisoryChip[]` in, a row of pills out, no `document` prop, no
  null-handling of its own — matching the same "Card lives in
  DraftScreen.tsx, the panel is just its content" split every sibling
  (`GapsPanel`, `ExcludedContentPanel`, `UnusedEvidencePanel`) already
  uses, rather than being the one panel that owned its own Card-shaped
  logic inline.
* `components/DraftScreen.tsx` now computes `buildAdvisoryChips(cvDocument)`
  once (same "cheap arithmetic, no memoization needed" reasoning
  `advisories.ts`'s own docstring already gives) and renders the new
  `Card`/`CardHeader`/`CardTitle("Worth a look")`/`CardContent` block
  right after the Gaps Card, *only* when there's at least one chip —
  deliberately not an always-visible empty-state Card like its
  neighbors: "nothing worth a second look" isn't information worth
  permanent shelf space the way "no gaps"/"nothing excluded" is.
* Tests follow the same split: `AdvisoryChips.test.tsx` now only
  confirms the render itself (given `chips`, not `document`) — the
  "should this render at all" and "what counts as worth flagging"
  questions already live in `DraftScreen.tsx`/`advisories.test.ts`
  respectively.

Verified: full suite 435 frontend passed (down from 437 — two
`document`-prop-shaped tests replaced by two `chips`-shaped ones, no
regressions), 651 backend passed (unchanged), `tsc`/lint clean.
Live-verified against the same real draft: the "Worth a look" Card now
renders in the action rail, directly below Gaps, with both outlier chips
intact; zero console errors in a fresh tab (the previous edit's own
stale-HMR error, same class as noted above, appeared once more mid-save
and cleared the same way — confirmed harmless, not re-documented in
detail a second time).

**Post-31, third follow-up — item boxes still didn't visually match their
new rail siblings.** Reported directly from a screenshot: each chip
still read as a fully-rounded pill with no background fill, next to
Gaps'/Excluded from CV's own `rounded-lg border bg-muted/40 p-3` item
boxes immediately above and below it. Confirmed by reading
`GapsPanel.tsx`/`ExcludedContentPanel.tsx`/`UnusedEvidencePanel.tsx`
directly: all three already use that exact class string for their own
per-item box — `AdvisoryChips.tsx`'s `rounded-full`/no-fill pill styling
was simply a leftover from when it rendered as a compact inline row
under the page, never updated once it moved into a context where it sits
directly alongside those other boxes.

`components/AdvisoryChips.tsx` switched from a `flex flex-wrap` row of
`rounded-full` badges to a `<ul className="space-y-2">` of `<li
className="rounded-lg border bg-muted/40 p-3">` — the identical class
string, one item per line instead of wrapped inline, matching its
siblings' own list shape as well as their box styling. Verified two
ways: `AdvisoryChips.test.tsx` asserts the exact class list directly on
a rendered item; live against the real draft, `getComputedStyle` on a
"Worth a look" item, a Gaps item, and an "Excluded from CV" item all
returned identical `border-radius: 10px` and `background-color:
oklab(0.97 0 0 / 0.4)`. Full suite: 435 frontend passed (unchanged count
— one test's assertions changed shape, no new/removed cases), 651
backend passed (unchanged), `tsc`/lint clean, zero console errors in the
live check.

**Post-31, fourth follow-up — the on-screen page-break guide over-counted
pages, on a completely different draft.** Reported directly: a draft
previewed as 4 pages on screen, with page 2 visibly cutting off mid-
bullet, but "in fact it's shorter" — and a guess at the cause: "+ Add
Bullet" buttons occupying page space they don't in the real export.

Verified against ground truth before touching any code: POSTed the
draft's real `assembled_cv`/`document` straight to the running `/export`
endpoint (`format: pdf, template_id: classic` — the same templated path
Playwright screenshots) and counted pages with `pypdf`. **Real export:
3 pages.** The guide's own predicted break count: 4. `pypdf`'s own
extracted text for page 2 ended with "...Led game design, including
effective team management, for the mobile adaptation of SuperCity." —
confirming the report exactly, and confirming the guide's own predicted
break landed *earlier* than that, not at it.

The reported hypothesis was directionally right, confirmed by the
numbers: `lib/tiptap/pageBreaks.ts`'s own `PAGE_CONTENT_HEIGHT_PX` ≈
986px, so 3 real pages need ≈ 2959px of true content. The live page,
buttons visible, measured 3196px; hiding all 9 "+ Add Bullet" buttons
(EntryNodeView.tsx) dropped it to 2971px — just barely over the 3-page
threshold, meaning their own height was very plausibly the whole gap.
`EntryNodeView.tsx`'s "+ Add Bullet" is genuinely real, normal-flow
content on screen — unlike every *other* piece of editor chrome (drag
handles, the checkbox/Sparkles gutter, the whole `DocumentGutter`
overlay), which Phase 28 had already made `position: absolute`
specifically to avoid shifting real content — but `PrintExperienceSection.tsx`
(what the real templated export actually screenshots) never renders an
"Add Bullet" affordance at all. Every visible button added height
`PageBreakGuide.tsx`'s `measureUnits` saw but the real export never
produces, compounding across every Experience role into a phantom extra
page.

Fixed by teaching the measurement to discount it, not by changing the
button's own on-screen layout (safer — no risk of it visually
overlapping the next role's heading, the tradeoff a `position: absolute`
version of the button would have carried):

* `components/tiptap/EntryNodeView.tsx` — the button gained
  `data-page-break-exclude="true"`, a plain DOM marker (same idea as
  Phase 30's own `data-page-break-before`, just for the opposite
  direction: discounting height instead of forcing a break).
* `components/tiptap/PageBreakGuide.tsx`'s `measureUnits` collects every
  `[data-page-break-exclude]` element's rect once per remeasure (not
  re-queried per unit) and `relativeRect` — converted from a module-level
  function taking `(page, el)` into a closure over that one collection —
  now subtracts however much excluded height sits above a given
  element's own position from both its `top` and `bottom`.

Live-verified against the real draft: the guide now predicts exactly 2
break lines (3 pages), matching the real export's own page count
exactly — the phantom 4th page is gone. The precise *content* at the
page-2/page-3 boundary still isn't pixel-identical to Playwright's own
real pagination (a few bullets' worth of remaining drift) — expected and
already documented as inherent to this being "an approximation, not a
re-implementation of Chromium's real pagination engine"
(`pageBreaks.ts`'s own docstring), not a regression from this fix; the
page *count* — the actual thing reported — now matches exactly. Full
suite: 435 frontend passed (unchanged — `measureUnits`'s own DOM-walking
logic isn't unit-tested directly, same as before this fix, per that
function's own docstring on why: `getBoundingClientRect()` is always a
zero rect under jsdom), 651 backend passed (unchanged), `tsc`/lint
clean, zero console errors in the live check.

**Post-31, fifth follow-up — the fourth follow-up's own fix was wrong,
caught immediately from a live screenshot.** After a server relaunch +
hard reload (ruling out stale HMR), the guide's break line now visibly
cut through the *middle* of a single bullet's own wrapped text —
between "...addressing challenges for player" and "engagement and
competitive fairness..." — not at a page edge at all.

Root cause, found by re-reading `computePageBreaks` itself: the fourth
follow-up's fix subtracted every excluded element's cumulative height
directly from each unit's own `top`/`bottom` in `measureUnits`. That
correctly fixed the page *count* (fewer phantom pages), but every one of
those `top`/`bottom` values is also used *directly* as the on-screen
pixel position for the rendered break line — shifting them into a
"corrected" coordinate space for the budget math also shifted the
*rendered* line away from where the real content actually sits,
landing it wherever "corrected top minus a few hundred px" happened to
fall, which was mid-sentence in this case. `computePageBreaks` itself
also documents, explicitly, that a single leaf (one bullet's own text)
is "never split further" — a break rendering *inside* one is a
contradiction of the algorithm's own stated behavior, which is what
made this findable from the code alone, not just the screenshot.

Fixed by decoupling the two uses instead of conflating them: units and
excluded rects both stay in real, untouched on-screen coordinates
throughout (`measureUnits` no longer subtracts anything); `computePageBreaks`
gained a third parameter, `excludedRects: PageBreakRect[]`, and instead
*widens the effective per-page budget* by however much excluded height
falls within whatever span is currently being checked
(`excludedHeightWithin(pageStart, unit.bottom)`) — the rendered break
position (`unit.top`) is never adjusted, only the *decision* of whether
a unit fits. `measureUnits` now returns `{ units, excludedRects }`
instead of bare `units`; `PageBreakGuide`'s own `remeasure` passes both
through to `computePageBreaks` explicitly (previously relying on that
function's own default page-height parameter).

New tests in `pageBreaks.test.ts` cover the corrected mechanism directly
against synthetic rects (same style as every other case in that file):
excluded height within a page's own span widens its effective budget
enough to keep a unit that would otherwise overflow; when it's *not*
enough, the break still lands at the unit's own real, unshifted `top`;
an excluded rect below the unit being measured has no effect; the
parameter defaults to `[]`, preserving every pre-existing test's own
behavior unchanged.

Live-verified against the same real draft, precisely this time — not
just the break *count* but the exact *content* on either side of each
break: the page-2/3 break now sits cleanly between "...for the mobile
adaptation of SuperCity." (a bullet's own full, unsplit text — matching
`pypdf`'s own extracted page-2 ending exactly, confirmed in the fourth
follow-up above) and "Lead Game Designer — Playkot (Jan 2016 – Feb
2017)" (the next role's own heading) — a clean entry-to-entry boundary,
never mid-paragraph. Full suite: 439 frontend passed (up from 435 — the
four new `excludedRects` cases), 651 backend passed (unchanged), `tsc`/
lint clean, zero console errors in a fresh tab.

**Post-31, sixth follow-up — AI-edit provenance popover redesign.**
Reported directly, with screenshots: the "Sparkles" popover (an
Experience bullet's rewrite rationale + "Revert to original") overlapped
the very bullet it was explaining, and clipped off-screen on a narrow
viewport. Root cause: `sparkles` (`BulletNodeView.tsx`) is handed to
`useGutterItem`, and `DocumentGutter.tsx` renders it inside *its own*
overlay at the page's left margin — so Radix's default anchor (the
Popover's own trigger, the small Sparkles icon) was a narrow point
sitting in that margin, not the bullet row it annotated; centering a
fixed ~320px card on that point let roughly half of it hang off
whichever side had less room. Requested redesign: the card should sit
strictly above or below the bullet, at the A4 page's own content width,
with Original shown before the rationale and an explicit close button.

* Gave the Popover an explicit anchor via `Popover.Anchor`'s own
  `virtualRef` prop (`@radix-ui/react-popper`'s `Measurable` — any
  object with `getBoundingClientRect()`, not necessarily a rendered
  child) pointing at the real bullet `<p>` itself
  (`anchorRef.current`'s own closest `.cv-print-bullet` ancestor —
  `anchorRef` already existed for `useGutterItem`'s own measurement,
  reused rather than adding a second ref). `PopoverContent` sizes itself
  to `width: var(--radix-popper-anchor-width)` — a real CSS custom
  property Radix sets from that same anchor's own measured width
  (confirmed directly in `@radix-ui/react-popper`'s source,
  `contentStyle.setProperty(...)`) — so the card exactly spans the
  bullet row's own width (the full A4 page's content width) rather than
  a fixed size. `side="bottom"` with Radix's own default collision
  avoidance flips to `"top"` automatically when there's no room below —
  "strictly above or below," never to the side, for free (confirmed
  live: `data-side="top"` on a bullet near the bottom of the visible
  page).
* Content reordered — Original now precedes the rationale — and gained
  an explicit close button (`ui/popover.tsx` gained a `PopoverClose`
  wrapper; none existed before this pass).

**A real Radix internal race condition, found live, not anticipated in
planning.** The first version kept `Popover.Trigger` wrapping the
Sparkles button (the standard pattern) alongside the new
`Popover.Anchor`. Live-instrumented (a temporary `window.__anchorCalls`
counter inside the virtual anchor's own `getBoundingClientRect`,
removed once diagnosed): the function was **never called at all** — the
rendered card stayed a tiny, mispositioned ~30px box regardless.
Traced directly in `@radix-ui/react-popover`'s own source:
`Popover.Trigger`, when no custom anchor has been registered *yet*,
implicitly wraps itself in its own anchor registration — and does so
unconditionally on the component's first render, since the
`hasCustomAnchor` context flag `Popover.Anchor`'s own effect sets can't
propagate until a full extra render cycle later. `PopperAnchor`'s own
unmount path only calls its registration callback when *attaching* a
node, never on detach, so once the Trigger's own implicit registration
wins that first race, nothing ever corrects it. Reordering
`Popover.Anchor` before `Popover.Trigger` in JSX did **not** fix it
(confirmed live, still zero calls) — the same race, just won by the
other side depending on effect-firing order, not a real fix. Fixed by
removing the second competitor entirely: the Sparkles button is now a
plain, manually-controlled trigger (`Popover open={provenancePopoverOpen}
onOpenChange={setProvenancePopoverOpen}` + a bare `onClick` toggling
that state, `aria-haspopup`/`aria-expanded` added by hand since
`Popover.Trigger` no longer supplies them) — with no `Popover.Trigger`
in the tree at all, there is nothing left to race against
`Popover.Anchor`'s own registration.

Live-verified against the real draft used throughout this phase's own
verification (candidate `595187d6`, draft `a916453c`): after the fix,
`--radix-popper-anchor-width` correctly resolved to the real bullet's
own measured width (657.64px, confirmed identical to the bullet's own
`getBoundingClientRect()`), `PopoverContent`'s own computed CSS `width`
matched exactly, and `data-side="top"` confirmed the collision-flip
worked for a bullet near the page's bottom. Content order (Original
before rationale) and the close button's own underlying state transition
(`aria-expanded` correctly flipping `true`→`false`, Radix's own
`data-state` correctly flipping to `"closed"`) were both confirmed
directly. One thing this pass could **not** fully confirm: whether the
close button's own CSS exit animation visually completes and unmounts
the card — `data-state` and `aria-expanded` both flip correctly, but the
element itself stayed present after the state change, with its CSS
`animationName` stuck on `"exit"` never resolving. The identical
symptom appeared on the *entry* animation too (`transform` permanently
stuck at `scale(0.95)`, `data-open:zoom-in-95`'s own starting keyframe,
confirmed via `getComputedStyle`, even long after `data-state="open"`
had already settled) — both consistent with, and not distinguishable
from, this session's own already-documented "Browser pane can't
composite frames" limitation (the same one that blocked `computer`'s
`screenshot` and `requestAnimationFrame` earlier in Phases 26/27):
CSS animations fundamentally depend on the same compositor pipeline,
and `animationend`/`transitionend` firing (which `Presence` needs to
actually unmount closed content) would be exactly what that limitation
blocks. Since the underlying React/Radix *state* is independently
confirmed correct both ways (open and close), and this exact animation
class (`data-open:animate-in`/`data-closed:animate-out`) is unchanged,
pre-existing `ui/popover.tsx` styling this pass didn't touch, this is
recorded as a real, not-fully-resolved verification gap rather than a
claimed fix — worth a real click in an actual browser to confirm
outright, the same category of follow-up Phase 25/26 already left open
under an identical tooling constraint.

New coverage: `DocumentEditor.test.tsx` gained a dedicated describe
block driving a real Experience bullet with `evidence_id`-linked
provenance through `initialDocument`/`provenance` props — opens on the
Sparkles trigger, confirms Original renders before the rationale via
`compareDocumentPosition`, confirms "Revert to original" actually
restores the bullet's text through `onModelChange`, and confirms the
explicit close button closes the popover (this last one exercises
`userEvent.click` under jsdom, a genuine trusted-enough interaction
unlike the Browser pane's own compositing gap above — jsdom has no
compositor at all, so `Presence`'s animation-driven unmount logic
there depends on jsdom's own synchronous, animation-free DOM semantics,
not a real CSS animation lifecycle). Full suite: 441 frontend passed (up
from 439 — two new provenance-popover cases), 651 backend passed
(unchanged — no backend code touched), `tsc`/lint clean.

**Follow-up, reported directly: no way to edit the CV's own role title
(`assembled_cv.headline`) per draft.** Until now `headline` was always
`candidate.headline` verbatim (`cv_assembler.py`), the same across every
draft — a person tailoring for a vacancy that didn't call for one of
their listed titles (e.g. dropping "Product Manager" from "Senior/Lead
Game Designer, Product Manager") had no way to say so without editing
the global profile field every *other* draft still relies on. Since
`CVDraft.assembled_cv` is already a per-draft snapshot in its own table
row, not a live join against `Candidate.headline`, this only needed a
new editable field, not a schema change — `DraftScreen.tsx` autosaves
`{ assembled_cv: { ...draft.assembled_cv, headline } }` on the same
~1.5s debounce as Vacancy title, already accepted by the existing
generic `update_cv_draft` partial-patch (`api/routes/entity_crud.py`),
no backend change required.

First version put the edit control in its own "Role title" form field
above the CV, next to Vacancy title — reworked immediately after a
mockup showing an X over that field and an arrow pointing at the actual
headline text inside the A4 preview: **"let me edit it here,"** plus a
broader steer that document.sections content, section headers included,
should ideally all be editable in place rather than through side
fields. Scoped to just the header for this pass (section-header editing
is a separate, materially larger change — `PrintDocumentSection.title`
isn't part of the Tiptap document schema at all today — left as an
explicit future item, not attempted here). `CvPrintHeader.tsx` gained an
optional `onHeadlineChange` prop: when passed, the headline renders as a
plain `<input>` (not a Tiptap node — no marks/formatting, just text)
styled with `font: inherit` so it's visually indistinguishable from the
static `<p>` it replaces; omitted, it stays exactly the original
read-only `<p>`. `DocumentEditor.tsx` forwards a new same-named prop
straight through to `CvPrintHeader`; `DraftScreen.tsx` passes
`setHeadline`. Every other caller (`PrintPreview.tsx`'s
Playwright-screenshot export path in particular, where this render *is*
the exported document) omits the prop and is unaffected.

A new `liveAssembledCv` (`draft.assembled_cv` with the in-progress
`headline` edit layered on top, mirroring how `cvDocument` already
stands in for `draft.document`) feeds `DocumentEditor`/`ExportButton`/
`WritebackDialog` instead of `draft.assembled_cv` directly, so the
on-screen preview and an Export/Writeback fired mid-edit both reflect
the typed title immediately rather than lagging behind the debounced
PUT. Safe to hand `DocumentEditor` a fresh `assembledCv` object on every
keystroke: its rebuild-from-`assembledCv` effect only fires before a
real `initialDocument` has been seeded (see that effect's own comment),
so this never touches in-progress document edits once a draft is loaded.

**A genuine, real data-corruption incident during this pass's own live
verification, disclosed rather than quietly overwritten:** the *first*
version's live check against the user's actual in-use draft (`c5ea4a06`)
truncated its persisted `assembled_cv.headline` from "…Product Manager"
to "…Product" — traced to Vite HMR pushing several successive
in-progress edits of `DraftScreen.tsx` into a browser tab that had been
left open on that real draft since before the edits started, rather
than to any bug present in the final code (a clean reload afterward,
checked directly against the network log, seeded correctly and fired no
spurious PUT). Confirmed no other draft was touched (`updated_at`
checked across all five of this candidate's drafts), then repaired by
PUTting the original text back before continuing. Lesson applied for
the rest of this pass: no further edits were made while a real draft
sat open in the live-reloading tab; verification reloaded fresh only
once the code was finished.
