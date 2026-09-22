"""Vendors and registers Unicode-capable (Latin + Cyrillic) TTF fonts for
reportlab — Version 4, Phase 4.4/4.9 — replacing reportlab's built-in
Base-14 fonts (Helvetica etc.), whose WinAnsi encoding has zero Cyrillic
glyphs (see app/cv_pdf.py's own docstring). Used by both the plain,
ATS-safe PDF export and the templated PDF export (Phase 4.9's browser-
free replacement for the old Playwright-screenshot approach — see
app/cv_pdf.py's render_templated_pdf).

Two families:

- NotoSans: the plain/ATS-safe PDF's universal font, and the "Modern"
  PDF template's font. Full four-weight family (Regular/Bold/Italic/
  BoldItalic), all with real Cyrillic coverage — `assets/fonts/`, SIL
  Open Font License (`assets/fonts/LICENSE_NOTO_SANS.txt`), which
  explicitly permits reproduction/redistribution/embedding. Static
  instances generated locally (`fonttools varLib.instancer
  --update-name-table`, wght=400/700, wdth=100) from Google Fonts' own
  published variable font files (`NotoSans[wdth,wght].ttf`/
  `NotoSans-Italic[wdth,wght].ttf`, github.com/google/fonts) — Google
  Fonts ships Noto Sans only as a variable font, and reportlab's TTFont
  has no notion of variable-font axes/instances, so a plain, single
  static TTF per weight is what reportlab actually needs.
  `--update-name-table` is not optional: without it, instancer pins the
  weight/width axes but leaves the font's internal `name` table (its
  PostScript name, read by reportlab's own TTFontFile.extractInfo) as
  the *base* variable font's — e.g. both a wght=400 and a wght=700
  instance would carry the internal name "NotoSans-Regular". reportlab's
  `pdfmetrics.registerFont` keys its de-duplication cache
  (`_dynFaceNames`) by that internal name, not by the registered font
  name or filename — so registering both under that flag omitted
  silently makes the second registration (e.g. "NotoSans-Bold") alias
  the *first* font object outright, same glyph data and all, not merely
  a naming collision. Caught by directly inspecting `pdfmetrics.
  getFont("NotoSans-Bold").face.filename` after the first version of
  this fix (it pointed at the Regular file) rather than trusting that
  `tt2ps` resolving the name string proved the fix worked — it only
  proves the family-table wiring, not that the underlying files differ.

  Replaced an earlier DejaVu-Sans-based version of this module (still
  vendored from an ephemeral `matplotlib` install, `LICENSE_DEJAVU` was
  that family's own license) that only had Regular + Oblique available
  from that source — no true bold face, so `<b>` markup silently fell
  back to the regular weight. Confirmed via real live testing (a
  friend's exported "Modern"-template PDF showing plain, non-bold role
  headers where the on-screen preview showed them bold) rather than
  caught during this project's own testing — DejaVu Serif's four-weight
  bundle (below) never had this gap, so it went unnoticed until someone
  actually used the Sans-based paths.
- DejaVuSerif: the "Classic" PDF template's font. Full four-weight
  family (Regular/Bold/Italic/BoldItalic) is vendored (same matplotlib
  source, `LICENSE_DEJAVU`), so this one has always rendered true
  bold/italic throughout — kept as-is; nothing here needed fixing.

register_pdf_fonts() is idempotent (guards against redundant filesystem
reads across repeated calls within one process — reportlab's own
pdfmetrics.registerFont would just re-register the same font under the
same name either way, this isn't working around a reportlab bug).
"""

from __future__ import annotations

from pathlib import Path

# Relative to the current working directory, matching app/config.py's
# `prompts_dir`/`Path("prompts")` convention (NOT `Path(__file__)`-based).
_FONTS_DIR = Path("assets/fonts")

_registered = False


def register_pdf_fonts() -> None:
    global _registered
    if _registered:
        return

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont("NotoSans", str(_FONTS_DIR / "NotoSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("NotoSans-Bold", str(_FONTS_DIR / "NotoSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("NotoSans-Italic", str(_FONTS_DIR / "NotoSans-Italic.ttf")))
    pdfmetrics.registerFont(TTFont("NotoSans-BoldItalic", str(_FONTS_DIR / "NotoSans-BoldItalic.ttf")))
    pdfmetrics.registerFontFamily(
        "NotoSans",
        normal="NotoSans",
        bold="NotoSans-Bold",
        italic="NotoSans-Italic",
        boldItalic="NotoSans-BoldItalic",
    )

    pdfmetrics.registerFont(TTFont("DejaVuSerif", str(_FONTS_DIR / "DejaVuSerif.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSerif-Bold", str(_FONTS_DIR / "DejaVuSerif-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSerif-Italic", str(_FONTS_DIR / "DejaVuSerif-Italic.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSerif-BoldItalic", str(_FONTS_DIR / "DejaVuSerif-BoldItalic.ttf")))
    pdfmetrics.registerFontFamily(
        "DejaVuSerif",
        normal="DejaVuSerif",
        bold="DejaVuSerif-Bold",
        italic="DejaVuSerif-Italic",
        boldItalic="DejaVuSerif-BoldItalic",
    )

    _registered = True
