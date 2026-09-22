"""Renders an AssembledCV to Markdown, section by section.

Split into one function per CV section (rather than a single monolithic
renderer) so the Phase 6 UI can show one editable text field per section
(docs/development_plan.md Phase 6: "editable text field per CV section")
while sharing the exact same formatting logic as the CLI's full-document
export. Both run_pipeline.py and ui/main_window.py import this module —
there is deliberately only one place that knows how an AssembledCV becomes
Markdown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from app.cv_locales import SECTION_TITLES_EN, section_titles_for
from domain.models import AssembledCV, PrintDocument, PrintDocumentBlock, PrintDocumentEntry, TailoredBullet, TextRun

# Order matters here: this is both the section order for the full document
# and the canonical list of valid section keys for assemble_markdown_from_sections.
# "contacts" first — right after the header, before Summary — so it still
# reads like the top-of-resume contact block a reader expects, even though
# it's now a real section (own heading, one entry per contact, each
# independently includable) rather than folded into the un-editable
# header. Moved out of the header at the user's request: previously every
# contact was unconditionally included with no way to drop, say, "Work
# Authorization" or "Relocation" for an application where it isn't
# relevant — every other CV fact already had that per-item control via
# its own section; Contacts was the one exception.
#
# Version 4, Phase 4.3: the real, localizable table moved to
# app/cv_locales.py (SECTION_TITLES_EN/_RU/section_titles_for) — this name
# stays as a backward-compat alias for the English table specifically.
# Existing callers below that have an AssembledCV/language in scope use
# section_titles_for(language) instead; nothing outside this module
# should gain a new reference to the bare SECTION_TITLES going forward.
SECTION_TITLES: dict[str, str] = SECTION_TITLES_EN


def render_header(cv: AssembledCV) -> str:
    lines = [f"# {cv.name}"]
    if cv.headline:
        lines.append(f"*{cv.headline}*")
    if cv.employment_types_sought:
        lines.append(f"Seeking: {', '.join(cv.employment_types_sought)}")
    return "\n".join(lines)


def render_contacts_section(cv: AssembledCV) -> str:
    """One bulleted `Label: value` line per contact — no categorization
    (Contacts never had that concept), so this is a flat list like
    render_certifications_section/render_awards_section, not a grouped
    one like render_skills_section."""
    return "\n".join(f"- {c.label}: {c.value}" for c in cv.contacts)


def render_summary_section(cv: AssembledCV) -> str:
    return cv.summary or ""


def render_projects_section(cv: AssembledCV) -> str:
    """Renders the standalone "Key Projects" section — always included as-is
    (not AI-tailored per vacancy), see domain.models.Project's docstring."""
    lines = []
    for project in cv.projects:
        entry = f"**{project.name}**"
        if project.description:
            entry += f" — {project.description}"
        if project.url:
            entry += f" ({project.url})"
        lines.append(f"- {entry}")
    return "\n".join(lines)


def render_portfolio_links_section(cv: AssembledCV) -> str:
    """Renders the standalone Portfolio Links section — always included
    as-is (not AI-tailored per vacancy), same treatment as `render_
    projects_section`. See domain.models.PortfolioLink's docstring."""
    lines = []
    for link in cv.portfolio_links:
        entry = f"{link.description} — {link.url}" if link.description else link.url
        lines.append(f"- {entry}")
    return "\n".join(lines)


def render_publications_section(cv: AssembledCV) -> str:
    """Always included as-is (not AI-tailored) — same treatment as
    render_projects_section, which this otherwise mirrors."""
    lines = []
    for pub in cv.publications:
        entry = f"**{pub.title}**"
        details = ", ".join(bit for bit in (pub.venue, pub.date) if bit)
        if details:
            entry += f" — {details}"
        if pub.url:
            entry += f" ({pub.url})"
        lines.append(f"- {entry}")
    return "\n".join(lines)


def _maybe_link(text: str, url: str | None) -> str:
    """Wraps `text` as a `[text](url)` Markdown link when `url` is given,
    otherwise returns it unchanged. `app/markdown_inline.py`'s
    `parse_inline_runs` (shared by `app/cv_pdf.py`/`app/cv_docx.py`) already
    turns this syntax into a real hyperlink wherever it appears in a
    rendered section, so callers here don't need any renderer-specific
    handling of their own — see `render_experience_section`'s `company_url`
    and `_render_bullets_grouped_by_project`'s `project_urls` for the two
    places this closes a real ingestion gap (a source PDF hyperlinking a
    company/project name to its own site, rather than writing the URL out
    as visible text — see `domain.models.ExperienceProject.url`'s
    docstring). `app/graph_writeback.py:_strip_markdown_link` is the
    inverse, needed so hand-editing this text back doesn't corrupt
    `company`/a project name with the literal `[text](url)` syntax.
    """
    return f"[{text}]({url})" if url else text


def _render_bullets_grouped_by_project(
    bullets: list[TailoredBullet], project_urls: dict[str, str] | None = None
) -> list[str]:
    """Renders one role's bullets, grouping any that share a `project` tag
    (Phase 7 — see domain.models.ExperienceProject) under a `*Project Name*`
    sub-line. Untagged bullets render as plain `- bullet` lines, same as
    before Phase 7. A project's bullets are gathered under one heading at
    the position of that project's first bullet, even if its bullets are
    interleaved with others in the source list — repeating the heading for
    every occurrence would be noisier than useful.

    `project_urls` (Post-4.10 follow-up) maps a project name to its known
    URL (`AssembledExperienceEntry.project_urls`, itself copied from
    `ExperienceProject.url`) — when a bullet's project has one, the heading
    becomes `*[Project Name](url)*` instead of plain `*Project Name*`. See
    `_maybe_link`.
    """
    project_bullets: dict[str, list[str]] = {}
    slots: list[tuple[str, str]] = []  # ("plain", text) or ("project", project_name)
    for bullet in bullets:
        if bullet.project:
            if bullet.project not in project_bullets:
                project_bullets[bullet.project] = []
                slots.append(("project", bullet.project))
            project_bullets[bullet.project].append(bullet.text)
        else:
            slots.append(("plain", bullet.text))

    lines: list[str] = []
    for kind, value in slots:
        if kind == "plain":
            lines.append(f"- {value}")
        else:
            heading = _maybe_link(value, (project_urls or {}).get(value))
            lines.append(f"*{heading}*")
            lines += [f"- {text}" for text in project_bullets[value]]
    return lines


def _render_period_and_location(period: str | None, location: str | None) -> str:
    """Joins period+location into one parenthetical, e.g. "(2020-2023, Berlin)".
    Grouped together rather than comma-appending location after company —
    a company name and a location are otherwise unparseable to tell apart
    in app/graph_writeback.py's header-rewriting regex."""
    bits = ", ".join(bit for bit in (period, location) if bit)
    return f" ({bits})" if bits else ""


def render_experience_section(cv: AssembledCV) -> str:
    if not cv.experience:
        return ""
    lines: list[str] = []
    for entry in cv.experience:
        if entry.is_gap:
            # Facts, not achievements — no bullets, italicized to read as a
            # timeline note rather than a role.
            header = f"*{entry.position}*"
            if entry.company:
                header += f", {_maybe_link(entry.company, entry.company_url)}"
            header += _render_period_and_location(entry.period, entry.location)
            lines.append(header)
            lines.append("")
            continue

        header = f"**{entry.position}**"
        if entry.company:
            header += f" — {_maybe_link(entry.company, entry.company_url)}"
        header += _render_period_and_location(entry.period, entry.location)
        lines.append(header)
        lines += _render_bullets_grouped_by_project(entry.bullets, entry.project_urls)
        lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def render_volunteer_experience_section(cv: AssembledCV) -> str:
    """Always included as-is (not AI-tailored) — same treatment as
    render_education_section. See domain.models.VolunteerExperience's
    docstring for why this is its own model rather than folded into
    Experience."""
    lines = []
    for entry in cv.volunteer_experience:
        header = f"**{entry.role}** — {entry.organization}"
        if entry.period:
            header += f" ({entry.period})"
        if entry.description:
            header += f": {entry.description}"
        lines.append(f"- {header}")
    return "\n".join(lines)


def render_education_section(cv: AssembledCV) -> str:
    if not cv.education:
        return ""
    lines = []
    for edu in cv.education:
        header = f"**{edu.institution}**"
        details = ", ".join(bit for bit in (edu.degree, edu.field) if bit)
        if details:
            header += f" — {details}"
        if edu.period:
            header += f" ({edu.period})"
        lines.append(f"- {header}")
    return "\n".join(lines)


_NO_CATEGORY_YET = object()


def _render_grouped_by_category(items) -> str:
    """Shared by render_skills_section/render_technologies_section — both
    `cv.skills`/`cv.technologies` are already grouped by category and
    ranked within each group by app/cv_assembler.py:_rank_by_category, so
    this just walks them once, emitting one compact
    `- **Category**: item1; item2 (Proficiency); item3` bullet line per
    contiguous category run (each item's own `proficiency`, if set, still
    appends `(Proficiency)` inline) — instead of a `**Category**` heading
    line followed by one bullet per item. Reported directly, from a real
    resume whose neatly-grouped "Label: item1, item2, item3" skill lines
    were exploding into one bullet per item on export, losing the
    original grouping entirely. Uncategorized items (no category at all)
    are unaffected — still individual `- item` bullet lines, wherever
    that run naturally falls.
    """
    lines: list[str] = []
    current_category: str | None | object = _NO_CATEGORY_YET
    group: list[str] = []
    for item in items:
        if item.category != current_category:
            if group:
                lines.append(f"- **{current_category}**: {'; '.join(group)}")
                group = []
            current_category = item.category
        entry = item.name
        if item.proficiency:
            entry += f" ({item.proficiency})"
        if current_category:
            group.append(entry)
        else:
            lines.append(f"- {entry}")
    if group:
        lines.append(f"- **{current_category}**: {'; '.join(group)}")
    return "\n".join(lines)


class RunsRenderable(Protocol):
    """Structural type both `PrintDocumentBlock` and `SubheadingGroupMember`
    satisfy — the minimum `_block_markdown_text` (below) and
    `app/cv_docx.py::_add_paragraph_with_runs` need to honor a block's own
    Phase 25/31 rich-run formatting, regardless of which concrete shape
    carries it. `SubheadingGroupMember` only exists because
    `group_entries_by_subheading`'s *grouped-category* branches
    (concatenating several members onto one line) can't sensibly carry
    per-member runs — see that dataclass's own docstring — but a
    standalone member (the common, ungrouped case) needs the exact same
    `runs`/`alignment` a `PrintDocumentBlock` would."""

    text: str
    runs: list[TextRun] | None
    alignment: Literal["left", "center", "right"] | None


@dataclass(frozen=True)
class SubheadingGroupMember:
    """One non-subheading entry inside a `SubheadingGroup` — just enough
    to render it either as a compact category-line member or a standalone
    bulleted line. `page_break_before` is Phase 30's manual-pagination
    flag, carried through from the source `PrintDocumentEntry` so a
    caller with a real page concept (app/cv_docx.py's
    `render_templated_docx`) can honor it; `render_sections_from_document`
    below reads only `.text` — flattened markdown/plain export has no
    page concept yet (see that function's docstring).

    Phase 31 — `runs`/`alignment` are carried through the same way, for
    the same reason, but *only* actually consumed for a standalone
    (ungrouped) member — see `RunsRenderable`'s own docstring for why a
    *grouped*-category member can't use them at all: concatenating
    several members' `.text` onto one compact `**Category**: a; b` line
    (the `group.category is not None` branch in both
    `render_sections_from_document` and `render_templated_docx`) has no
    per-member place to attach a run boundary without redesigning that
    line format entirely — confirmed out of scope for this phase, and
    harmless in practice: `structuredDocument.ts`'s
    `collapseSkillsAndTechnologiesIfNeeded` migrates every loaded
    Skills/Technologies draft to `kind: "compact"` entries (a standalone
    member, not a grouped one) before the BubbleMenu can ever apply a
    run there."""

    text: str
    page_break_before: bool
    runs: list[TextRun] | None = None
    alignment: Literal["left", "center", "right"] | None = None


@dataclass(frozen=True)
class SubheadingGroup:
    """One `(category, members)` group — `category is None` means "no
    subheading seen yet", rendered as individual bullets rather than a
    compact `**Category**: a; b` line. `category_page_break_before` is the
    subheading entry's own `page_break_before` (irrelevant when
    `category is None`, since there is no subheading entry to carry it)."""

    category: str | None
    category_page_break_before: bool
    members: list[SubheadingGroupMember]


def group_entries_by_subheading(entries: list[PrintDocumentEntry]) -> list[SubheadingGroup]:
    """Walks a section's entries, starting a new `SubheadingGroup` on every
    `kind == "subheading"` entry — the PrintDocument-entry equivalent of
    `_render_grouped_by_category` above, used wherever a Skills/
    Technologies section is rendered from the *edited* structured document
    rather than fresh from an AssembledCV (`render_sections_from_document`
    below, and app/cv_docx.py's `render_templated_docx`) — kept here, not
    duplicated in cv_docx.py, since a second copy is exactly how
    `render_sections_from_document` ended up with its own unfixed,
    un-grouped rendering the first time around (reported directly, from a
    real tailored PDF export). Entries before the first subheading (or
    when there never is one) collect into one leading
    `SubheadingGroup(None, False, [...])` group, meaning "no category" —
    the caller renders that group as individual bullets, not a compact
    line.
    """
    groups: list[SubheadingGroup] = [SubheadingGroup(None, False, [])]
    for entry in entries:
        if entry.kind == "subheading":
            groups.append(SubheadingGroup(entry.text, entry.page_break_before, []))
        else:
            groups[-1].members.append(
                SubheadingGroupMember(entry.text, entry.page_break_before, entry.runs, entry.alignment)
            )
    return groups


def render_skills_section(cv: AssembledCV) -> str:
    return _render_grouped_by_category(cv.skills)


def render_technologies_section(cv: AssembledCV) -> str:
    return _render_grouped_by_category(cv.technologies)


def render_languages_section(cv: AssembledCV) -> str:
    lines = []
    for lang in cv.languages:
        entry = lang.name
        if lang.proficiency:
            entry += f" ({lang.proficiency})"
        lines.append(f"- {entry}")
    return "\n".join(lines)


def render_certifications_section(cv: AssembledCV) -> str:
    lines = []
    for cert in cv.certifications:
        entry = cert.name
        details = ", ".join(bit for bit in (cert.issuer, cert.date) if bit)
        if details:
            entry += f" — {details}"
        lines.append(f"- {entry}")
    return "\n".join(lines)


def render_awards_section(cv: AssembledCV) -> str:
    """Always included as-is (not AI-tailored) — same treatment as
    render_certifications_section, which this mirrors exactly. See
    domain.models.Award's docstring for why this is separate from
    Certification."""
    lines = []
    for award in cv.awards:
        entry = award.name
        details = ", ".join(bit for bit in (award.issuer, award.date) if bit)
        if details:
            entry += f" — {details}"
        lines.append(f"- {entry}")
    return "\n".join(lines)


_SECTION_RENDERERS = {
    "contacts": render_contacts_section,
    "summary": render_summary_section,
    "projects": render_projects_section,
    "portfolio_links": render_portfolio_links_section,
    "publications": render_publications_section,
    "experience": render_experience_section,
    "volunteer_experience": render_volunteer_experience_section,
    "education": render_education_section,
    "skills": render_skills_section,
    "technologies": render_technologies_section,
    "languages": render_languages_section,
    "certifications": render_certifications_section,
    "awards": render_awards_section,
}


def render_all_sections(cv: AssembledCV) -> dict[str, str]:
    """Render every section body (not the header) into a {key: text} dict,
    in SECTION_TITLES order. Used by the UI to populate one editable field
    per section."""
    return {key: renderer(cv) for key, renderer in _SECTION_RENDERERS.items()}


def _serialize_runs(runs: list[TextRun]) -> str:
    """Phase 25 — inverse of app/markdown_inline.py::parse_inline_runs:
    turns a block's explicit `runs` back into that module's tiny inline-
    markdown dialect, so the plain (non-templated) DOCX/PDF export path
    (both already built on `parse_inline_runs`) picks up bold/italic/
    underline/links for free, with no changes of their own beyond
    threading `underline` through (see app/cv_docx.py::_add_runs,
    app/cv_pdf.py::_runs_to_markup). One-way only — nothing parses this
    text back into `runs`; the structured `PrintDocument` a person is
    actually editing never round-trips through it (`render_templated_docx`
    and the Playwright-screenshotted templated PDF both consume `.runs`
    directly instead, with full multi-attribute fidelity — see below).

    Deliberate, documented limitation: a run with more than one of
    bold/italic/underline set collapses to just the highest-priority one
    here (bold > italic > underline), since `parse_inline_runs` has no
    nested-span support to round-trip a combination through plain text
    (see that module's own docstring on nesting). This only affects this
    flat-text export bridge — `render_templated_docx`/the templated PDF
    render every run's full, simultaneous style set faithfully, since
    they consume `TextRun` objects directly and never go through text at
    all. Not worth solving speculatively now: no `runs` exist anywhere
    yet (there's still no UI to create one — that's Phase 31), so this is
    unverifiable-by-real-usage either way; revisit once combined styles
    are something a person can actually produce. Doesn't escape a run's
    own literal `*`/`_`/`[`/`]` characters either — the same limitation
    every other renderer below already has wrapping `**`/`*` around
    free-form resume text.

    A zero-width space is inserted between two consecutive runs whose
    wrapped text meets at an ambiguous `*`/`_` boundary — found from a
    real hand-crafted export: a bold run immediately followed by an
    italic run serialized to `"**Engineer**" + "* — Acme*"`, which
    concatenates into `"**Engineer*** — Acme*"` — three `*` in a row is
    not unambiguously "end bold, start italic" to a human glancing at the
    raw text (or to a real Markdown renderer, if the `.md` export is
    opened directly rather than fed back through `parse_inline_runs`,
    which never happens in this app but is a real, plausible thing to do
    with a downloaded `.md` file). The zero-width space is invisible in
    both a rendered Markdown preview and this app's own DOCX/PDF export
    (`_add_runs`/`_runs_to_markup` render it as an ordinary, invisible
    character, not a real Unicode replacement-glyph box), so it costs
    nothing visually either way.
    """
    parts: list[str] = []
    for run in runs:
        if run.link:
            text = f"[{run.text}]({run.link})"
        elif run.bold:
            text = f"**{run.text}**"
        elif run.italic:
            text = f"*{run.text}*"
        elif run.underline:
            text = f"__{run.text}__"
        else:
            text = run.text
        if parts and _run_boundary_is_ambiguous(parts[-1], text):
            parts.append("​")
        parts.append(text)
    return "".join(parts)


def _run_boundary_is_ambiguous(prev: str, next_: str) -> bool:
    return bool(prev) and bool(next_) and prev[-1] in "*_" and next_[0] in "*_"


def _block_markdown_text(block: RunsRenderable) -> str:
    """`block.text` unless explicit `runs` are set, in which case those
    are authoritative (see `PrintDocumentBlock.runs`'s docstring) — and
    take over entirely, including any automatic block-level styling a
    caller would otherwise wrap around plain `text` (e.g. an Experience
    role header's automatic `**bold**`/gap `*italic*`), since `runs`
    represents a person's own explicit formatting overriding that
    default.

    Phase 25 scoped this to Summary + Experience only, since nothing
    else could ever produce a `runs`-bearing block yet. Phase 31 (the
    on-screen BubbleMenu) widened that to every section — every call
    site in `render_sections_from_document` below now routes through
    this helper instead of raw `.text`, *except* the still-legacy
    `group.category is not None`/flat-compact-join branches just above
    the generic one, which stay `.text`-only on purpose: both are only
    ever reached for a not-yet-migrated Skills/Technologies document
    (`collapseSkillsAndTechnologiesIfNeeded` migrates every loaded draft
    to `kind: "compact"` entries before the BubbleMenu can ever touch
    them — see structuredDocument.ts), so a `runs`-bearing member can't
    actually reach either branch in practice.
    """
    return _serialize_runs(block.runs) if block.runs else block.text


# Phase 30 — manual pagination control's plain-export equivalent. The
# structured document expresses "start this section/entry on a new page"
# as a `page_break_before` bool (domain/models.py); the flat markdown-text
# bridge `render_sections_from_document` produces has no such concept of
# its own, so a forced break is encoded as one extra line consisting of
# nothing but a sentinel, placed immediately before the line(s) it
# applies to. Two distinct sentinels, not one — a *section's* own flag is
# always the literal first line of that section's body, but an *entry's*
# flag can land there too (its section's very first entry, flagged, with
# the section itself not flagged) and the two cases render differently
# (see `split_leading_page_break_marker`'s docstring): a single shared
# marker would make that first line ambiguous between "start the whole
# section, heading included, on a new page" and "leave the heading behind
# alone; only this first entry jumps". Neither sentinel can occur in a
# person's own entered CV text, and neither is valid Markdown syntax, so
# collisions with real content aren't a concern. Emitted only by
# `render_sections_from_document` below; consumed only by
# app/cv_docx.py::render_docx and app/cv_pdf.py::render_pdf (the plain,
# untemplated export paths) — `SECTION_PAGE_BREAK_MARKER` via
# `split_leading_page_break_marker`, `ENTRY_PAGE_BREAK_MARKER` via each
# module's own `_render_body`. `render_templated_docx`/
# PrintSectionBlock.tsx don't need any of this — they still have the
# structured `PrintDocumentSection`/`PrintDocumentEntry` objects on hand
# and read `page_break_before` off them directly.
SECTION_PAGE_BREAK_MARKER = "\x0c"
ENTRY_PAGE_BREAK_MARKER = "\x0b"


def split_leading_page_break_marker(body: str) -> tuple[bool, str]:
    """`(True, rest)` when `body`'s very first line is
    `SECTION_PAGE_BREAK_MARKER` — i.e. the *section* itself was flagged —
    with that marker line (and the blank line separating it from real
    content, if any) stripped off. `(False, body)` unchanged otherwise —
    including when the first line is instead `ENTRY_PAGE_BREAK_MARKER`,
    which this deliberately leaves untouched for `_render_body` to handle
    as an ordinary mid-body marker (see that constant's docstring for why
    the two cases render differently)."""
    if not body.startswith(SECTION_PAGE_BREAK_MARKER):
        return False, body
    rest = body[len(SECTION_PAGE_BREAK_MARKER) :]
    if rest.startswith("\n"):
        rest = rest[1:]
    return True, rest


def render_sections_from_document(document: PrintDocument) -> dict[str, str]:
    """Phase 16c — the inverse of `render_all_sections`: turns the *edited*
    structured document (the A4 Preview tab's state — already reordered/
    toggled by the user) back into the same `{key: markdown-text}` shape
    `render_all_sections` produces, so `assemble_markdown_from_sections`/
    `render_pdf`/`render_docx` (all of which only ever understood that flat
    shape) can render it with zero changes on their end — this is what lets
    plain, untemplated export reflect what the user actually edited instead
    of a stale server-computed snapshot.

    Skips excluded sections/entries/bullets entirely. Emits the exact same
    markdown-line conventions the per-section renderers above already use
    (`**bold**` headers/categories, `*italic*` gap/project lines, `- `
    bullets) so `_render_body`'s existing inline-markdown parser
    (app/cv_docx.py, app/cv_pdf.py) handles the output identically to text
    `render_all_sections` would have produced fresh from an `AssembledCV`.

    Skills/Technologies `kind == "subheading"` entries (category names)
    and the members below them are rendered via `group_entries_by_subheading`
    into the same compact `- **Category**: item1; item2` line
    `_render_grouped_by_category` produces — this function used to build
    that heading-line-then-one-bullet-per-item shape by hand, inline,
    which was a separate, un-fixed copy of the exact bug
    `_render_grouped_by_category` was fixed for (reported directly, from
    a real *tailored* PDF export: `render_pdf`/`render_docx` always go
    through this function, not `render_all_sections`, since export always
    reflects the edited `PrintDocument`).

    Phase 25/31: any entry/bullet with explicit `runs` set renders those
    (via `_block_markdown_text`) instead of its plain `text` — every
    section, not just Summary/Experience (Phase 25's original scope,
    before there was a UI to produce `runs` anywhere else). See
    `_block_markdown_text`'s own docstring for the two still-legacy
    branches inside `group_entries_by_subheading` below that stay
    `.text`-only, and why that's harmless in practice.

    Phase 30: a section's own `page_break_before` becomes a leading
    `SECTION_PAGE_BREAK_MARKER` line; an entry/subheading-group's own
    becomes an `ENTRY_PAGE_BREAK_MARKER` line immediately before it —
    see those constants' docstrings for why they're distinct sentinels,
    not one shared marker. Bullets never carry `page_break_before` (only
    `PrintDocumentEntry`/`PrintDocumentSection` have the field, not
    `PrintDocumentBlock`), so bullet lines never emit one.
    """
    sections: dict[str, str] = {}
    for section in document.sections:
        if not section.included:
            continue
        entries = [entry for entry in section.entries if entry.included]
        if not entries:
            continue
        lines: list[str] = []
        if section.page_break_before:
            lines.append(SECTION_PAGE_BREAK_MARKER)
        if section.key == "summary":
            for entry in entries:
                if entry.page_break_before:
                    lines.append(ENTRY_PAGE_BREAK_MARKER)
                lines.append(_block_markdown_text(entry))
        elif section.key == "experience":
            for entry in entries:
                if entry.page_break_before:
                    lines.append(ENTRY_PAGE_BREAK_MARKER)
                if entry.runs:
                    lines.append(_block_markdown_text(entry))
                else:
                    lines.append(f"*{entry.text}*" if entry.locked else f"**{entry.text}**")
                for bullet in entry.bullets or []:
                    if not bullet.included:
                        continue
                    if bullet.kind == "subheading":
                        # No "- " marker either way — only whether the
                        # italic default or the person's own runs wins.
                        lines.append(_block_markdown_text(bullet) if bullet.runs else f"*{bullet.text}*")
                    else:
                        # "- " is a list marker, not a style default — it
                        # always applies, runs or not; only the text after
                        # it depends on whether `runs` is set.
                        lines.append(f"- {_block_markdown_text(bullet)}")
                lines.append("")
            if lines and lines[-1] == "":
                lines.pop()
        elif section.key in ("skills", "technologies") and all(entry.kind == "compact" for entry in entries):
            # Post-31 — an entry that's already a whole pre-joined, final
            # line (structuredDocument.ts's buildCompactSkillEntries —
            # see domain/models.py's PrintDocumentBlock.kind docstring)
            # renders standalone: no "- " bullet marker (mirrors
            # PrintSectionBlock.tsx's identical no-bulletChar treatment
            # for the same entries), and never goes through
            # group_entries_by_subheading below at all — grouping two
            # already-final lines together (e.g. two separate category
            # lines) would wrongly fuse them onto one, the exact bug
            # `kind: "compact"` exists to prevent. `_block_markdown_text`
            # re-serializes a category entry's own bold `runs` back into
            # literal `**...**` markdown, so its bold label survives here
            # too — see that helper's own widened scope note.
            for entry in entries:
                if entry.page_break_before:
                    lines.append(ENTRY_PAGE_BREAK_MARKER)
                lines.append(_block_markdown_text(entry))
        else:
            for group in group_entries_by_subheading(entries):
                if group.category is not None:
                    if group.category_page_break_before:
                        lines.append(ENTRY_PAGE_BREAK_MARKER)
                    line = f"- **{group.category}**"
                    if group.members:
                        line += f": {'; '.join(member.text for member in group.members)}"
                    lines.append(line)
                elif section.key in ("skills", "technologies") and group.members:
                    # Post-30 polish — reported directly: a long flat
                    # skill list read as too many separate bullet lines
                    # and ate too much of the page. Every member in the
                    # group joins onto one `- `-prefixed line, `" · "`-
                    # separated, instead of one bullet each — the same
                    # "compact single line" treatment a *categorized*
                    # group already gets just above, minus the category
                    # label. Mirrors PrintSectionBlock.tsx's identical
                    # `renderFlatGroup` exception exactly, so the plain/
                    # ATS export (this bridge feeds render_pdf/render_docx)
                    # stays visually consistent with the templated one.
                    # Only the first member's own `page_break_before` has
                    # anywhere left to apply once every member is fused
                    # onto one line — mirrors a category's own flag.
                    #
                    # Only reached for a *legacy*, not-yet-migrated
                    # section (one skill per entry, a real `kind ==
                    # "subheading"` category marker) — the branch just
                    # above handles an already-compact section instead,
                    # never entering group_entries_by_subheading at all.
                    if group.members[0].page_break_before:
                        lines.append(ENTRY_PAGE_BREAK_MARKER)
                    lines.append(f"- {' · '.join(member.text for member in group.members)}")
                else:
                    # Phase 31 — the generic "one bullet per member" path
                    # for every section without its own special case above
                    # (Contacts, Education, Certifications, Awards,
                    # Publications, Volunteer Experience, Portfolio
                    # Links): `_block_markdown_text` honors an explicit
                    # `member.runs` when the user formatted it via the
                    # BubbleMenu, falling back to plain `.text` otherwise
                    # — same call `_block_markdown_text`'s own docstring
                    # already documents for Summary/Experience.
                    for member in group.members:
                        if member.page_break_before:
                            lines.append(ENTRY_PAGE_BREAK_MARKER)
                        lines.append(f"- {_block_markdown_text(member)}")
        if lines:
            sections[section.key] = "\n".join(lines)
    return sections


def iter_section_lines_with_ids(document: PrintDocument) -> dict[str, list[tuple[str, list[str]]]]:
    """Version 4, Phase 4.9 follow-up (on-screen page-break prediction) —
    `app/cv_pdf.py::compute_page_breaks` needs to know which
    `PrintDocumentEntry`/`PrintDocumentBlock` id(s) produced each line of
    `render_sections_from_document`'s output, so it can tag the reportlab
    flowable built from that line and later report "this id starts page
    N" back to the frontend. Deliberately a separate, parallel walk from
    `render_sections_from_document` above, not a refactor of it — mirrors
    its Summary/Experience/compact-Skills branches exactly (same
    literal line text, line for line — kept in sync by hand, the same
    established convention `app/cv_templates.py`'s DOCX/PDF template
    tables and `app/cv_pdf.py`/`app/cv_docx.py` themselves already use for
    "two implementations of the same shape, different technology") —
    covering the sections where per-line id tracking is both reliable (no
    fused/joined lines) and highest-value (Experience is where nearly
    every real page-break lands, and Summary/compact-Skills are simple
    one-line-per-entry cases).

    The remaining sections — everything routed through
    `group_entries_by_subheading`'s generic grouped-category/flat-join/
    per-member branches (Contacts, Education, Certifications, Awards,
    Publications, Volunteer Experience, Portfolio Links, and any
    not-yet-migrated legacy Skills/Technologies section) — get an empty
    owner-id list for every line: `SubheadingGroupMember` carries no `id`
    at all (by design, see its own docstring), and a grouped/joined line
    can legitimately represent several source entries fused onto one line
    anyway, which has no single correct "owner." `compute_page_breaks`
    treats an empty-owner line as simply not a possible break-reporting
    boundary — those sections still count toward page height/flow
    correctly (their text is identical either way), they just don't get
    individual on-screen break markers within themselves; the section's
    own heading is still tracked, so a break at the section's own
    boundary is still reported.

    Every returned list is the same length as
    `render_sections_from_document(document)[key].split("\\n")` would be,
    index-for-index — `app/cv_pdf.py` relies on this exact alignment to
    zip a line's text and its owner ids together.
    """
    result: dict[str, list[tuple[str, list[str]]]] = {}
    for section in document.sections:
        if not section.included:
            continue
        entries = [entry for entry in section.entries if entry.included]
        if not entries:
            continue
        lines: list[tuple[str, list[str]]] = []
        if section.page_break_before:
            lines.append((SECTION_PAGE_BREAK_MARKER, []))
        if section.key == "summary":
            for entry in entries:
                if entry.page_break_before:
                    lines.append((ENTRY_PAGE_BREAK_MARKER, []))
                lines.append((_block_markdown_text(entry), [entry.id]))
        elif section.key == "experience":
            for entry in entries:
                if entry.page_break_before:
                    lines.append((ENTRY_PAGE_BREAK_MARKER, []))
                if entry.runs:
                    lines.append((_block_markdown_text(entry), [entry.id]))
                else:
                    lines.append(
                        (f"*{entry.text}*" if entry.locked else f"**{entry.text}**", [entry.id])
                    )
                for bullet in entry.bullets or []:
                    if not bullet.included:
                        continue
                    if bullet.kind == "subheading":
                        lines.append(
                            (_block_markdown_text(bullet) if bullet.runs else f"*{bullet.text}*", [bullet.id])
                        )
                    else:
                        lines.append((f"- {_block_markdown_text(bullet)}", [bullet.id]))
                lines.append(("", []))
            if lines and lines[-1][0] == "":
                lines.pop()
        elif section.key in ("skills", "technologies") and all(entry.kind == "compact" for entry in entries):
            for entry in entries:
                if entry.page_break_before:
                    lines.append((ENTRY_PAGE_BREAK_MARKER, []))
                lines.append((_block_markdown_text(entry), [entry.id]))
        else:
            for group in group_entries_by_subheading(entries):
                if group.category is not None:
                    if group.category_page_break_before:
                        lines.append((ENTRY_PAGE_BREAK_MARKER, []))
                    line = f"- **{group.category}**"
                    if group.members:
                        line += f": {'; '.join(member.text for member in group.members)}"
                    lines.append((line, []))
                elif section.key in ("skills", "technologies") and group.members:
                    if group.members[0].page_break_before:
                        lines.append((ENTRY_PAGE_BREAK_MARKER, []))
                    lines.append((f"- {' · '.join(member.text for member in group.members)}", []))
                else:
                    for member in group.members:
                        if member.page_break_before:
                            lines.append((ENTRY_PAGE_BREAK_MARKER, []))
                        lines.append((f"- {_block_markdown_text(member)}", []))
        if lines:
            result[section.key] = lines
    return result


def render_full_markdown(cv: AssembledCV) -> str:
    """Full single-document export, freshly rendered from an AssembledCV."""
    parts = [render_header(cv)]
    titles = section_titles_for(cv.language)
    for key, title in titles.items():
        body = _SECTION_RENDERERS[key](cv)
        if not body:
            continue
        parts.append(f"## {title}\n{body}")
    return "\n\n".join(parts) + "\n"


def assemble_markdown_from_sections(header: str, sections: dict[str, str], language: str = "en") -> str:
    """Join a (possibly hand-edited) header + section texts back into one
    Markdown document.

    Used by the Phase 6 UI on export: each section is independently
    editable there, and per "no diffing/versioning" (docs/development_plan.md
    Phase 6) edited text is never re-parsed back into an AssembledCV — it's
    just concatenated as-is.

    `sections` keys should be a subset of SECTION_TITLES; unknown keys are
    ignored. A section is skipped if its text is blank/whitespace-only, same
    as render_full_markdown skips empty sections. `language` (Version 4,
    Phase 4.3) picks which locale's headings to render — the caller
    (api/routes/export.py) passes the exporting AssembledCV's own
    `.language`.
    """
    parts = [header.strip()] if header.strip() else []
    titles = section_titles_for(language)
    for key, title in titles.items():
        body = sections.get(key, "")
        if not body.strip():
            continue
        parts.append(f"## {title}\n{body.strip()}")
    return "\n\n".join(parts) + "\n"
