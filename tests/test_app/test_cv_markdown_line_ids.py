"""Tests app/cv_markdown.py's iter_section_lines_with_ids — the on-screen
page-break-prediction fix (Version 4, follow-up to Phase 4.9). Two things
matter here: (1) its text column stays byte-for-byte aligned with
render_sections_from_document's own output for the same document (the
guarantee app/cv_pdf.py's compute_page_breaks relies on to zip text and
ids together), and (2) it attaches the right owner id(s) to each line.
"""

from app.cv_markdown import (
    ENTRY_PAGE_BREAK_MARKER,
    SECTION_PAGE_BREAK_MARKER,
    iter_section_lines_with_ids,
    render_sections_from_document,
)
from domain.models import PrintDocument


def _text(document: PrintDocument, key: str) -> str:
    return "\n".join(text for text, _ in iter_section_lines_with_ids(document)[key])


def assert_text_matches_render_sections_from_document(document: PrintDocument) -> None:
    expected = render_sections_from_document(document)
    actual_with_ids = iter_section_lines_with_ids(document)
    assert set(actual_with_ids) == set(expected)
    for key in expected:
        assert _text(document, key) == expected[key]


def test_summary_line_is_owned_by_its_entry_id():
    document = PrintDocument(
        sections=[
            {
                "key": "summary",
                "title": "Summary",
                "included": True,
                "entries": [{"id": "summary-1", "text": "A summary.", "included": True}],
            }
        ]
    )

    assert_text_matches_render_sections_from_document(document)
    lines = iter_section_lines_with_ids(document)["summary"]
    assert lines == [("A summary.", ["summary-1"])]


def test_experience_role_and_bullets_are_owned_by_their_own_ids():
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
                        "bullets": [
                            {"id": "b1", "text": "Shipped a feature", "included": True},
                            {"id": "proj-1", "text": "Internal tool", "included": True, "kind": "subheading"},
                            {"id": "b2", "text": "Owned the backend", "included": True},
                        ],
                    },
                    {"id": "exp-2", "text": "Career break", "included": True, "locked": True, "bullets": []},
                ],
            }
        ]
    )

    assert_text_matches_render_sections_from_document(document)
    lines = iter_section_lines_with_ids(document)["experience"]
    assert lines == [
        ("**Engineer — Acme**", ["exp-1"]),
        ("- Shipped a feature", ["b1"]),
        ("*Internal tool*", ["proj-1"]),
        ("- Owned the backend", ["b2"]),
        ("", []),
        ("*Career break*", ["exp-2"]),
    ]


def test_compact_skills_entry_is_owned_by_its_own_id():
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {
                        "id": "skills-0",
                        "text": "Design: Roadmapping; UX Design",
                        "included": True,
                        "kind": "compact",
                    }
                ],
            }
        ]
    )

    assert_text_matches_render_sections_from_document(document)
    lines = iter_section_lines_with_ids(document)["skills"]
    assert lines == [("Design: Roadmapping; UX Design", ["skills-0"])]


def test_legacy_grouped_category_line_gets_no_owner_id():
    # SubheadingGroupMember carries no id at all (by design) — a grouped/
    # joined line can represent several source entries fused onto one
    # line, with no single correct "owner". This is the documented,
    # accepted gap: compute_page_breaks simply can't offer a break marker
    # *within* this section, only at its own heading boundary.
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading"},
                    {"id": "s1", "text": "Roadmapping", "included": True},
                ],
            }
        ]
    )

    assert_text_matches_render_sections_from_document(document)
    lines = iter_section_lines_with_ids(document)["skills"]
    assert lines == [("- **Design**: Roadmapping", [])]


def test_generic_flat_join_line_gets_no_owner_id():
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "s0", "text": "Mentoring", "included": True},
                    {"id": "s1", "text": "Roadmapping", "included": True},
                ],
            }
        ]
    )

    assert_text_matches_render_sections_from_document(document)
    lines = iter_section_lines_with_ids(document)["skills"]
    assert lines == [("- Mentoring · Roadmapping", [])]


def test_generic_one_per_member_education_line_gets_no_owner_id():
    # Education/Certifications/Awards/etc. all route through the same
    # generic group_entries_by_subheading path as the legacy-grouped
    # Skills case above — SubheadingGroupMember strips the id regardless
    # of whether the line ends up alone or joined with others.
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

    assert_text_matches_render_sections_from_document(document)
    lines = iter_section_lines_with_ids(document)["education"]
    assert lines == [("- State University", [])]


def test_section_and_entry_page_break_markers_get_no_owner_id():
    document = PrintDocument(
        sections=[
            {
                "key": "summary",
                "title": "Summary",
                "included": True,
                "page_break_before": True,
                "entries": [
                    {"id": "s1", "text": "First.", "included": True, "page_break_before": True},
                ],
            }
        ]
    )

    assert_text_matches_render_sections_from_document(document)
    lines = iter_section_lines_with_ids(document)["summary"]
    assert lines == [
        (SECTION_PAGE_BREAK_MARKER, []),
        (ENTRY_PAGE_BREAK_MARKER, []),
        ("First.", ["s1"]),
    ]


def test_excluded_entries_and_bullets_are_skipped_entirely():
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
                "entries": [{"id": "edu-1", "text": "State University", "included": True}],
            },
        ]
    )

    assert_text_matches_render_sections_from_document(document)
    result = iter_section_lines_with_ids(document)
    ids = {i for _, ids in result["experience"] for i in ids}
    assert ids == {"exp-1", "b1"}
    assert "education" not in result
