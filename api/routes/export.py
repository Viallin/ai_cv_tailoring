"""POST /export — the API equivalent of ui/main_window.py's
_on_export_clicked dispatch.

Stateless by design: the client resends the full AssembledCV plus its
current (possibly-edited) structured document — exactly what
ui/main_window.py holds client-side for its own export dispatch, just a
structured document here instead of that app's flat section-edit text —
rather than looking anything up server-side. The /jobs store is
in-memory/ephemeral (api/routes/jobs.py) and there is no persisted
CVDraft until Phase 20, so there is nothing durable to look up by job id
anyway.

The header is always computed server-side via render_header(cv) — never
trusted from the client — matching how render_docx/render_pdf already only
take `cv` (no header-string parameter) for exactly the same reason.

Phase 16c made `document` (the A4 Preview tab's structured document) the
single source of truth for every export format, plain and templated
alike — the old flat `sections: dict[str,str]` field (server-computed,
never-since-edited) is gone. `template_id` is now the only optional
switch: absent = plain/ATS-safe rendering, still via the untouched
render_pdf/render_docx, just fed by app/cv_markdown.py's
render_sections_from_document(document) instead of a stale dict; present
= the templated path (direct python-docx/reportlab styling for both DOCX
and PDF — see app/cv_pdf.py's docstring for why PDF is no longer a
second HTTP hop through a Playwright-driven browser as of Version 4,
Phase 4.9). Markdown export stays template-less either way.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, model_validator

from app.cv_docx import render_docx, render_templated_docx
from app.cv_markdown import assemble_markdown_from_sections, render_header, render_sections_from_document
from app.cv_pdf import compute_page_breaks, render_pdf, render_templated_pdf
from domain.models import AssembledCV, PrintDocument

router = APIRouter(tags=["export"])

_CONTENT_TYPES: dict[str, str] = {
    "md": "text/markdown; charset=utf-8",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


class ExportRequest(BaseModel):
    assembled_cv: AssembledCV
    document: PrintDocument
    format: Literal["md", "docx", "pdf"]
    template_id: str | None = None

    @model_validator(mode="after")
    def _validate_template_combination(self) -> "ExportRequest":
        if self.template_id is not None and self.format == "md":
            raise ValueError("template_id is not applicable to markdown export.")
        return self


@router.post("/export")
def export_cv(body: ExportRequest) -> Response:
    if body.format == "md":
        data = assemble_markdown_from_sections(
            render_header(body.assembled_cv),
            render_sections_from_document(body.document),
            language=body.assembled_cv.language,
        ).encode("utf-8")
    elif body.format == "docx":
        data = (
            render_templated_docx(body.assembled_cv, body.document, body.template_id)
            if body.template_id is not None
            else render_docx(body.assembled_cv, render_sections_from_document(body.document))
        )
    else:
        data = (
            render_templated_pdf(body.assembled_cv, body.document, body.template_id)
            if body.template_id is not None
            else render_pdf(body.assembled_cv, render_sections_from_document(body.document))
        )

    return Response(
        content=data,
        media_type=_CONTENT_TYPES[body.format],
        headers={"Content-Disposition": f'attachment; filename="cv.{body.format}"'},
    )


class PageBreaksRequest(BaseModel):
    assembled_cv: AssembledCV
    document: PrintDocument
    # Absent = plain/ATS-safe PDF, matching ExportRequest.template_id's
    # own convention — no `format` field here at all, since page breaks
    # are exclusively a PDF concept (see app/cv_pdf.py::compute_page_breaks's
    # own docstring for why DOCX/Markdown have no equivalent).
    template_id: str | None = None


class PageBreakPositionOut(BaseModel):
    kind: Literal["section", "line"]
    element_id: str
    page: int


@router.post("/export/page-breaks")
def get_page_breaks(body: PageBreaksRequest) -> list[PageBreakPositionOut]:
    """On-screen page-break-prediction fix — see
    app/cv_pdf.py::compute_page_breaks's own docstring for the full
    story. The frontend's PageBreakGuide.tsx calls this (debounced, not
    on every keystroke) instead of approximating from the live DOM."""
    return [
        PageBreakPositionOut(kind=b.kind, element_id=b.element_id, page=b.page)
        for b in compute_page_breaks(body.assembled_cv, body.document, body.template_id)
    ]
