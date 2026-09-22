"""Save edited CV content back into the Candidate Profile — Phase 8.3,
extended in Phase 11 to also cover an Experience block's header facts
(position/company/period) and project renames, not just bullets — see
build_experience_proposals's docstring.

Reverses Phase 6's "edited text is never re-parsed back into the domain
model" for the sections where it's unambiguous to do (Summary, Experience,
Skills) — not Education/Languages/Certifications/Key Projects, which are
already deterministic 1:1 mirrors of Candidate facts (see
docs/development_plan.md Phase 8 notes), so there's no edit-vs-source
divergence to save back there.

Phase 11 scope note: this covers write-back *completeness* (nothing the
user visibly edits gets silently dropped or duplicated). It does not cover
"conflict handling when the same Evidence has diverged across CV versions"
(docs/development_plan.md Phase 11's second bullet) or Phase 8.1's
profile-merge note — those need staleness detection plus a merge/overwrite
UI, a distinct feature left for separate scoping.

Per docs/architecture.md, the UI never builds or modifies domain models
directly — this module is the Application Service that does that; UI code
(ui/main_window.py) only calls into it and renders whatever it returns.

Each `build_*_proposals()` function turns a section's currently-edited text
into a list of `WritebackProposal`s — one checkbox's worth of a pending
write each, per docs/phase_8_wireframes_spec.md's confirm-dialog spec.
Building a proposal never touches storage; `WritebackProposal.apply()` does,
against whichever CandidateService the caller decides to target (the
profile that produced the CV being edited — see ui/main_window.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from app.candidate_service import CandidateService
from app.cv_markdown import render_sections_from_document
from domain.models import AssembledExperienceEntry, Candidate, PrintDocument, TailoredBullet


@dataclass
class WritebackProposal:
    """One proposed write, shown as one checkbox in the confirm dialog.

    `enabled=False` represents a write that couldn't be safely determined
    (see build_experience_proposals's block-count-mismatch case) — shown
    disabled with a warning color rather than silently omitted, per
    docs/phase_8_wireframes_spec.md. `apply` is None in that case.
    """

    label: str
    enabled: bool
    apply: Callable[[CandidateService], None] | None


def build_summary_proposal(edited_text: str) -> WritebackProposal:
    text = edited_text.strip()

    def apply(service: CandidateService) -> None:
        service.update(summary=text)

    return WritebackProposal(label="Update candidate summary", enabled=True, apply=apply)


_SKILL_LINE_RE = re.compile(r"^(?P<name>.+?) \((?P<proficiency>[^()]+)\)$")
_CATEGORY_LINE_RE = re.compile(r"^\*\*(?P<category>.+?)\*\*(?:: (?P<members>.+))?$")


def _split_skill_line(text: str) -> tuple[str, str | None]:
    """Inverts a single skill/technology *item*'s `Name (Proficiency)`
    suffix — the format app/cv_markdown.py's `_render_grouped_by_category`
    appends to each item, whether or not it's part of a category group.
    Returns (text, None) unchanged when there's no such suffix."""
    match = _SKILL_LINE_RE.match(text)
    if match:
        return match.group("name"), match.group("proficiency")
    return text, None


def _iter_skill_line_items(line: str) -> list[tuple[str, str | None, str | None]]:
    """Yields (name, proficiency, category) for every skill named on one
    already-`"- "`-stripped line of app/cv_markdown.py's rendered Skills
    text. Handles all three shapes `_render_grouped_by_category`/
    `group_entries_by_subheading`/`render_sections_from_document` produce:
    * a plain `Name (Proficiency)` line — one item, category=None.
    * a compact `**Category**: item1 (Prof); item2` line — split on "; "
      into one (name, proficiency, category) item per member. A category
      with no members (`**Category**` alone) yields nothing — there's no
      item to propose adding.
    * Post-30: a flat, *uncategorized* `Item1 · Item2 · Item3` line (no
      leading `**Category**` — an entire uncategorized skills/
      technologies list now joins onto one line this way, the same
      "compact single line" treatment a categorized group already got —
      see PrintSectionBlock.tsx's/app/cv_docx.py's identical `" · "`
      join) — split on `" · "` into one item per member, category=None
      each. Checked only once the category shape above doesn't match, so
      a category's own compact line (which never contains a literal
      `" · "`) is never misread as this case instead.

    Regression guard: an earlier version of this function only understood
    the plain shape, so a real categorized skill's whole compact line —
    asterisks, colon, semicolons and all — was proposed as one bogus
    "skill" (e.g. "Add skill: **Vendor & Pipeline Management**:
    outsourcing management; documentation"). Reported directly, from a
    real tailored export whose Skills text was entirely category-grouped.
    The same failure mode resurfaced for the flat-line case once that
    started joining multiple skills onto one line too (e.g. "Add skill:
    Python · Go" as one bogus item) — this second split fixes it the same
    way, one line lower.
    """
    category_match = _CATEGORY_LINE_RE.match(line)
    if category_match is not None:
        members = category_match.group("members")
        if not members:
            return []
        category = category_match.group("category")
        return [(*_split_skill_line(member), category) for member in members.split("; ")]
    if " · " in line:
        return [(*_split_skill_line(member), None) for member in line.split(" · ")]
    return [(*_split_skill_line(line), None)]


def build_skills_proposals(candidate: Candidate, edited_text: str) -> list[WritebackProposal]:
    """One proposal per skill name in the edited text that isn't already on
    the Candidate (case-insensitive match on name alone — a `(Proficiency)`
    suffix is real bug found via actual pipeline output: a candidate whose
    existing skill has a proficiency set (e.g. "Roadmapping (Expertise)")
    was proposed as a brand-new "Add skill: Roadmapping (Expertise)" every
    time, since the raw line never matched the bare stored name) —
    additive-only. Never proposes removing an existing skill just because
    this vacancy's tailored list dropped it; that list is a per-vacancy
    subset, not the full profile (same reasoning as Candidate.projects's
    always-included treatment).

    A category-grouped line (see `_iter_skill_line_items`) proposes one
    "Add skill" per member, each carrying that line's category through to
    `CandidateService.add_skill` — so accepting the proposal recreates the
    same category, not an uncategorized duplicate.
    """
    existing = {skill.name.strip().lower() for skill in candidate.skills}
    seen: set[str] = set()
    proposals: list[WritebackProposal] = []

    for raw_line in edited_text.split("\n"):
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        for name, proficiency, category in _iter_skill_line_items(line[2:].strip()):
            key = name.lower()
            if not name or key in existing or key in seen:
                continue
            seen.add(key)

            def apply(
                service: CandidateService,
                name: str = name,
                proficiency: str | None = proficiency,
                category: str | None = category,
            ) -> None:
                service.add_skill(name=name, proficiency=proficiency, category=category)

            label = f"Add skill: {name}" + (f" ({proficiency})" if proficiency else "")
            proposals.append(WritebackProposal(label=label, enabled=True, apply=apply))

    return proposals


_MISMATCH_LABEL = (
    "Could not map the Experience section to profile entries — the number "
    "of role blocks changed. Edit bullets within a role instead of "
    "adding/removing whole role blocks, then try saving again."
)


def build_experience_proposals(
    assembled_experience: list[AssembledExperienceEntry],
    edited_text: str,
) -> list[WritebackProposal]:
    """One proposal per non-gap Experience entry whose block of edited text
    can be matched back to it. Blocks are matched *positionally* — split on
    blank lines (the same convention app/cv_markdown.py:
    render_experience_section() emits: `**Position**...` header, optional
    `*Project Name*` sub-headers, `- bullet` lines) and zipped 1:1, in
    order, against `assembled_experience` (which already includes gap
    entries in their correct chronological slot, same as the rendered
    text). Gap-entry blocks are skipped — they have no achievements to
    save. Entries where *neither* the header facts (position/company/
    period/location, via `_parse_header`) *nor* the bullets differ from
    `entry` are also skipped, so the confirm dialog only lists roles the
    user actually edited — a title-only edit with identical bullets still
    produces a proposal (Phase 11; previously silently dropped, see module
    docstring).

    If the block count doesn't match (a whole role added/removed, not just
    edited), returns a single disabled proposal explaining why, rather
    than guessing which block maps where.
    """
    blocks = _split_into_blocks(edited_text)
    if len(blocks) != len(assembled_experience):
        return [WritebackProposal(label=_MISMATCH_LABEL, enabled=False, apply=None)]

    proposals: list[WritebackProposal] = []
    for entry, block in zip(assembled_experience, blocks):
        if entry.is_gap or entry.experience_id is None:
            continue

        header_line = block.split("\n", 1)[0]
        parsed_header = _parse_header(header_line)
        facts_changed = parsed_header is not None and parsed_header != (
            entry.position,
            entry.company,
            entry.period,
            entry.location,
        )

        role_bullets, project_bullets = _parse_block_bullets(block)
        bullets_changed = (role_bullets, project_bullets) != _group_tailored_bullets(entry.bullets)

        if not facts_changed and not bullets_changed:
            continue

        if facts_changed:
            position, company, _period, _location = parsed_header
            label = position + (f" — {company}" if company else "")
        else:
            label = entry.position + (f" — {entry.company}" if entry.company else "")
        experience_id = entry.experience_id
        fact_fields = (
            {
                "position": parsed_header[0],
                "company": parsed_header[1],
                "period": parsed_header[2],
                "location": parsed_header[3],
            }
            if facts_changed
            else {}
        )

        def apply(
            service: CandidateService,
            experience_id: str = experience_id,
            role_bullets: list[str] = role_bullets,
            project_bullets: dict[str, list[str]] = project_bullets,
            fact_fields: dict[str, str | None] = fact_fields,
        ) -> None:
            service.update_experience(experience_id, achievements=role_bullets, **fact_fields)
            if not project_bullets:
                return
            candidate = service.get()
            source = next(e for e in candidate.experience if e.id == experience_id)
            existing_project_ids = {project.name: project.id for project in source.projects}

            # A project name with no match on either side is ambiguous from
            # text alone — was it renamed, or removed-and-replaced? Only
            # resolve the unambiguous case (exactly one name disappeared,
            # exactly one appeared): rename in place instead of leaving an
            # orphaned old project plus a duplicate new one. Any other shape
            # (multiple simultaneous renames, a genuinely new project added
            # to a role that already had none, etc.) falls back to the
            # additive-only behavior below, same philosophy as
            # build_skills_proposals.
            removed_names = set(existing_project_ids) - set(project_bullets)
            added_names = set(project_bullets) - set(existing_project_ids)
            rename_map: dict[str, str] = {}
            if len(removed_names) == 1 and len(added_names) == 1:
                rename_map = {next(iter(added_names)): next(iter(removed_names))}

            for project_name, achievements in project_bullets.items():
                if project_name in existing_project_ids:
                    service.update_experience_project(
                        experience_id, existing_project_ids[project_name], achievements=achievements
                    )
                elif project_name in rename_map:
                    old_name = rename_map[project_name]
                    service.update_experience_project(
                        experience_id,
                        existing_project_ids[old_name],
                        name=project_name,
                        achievements=achievements,
                    )
                else:
                    service.add_experience_project(
                        experience_id, name=project_name, achievements=achievements
                    )

        proposals.append(WritebackProposal(label=label, enabled=True, apply=apply))

    return proposals


def build_proposals_from_document(
    candidate: Candidate,
    assembled_experience: list[AssembledExperienceEntry],
    document: PrintDocument,
) -> list[WritebackProposal]:
    """Phase 19: the web app's entry point into write-back — adapts the A4
    editor's *structured* `PrintDocument` (Phase 16) to the three builders
    above, which only ever understood flat per-section markdown text (the
    desktop app's Phase 6 editor).

    No new parsing logic: `app/cv_markdown.py::render_sections_from_document`
    (Phase 16c) already turns an edited `PrintDocument` into that exact flat
    `{key: markdown-text}` shape — built for plain export, reused verbatim
    here — so `build_summary_proposal`/`build_skills_proposals`/
    `build_experience_proposals` need zero changes.
    """
    sections = render_sections_from_document(document)
    return [
        build_summary_proposal(sections.get("summary", "")),
        *build_skills_proposals(candidate, sections.get("skills", "")),
        *build_experience_proposals(assembled_experience, sections.get("experience", "")),
    ]


def _split_into_blocks(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    return re.split(r"\n\s*\n", stripped)


_HEADER_RE = re.compile(
    r"^\*\*(?P<position>.+?)\*\*(?: — (?P<company>.+?))?"
    r"(?: \((?P<period>.+?)(?:, (?P<location>.+?))?\))?$"
)

_PLAIN_HEADER_RE = re.compile(
    r"^(?P<position>.+?)(?: — (?P<company>.+?))?"
    r"(?: \((?P<period>.+?)(?:, (?P<location>.+?))?\))?$"
)

_MARKDOWN_LINK_RE = re.compile(r"^\[(?P<text>.+)\]\((?P<url>.+)\)$")


def _strip_markdown_link(text: str) -> str:
    """Reduces a possibly `[text](url)`-wrapped string back to its plain
    display text — inverts the hyperlink `app/cv_markdown.py`'s
    `render_experience_section`/`_render_bullets_grouped_by_project` add to
    a company/project name that has a known `company_url`/project `url`
    (Post-4.10 follow-up, see `domain.models.ExperienceProject.url`'s
    docstring). Without this, `_parse_header`'s/`_parse_block_bullets`'s
    already-lenient `.+?` capture would happily swallow the whole
    `[Kefir](https://kefirgames.com/)` literal as if it were the company
    name itself, corrupting `Experience.company` the next time any OTHER
    part of that block gets hand-edited and saved.

    The URL itself is deliberately never round-tripped back into
    `Experience.company_url`/`ExperienceProject.url` from free-text edits
    here — those are ingestion-only facts (or set via ExperienceForm.tsx's
    own dedicated fields), not something this text editor is meant to
    change; a plain string edit can only ever rename the display text, the
    same as it always could for an unlinked company/project. A plain
    (unlinked) string passes through unchanged.
    """
    match = _MARKDOWN_LINK_RE.match(text)
    return match.group("text") if match else text


def _parse_header(line: str) -> tuple[str, str | None, str | None, str | None] | None:
    """Inverts a non-gap Experience header line's shape. Two different
    renderers produce this line, with the same plain content but different
    `**` placement: app/cv_markdown.py:render_experience_section() (the
    desktop app's flat-text editor) bolds only Position — `**Position** —
    Company (Period)`; render_sections_from_document() (Phase 16c/19, the
    web app's structured-document editor) bolds the whole line — `**Position
    — Company (Period)**`. Disambiguated structurally, not by caller: a
    line ending in `**` only happens when the whole line is wrapped (Company/
    Period, if present, always follow Position's own closing `**` in the
    desktop format, so that format never ends in `**` once either is set) —
    strip the outer wrapper and parse the plain remainder in that case;
    otherwise require Position's own `**...**` at the start, exactly as
    before.

    Returns None if the line doesn't match either shape (e.g. the user
    deleted Position's `**` markers on the desktop, or the whole line's on
    the web) — same fail-safe philosophy as the block-count-mismatch case:
    don't guess, just leave the facts part of the proposal alone rather
    than risk a wrong write.

    Location is grouped with Period inside the parenthetical (not
    comma-appended after Company) specifically so this regex never has to
    guess whether free text after a comma is part of the company name or a
    location — see app/cv_markdown.py:_render_period_and_location.

    `company` is run through `_strip_markdown_link` before being returned —
    see that function's own docstring for why a hyperlinked company name
    (Post-4.10 follow-up) must never round-trip back into
    `Experience.company` as the literal `[text](url)` it renders as.
    """
    text = line.strip()
    if text.startswith("**") and text.endswith("**") and len(text) > 4:
        match = _PLAIN_HEADER_RE.match(text[2:-2])
    else:
        match = _HEADER_RE.match(text)
    if not match:
        return None
    company = match.group("company")
    return (
        match.group("position"),
        _strip_markdown_link(company) if company is not None else None,
        match.group("period"),
        match.group("location"),
    )


def _parse_block_bullets(block: str) -> tuple[list[str], dict[str, list[str]]]:
    """Parses one Experience block's body (everything after its header
    line) into role-level achievements and {project_name: achievements},
    inverting app/cv_markdown.py's _render_bullets_grouped_by_project().

    A project heading run through `_strip_markdown_link` before use as a
    dict key — a project with a known `url` (Post-4.10 follow-up) renders
    as `*[Project Name](url)*`, and the dict key here must match the plain
    project name `TailoredBullet.project` actually holds, or every edit to
    this block would spuriously look like a renamed/duplicated project
    (see `_strip_markdown_link`'s own docstring).
    """
    body_lines = block.split("\n")[1:]  # [0] is the header line, not content

    role_bullets: list[str] = []
    project_bullets: dict[str, list[str]] = {}
    current_project: str | None = None

    for raw_line in body_lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            text = line[2:].strip()
            if current_project is not None:
                project_bullets[current_project].append(text)
            else:
                role_bullets.append(text)
        elif line.startswith("*") and line.endswith("*") and not line.startswith("**"):
            current_project = _strip_markdown_link(line[1:-1].strip())
            project_bullets.setdefault(current_project, [])

    return role_bullets, project_bullets


def _group_tailored_bullets(bullets: list[TailoredBullet]) -> tuple[list[str], dict[str, list[str]]]:
    """Groups a role's stored bullets into the same (role_bullets,
    project_bullets) shape _parse_block_bullets extracts from edited text,
    so the two can be diffed to tell whether a role's block actually
    changed. Mirrors the grouping in app/cv_markdown.py's
    _render_bullets_grouped_by_project()."""
    role_bullets: list[str] = []
    project_bullets: dict[str, list[str]] = {}
    for bullet in bullets:
        if bullet.project:
            project_bullets.setdefault(bullet.project, []).append(bullet.text)
        else:
            role_bullets.append(bullet.text)
    return role_bullets, project_bullets
