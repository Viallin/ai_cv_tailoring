"""Template table for the templated DOCX export (Phase 16b).

A deliberately separate, parallel implementation from
frontend/src/lib/cvTemplates.ts's CSS-variable table — python-docx has no
CSS-variable concept, so there's nothing to literally share between the
two beyond matching ids ("classic"/"modern") for traceability. Each
table expresses the same visual intent through whatever mechanism its
own rendering technology actually offers.

Font-name caveat (mirrors app/cv_pdf.py's own documented Helvetica-only
limitation): "Geist" is a self-hosted webfont, not something a
recipient's installed Word necessarily has. python-docx only writes the
font *name* into the document XML — Word silently substitutes a fallback
if it's missing. Named consistently with cvTemplates.ts anyway (rather
than picking an unrelated "Word-safe" font) so a templated DOCX at least
visually intends to match its PDF/on-screen counterpart.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class DocxTemplate:
    id: str
    heading_font: str
    body_font: str
    bullet_char: str
    section_spacing_pt: float


DOCX_TEMPLATES: dict[str, DocxTemplate] = {
    "classic": DocxTemplate(
        id="classic",
        heading_font="Georgia",
        body_font="Georgia",
        bullet_char="–",  # en dash, matches cvTemplates.ts's classic bullet marker
        section_spacing_pt=18.0,
    ),
    "modern": DocxTemplate(
        id="modern",
        heading_font="Geist",
        body_font="Geist",
        bullet_char="•",  # bullet, matches cvTemplates.ts's modern bullet marker
        section_spacing_pt=12.0,
    ),
}

# Version 4, Phase 4.4 — Georgia's and Geist's Cyrillic coverage is
# inconsistent-to-absent (Geist Variable's public charset is Latin-
# focused; Georgia's Cyrillic support varies by OS/font version) and
# python-docx has no way to detect that from Python — it only ever writes
# a font *name* into the document XML, and Word silently substitutes
# whatever it likes when the named font can't render a character, with no
# error surfaced anywhere. Rather than gamble on that substitution,
# resolve_docx_template swaps both fonts to Calibri for any non-English
# profile — ships with every modern Word install, full Cyrillic coverage,
# no silent-substitution risk. A deliberate, documented trade-off: this
# costs each template's own visual distinctiveness for Cyrillic content,
# same reasoning app/cv_pdf.py's DejaVu Sans/Serif substitution accepted
# for reliability over per-template distinctiveness under the same
# constraint (reportlab has the opposite problem — no fallback at all — but
# the same "don't gamble on an uncertain font's glyph coverage" root cause).
def resolve_docx_template(template_id: str, language: str) -> DocxTemplate:
    template = DOCX_TEMPLATES.get(template_id, DOCX_TEMPLATES["classic"])
    if language == "en":
        return template
    return dataclasses.replace(template, heading_font="Calibri", body_font="Calibri")
