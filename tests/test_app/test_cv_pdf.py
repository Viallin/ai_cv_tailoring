import io

import pytest
from pypdf import PdfReader

from app.cv_markdown import ENTRY_PAGE_BREAK_MARKER, SECTION_PAGE_BREAK_MARKER
from app.cv_pdf import _protect_lines_from_page_splits, _runs_to_markup, render_pdf
from app.errors import ExportError
from app.markdown_inline import InlineRun
from domain.models import AssembledCV, AssembledExperienceEntry, ContactItem, Project, TailoredBullet


def make_cv(**overrides) -> AssembledCV:
    defaults = dict(name="Ada Lovelace", summary="A summary.")
    defaults.update(overrides)
    return AssembledCV(**defaults)


def extract_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() for page in reader.pages)


def hyperlink_targets(data: bytes) -> set[str]:
    reader = PdfReader(io.BytesIO(data))
    targets = set()
    for page in reader.pages:
        for annot in page.get("/Annots", []):
            action = annot.get_object().get("/A")
            if action and "/URI" in action:
                targets.add(str(action["/URI"]))
    return targets


def test_produces_a_valid_pdf_under_the_size_limit():
    data = render_pdf(make_cv(), sections={})

    assert data[:4] == b"%PDF"
    assert len(data) < 2_000_000


def test_extracted_text_includes_name_and_headline():
    cv = make_cv(headline="Analytical Engineer")

    text = extract_text(render_pdf(cv, sections={}))

    assert "Ada Lovelace" in text
    assert "Analytical Engineer" in text


def test_contacts_section_appears_in_extracted_text():
    # Contacts moved out of the header into its own section (Contacts is
    # first in SECTION_TITLES) — this is the same "edited sections dict"
    # path every other section already uses, not header-special-cased.
    cv = make_cv()
    sections = {"contacts": "- Email: ada@example.com"}

    text = extract_text(render_pdf(cv, sections))

    assert "Email: ada@example.com" in text


def test_renders_without_error_for_a_russian_language_cv():
    # Version 4, Phase 4.3: headings localize correctly (section_titles_for).
    cv = make_cv(language="ru", summary="О себе.")

    data = render_pdf(cv, sections={"summary": "Текст на русском."})

    assert data[:4] == b"%PDF"


def test_cyrillic_text_is_correctly_extractable():
    # Version 4, Phase 4.4: Base-14 Helvetica's WinAnsi encoding has zero
    # Cyrillic glyphs — before DejaVu Sans embedding (app/cv_fonts.py),
    # every Cyrillic character round-tripped through pypdf's text
    # extraction as a tofu box / mojibake, confirmed live against an
    # actual generated PDF. This pins the fix: real Cyrillic text survives
    # the full render-then-extract round trip byte for byte.
    cv = make_cv(language="ru", name="Ада Ловлейс", headline="Ведущий инженер")

    text = extract_text(render_pdf(cv, sections={"summary": "Работал с Python и SQL."}))

    assert "Ада Ловлейс" in text
    assert "Ведущий инженер" in text
    assert "Работал с Python и SQL." in text


def test_only_non_blank_sections_are_included():
    cv = make_cv()
    sections = {"summary": "Some text.", "skills": "", "experience": "   "}

    text = extract_text(render_pdf(cv, sections))

    assert "Summary" in text
    assert "Some text." in text
    assert "Skills" not in text
    assert "Experience" not in text


def test_bullet_lines_and_inline_styling_are_extractable():
    cv = make_cv(
        experience=[
            AssembledExperienceEntry(
                experience_id="exp-1",
                position="Engineer",
                company="Acme",
                bullets=[TailoredBullet(text="Did a thing")],
            )
        ]
    )
    sections = {"experience": "**Engineer** — Acme\n- Did a thing"}

    text = extract_text(render_pdf(cv, sections))

    assert "Engineer" in text and "Acme" in text
    assert "Did a thing" in text


# ----- Phase 25: __underline__ spans, only ever produced by
# cv_markdown.py::_serialize_runs for a block with explicit runs ----------


def test_runs_to_markup_wraps_underline_runs_in_a_u_tag():
    markup = _runs_to_markup([InlineRun("Underlined", bold=False, italic=False, underline=True)])

    assert markup == "<u>Underlined</u>"


def test_runs_to_markup_does_not_double_underline_a_link_run():
    # A link run already gets its own <u> from the hyperlink markup —
    # explicitly setting run.underline too (unlikely in practice, since
    # markdown_inline.py never produces both on the same run) shouldn't
    # wrap it a second time.
    markup = _runs_to_markup([InlineRun("Portfolio", bold=False, italic=False, underline=True, url="https://x.example")])

    assert markup.count("<u>") == 1


def test_underline_span_is_extractable_end_to_end():
    cv = make_cv()
    sections = {"experience": "__Engineer__ — Acme"}

    text = extract_text(render_pdf(cv, sections))

    assert "Engineer — Acme" in text


def test_contact_url_becomes_a_clickable_link_annotation():
    cv = make_cv()
    sections = {"contacts": "- Email: ada@example.com\n- Portfolio: https://ada.example.com/portfolio"}

    data = render_pdf(cv, sections)

    assert hyperlink_targets(data) == {"https://ada.example.com/portfolio"}
    assert "https://ada.example.com/portfolio" in extract_text(data)


def test_project_url_becomes_a_clickable_link_annotation():
    cv = make_cv(projects=[Project(id="p1", name="Analytical Engine", url="https://example.com/engine")])
    sections = {"projects": "- **Analytical Engine** (https://example.com/engine)"}

    data = render_pdf(cv, sections)

    assert hyperlink_targets(data) == {"https://example.com/engine"}


def test_portfolio_link_url_becomes_a_clickable_link_annotation():
    cv = make_cv()
    sections = {"portfolio_links": "- Concept art — https://example.com/portfolio"}

    data = render_pdf(cv, sections)

    assert hyperlink_targets(data) == {"https://example.com/portfolio"}


def test_publication_url_becomes_a_clickable_link_annotation():
    cv = make_cv()
    sections = {"publications": "- **Scaling LiveOps** — Medium (https://example.com/article)"}

    data = render_pdf(cv, sections)

    assert hyperlink_targets(data) == {"https://example.com/article"}


def test_section_heading_is_kept_together_with_its_first_line(monkeypatch):
    # Real bug found from a real export: reportlab's SimpleDocTemplate
    # breaks pages purely by available space, with no protection against
    # stranding a heading alone at the bottom of a page while its content
    # starts fresh on the next. Only the heading + its *first* line are
    # wrapped (not the whole section) so a long section like Experience
    # still flows naturally across pages instead of jumping as one atomic
    # block — same reasoning app/cv_docx.py's identical fix uses.
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate

    captured: dict = {}

    def fake_build(self, flowables):
        captured["flowables"] = flowables

    monkeypatch.setattr(SimpleDocTemplate, "build", fake_build)

    render_pdf(make_cv(), sections={"summary": "A summary line.\nA second line."})

    keep_together = next(f for f in captured["flowables"] if isinstance(f, KeepTogether))
    assert len(keep_together._content) == 2
    heading, first_line = keep_together._content
    assert isinstance(heading, Paragraph) and "Summary" in heading.text
    assert isinstance(first_line, Paragraph) and "A summary line." in first_line.text
    # The second line stays outside the KeepTogether, free to flow normally.
    assert not any(
        isinstance(f, Paragraph) and "A second line." in f.text for f in keep_together._content
    )


# ----- Phase 30: manual pagination control (plain/ATS-safe PDF) ----------


def _captured_flowables(monkeypatch, sections: dict[str, str]) -> list:
    from reportlab.platypus import SimpleDocTemplate

    captured: dict = {}

    def fake_build(self, flowables):
        captured["flowables"] = flowables

    monkeypatch.setattr(SimpleDocTemplate, "build", fake_build)
    render_pdf(make_cv(), sections=sections)
    return captured["flowables"]


def test_section_level_marker_inserts_a_page_break_before_the_heading(monkeypatch):
    # A section-level break: the PageBreak lands before the heading, and
    # the heading + its first line are still KeepTogether'd as normal —
    # they both just start on the new page instead of wherever they'd
    # otherwise have flowed to.
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph

    flowables = _captured_flowables(
        monkeypatch, {"summary": f"{SECTION_PAGE_BREAK_MARKER}\nA summary line."}
    )

    break_index = next(i for i, f in enumerate(flowables) if isinstance(f, PageBreak))
    keep_together = next(f for f in flowables[break_index + 1 :] if isinstance(f, KeepTogether))
    heading, first_line = keep_together._content
    assert isinstance(heading, Paragraph) and "Summary" in heading.text
    assert isinstance(first_line, Paragraph) and "A summary line." in first_line.text


def test_entry_level_marker_inserts_a_page_break_after_the_heading(monkeypatch):
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph

    flowables = _captured_flowables(
        monkeypatch,
        {"summary": f"First line.\n{ENTRY_PAGE_BREAK_MARKER}\nSecond line."},
    )

    # The heading + first line are still KeepTogether'd as normal (no
    # section-level break here) — the forced break only affects the
    # second line, further down the flowables list.
    keep_together = next(f for f in flowables if isinstance(f, KeepTogether))
    assert any("First line." in f.text for f in keep_together._content if isinstance(f, Paragraph))

    # "Second line." is itself wrapped in its own single-item KeepTogether
    # now (_protect_lines_from_page_splits) — every line after the first
    # is, so it can never split mid-sentence across a page boundary (see
    # that function's own docstring). Unwrap one level to reach the
    # actual Paragraph.
    break_index = next(i for i, f in enumerate(flowables) if isinstance(f, PageBreak))
    second_line_wrapper = next(f for f in flowables[break_index + 1 :] if isinstance(f, KeepTogether))
    second_line = second_line_wrapper._content[0]
    assert isinstance(second_line, Paragraph) and "Second line." in second_line.text


def test_entry_marker_on_a_sections_very_first_line_orphans_the_heading_not_keeps_it_with_content(monkeypatch):
    # An entry-level break on a section's *first* entry (not the section
    # itself, hence ENTRY_PAGE_BREAK_MARKER, not SECTION_PAGE_BREAK_MARKER
    # — see that constant's docstring for why body's leading line is
    # ambiguous between the two without distinct sentinels) — the heading
    # has nothing to KeepTogether with, since the very next flowable is a
    # forced break, not a Paragraph. Matches the CSS-driven templated
    # path's identical behavior (no special-casing to drag the heading
    # along). "Only line." itself still gets wrapped in its own single-
    # item KeepTogether (_protect_lines_from_page_splits protects every
    # line, not just ones following a merged heading) — what this test
    # actually pins is that the *heading* specifically was never folded
    # into any KeepTogether, not that none exist anywhere in the output.
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph

    flowables = _captured_flowables(
        monkeypatch, {"summary": f"{ENTRY_PAGE_BREAK_MARKER}\nOnly line."}
    )

    heading = next(f for f in flowables if isinstance(f, Paragraph) and "Summary" in f.text)
    heading_index = flowables.index(heading)
    assert isinstance(flowables[heading_index + 1], PageBreak)
    assert not any(
        isinstance(f, KeepTogether) and heading in f._content for f in flowables
    )


def test_marker_text_itself_never_leaks_into_rendered_content(monkeypatch):
    from reportlab.platypus import Paragraph

    flowables = _captured_flowables(
        monkeypatch, {"summary": f"{SECTION_PAGE_BREAK_MARKER}\nA summary line."}
    )

    assert not any(
        isinstance(f, Paragraph) and (SECTION_PAGE_BREAK_MARKER in f.text or ENTRY_PAGE_BREAK_MARKER in f.text)
        for f in flowables
    )


# ----- Bug fix: a bullet/line must never split mid-sentence across a
# page boundary (found from a real Cyrillic export — a long bullet's own
# wrapped second line landed on the next page, orphaned from its
# sentence-ending first line) ----------------------------------------


def test_protect_lines_from_page_splits_wraps_every_paragraph_individually():
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph

    from reportlab.lib.styles import getSampleStyleSheet

    style = getSampleStyleSheet()["Normal"]
    para_a = Paragraph("A", style)
    para_b = Paragraph("B", style)
    page_break = PageBreak()

    protected = _protect_lines_from_page_splits([para_a, page_break, para_b])

    assert isinstance(protected[0], KeepTogether) and protected[0]._content == [para_a]
    assert protected[1] is page_break  # passed through unwrapped
    assert isinstance(protected[2], KeepTogether) and protected[2]._content == [para_b]


def test_every_bullet_after_the_first_is_individually_protected_from_page_splits(monkeypatch):
    from reportlab.platypus import KeepTogether, Paragraph

    flowables = _captured_flowables(
        monkeypatch,
        {"experience": "**Engineer** — Acme\n- First bullet.\n- Second bullet.\n- Third bullet."},
    )

    # The heading + role-header line share one KeepTogether (existing
    # behavior, unchanged) — each of the three *bullets* gets its own,
    # separate one, confirmed by checking each is a single-item
    # KeepTogether whose one Paragraph is that exact bullet's text (not,
    # say, all three sharing one combined KeepTogether, which would bring
    # back the old "moves as one atomic block" problem Post-30 already
    # fixed for whole entries).
    bullet_texts = ["First bullet.", "Second bullet.", "Third bullet."]
    for text in bullet_texts:
        wrapper = next(
            f
            for f in flowables
            if isinstance(f, KeepTogether)
            and len(f._content) == 1
            and isinstance(f._content[0], Paragraph)
            and text in f._content[0].text
        )
        assert isinstance(wrapper._content[0], Paragraph)


def test_raises_export_error_when_content_exceeds_size_limit(monkeypatch):
    import app.cv_pdf as cv_pdf_module

    monkeypatch.setattr(cv_pdf_module, "_MAX_EXPORT_BYTES", 10)
    cv = make_cv()

    with pytest.raises(ExportError, match="2MB"):
        render_pdf(cv, sections={"summary": "Some text."})
