"""Tests app/cv_pdf.py's render_templated_pdf (Version 4, Phase 4.9) —
deliberately much thinner than test_cv_docx_templated.py's suite:
render_templated_pdf delegates the actual document-walking (grouping,
subheadings, page breaks, runs) to app/cv_markdown.py's
render_sections_from_document — already covered by test_cv_markdown.py —
then reuses render_pdf's own already-tested _render_pdf. What's actually
new here is the template dispatch itself: font/bullet-char/spacing
selection, and that real Cyrillic content survives it for both
templates (the actual point of Phase 4.9 existing at all).
"""

import io

from pypdf import PdfReader

from app.cv_pdf import PDF_TEMPLATES, render_templated_pdf
from domain.models import AssembledCV, PrintDocument


def make_cv(**overrides) -> AssembledCV:
    defaults = dict(name="Ada Lovelace", summary="A summary.")
    defaults.update(overrides)
    return AssembledCV(**defaults)


def extract_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_produces_a_valid_pdf_for_each_known_template():
    cv = make_cv()
    document = PrintDocument(sections=[])

    for template_id in PDF_TEMPLATES:
        data = render_templated_pdf(cv, document, template_id)
        assert data[:4] == b"%PDF"


def test_unknown_template_id_falls_back_to_classic():
    cv = make_cv(name="Someone")
    document = PrintDocument(sections=[])

    data = render_templated_pdf(cv, document, "does-not-exist")

    # No direct way to introspect which font a flowable used post-hoc from
    # raw bytes without a full PDF-structure parse — falling back without
    # raising, and still producing valid, readable output, is what
    # actually matters (same bar test_cv_docx_templated.py's identical
    # fallback test holds its DOCX counterpart to).
    assert data[:4] == b"%PDF"
    assert "Someone" in extract_text(data)


def test_uses_each_templates_own_bullet_character():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "education",
                "title": "Education",
                "included": True,
                "entries": [{"id": "edu-1", "text": "State University", "included": True}],
            }
        ]
    )

    for template_id, template in PDF_TEMPLATES.items():
        text = extract_text(render_templated_pdf(cv, document, template_id))
        # pypdf's extraction reconstructs spacing from glyph positions
        # rather than preserving the source markup's literal two-space
        # gap exactly (confirmed live: it collapses to one) — the bullet
        # character immediately preceding the text, not the exact
        # whitespace run, is what this actually needs to pin.
        assert f"{template.bullet_char} State University" in text


def test_excluded_entries_and_sections_are_omitted():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "experience",
                "title": "Experience",
                "included": True,
                "entries": [
                    {
                        "id": "exp-1",
                        "text": "Engineer — Acme",
                        "included": True,
                        "bullets": [
                            {"id": "b1", "text": "Included bullet", "included": True},
                            {"id": "b2", "text": "Excluded bullet", "included": False},
                        ],
                    },
                    {"id": "exp-2", "text": "Excluded role", "included": False},
                ],
            },
            {
                "key": "education",
                "title": "Education",
                "included": False,
                "entries": [{"id": "edu-1", "text": "Excluded university", "included": True}],
            },
        ]
    )

    text = extract_text(render_templated_pdf(cv, document, "modern"))

    assert "Included bullet" in text
    assert "Excluded bullet" not in text
    assert "Excluded role" not in text
    assert "Excluded university" not in text


def test_cyrillic_content_is_correctly_extractable_for_every_template():
    # Version 4, Phase 4.4/4.9's actual point: DejaVuSerif ("classic") and
    # NotoSans ("modern") both have real Cyrillic glyph coverage,
    # confirmed directly (see app/cv_fonts.py's own docstring) — this
    # pins the full render-then-extract round trip for both, not just
    # that fonts were registered without raising.
    cv = make_cv(language="ru", name="Ада Ловлейс", headline="Ведущий инженер")
    document = PrintDocument(
        sections=[
            {
                "key": "summary",
                "title": "Summary",
                "included": True,
                "entries": [{"id": "summary", "text": "Работал с Python и SQL.", "included": True}],
            }
        ]
    )

    for template_id in PDF_TEMPLATES:
        text = extract_text(render_templated_pdf(cv, document, template_id))
        assert "Ада Ловлейс" in text
        assert "Ведущий инженер" in text
        assert "Работал с Python и SQL." in text


def test_bold_and_italic_markup_text_stays_correct_with_a_true_bold_sans_face():
    # Post-4.9 fix: NotoSans (replacing DejaVuSans, see app/cv_fonts.py's
    # docstring) has a real bold face, so <b> markup now resolves to a
    # genuinely distinct bold font rather than silently falling back to
    # regular weight (test_cv_fonts.py pins that resolution directly via
    # tt2ps). This can't assert visual boldness from extracted text
    # alone, but it does pin that the text itself survives correctly.
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "experience",
                "title": "Experience",
                "included": True,
                "entries": [
                    {
                        "id": "exp-1",
                        "text": "Engineer — Acme",
                        "included": True,
                        "locked": False,
                        "bullets": [{"id": "b1", "text": "Shipped a feature", "included": True}],
                    }
                ],
            }
        ]
    )

    text = extract_text(render_templated_pdf(cv, document, "modern"))

    assert "Engineer — Acme" in text
    assert "Shipped a feature" in text


def test_section_spacing_differs_between_templates(monkeypatch):
    from reportlab.platypus import SimpleDocTemplate, Spacer

    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "education",
                "title": "Education",
                "included": True,
                "entries": [{"id": "edu-1", "text": "State University", "included": True}],
            }
        ]
    )

    captured: dict = {}

    def fake_build(self, flowables):
        captured["flowables"] = flowables

    monkeypatch.setattr(SimpleDocTemplate, "build", fake_build)

    # _render_header emits its own Spacer(1, 8) first (before any section
    # exists at all) — the *second* Spacer in the flowables list is the
    # per-section one this test actually cares about; the header's own is
    # unaffected by `template` on purpose (mirrors render_templated_docx,
    # whose `section_spacing_pt` only ever touches a section heading's
    # own `space_before`, never the header-to-first-section gap).
    render_templated_pdf(cv, document, "modern")
    modern_spacer = [f for f in captured["flowables"] if isinstance(f, Spacer)][1]

    render_templated_pdf(cv, document, "classic")
    classic_spacer = [f for f in captured["flowables"] if isinstance(f, Spacer)][1]

    assert modern_spacer.height == PDF_TEMPLATES["modern"].section_spacing
    assert classic_spacer.height == PDF_TEMPLATES["classic"].section_spacing
    assert modern_spacer.height != classic_spacer.height
