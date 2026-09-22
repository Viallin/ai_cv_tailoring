from app.cv_templates import DOCX_TEMPLATES, resolve_docx_template


def test_english_returns_the_template_unchanged():
    resolved = resolve_docx_template("modern", "en")

    assert resolved == DOCX_TEMPLATES["modern"]


def test_non_english_substitutes_calibri_for_both_fonts():
    resolved = resolve_docx_template("classic", "ru")

    assert resolved.heading_font == "Calibri"
    assert resolved.body_font == "Calibri"


def test_non_english_substitution_preserves_bullet_char_and_spacing():
    original = DOCX_TEMPLATES["modern"]

    resolved = resolve_docx_template("modern", "ru")

    assert resolved.bullet_char == original.bullet_char
    assert resolved.section_spacing_pt == original.section_spacing_pt
    assert resolved.id == original.id


def test_unknown_template_id_falls_back_to_classic():
    resolved = resolve_docx_template("does-not-exist", "en")

    assert resolved == DOCX_TEMPLATES["classic"]


def test_unknown_template_id_still_gets_calibri_substitution_for_non_english():
    resolved = resolve_docx_template("does-not-exist", "ru")

    assert resolved.heading_font == "Calibri"
    assert resolved.bullet_char == DOCX_TEMPLATES["classic"].bullet_char
