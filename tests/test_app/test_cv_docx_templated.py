import io

from docx import Document

from app.cv_docx import render_templated_docx
from app.cv_templates import DOCX_TEMPLATES
from domain.models import AssembledCV, PrintDocument


def make_cv(**overrides) -> AssembledCV:
    defaults = dict(name="Ada Lovelace", summary="A summary.")
    defaults.update(overrides)
    return AssembledCV(**defaults)


def paragraphs(data: bytes):
    doc = Document(io.BytesIO(data))
    return [p for p in doc.paragraphs if p.text.strip()]


def paragraph_texts(data: bytes) -> list[str]:
    return [p.text for p in paragraphs(data)]


def test_header_uses_the_template_heading_font():
    cv = make_cv()
    document = PrintDocument(sections=[])

    data = render_templated_docx(cv, document, "modern")

    doc = Document(io.BytesIO(data))
    name_paragraph = doc.paragraphs[0]
    assert name_paragraph.text == "Ada Lovelace"
    assert name_paragraph.runs[0].font.name == DOCX_TEMPLATES["modern"].heading_font


# ----- Version 4, Phase 4.4: Calibri substitution for non-English -----


def test_non_english_profile_substitutes_calibri_for_both_templates():
    document = PrintDocument(sections=[])

    for template_id in ("classic", "modern"):
        cv = make_cv(language="ru")
        data = render_templated_docx(cv, document, template_id)
        name_paragraph = Document(io.BytesIO(data)).paragraphs[0]
        assert name_paragraph.runs[0].font.name == "Calibri"


def test_english_profile_keeps_the_templates_own_font():
    cv = make_cv(language="en")
    document = PrintDocument(sections=[])

    data = render_templated_docx(cv, document, "modern")

    name_paragraph = Document(io.BytesIO(data)).paragraphs[0]
    assert name_paragraph.runs[0].font.name == DOCX_TEMPLATES["modern"].heading_font
    assert name_paragraph.runs[0].font.name != "Calibri"


def test_calibri_substitution_leaves_bullet_char_and_spacing_unchanged():
    # Only the font names swap — the template's own visual bullet
    # marker/spacing identity survives the substitution.
    cv = make_cv(language="ru")
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

    data = render_templated_docx(cv, document, "modern")
    entry_paragraph = next(p for p in paragraphs(data) if "State University" in p.text)

    assert entry_paragraph.text.startswith(DOCX_TEMPLATES["modern"].bullet_char)


def test_excluded_entries_and_bullets_produce_no_matching_text():
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
            }
        ]
    )

    texts = " ".join(paragraph_texts(render_templated_docx(cv, document, "classic")))

    assert "Included bullet" in texts
    assert "Excluded bullet" not in texts
    assert "Excluded role" not in texts


def test_excluded_section_produces_no_heading_or_content():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "education",
                "title": "Education",
                "included": False,
                "entries": [{"id": "edu-1", "text": "State University", "included": True}],
            }
        ]
    )

    texts = paragraph_texts(render_templated_docx(cv, document, "classic"))

    assert "Education" not in texts
    assert "State University" not in texts


def test_generic_section_entries_render_as_bulleted_lines():
    # Every non-Experience section renders every (non-subheading) entry
    # as a bulleted line, matching app/cv_markdown.py's own
    # render_education_section/render_languages_section/etc. — all of
    # which use a "- " prefix. This was the actual bug reported: entries
    # rendered as plain, unbulleted paragraphs.
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

    data = render_templated_docx(cv, document, "modern")
    entry_paragraph = next(p for p in paragraphs(data) if "State University" in p.text)

    assert entry_paragraph.text.startswith(DOCX_TEMPLATES["modern"].bullet_char)
    assert entry_paragraph.runs[0].bold is not True


def test_section_heading_is_kept_with_the_following_paragraph():
    # Same real bug as render_docx's identical test: without this, Word
    # is free to break the page right after a section heading, stranding
    # it alone with its content starting fresh on the next page.
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

    data = render_templated_docx(cv, document, "modern")
    heading = next(p for p in paragraphs(data) if p.text == "Education")

    assert heading.paragraph_format.keep_with_next is True


def test_bullets_use_a_literal_template_character_not_list_bullet_style():
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
                        "bullets": [{"id": "b1", "text": "Shipped a feature", "included": True}],
                    }
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "modern")
    doc = Document(io.BytesIO(data))

    bullet_paragraph = next(p for p in doc.paragraphs if "Shipped a feature" in p.text)
    assert bullet_paragraph.style.name != "List Bullet"
    assert bullet_paragraph.text.startswith(DOCX_TEMPLATES["modern"].bullet_char)
    assert not any(p.style.name == "List Bullet" for p in doc.paragraphs)


def test_experience_role_header_is_bold_and_not_bulleted():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "experience",
                "title": "Experience",
                "included": True,
                "entries": [
                    {"id": "exp-1", "text": "Engineer — Acme", "included": True, "locked": False, "bullets": []}
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    role_paragraph = next(p for p in paragraphs(data) if p.text == "Engineer — Acme")

    assert role_paragraph.runs[0].bold is True
    assert not role_paragraph.text.startswith(DOCX_TEMPLATES["classic"].bullet_char)


def test_is_gap_entry_renders_italic_not_bold():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "experience",
                "title": "Experience",
                "included": True,
                "entries": [{"id": "exp-1", "text": "Career break", "included": True, "locked": True, "bullets": []}],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    gap_paragraph = next(p for p in paragraphs(data) if p.text == "Career break")

    assert gap_paragraph.runs[0].italic is True
    assert gap_paragraph.runs[0].bold is not True


def test_skills_category_renders_as_one_compact_grouped_paragraph():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading"},
                    {"id": "s1", "text": "Roadmapping (Expertise)", "included": True},
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    group_paragraph = next(p for p in paragraphs(data) if "Roadmapping" in p.text)

    # One paragraph for the whole category group, not a heading paragraph
    # plus a separate bulleted item paragraph.
    assert group_paragraph.text == "Design: Roadmapping (Expertise)"
    assert not group_paragraph.text.startswith(DOCX_TEMPLATES["classic"].bullet_char)
    assert group_paragraph.runs[0].text == "Design"
    assert group_paragraph.runs[0].bold is True
    assert group_paragraph.runs[1].text == ": Roadmapping (Expertise)"
    assert group_paragraph.runs[1].bold is not True


def test_skills_multiple_categories_each_render_as_their_own_paragraph():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading"},
                    {"id": "s1", "text": "Roadmapping", "included": True},
                    {"id": "s2", "text": "Level Design", "included": True},
                    {"id": "cat-2", "text": "Tools", "included": True, "kind": "subheading"},
                    {"id": "s3", "text": "Unity", "included": True},
                ],
            }
        ]
    )

    texts = paragraph_texts(render_templated_docx(cv, document, "classic"))

    assert "Design: Roadmapping; Level Design" in texts
    assert "Tools: Unity" in texts


def test_skills_uncategorized_entries_before_a_category_render_as_one_unbulleted_line():
    # Post-30 — a Skills/Technologies flat run (before, or entirely
    # without, a category) joins onto one "  ·  "-separated line instead
    # of one bulleted paragraph per entry — reported directly, a long
    # flat skill list read as too many separate lines. A lone member (as
    # here) still gets this treatment: no bullet character, even though
    # there's nothing else to join it with.
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "s0", "text": "Mentoring", "included": True},
                    {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading"},
                    {"id": "s1", "text": "Roadmapping", "included": True},
                ],
            }
        ]
    )

    texts = paragraph_texts(render_templated_docx(cv, document, "classic"))

    assert "Mentoring" in texts
    assert f"{DOCX_TEMPLATES['classic'].bullet_char} Mentoring" not in texts
    assert "Design: Roadmapping" in texts


def test_skills_multiple_flat_members_join_onto_one_line_in_given_order():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "s0", "text": "Mentoring", "included": True},
                    {"id": "s1", "text": "Roadmapping", "included": True},
                    {"id": "s2", "text": "System Design", "included": True},
                ],
            }
        ]
    )

    texts = paragraph_texts(render_templated_docx(cv, document, "classic"))

    assert "Mentoring · Roadmapping · System Design" in texts


def test_skills_category_with_no_members_renders_bold_label_with_no_trailing_colon():
    # Edge case: a category header with every member excluded (or none
    # ever added) still renders — just as its bold label alone, no ": "
    # suffix since there's nothing to join.
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading"},
                ],
            }
        ]
    )

    group_paragraph = next(
        p for p in paragraphs(render_templated_docx(cv, document, "classic")) if p.text == "Design"
    )

    assert group_paragraph.runs[0].bold is True
    assert len(group_paragraph.runs) == 1


def test_experience_project_subheading_renders_italic_with_no_bullet():
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
                        "bullets": [
                            {"id": "proj-1", "text": "Internal tool", "included": True, "kind": "subheading"},
                            {"id": "b1", "text": "Owned the backend", "included": True},
                        ],
                    }
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "modern")
    project_paragraph = next(p for p in paragraphs(data) if p.text == "Internal tool")
    bullet_paragraph = next(p for p in paragraphs(data) if "Owned the backend" in p.text)

    assert project_paragraph.runs[0].italic is True
    assert not project_paragraph.text.startswith(DOCX_TEMPLATES["modern"].bullet_char)
    assert bullet_paragraph.text.startswith(DOCX_TEMPLATES["modern"].bullet_char)


def test_entries_appear_in_the_given_already_reordered_order():
    cv = make_cv()
    # Entries given in a deliberately non-alphabetical / non-"original"
    # order — pins that templated DOCX walks `document` as given (already
    # reordered by the Preview tab), not any order derived from AssembledCV.
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "s2", "text": "Second entry", "included": True},
                    {"id": "s1", "text": "First entry", "included": True},
                ],
            }
        ]
    )

    texts = paragraph_texts(render_templated_docx(cv, document, "classic"))

    # Post-30 — Skills' flat members join onto one line now; the given
    # (already-reordered) order still has to survive that join.
    assert "Second entry · First entry" in texts


# ----- Phase 25: Experience entries/bullets honor explicit runs/alignment --

def test_experience_role_with_runs_overrides_the_automatic_bold_run():
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
                        "text": "stale plain text",
                        "included": True,
                        "runs": [
                            {"text": "Engineer", "bold": True},
                            {"text": " — Acme", "italic": True},
                        ],
                        "bullets": [],
                    }
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    role_paragraph = next(p for p in paragraphs(data) if p.text == "Engineer — Acme")

    assert role_paragraph.runs[0].text == "Engineer"
    assert role_paragraph.runs[0].bold is True
    assert role_paragraph.runs[0].italic is not True
    assert role_paragraph.runs[1].text == " — Acme"
    assert role_paragraph.runs[1].italic is True
    assert role_paragraph.runs[1].bold is not True


def test_experience_bullet_with_runs_keeps_its_bullet_character_prefix():
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
                            {
                                "id": "b1",
                                "text": "stale plain text",
                                "included": True,
                                "runs": [{"text": "Shipped a "}, {"text": "feature", "underline": True}],
                            }
                        ],
                    }
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "modern")
    bullet_paragraph = next(p for p in paragraphs(data) if "Shipped a feature" in p.text)

    assert bullet_paragraph.text.startswith(DOCX_TEMPLATES["modern"].bullet_char)
    text_runs = [r for r in bullet_paragraph.runs if r.text.strip()]
    assert text_runs[-2].text == "Shipped a "
    assert text_runs[-1].text == "feature"
    assert text_runs[-1].underline is True


def test_generic_section_entry_with_runs_and_alignment_renders_both():
    # Phase 31 — the generic per-section-member branch of
    # render_templated_docx (Contacts/Education/Certifications/Awards/
    # Publications/Volunteer Experience/Portfolio Links) used to render
    # `member.text` via `_add_styled_paragraph`, a bare string with no
    # runs/alignment support at all. Switched to `_add_paragraph_with_runs`
    # (already used for Experience) so a BubbleMenu-formatted Education
    # entry gets the same fidelity.
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "education",
                "title": "Education",
                "included": True,
                "entries": [
                    {
                        "id": "edu-1",
                        "text": "stale plain text",
                        "included": True,
                        "alignment": "center",
                        "runs": [{"text": "State University", "bold": True}],
                    }
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    entry_paragraph = next(p for p in paragraphs(data) if "State University" in p.text)

    from docx.enum.text import WD_ALIGN_PARAGRAPH

    assert entry_paragraph.text.startswith(DOCX_TEMPLATES["classic"].bullet_char)
    assert entry_paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER
    bold_run = next(r for r in entry_paragraph.runs if "State University" in r.text)
    assert bold_run.bold is True


def test_summary_entry_with_runs_is_honored():
    # Phase 31 fix, found during implementation: despite Phase 25's own
    # claim of "Summary + Experience" runs support in every export path,
    # render_templated_docx's Summary branch was still `.text`-only.
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "summary",
                "title": "Summary",
                "included": True,
                "entries": [
                    {
                        "id": "summary",
                        "text": "stale plain text",
                        "included": True,
                        "runs": [{"text": "Award-winning", "bold": True}, {"text": " engineer.", "bold": False}],
                    }
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    summary_paragraph = next(p for p in paragraphs(data) if "Award-winning engineer." in p.text)

    # No bullet character — Summary isn't a list (Post-30 polish, unchanged).
    assert not summary_paragraph.text.startswith(DOCX_TEMPLATES["classic"].bullet_char)
    assert summary_paragraph.runs[0].text == "Award-winning"
    assert summary_paragraph.runs[0].bold is True
    assert summary_paragraph.runs[1].text == " engineer."
    assert summary_paragraph.runs[1].bold is not True


def test_experience_bullet_link_run_becomes_a_real_hyperlink():
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
                            {
                                "id": "b1",
                                "text": "stale plain text",
                                "included": True,
                                "runs": [{"text": "See my portfolio", "link": "https://example.com/portfolio"}],
                            }
                        ],
                    }
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    doc = Document(io.BytesIO(data))
    targets = {
        rel.target_ref
        for rel in doc.part.rels.values()
        if rel.reltype == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
    }

    assert "https://example.com/portfolio" in targets


def test_experience_entry_alignment_sets_the_paragraph_alignment():
    from docx.enum.text import WD_ALIGN_PARAGRAPH

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
                        "alignment": "center",
                        "bullets": [],
                    }
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    role_paragraph = next(p for p in paragraphs(data) if p.text == "Engineer — Acme")

    assert role_paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER


def test_experience_entry_with_no_alignment_leaves_paragraph_alignment_unset():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "experience",
                "title": "Experience",
                "included": True,
                "entries": [{"id": "exp-1", "text": "Engineer — Acme", "included": True, "bullets": []}],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    role_paragraph = next(p for p in paragraphs(data) if p.text == "Engineer — Acme")

    assert role_paragraph.alignment is None


def test_unknown_template_id_falls_back_to_classic():
    cv = make_cv()
    document = PrintDocument(sections=[])

    data = render_templated_docx(cv, document, "does-not-exist")

    doc = Document(io.BytesIO(data))
    assert doc.paragraphs[0].runs[0].font.name == DOCX_TEMPLATES["classic"].heading_font


# ----- Phase 30: manual pagination control -----------------------------


def test_section_page_break_before_sets_the_heading_paragraph_flag():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "education",
                "title": "Education",
                "included": True,
                "page_break_before": True,
                "entries": [{"id": "edu-1", "text": "State University", "included": True}],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    heading = next(p for p in paragraphs(data) if p.text == "Education")

    assert heading.paragraph_format.page_break_before is True


def test_section_without_page_break_before_leaves_the_heading_flag_unset():
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

    data = render_templated_docx(cv, document, "classic")
    heading = next(p for p in paragraphs(data) if p.text == "Education")

    assert not heading.paragraph_format.page_break_before


def test_experience_entry_page_break_before_sets_the_role_header_flag_not_its_bullets():
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
                        "page_break_before": True,
                        "bullets": [{"id": "b1", "text": "Shipped a feature", "included": True}],
                    },
                    {"id": "exp-2", "text": "Designer — Acme", "included": True, "bullets": []},
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    role_paragraph = next(p for p in paragraphs(data) if p.text == "Engineer — Acme")
    bullet_paragraph = next(p for p in paragraphs(data) if "Shipped a feature" in p.text)
    other_role_paragraph = next(p for p in paragraphs(data) if p.text == "Designer — Acme")

    assert role_paragraph.paragraph_format.page_break_before is True
    assert not bullet_paragraph.paragraph_format.page_break_before
    assert not other_role_paragraph.paragraph_format.page_break_before


def test_skills_category_page_break_before_sets_the_grouped_paragraph_flag():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading", "page_break_before": True},
                    {"id": "s1", "text": "Roadmapping", "included": True},
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    group_paragraph = next(p for p in paragraphs(data) if "Roadmapping" in p.text)

    assert group_paragraph.paragraph_format.page_break_before is True


def test_skills_first_flat_members_page_break_before_sets_the_whole_joined_lines_flag():
    # Post-30 — once every flat member joins onto one paragraph, only the
    # *first* member's own `page_break_before` has anywhere left to
    # apply; it forces a break before the whole joined line.
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "s0", "text": "Mentoring", "included": True, "page_break_before": True},
                    {"id": "s1", "text": "Roadmapping", "included": True},
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    joined_paragraph = next(p for p in paragraphs(data) if p.text == "Mentoring · Roadmapping")

    assert joined_paragraph.paragraph_format.page_break_before is True


def test_skills_a_later_flat_members_page_break_before_is_silently_absorbed():
    # The mirror case: a flag on anything but the *first* member has no
    # paragraph of its own left to attach to once joined, and is silently
    # dropped rather than (wrongly) forcing a break before the section's
    # very first line.
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "s0", "text": "Mentoring", "included": True},
                    {"id": "s1", "text": "Roadmapping", "included": True, "page_break_before": True},
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    joined_paragraph = next(p for p in paragraphs(data) if p.text == "Mentoring · Roadmapping")

    assert not joined_paragraph.paragraph_format.page_break_before


# ----- Post-31: pre-rendered compact Skills/Technologies entries -----------


def test_compact_category_entry_renders_its_runs_as_a_real_bold_run_no_bullet():
    cv = make_cv()
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
                        "runs": [
                            {"text": "Design", "bold": True},
                            {"text": ": Roadmapping; UX Design", "bold": False},
                        ],
                    }
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    paragraph = next(p for p in paragraphs(data) if "Roadmapping; UX Design" in p.text)

    assert paragraph.text == "Design: Roadmapping; UX Design"
    assert not paragraph.text.startswith(DOCX_TEMPLATES["classic"].bullet_char)
    assert paragraph.runs[0].text == "Design"
    assert paragraph.runs[0].bold is True
    assert paragraph.runs[1].text == ": Roadmapping; UX Design"
    assert paragraph.runs[1].bold is not True


def test_compact_flat_entry_renders_plain_with_no_bullet():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {
                        "id": "skills-0",
                        "text": "Mentoring · Team Management",
                        "included": True,
                        "kind": "compact",
                    }
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    paragraph = next(p for p in paragraphs(data) if "Mentoring" in p.text)

    assert paragraph.text == "Mentoring · Team Management"
    assert not paragraph.text.startswith(DOCX_TEMPLATES["classic"].bullet_char)


def test_two_compact_entries_render_as_two_separate_paragraphs_not_rejoined():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "skills-0", "text": "Mentoring", "included": True, "kind": "compact"},
                    {
                        "id": "skills-1",
                        "text": "Design: Roadmapping",
                        "included": True,
                        "kind": "compact",
                        "runs": [
                            {"text": "Design", "bold": True},
                            {"text": ": Roadmapping", "bold": False},
                        ],
                    },
                ],
            }
        ]
    )

    texts = paragraph_texts(render_templated_docx(cv, document, "classic"))

    # Two distinct paragraphs, not one fused "Mentoring Design: Roadmapping" —
    # `texts` is a list, one entry per real paragraph, so each surviving
    # as its own list item already proves that.
    assert texts.count("Mentoring") == 1
    assert texts.count("Design: Roadmapping") == 1


def test_compact_entry_page_break_before_sets_just_that_paragraphs_flag():
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "skills-0", "text": "Mentoring", "included": True, "kind": "compact"},
                    {
                        "id": "skills-1",
                        "text": "Design: Roadmapping",
                        "included": True,
                        "kind": "compact",
                        "page_break_before": True,
                        "runs": [
                            {"text": "Design", "bold": True},
                            {"text": ": Roadmapping", "bold": False},
                        ],
                    },
                ],
            }
        ]
    )

    data = render_templated_docx(cv, document, "classic")
    first = next(p for p in paragraphs(data) if p.text == "Mentoring")
    second = next(p for p in paragraphs(data) if p.text == "Design: Roadmapping")

    assert not first.paragraph_format.page_break_before
    assert second.paragraph_format.page_break_before is True


def test_a_section_that_is_not_yet_fully_compact_still_uses_the_legacy_grouping_path():
    # Only reached once every included entry carries kind == "compact" —
    # a section with even one legacy-shape entry left (an old subheading
    # + member pair here) still goes through group_entries_by_subheading,
    # unaffected by this phase.
    cv = make_cv()
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "skills-0", "text": "Mentoring", "included": True, "kind": "compact"},
                    {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading"},
                    {"id": "s1", "text": "Roadmapping", "included": True},
                ],
            }
        ]
    )

    texts = paragraph_texts(render_templated_docx(cv, document, "classic"))

    # "Mentoring" still has no bullet character either way here — the
    # pre-existing Post-30 skills/technologies flat-join exception (see
    # render_templated_docx's own comment on it) already never bullets a
    # flat group in this section, single-member or not; this test is
    # only pinning that the *legacy grouping path itself* still runs
    # (group_entries_by_subheading, not the new compact short-circuit).
    assert "Mentoring" in texts
    assert "Design: Roadmapping" in texts
