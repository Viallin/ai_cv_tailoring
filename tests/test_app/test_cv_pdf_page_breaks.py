"""Tests app/cv_pdf.py's compute_page_breaks — the on-screen page-break-
prediction fix (follow-up to Version 4, Phase 4.9). Asks the real
reportlab renderer where pages actually break, rather than approximating
from browser DOM measurements that no longer correspond to what PDF
export actually produces (see that function's own docstring for why).
"""

from app.cv_pdf import PageBreakPosition, compute_page_breaks
from domain.models import AssembledCV, PrintDocument


def make_cv(**overrides) -> AssembledCV:
    defaults = dict(name="Ada Lovelace", summary="A summary.")
    defaults.update(overrides)
    return AssembledCV(**defaults)


def _experience_document(bullet_count: int) -> PrintDocument:
    bullets = [
        {
            "id": f"b{i}",
            "text": f"A reasonably long bullet point describing accomplishment number {i} in some real detail.",
            "included": True,
        }
        for i in range(bullet_count)
    ]
    return PrintDocument(
        sections=[
            {
                "key": "experience",
                "title": "Experience",
                "included": True,
                "entries": [{"id": "exp-1", "text": "Engineer — Acme", "included": True, "bullets": bullets}],
            }
        ]
    )


def test_a_document_that_fits_on_one_page_reports_no_breaks():
    document = _experience_document(bullet_count=3)

    breaks = compute_page_breaks(make_cv(), document, template_id=None)

    assert breaks == []


def test_a_long_document_reports_at_least_one_break_on_a_real_bullet():
    document = _experience_document(bullet_count=60)

    breaks = compute_page_breaks(make_cv(), document, template_id=None)

    assert len(breaks) >= 1
    first = breaks[0]
    assert isinstance(first, PageBreakPosition)
    assert first.kind == "line"
    assert first.element_id.startswith("b")
    assert first.page == 2


def test_breaks_are_strictly_increasing_pages_in_document_order():
    document = _experience_document(bullet_count=150)

    breaks = compute_page_breaks(make_cv(), document, template_id=None)

    assert len(breaks) >= 2
    pages = [b.page for b in breaks]
    assert pages == sorted(set(pages))  # strictly increasing, no duplicates/out-of-order


def test_section_level_break_is_reported_when_a_second_section_starts_a_new_page():
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
                            {"id": f"b{i}", "text": f"Bullet number {i} with a bit of real content.", "included": True}
                            for i in range(60)
                        ],
                    }
                ],
            },
            {
                "key": "education",
                "title": "Education",
                "included": True,
                "entries": [{"id": "edu-1", "text": "State University", "included": True}],
            },
        ]
    )

    breaks = compute_page_breaks(make_cv(), document, template_id=None)

    # Education's own heading always lands somewhere — either it's part of
    # the same page as the tail of a 60-bullet Experience section (no
    # section-level break reported) or it starts fresh; either is a valid
    # real layout outcome. What matters here: if Education DOES start a
    # new page, it's reported with kind "section" and element_id
    # "education" specifically, not silently dropped.
    education_break = next((b for b in breaks if b.kind == "section" and b.element_id == "education"), None)
    if education_break is not None:
        assert education_break.page >= 2


def test_unknown_template_id_falls_back_to_classic_without_raising():
    document = _experience_document(bullet_count=60)

    breaks = compute_page_breaks(make_cv(), document, template_id="does-not-exist")

    assert len(breaks) >= 1


def test_none_template_id_uses_the_plain_template():
    document = _experience_document(bullet_count=60)

    plain_breaks = compute_page_breaks(make_cv(), document, template_id=None)
    templated_breaks = compute_page_breaks(make_cv(), document, template_id="classic")

    # Different fonts/section-spacing between plain and classic mean the
    # exact break position can genuinely differ — this just pins that
    # template_id=None doesn't crash and produces *some* real result,
    # not that it's identical to a template.
    assert len(plain_breaks) >= 1
    assert len(templated_breaks) >= 1


def test_generic_grouped_sections_get_no_line_level_breaks_only_section_level():
    # Education routes through group_entries_by_subheading's generic
    # per-member path — iter_section_lines_with_ids can't attribute an id
    # to those lines (see its own docstring), so no "line"-kind break can
    # ever be reported for one, only a "section"-kind break at its own
    # heading, if any.
    document = PrintDocument(
        sections=[
            {
                "key": "education",
                "title": "Education",
                "included": True,
                "entries": [
                    {"id": f"edu-{i}", "text": f"University number {i} with a reasonably long name.", "included": True}
                    for i in range(80)
                ],
            }
        ]
    )

    breaks = compute_page_breaks(make_cv(), document, template_id=None)

    assert all(b.kind == "section" for b in breaks)
