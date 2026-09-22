"""Renders an AssembledCV + edited section text into a PDF — the plain,
ATS-safe export (`render_pdf`) and, as of Version 4, Phase 4.9, the
templated export (`render_templated_pdf`) too. Both share the same
underlying flowable-building logic (`_render_pdf`, parameterized by
font/bullet-char/section-spacing) rather than being two independent
implementations — the only thing that differs between "plain" and
"classic"/"modern" is which `PdfTemplate` those three values come from.

Same header/edited-section-text traversal as app/cv_docx.py (see that
module's docstring for why the header comes from `cv` directly while
section bodies come from already-edited text) — kept in a separate module
because the two libraries' document models don't share an abstraction
worth forcing together.

Templated PDF used to be a separate module (app/cv_pdf_playwright.py,
removed this phase) that screenshotted the frontend's own on-screen print
preview via headless Chromium — pixel-perfect "by construction," but it
needed a browser binary a packaged Tauri build can't reasonably bundle
*and* an HTTP server for that browser to navigate to, which a packaged
build's frontend (served via Tauri's own asset protocol, not real HTTP)
doesn't have either. `render_templated_pdf` here instead reuses
app/cv_markdown.py's `render_sections_from_document` — the same
edited-PrintDocument-to-markdown-text bridge the plain PDF/DOCX paths
already use — so it inherits that function's already-correct handling of
grouping/subheadings/compact-Skills/page-breaks/runs for free, rather
than re-implementing any of it. The trade-off, accepted deliberately (see
docs/development_plan.md's Version 4, Phase 4.9 entry): this is now a
genuinely separate implementation from the on-screen preview that has to
be kept visually in sync by hand, the same trade-off render_templated_docx
already lived with.

ATS-readability constraints on the *plain* export specifically,
deliberately baked in rather than configurable (per
docs/PROJECT_CONTEXT.md non-goal "Export templates" — one clean layout,
not a template system):
* Single-column, top-to-bottom flow — no tables/text-boxes/multi-column
  layout, which can scramble an ATS parser's reading order.
* Real selectable text (reportlab Paragraph flowables), never text
  rendered as vector paths/images.
* Plain hyphen bullets, not "•" glyphs — an ATS-conventional choice, not
  a font limitation (Version 4, Phase 4.4 replaced Base-14 Helvetica with
  an embedded Unicode font that CAN render "•" correctly; the plain
  export just doesn't use it, on purpose). Templated PDF uses whichever
  bullet character its PdfTemplate specifies instead.
* Noto Sans (app/cv_fonts.py), not Base-14 Helvetica — Helvetica's
  WinAnsi encoding has zero Cyrillic glyphs, confirmed by generating a
  Russian-language PDF pre-Phase-4.4 and finding every Cyrillic character
  came back as a tofu box. Applied unconditionally (not just for Russian
  content) — simpler than branching on language, and there's no
  Helvetica-specific visual identity worth preserving for English CVs.
  (Post-4.9 fix: originally DejaVu Sans, swapped for Noto Sans because
  the DejaVu Sans build vendored here had no true bold face — see
  app/cv_fonts.py's docstring.)

Raw `http(s)://` URLs (a contact's Portfolio/LinkedIn value, a Project's
`(url)` — see app/markdown_inline.py) become real clickable link
annotations via reportlab's `<link href="...">` markup, not just styled
text — the visible URL text stays fully selectable/extractable either way,
so this doesn't affect ATS-readability.

`reportlab` is imported lazily (mirrors providers/gemini_provider.py's and
app/resume_reader.py's lazy-import convention) since it's only needed at
actual export time.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from xml.sax.saxutils import escape

from app.cv_fonts import register_pdf_fonts
from app.cv_locales import section_titles_for
from app.cv_markdown import (
    ENTRY_PAGE_BREAK_MARKER,
    iter_section_lines_with_ids,
    render_sections_from_document,
    split_leading_page_break_marker,
)
from app.errors import ExportError
from app.markdown_inline import InlineRun, parse_inline_runs
from domain.models import AssembledCV, PrintDocument

_MAX_EXPORT_BYTES = 2_000_000


# Version 4, Phase 4.9 — a deliberately separate, parallel table from
# app/cv_templates.py's DOCX_TEMPLATES, matching that module's own
# reasoning: python-docx and reportlab don't share a font-naming or
# styling abstraction worth forcing together, so there's nothing to
# literally share beyond matching ids ("classic"/"modern") for
# traceability. `heading_font`/`body_font` here are reportlab-registered
# family names (app/cv_fonts.py), not the DOCX table's raw "Georgia"/
# "Geist" strings — those name real installed-on-the-reader's-machine
# fonts Word substitutes if missing; reportlab has no such fallback, so
# these must be fonts this module has actually embedded.
@dataclass(frozen=True)
class PdfTemplate:
    id: str
    heading_font: str
    body_font: str
    bullet_char: str
    section_spacing: float


PDF_TEMPLATES: dict[str, PdfTemplate] = {
    "classic": PdfTemplate(
        id="classic",
        heading_font="DejaVuSerif",
        body_font="DejaVuSerif",
        bullet_char="–",  # en dash, matches cvTemplates.ts's classic bullet marker
        section_spacing=18.0,
    ),
    "modern": PdfTemplate(
        id="modern",
        heading_font="NotoSans",
        body_font="NotoSans",
        bullet_char="•",  # matches cvTemplates.ts's modern bullet marker — Noto Sans
        # renders it correctly (unlike Base-14 Helvetica's WinAnsi encoding, see this
        # module's own docstring), so there's no ATS-style reason to avoid it here.
        section_spacing=12.0,
    ),
}

_PLAIN_TEMPLATE = PdfTemplate(
    id="plain", heading_font="NotoSans", body_font="NotoSans", bullet_char="-", section_spacing=8.0
)


def render_pdf(cv: AssembledCV, sections: dict[str, str]) -> bytes:
    return _render_pdf(cv, sections, _PLAIN_TEMPLATE)


def render_templated_pdf(cv: AssembledCV, document: PrintDocument, template_id: str) -> bytes:
    """Version 4, Phase 4.9 — the template-aware PDF export, browser-free
    (see this module's own docstring for what it replaced and why).
    Mirrors app/cv_docx.py's render_templated_docx's *signature* exactly,
    but not its approach: DOCX's templated path walks `document` directly,
    since it needs real Word-native paragraph/run objects. This one
    instead reuses `render_sections_from_document` — the same edited-
    PrintDocument-to-markdown-text bridge the *plain* PDF/DOCX paths
    already use — since reportlab's markup-based Paragraph model can
    already render that exact text shape via `_render_pdf`/`_render_body`
    below, unchanged. That's what makes this a small addition rather than
    a second full walk of `document`'s grouping/subheading/page-break
    logic: `render_sections_from_document` already handles all of that.
    """
    template = PDF_TEMPLATES.get(template_id, PDF_TEMPLATES["classic"])
    sections = render_sections_from_document(document)
    return _render_pdf(cv, sections, template)


@dataclass(frozen=True)
class PageBreakPosition:
    """One element that starts a new page in the real reportlab-computed
    pagination for a given document+template. `kind == "section"` means
    `element_id` is a section key (look it up via `data-section-key`);
    `kind == "line"` means `element_id` is an entry or bullet id — a
    single combined `[data-entry-id="X"], [data-bullet-id="X"]` selector
    finds it either way, so the frontend never needs to know which of the
    two it actually is (ids are unique across the whole document
    regardless of which kind of block produced them). `page` is the
    1-indexed page the element starts on."""

    kind: str  # "section" | "line"
    element_id: str
    page: int


def compute_page_breaks(cv: AssembledCV, document: PrintDocument, template_id: str | None) -> list[PageBreakPosition]:
    """On-screen page-break-prediction fix (follow-up to Version 4, Phase
    4.9) — replaces the old approach (frontend/src/lib/tiptap/pageBreaks.ts,
    removed alongside this) of approximating page breaks by measuring the
    live browser DOM. That approximation was only ever valid while
    templated PDF export was itself a screenshot of that same DOM
    (Playwright, pre-Phase-4.9) — once PDF export became a genuinely
    separate, browser-free reportlab renderer using different fonts
    (DejaVu vs. the on-screen preview's Geist/Georgia), measuring the DOM
    was measuring the wrong thing entirely, for every export, not just
    Cyrillic ones (reported directly, from real live testing).

    This asks the real renderer instead of guessing: builds the exact
    same flowables `render_pdf`/`render_templated_pdf` would (via
    `_build_flowables`, tagged with each line's owner id via
    `app/cv_markdown.py::iter_section_lines_with_ids`), runs them through
    a `SimpleDocTemplate` subclass that records which page each tagged
    flowable actually lands on, then reports every point where the page
    number increases as we walk the document in order — "this element is
    the first thing on page N."

    `template_id=None` means the plain/ATS-safe export — mirrors
    `ExportRequest.template_id`'s own convention (api/routes/export.py).

    Scope, deliberately: only elements `iter_section_lines_with_ids` can
    reliably attribute to a single source id get reported (Summary,
    Experience entries/bullets, compact Skills/Technologies, and every
    section's own heading) — see that function's own docstring for why
    the generic grouped-line sections (Contacts, Education,
    Certifications, Awards, Publications, Volunteer Experience, Portfolio
    Links) don't get individual break markers within themselves yet, only
    at their own heading boundary.
    """
    from reportlab.lib.pagesizes import LETTER
    from reportlab.platypus import SimpleDocTemplate

    template = PDF_TEMPLATES.get(template_id, PDF_TEMPLATES["classic"]) if template_id else _PLAIN_TEMPLATE
    lines_by_section = iter_section_lines_with_ids(document)
    sections = {key: "\n".join(text for text, _ in lines) for key, lines in lines_by_section.items()}
    section_line_ids = {key: [ids for _, ids in lines] for key, lines in lines_by_section.items()}

    flowables = _build_flowables(cv, sections, template, section_line_ids=section_line_ids)

    class _TrackingDocTemplate(SimpleDocTemplate):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.tracked_pages: dict[str, int] = {}

        def afterFlowable(self, flowable):
            # A KeepTogether's own *contained* flowable is what this
            # fires for, not the KeepTogether wrapper itself — confirmed
            # empirically, not assumed, since reportlab's docs don't spell
            # this out. `_owner_ids` is set directly on the inner
            # Paragraph by `_build_flowables`/`_render_body`, so this
            # still finds it regardless of KeepTogether wrapping.
            for owner_id in getattr(flowable, "_owner_ids", None) or ():
                self.tracked_pages.setdefault(owner_id, self.page)

    buffer = io.BytesIO()
    doc = _TrackingDocTemplate(buffer, pagesize=LETTER)
    doc.build(flowables)

    # `(kind, element_id_to_report, key tracked_pages was recorded under)`
    # for every trackable element, in the exact order `_build_flowables`
    # emitted them — a section's own heading first, then each of its
    # lines' owner id(s) (0 or 1 in practice; iter_section_lines_with_ids'
    # own docstring covers when it's 0).
    ordered: list[tuple[str, str, str]] = []
    for key in section_titles_for(cv.language):
        if key not in lines_by_section:
            continue
        ordered.append(("section", key, f"section:{key}"))
        for _, owner_ids in lines_by_section[key]:
            ordered.extend(("line", owner_id, owner_id) for owner_id in owner_ids)

    # Walk that same order, reporting every point where the tracked page
    # number actually increases — that transition is a real break; an
    # element `tracked_pages` never saw (the generic-grouped-line gap
    # documented on iter_section_lines_with_ids) is simply skipped, not
    # treated as page 1.
    breaks: list[PageBreakPosition] = []
    current_page = 1
    for kind, element_id, tracking_key in ordered:
        page = doc.tracked_pages.get(tracking_key)
        if page is None or page <= current_page:
            continue
        breaks.append(PageBreakPosition(kind=kind, element_id=element_id, page=page))
        current_page = page
    return breaks


def _render_pdf(cv: AssembledCV, sections: dict[str, str], template: PdfTemplate) -> bytes:
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.platypus import SimpleDocTemplate
    except ImportError as exc:
        raise ExportError(
            "PDF export requires the 'reportlab' package (listed in pyproject.toml)."
        ) from exc

    try:
        flowables = _build_flowables(cv, sections, template)
        buffer = io.BytesIO()
        SimpleDocTemplate(buffer, pagesize=LETTER).build(flowables)
        data = buffer.getvalue()
    except Exception as exc:  # noqa: BLE001 - translate any reportlab error
        raise ExportError(f"Could not build PDF export: {exc}") from exc

    if len(data) > _MAX_EXPORT_BYTES:
        raise ExportError(
            f"Generated PDF is {len(data) / 1_000_000:.1f}MB, exceeding the 2MB export limit."
        )
    return data


def _build_flowables(
    cv: AssembledCV,
    sections: dict[str, str],
    template: PdfTemplate,
    section_line_ids: dict[str, list[list[str]]] | None = None,
) -> list:
    """The actual flowable-building logic — split out from `_render_pdf`
    so `compute_page_breaks` below can reuse it verbatim (same fonts, same
    KeepTogether protection, same everything) against a page-*tracking*
    DocTemplate instead of a normal one, guaranteeing the reported break
    positions describe the exact same document a real export would
    produce — never a second, independently-drifting approximation.

    `section_line_ids`, when given, must be index-aligned with
    `sections[key].split("\\n")` for every key it covers (exactly what
    `app/cv_markdown.py::iter_section_lines_with_ids` produces) — each
    Paragraph built from `sections[key]` gets tagged with its
    corresponding owner id(s) (`._owner_ids`), and the section's own
    heading gets tagged with `[f"section:{key}"]`. `None` (the normal
    render path) skips tagging entirely — zero behavior change, zero
    overhead, for actual PDF generation.
    """
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer

    register_pdf_fonts()

    styles = getSampleStyleSheet()
    styles["Title"].fontName = template.heading_font
    styles["Heading2"].fontName = template.heading_font
    styles["Normal"].fontName = template.body_font
    bullet_style = ParagraphStyle(
        "Bullet", parent=styles["Normal"], leftIndent=14, spaceAfter=2, fontName=template.body_font
    )
    body_style = ParagraphStyle("Body", parent=styles["Normal"], spaceAfter=2, fontName=template.body_font)

    flowables = _render_header(cv, styles)
    for key, title in section_titles_for(cv.language).items():
        body = sections.get(key, "")
        if not body.strip():
            continue
        # Phase 30 — manual pagination control. A section-level break
        # forces the heading itself onto a new page, so it's handled
        # here (before `heading` even exists) rather than folded into
        # `_render_body`'s per-line marker handling below, which only
        # ever affects content *within* a section.
        section_break, body = split_leading_page_break_marker(body)
        if section_break:
            flowables.append(PageBreak())
        flowables.append(Spacer(1, template.section_spacing))
        heading = Paragraph(escape(title), styles["Heading2"])
        if section_line_ids is not None:
            heading._owner_ids = [f"section:{key}"]
        line_ids = section_line_ids.get(key) if section_line_ids is not None else None
        body_flowables = _render_body(body, body_style, bullet_style, template.bullet_char, line_ids)
        if body_flowables:
            if isinstance(body_flowables[0], PageBreak):
                # The section's first entry/category (not the section
                # itself) is the one flagged — the heading stays put;
                # only the content after it jumps to the new page. Not
                # meaningful to KeepTogether a heading with a forced
                # break, so that trick is skipped for this case only.
                flowables.append(heading)
                flowables += _protect_lines_from_page_splits(body_flowables)
            else:
                # KeepTogether just the heading + its first line, not
                # the whole section — reportlab's
                # SimpleDocTemplate.build() otherwise breaks pages
                # purely by available space, with no protection
                # against stranding a heading alone at the bottom of a
                # page with its content starting fresh on the next (a
                # real bug found from a real export). Wrapping the
                # *whole* section would trade that for a worse one: a
                # long section like Experience would jump to a new
                # page as one atomic block instead of flowing
                # naturally — same reasoning app/cv_docx.py's
                # identical fix and the on-screen preview's own CSS
                # fix (Phase 16c) both already settled on. The first
                # line stays a bare Paragraph *inside* this
                # KeepTogether (not separately wrapped) — being part
                # of this unit already protects it from an internal
                # split the same way _protect_lines_from_page_splits
                # protects every other line below.
                flowables.append(KeepTogether([heading, body_flowables[0]]))
                flowables += _protect_lines_from_page_splits(body_flowables[1:])
        else:
            flowables.append(heading)
    return flowables


def _protect_lines_from_page_splits(items: list) -> list:
    """Wraps each Paragraph in its own single-item KeepTogether so a
    bullet or plain line can never be split mid-sentence across a page
    boundary — reportlab's `SimpleDocTemplate.build()` otherwise allows a
    Paragraph tall enough to wrap onto two lines to have *those lines*
    land on different pages, a real bug found from a real Cyrillic
    export (a bullet's own wrapped second line stranded alone at the top
    of the next page, the first line's sentence cut off mid-word at the
    bottom of the previous one). Mirrors CSS's `break-inside: avoid` on
    `.cv-print-bullet`/a flat `p.cv-print-entry` line — the same rule
    `frontend/src/lib/tiptap/pageBreaks.ts`'s on-screen prediction already
    assumes holds (see that module's own `leaves` fallback docstring).

    `PageBreak` markers pass through unwrapped — nothing to protect
    there. A KeepTogether around a single flowable is a no-op in every
    case except this one: if the flowable alone is taller than a whole
    page, KeepTogether renders it in place rather than moving it forward
    forever looking for a page it'll never fit on whole — the one
    documented, accepted edge case (see pageBreaks.ts) where a line can
    still split, exactly matching reportlab's own default behavior for
    that same edge case.
    """
    from reportlab.platypus import KeepTogether, Paragraph

    return [KeepTogether([item]) if isinstance(item, Paragraph) else item for item in items]


def _render_header(cv: AssembledCV, styles) -> list:
    from reportlab.platypus import Paragraph, Spacer

    # Contacts moved out of the header into its own section (Contacts is
    # now first in SECTION_TITLES) so each contact can be independently
    # included/excluded like every other CV fact — see
    # app/cv_markdown.py::render_contacts_section.
    flowables = [Paragraph(escape(cv.name), styles["Title"])]
    if cv.headline:
        flowables.append(Paragraph(f"<i>{escape(cv.headline)}</i>", styles["Normal"]))
    flowables.append(Spacer(1, 8))
    return flowables


def _runs_to_markup(runs: list[InlineRun]) -> str:
    parts = []
    for run in runs:
        text = escape(run.text)
        if run.bold:
            text = f"<b>{text}</b>"
        if run.italic:
            text = f"<i>{text}</i>"
        if run.url:
            # Already gets its own <u> from the link markup below — an
            # explicit run.underline on a link run would just double it
            # up, so it's deliberately not also applied here.
            href = escape(run.url).replace('"', "&quot;")
            text = f'<link href="{href}"><font color="#0563C1"><u>{text}</u></font></link>'
        elif run.underline:
            text = f"<u>{text}</u>"
        parts.append(text)
    return "".join(parts)


def _render_body(
    body: str, body_style, bullet_style, bullet_char: str, line_ids: list[list[str]] | None = None
) -> list:
    from reportlab.platypus import PageBreak, Paragraph

    flowables = []
    lines = body.split("\n")
    # `line_ids`, when given, is index-aligned with `lines` — see
    # `_build_flowables`'s own docstring and
    # `app/cv_markdown.py::iter_section_lines_with_ids`'s alignment
    # guarantee. `enumerate` here, not a second parallel loop, so a
    # length mismatch (a bug, never expected in practice) raises an
    # IndexError immediately rather than silently mis-tagging lines.
    for index, line in enumerate(lines):
        # Phase 30 — an entry/category-group's own forced break, encoded
        # as its own marker-only line by render_sections_from_document
        # (see ENTRY_PAGE_BREAK_MARKER's docstring). Checked before
        # `.strip()` below: this sentinel IS whitespace by Python's
        # definition, so stripping it first would silently swallow the
        # line instead of emitting the break it represents.
        if line == ENTRY_PAGE_BREAK_MARKER:
            flowables.append(PageBreak())
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            # `render_sections_from_document`'s own "- " list-marker
            # convention identifies which lines are bullets — the actual
            # rendered marker is this call's `bullet_char` (the plain
            # export's own hyphen for `render_pdf`, or a PdfTemplate's
            # bullet_char for `render_templated_pdf`), not necessarily a
            # literal hyphen.
            markup = escape(bullet_char) + "  " + _runs_to_markup(parse_inline_runs(stripped[2:]))
            paragraph = Paragraph(markup, bullet_style)
        else:
            markup = _runs_to_markup(parse_inline_runs(stripped))
            paragraph = Paragraph(markup, body_style)
        if line_ids is not None and line_ids[index]:
            paragraph._owner_ids = line_ids[index]
        flowables.append(paragraph)
    return flowables
