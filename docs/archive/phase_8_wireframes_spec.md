# Phase 8.1–8.3 UI wireframes (dead — archived 2026-08-07)

> Moved here from `docs/phase_8_wireframes_spec.md` — its subject (Qt/
> PySide6 widgets: `QComboBox`, `QDialog`, `QTextEdit`) has no forward
> relevance at all. `ui/main_window.py` has been frozen and unbuilt-on
> since 2026-07-24 (confirmed via `git log -- ui/`), superseded first by
> the features it specs shipping in Qt, then by the entire Qt UI being
> replaced by the React frontend (Phase 14+). Kept only for historical
> curiosity, not as a reference for anything still buildable.

# Phase 8.1–8.3 UI wireframes

Companion to `docs/development_plan.md`. Visual references were sketched as
HTML mockups in a chat session (not code) — this doc is the Qt-native
translation meant to actually be implemented.

---

## Phase 8.1 — Multiple candidate profiles

**Where**: new row above the existing "Resume" section, left pane.

**New widgets**:
- `QComboBox` (`profile_selector`) — populated with `"{name} — {n} entries"`
  per saved profile; current selection reflects the active profile.
- `QPushButton` ("+ New profile") — optional if ingest always forks; see
  open question below.
- `QLabel`, small/muted — note under the Ingest button: "Ingesting creates
  a new profile, it won't overwrite '{active profile name}'."

**Behavior**:
- Selecting a different profile in the combo box loads it into the right
  pane, same as a fresh ingest currently does.
- On ingest, a new profile is created and appended to the combo box; the
  combo box switches to the new profile automatically.

**Open questions**:
- Should ingest *always* fork, or prompt "Overwrite '{name}' / Create new
  profile" each time? Silent forking risks surprise duplicates if the user
  intended an update.
- Storage: one JSON file per profile under a `profiles/` directory, keyed
  by profile id? Needs a small addition to `CandidateService`.

---

## Phase 8.2 — Actionable gap analysis

**Where**: existing "Gaps" panel, right pane (currently a flat text dump
inside the Skills/Certifications `QTextEdit`).

**Change**: replace plain-text rendering with either
(a) rich HTML inside the existing `QTextEdit` (colored `<span>` per
severity, simplest to ship), or
(b) a `QListWidget` with a custom item widget per gap (more work now, but
sets up future per-gap actions like "copy suggestion" or "dismiss").
Recommend (a) for the prototype, (b) once gaps become interactive.

**Per-gap layout**:
- Severity tag, left-aligned, color-coded: `HIGH` (red), `MED` (amber),
  `LOW` (gray/muted).
- Gap description, one line.
- Suggested-edit line, indented, muted/accent color, informational only —
  never wired to an "apply" action (would risk inventing ungrounded
  claims in the tailored CV).
- Gaps sorted severity-desc; low-severity items collapsed under a static
  `"+ N more, low priority · collapsed"` line for the prototype.

**Open questions**:
- Severity source: LLM-assigned in the same `analyze()` call that
  produces gaps, or a deterministic heuristic (e.g. how many JD keywords
  the gap touches)? Affects both cost and how defensible the sort is.
- Does "collapsed" need to be click-to-expand in this phase, or is a
  static count acceptable until 8.2 is revisited?

---

## Phase 8.3 — Save edits back to the graph

**Where**: each editable section in the right pane — Summary, Experience
bullets, Skills.

**New widgets**:
- `QPushButton` ("Save edits to profile") under each editable section —
  enabled only when the section's current text differs from what was
  last loaded/generated (dirty-check against the `AssembledCV` output).
- `QDialog` ("Save to profile?") triggered by that button:
  - One `QCheckBox` per proposed write, pre-checked when the target field
    exists on the domain model.
  - Disabled `QCheckBox` with a warning color when no target field exists
    yet (see Summary gap below) — visible, not silently dropped.
  - `QPushButton` "Cancel" / "Save selected".

**Mapping specifics**:
- Experience bullets: straightforward — `CVProjection` groups bullets by
  `experience_id` already, so a save maps 1:1 to an `Experience` entry.
- Summary: **`Candidate` has no `summary` field today** (only `headline`).
  There's nowhere for this write to land until that's decided — add a
  field, or route it somewhere else entirely (e.g. a new `Evidence` of
  its own type).
- Skills: per-skill diff (match by name, fragile against typos/reorder)
  vs. treat any Skills-box edit as a full-list replace (simpler, loses
  per-skill history). Needs a decision before implementation.

---

## For Claude Code

Pair this doc with screenshots of the three rendered mockups from the
design chat (profile switcher, sorted gaps panel, save-to-profile flow)
for visual reference — the widget/state spec above is the part meant to
actually be implemented from.
