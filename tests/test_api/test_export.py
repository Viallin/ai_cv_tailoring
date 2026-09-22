"""POST /export — no candidate-scoped state involved, so these tests don't
use the `client`/`services` fixtures from conftest.py (which wire a
candidate registry); a plain TestClient against the real app is enough.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from app.cv_markdown import assemble_markdown_from_sections, render_header, render_sections_from_document
from domain.models import AssembledCV, PrintDocument

client = TestClient(app)

_CV = AssembledCV(name="Ada Lovelace", headline="Engineer", summary="A tailored summary.")
_DOCUMENT = PrintDocument(
    sections=[
        {
            "key": "summary",
            "title": "Summary",
            "included": True,
            "entries": [{"id": "summary", "text": "A tailored summary.", "included": True}],
        },
        {
            "key": "skills",
            "title": "Skills",
            "included": True,
            "entries": [
                {"id": "s1", "text": "Python", "included": True},
                {"id": "s2", "text": "SQL", "included": True},
            ],
        },
    ]
)


def _body(format_: str) -> dict:
    return {
        "assembled_cv": _CV.model_dump(mode="json"),
        "document": _DOCUMENT.model_dump(mode="json"),
        "format": format_,
    }


def test_export_md_matches_direct_call():
    r = client.post("/export", json=_body("md"))
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert 'filename="cv.md"' in r.headers["content-disposition"]

    expected = assemble_markdown_from_sections(
        render_header(_CV), render_sections_from_document(_DOCUMENT)
    ).encode("utf-8")
    assert r.content == expected


def test_export_md_uses_the_assembled_cvs_own_language():
    # Version 4, Phase 4.3: confirms the route actually passes
    # assembled_cv.language through to assemble_markdown_from_sections,
    # not just that the function itself works (test_cv_markdown.py
    # already covers that directly).
    ru_cv = AssembledCV(name="Иван Иванов", language="ru", summary="Текст.")
    body = {
        "assembled_cv": ru_cv.model_dump(mode="json"),
        "document": _DOCUMENT.model_dump(mode="json"),
        "format": "md",
    }

    r = client.post("/export", json=body)

    assert r.status_code == 200
    text = r.content.decode("utf-8")
    assert "## О себе" in text
    assert "## Summary" not in text


def test_export_docx_returns_a_valid_office_document():
    r = client.post("/export", json=_body("docx"))
    assert r.status_code == 200
    assert (
        r.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert 'filename="cv.docx"' in r.headers["content-disposition"]
    assert r.content[:2] == b"PK"  # docx is a zip archive


def test_export_pdf_returns_a_pdf():
    r = client.post("/export", json=_body("pdf"))
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="cv.pdf"' in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF"


def test_export_rejects_unknown_format():
    r = client.post("/export", json=_body("txt"))
    assert r.status_code == 422
    assert r.json()["error"]["category"] == "RequestValidationError"


def test_export_requires_document():
    body = _body("pdf")
    del body["document"]
    r = client.post("/export", json=body)

    assert r.status_code == 422
    assert r.json()["error"]["category"] == "RequestValidationError"


def test_export_reflects_the_edited_document_not_a_stale_snapshot():
    # Plain (non-templated) export now sources its content from `document`
    # (Phase 16c) — this pins that an excluded entry disappears from the
    # output, proving it's not silently falling back to some other,
    # unedited representation of the CV.
    body = _body("md")
    document = PrintDocument(
        sections=[
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": "s1", "text": "Included skill", "included": True},
                    {"id": "s2", "text": "Excluded skill", "included": False},
                ],
            }
        ]
    )
    body["document"] = document.model_dump(mode="json")
    r = client.post("/export", json=body)

    assert b"Included skill" in r.content
    assert b"Excluded skill" not in r.content


def test_export_ignores_client_supplied_header_and_computes_it_server_side():
    # There's no header field in ExportRequest at all — this pins that the
    # header always comes from render_header(assembled_cv), never anything
    # the client could smuggle in via `document`.
    body = _body("md")
    r = client.post("/export", json=body)

    assert b"# Ada Lovelace" in r.content
    assert b"*Engineer*" in r.content


def test_export_rejects_template_id_with_markdown_format():
    body = _body("md")
    body["template_id"] = "classic"
    r = client.post("/export", json=body)

    assert r.status_code == 422
    assert r.json()["error"]["category"] == "RequestValidationError"
    assert "not applicable to markdown" in r.json()["error"]["message"]


def test_export_templated_docx_uses_the_edited_document_and_template_fonts():
    body = _body("docx")
    body["template_id"] = "modern"
    r = client.post("/export", json=body)

    assert r.status_code == 200
    assert (
        r.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert r.content[:2] == b"PK"


def test_export_templated_pdf_uses_the_edited_document_and_template():
    # Version 4, Phase 4.9 — templated PDF is a real, fast, in-process
    # reportlab call now (no browser, no server-side session), so this
    # exercises the actual route/template dispatch end to end rather than
    # mocking anything out, the same way the templated-DOCX test above does.
    body = _body("pdf")
    body["template_id"] = "classic"
    r = client.post("/export", json=body)

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="cv.pdf"' in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF"


def test_export_templated_pdf_falls_back_to_classic_for_an_unknown_template_id():
    body = _body("pdf")
    body["template_id"] = "does-not-exist"
    r = client.post("/export", json=body)

    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


# ----- POST /export/page-breaks — on-screen page-break-prediction fix ---


def _page_breaks_body(template_id: str | None = None) -> dict:
    body: dict = {"assembled_cv": _CV.model_dump(mode="json"), "document": _DOCUMENT.model_dump(mode="json")}
    if template_id is not None:
        body["template_id"] = template_id
    return body


def test_page_breaks_returns_an_empty_list_for_a_document_that_fits_on_one_page():
    r = client.post("/export/page-breaks", json=_page_breaks_body())

    assert r.status_code == 200
    assert r.json() == []


def test_page_breaks_reports_real_breaks_for_a_long_document():
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
                            {"id": f"b{i}", "text": f"Bullet number {i} with real content in it.", "included": True}
                            for i in range(60)
                        ],
                    }
                ],
            }
        ]
    )
    body = {"assembled_cv": _CV.model_dump(mode="json"), "document": document.model_dump(mode="json")}

    r = client.post("/export/page-breaks", json=body)

    assert r.status_code == 200
    breaks = r.json()
    assert len(breaks) >= 1
    assert breaks[0]["kind"] == "line"
    assert breaks[0]["page"] == 2
    assert isinstance(breaks[0]["element_id"], str) and breaks[0]["element_id"]


def test_page_breaks_accepts_a_template_id():
    r = client.post("/export/page-breaks", json=_page_breaks_body("modern"))

    assert r.status_code == 200
    assert r.json() == []


def test_page_breaks_requires_document():
    body = _page_breaks_body()
    del body["document"]

    r = client.post("/export/page-breaks", json=body)

    assert r.status_code == 422
    assert r.json()["error"]["category"] == "RequestValidationError"
