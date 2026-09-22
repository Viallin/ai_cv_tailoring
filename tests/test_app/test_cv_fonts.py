"""Tests app/cv_fonts.py's font registration directly — app/cv_pdf.py's
own tests already prove the *effect* (Cyrillic text is extractable); this
pins the registration mechanism itself: idempotency, and that reportlab
actually resolves each registered family to a real, distinct font.
"""

from app.cv_fonts import register_pdf_fonts


def test_register_pdf_fonts_is_idempotent():
    # Calling it twice must not raise (a naive re-registration could
    # error, or at minimum re-read the font files from disk pointlessly).
    register_pdf_fonts()
    register_pdf_fonts()


def test_registers_noto_sans_and_dejavu_serif_as_distinct_fonts():
    from reportlab.pdfbase import pdfmetrics

    register_pdf_fonts()

    sans = pdfmetrics.getFont("NotoSans")
    serif = pdfmetrics.getFont("DejaVuSerif")

    assert sans.fontName == "NotoSans"
    assert serif.fontName == "DejaVuSerif"
    assert sans is not serif


def test_registers_a_real_bold_face_for_both_sans_and_serif():
    # See app/cv_fonts.py's own docstring: unlike the DejaVu-Sans-based
    # version of this module (no true bold face — matplotlib's bundle
    # doesn't ship DejaVu Sans Bold), Noto Sans is vendored here with a
    # genuine, distinct bold static instance, same as DejaVu Serif always
    # had. tt2ps is exactly what reportlab's Paragraph markup parser
    # calls when it hits a <b>/<i> tag inside a paragraph whose base font
    # is a registered family, so this pins the actual resolution it
    # performs, not just that registerFontFamily() was called with some
    # arguments.
    register_pdf_fonts()
    from reportlab.lib.fonts import ps2tt, tt2ps

    sans_bold_ps = tt2ps("NotoSans", 1, 0)
    serif_bold_ps = tt2ps("DejaVuSerif", 1, 0)

    assert sans_bold_ps == "NotoSans-Bold"  # a distinct bold face, not a silent fallback
    assert serif_bold_ps == "DejaVuSerif-Bold"

    # ps2tt is the inverse lookup — confirms the family mapping resolves
    # both directions, not just tt2ps's. Family name comes back
    # lowercased (reportlab's own normalization), not a bug here.
    assert ps2tt(sans_bold_ps) == ("notosans", 1, 0)
    assert ps2tt(serif_bold_ps) == ("dejavuserif", 1, 0)
