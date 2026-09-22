"""Reads raw resume text from a source file.

Phase 3 scope (docs/development_plan.md): plain text and *simple* PDF-to-text
only. Version 4, Phase 4.5 (docs/development_plan.md) extends this with
DOCX and RTF, ahead of the file-upload ingestion UI those formats exist
for. Still no OCR for scanned/image PDFs. This is a thin
input-normalization step; it does no parsing of resume *structure* —
that's ResumeIngestionService's job.
"""

from __future__ import annotations

from pathlib import Path

from app.errors import ParsingError

_PLAIN_TEXT_SUFFIXES = {".txt", ".md", ""}


def read_resume_text(path: Path) -> str:
    """Read raw resume text from `path`, dispatching on file extension.

    Supported: .txt/.md/no-extension (read as-is, UTF-8), .pdf (simple text
    extraction via pypdf), .docx (paragraph text via python-docx), and .rtf
    (via striprtf).
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf(path)
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".rtf":
        return _read_rtf(path)
    if suffix in _PLAIN_TEXT_SUFFIXES:
        return path.read_text(encoding="utf-8")
    raise ParsingError(
        f"Unsupported resume file type '{suffix}'. Supported: .txt, .md, .pdf, .docx, .rtf."
    )


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader  # imported lazily, mirrors GeminiProvider's pattern
    except ImportError as exc:
        raise ParsingError(
            "PDF support requires the 'pypdf' package (listed in pyproject.toml). "
            "Install project dependencies and try again."
        ) from exc

    try:
        reader = PdfReader(str(path))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        links = _extract_pdf_links(reader)
    except Exception as exc:  # noqa: BLE001 - translate any pypdf error
        raise ParsingError(f"Could not read PDF '{path}': {exc}") from exc

    text = "\n".join(pages_text).strip()
    if not text:
        raise ParsingError(
            f"No extractable text found in '{path}'. It may be a scanned/"
            "image-only PDF — OCR is not supported yet."
        )
    text += "\n\n" + _TRUNCATION_CAVEAT
    if links:
        text += "\n\n" + _format_pdf_links_section(links)
    return text


def _extract_pdf_links(reader: PdfReader) -> list[str]:
    """Collects every unique hyperlink URI from every page's `/Annots`, in
    the order first encountered.

    `page.extract_text()` (used by `_read_pdf` above) only reads glyph
    text — it has no idea a `/Link` annotation exists at all. A hyperlink
    whose visible label is the URL itself (e.g. "behance.net/lugantseva")
    survives fine as plain text; one whose label is a plain word or an
    icon (e.g. a "LinkedIn"/"Figma" contact row, or a company name
    hyperlinked to its own website) does not — the href is invisible to
    everything downstream, and the actual URL is silently lost. Found
    live: a candidate's profile page for a PDF where "figma"/"linkedin"
    both hyperlinked to real profile/portfolio URLs came out of ingestion
    as literal bare words, with no URL anywhere in the stored Candidate.

    Deliberately doesn't try to pair each URI with *which* visible text it
    belongs to — that would need per-glyph position matching against each
    annotation's `/Rect`, which is fragile (a Figma-style export can place
    text via arbitrary content-stream transforms `/Rect` coordinates don't
    directly correspond to) and unnecessary: `_format_pdf_links_section`
    hands the raw list to the CV Parser LLM alongside the extracted text,
    and matching a bare mention ("linkedin") to the one URL in the list
    that's obviously about LinkedIn is exactly the kind of judgment call an
    LLM handles better than brittle coordinate math would.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for page in reader.pages:
        annotations = page.get("/Annots")
        if not annotations:
            continue
        for annotation_ref in annotations:
            try:
                annotation = annotation_ref.get_object()
                if annotation.get("/Subtype") != "/Link":
                    continue
                action = annotation.get("/A")
                if action is None:
                    continue
                uri = action.get_object().get("/URI")
            except Exception:  # noqa: BLE001 - one malformed annotation shouldn't lose the rest
                continue
            if uri and uri not in seen:
                seen.add(uri)
                ordered.append(uri)
    return ordered


# Some PDF exporters (a Figma "export as PDF" in particular — see
# _extract_pdf_links's docstring for the same document) subset/reassign
# glyph ids per line in a way pypdf's text extraction can silently lose —
# most often the very last character of a wrapped line vanishes with no
# replacement mark of any kind, nothing in the text itself to detect: an
# extracted "efficienc" reads as a plausible (if slightly odd) word on its
# own, not as visibly broken the way a stray symbol would. Confirmed by
# diffing this exact PDF's real text against pypdf's extraction character
# by character — punctuation like en-dashes decodes correctly; only
# trailing letters/digits go missing. Found live: a resume with this
# throughout came back from the CV Parser LLM with the truncated spelling
# copied straight into the stored Candidate profile in some spots
# ("Presen'" for "Present") and, far worse, actively fabricated in others —
# one employment period's end year was invented as "2011" from a missing
# final digit, three years *before* that same role's own start year. Since
# there is no marker to detect and conditionally warn about, this caveat is
# appended to every PDF's extracted text unconditionally — see
# 01_cv_parser_v1.md's "PDF text extraction" rule for the actual instruction
# this sets up.
_TRUNCATION_CAVEAT = (
    "Note: this text was extracted from a PDF. PDF text extraction "
    "occasionally drops the last character or two of a wrapped line "
    "silently, with no visible mark left behind — the source PDF itself is "
    "fine, only this extraction step loses it. If a word at the end of a "
    "line looks implausibly short or cut off for its context (e.g. "
    "\"efficienc\" where \"efficiency\" is obviously intended), that's "
    "almost certainly this, not a word the original resume actually used."
)


def _format_pdf_links_section(links: list[str]) -> str:
    bullets = "\n".join(f"- {link}" for link in links)
    return (
        "Hyperlinks embedded in this PDF (from its link annotations, not "
        "necessarily visible as URLs in the text above — a link's visible "
        "label is often just a plain word, a company name, or an icon, with "
        "the actual address only reachable through the PDF's own link "
        "annotation). If something above names a service, employer, or "
        "portfolio site with no visible URL and one of these is obviously "
        "its target (matching by domain, e.g. a bare \"LinkedIn\" mention "
        "and a linkedin.com URL), that hyperlink is its real value — never "
        "guess a match that isn't obvious from the domain itself:\n" + bullets
    )


def _read_docx(path: Path) -> str:
    try:
        from docx import Document  # python-docx; imported lazily, mirrors _read_pdf's pattern
    except ImportError as exc:
        raise ParsingError(
            "DOCX support requires the 'python-docx' package (listed in pyproject.toml). "
            "Install project dependencies and try again."
        ) from exc

    try:
        document = Document(str(path))
        paragraphs_text = [paragraph.text for paragraph in document.paragraphs]
    except Exception as exc:  # noqa: BLE001 - translate any python-docx error
        raise ParsingError(f"Could not read DOCX '{path}': {exc}") from exc

    text = "\n".join(paragraphs_text).strip()
    if not text:
        raise ParsingError(f"No extractable text found in '{path}'.")
    return text


def _read_rtf(path: Path) -> str:
    try:
        from striprtf.striprtf import rtf_to_text  # imported lazily, mirrors _read_pdf's pattern
    except ImportError as exc:
        raise ParsingError(
            "RTF support requires the 'striprtf' package (listed in pyproject.toml). "
            "Install project dependencies and try again."
        ) from exc

    try:
        # RTF's own byte stream is ASCII-safe outside of \'XX hex escapes —
        # RTF's mechanism for non-ASCII characters, keyed to the \ansicpg
        # codepage declared in the file's own header (e.g. \ansicpg1251 for
        # legacy Cyrillic Windows text). latin-1 is a lossless 1:1
        # byte<->codepoint mapping (unlike cp1252, which has undefined
        # bytes), so decoding the raw bytes with it here can never corrupt
        # those escapes before striprtf's own regex-based parser reads
        # them; striprtf then decodes each \'XX run using the codepage it
        # detects from \ansicpg (falling back to cp1252 only if the file
        # declares none) — independent of, and unaffected by, this outer
        # decode. Confirmed against a real \ansicpg1251 sample, not assumed.
        raw_text = path.read_bytes().decode("latin-1")
        text = rtf_to_text(raw_text).strip()
    except Exception as exc:  # noqa: BLE001 - translate any striprtf error
        raise ParsingError(f"Could not read RTF '{path}': {exc}") from exc

    if not text:
        raise ParsingError(f"No extractable text found in '{path}'.")
    return text
