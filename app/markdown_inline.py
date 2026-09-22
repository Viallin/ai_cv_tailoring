"""Parses the tiny Markdown-inline subset app/cv_markdown.py's renderers
emit — `**bold**`, `*italic*`, and `__underline__` spans, plus
`[text](url)` links, mixed inline within a line (e.g.
`"**Position** — Company (Period)"`) — into styled runs, and auto-detects
raw `http(s)://` URLs within those runs (e.g. a contact's Portfolio/LinkedIn
value, or a Project's `(url)` — see app/cv_markdown.py's render_contacts_section
and render_projects_section) so exporters can turn them into real hyperlinks.

Not a general Markdown parser: cv_markdown.py's own section renderers never
produce nested spans or `__underline__`/`[text](url)` — only
`_serialize_runs` (Phase 25, for a block with explicit `PrintDocumentBlock.
runs`) does, so this only needs to handle exactly `**`/`*`/`__` spans plus
`[text](url)`/bare URLs, still with no nesting. Shared by app/cv_docx.py
and app/cv_pdf.py so the same tokenizing logic isn't duplicated across both
export formats.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class InlineRun(NamedTuple):
    text: str
    bold: bool
    italic: bool
    underline: bool = False
    url: str | None = None


_TOKEN_RE = re.compile(
    r"\[(?P<link_text>[^\]]+)\]\((?P<link_url>\S+?)\)"
    r"|\*\*(?P<bold>.+?)\*\*"
    r"|__(?P<underline>.+?)__"
    r"|\*(?P<italic>.+?)\*"
)
_URL_RE = re.compile(r"https?://\S+")
# Trailing characters that are almost always sentence/list punctuation
# rather than part of the URL itself (e.g. "(https://x.com)", "https://x.com,"
# or "https://x.com | Phone: ...").
_URL_TRAILING_PUNCTUATION = ".,;:!?'\")]}»|"


def parse_inline_runs(line: str) -> list[InlineRun]:
    """Splits `line` into runs, applying bold to `**...**` spans, italic to
    `*...*` spans, underline to `__...__` spans, and an explicit `url` to
    `[text](url)` spans (display text taken literally, not itself scanned
    for further spans or bare URLs — see the module docstring on nesting),
    then a second pass gives any remaining `http(s)://` substring within a
    still-plain run its `url` field too (keeping that run's bold/italic/
    underline). A stray/unmatched `*`/`_`/`[` (no closing partner) is
    treated as a literal character rather than an error — edited text is
    free-form user input, not guaranteed well-formed Markdown."""
    raw_runs: list[InlineRun] = []
    pos = 0
    for match in _TOKEN_RE.finditer(line):
        if match.start() > pos:
            raw_runs.append(InlineRun(line[pos : match.start()], bold=False, italic=False))
        if match.group("link_text") is not None:
            raw_runs.append(
                InlineRun(match.group("link_text"), bold=False, italic=False, url=match.group("link_url"))
            )
        elif match.group("bold") is not None:
            raw_runs.append(InlineRun(match.group("bold"), bold=True, italic=False))
        elif match.group("underline") is not None:
            raw_runs.append(InlineRun(match.group("underline"), bold=False, italic=False, underline=True))
        else:
            raw_runs.append(InlineRun(match.group("italic"), bold=False, italic=True))
        pos = match.end()
    if pos < len(line):
        raw_runs.append(InlineRun(line[pos:], bold=False, italic=False))

    runs: list[InlineRun] = []
    for run in raw_runs:
        # A `[text](url)` span already carries its own explicit `url` —
        # don't also bare-URL-scan its display text (which is free-form
        # and not expected to itself look like a link).
        runs.extend([run] if run.url else _split_urls(run))
    return runs


def _split_urls(run: InlineRun) -> list[InlineRun]:
    matches = list(_URL_RE.finditer(run.text))
    if not matches:
        return [run]

    runs: list[InlineRun] = []
    pos = 0
    for match in matches:
        start = match.start()
        url = match.group().rstrip(_URL_TRAILING_PUNCTUATION)
        if not url:
            continue
        if start > pos:
            runs.append(run._replace(text=run.text[pos:start]))
        runs.append(run._replace(text=url, url=url))
        pos = start + len(url)
    if pos < len(run.text):
        runs.append(run._replace(text=run.text[pos:]))
    return runs if runs else [run]
