"""CVDraft (Phase 20): create/update/remove go through
api/routes/entity_crud.py's generic factory (registered path_segment
"drafts"); list/get-one are hand-written in api/routes/cv_drafts.py.
"""

from __future__ import annotations


def _create_candidate(client) -> str:
    r = client.post("/candidates", json={"name": "Ada Lovelace"})
    assert r.status_code == 201
    return r.json()["id"]


def _draft_body() -> dict:
    return {
        "vacancy": {"title": "Engineer", "company": "Acme", "raw_text": "jd text", "requirements": []},
        "assembled_cv": {"name": "Ada Lovelace", "summary": "Tailored summary."},
        "document": {
            "sections": [
                {
                    "key": "summary",
                    "title": "Summary",
                    "included": True,
                    "entries": [{"id": "summary", "text": "Tailored summary.", "included": True}],
                }
            ]
        },
    }


def test_create_draft(client):
    candidate_id = _create_candidate(client)

    r = client.post(f"/candidates/{candidate_id}/drafts", json=_draft_body())
    assert r.status_code == 201
    body = r.json()
    assert body["candidate_id"] == candidate_id
    assert body["vacancy"]["title"] == "Engineer"
    assert body["created_at"] == body["updated_at"]


def test_get_one_draft(client):
    candidate_id = _create_candidate(client)
    draft_id = client.post(f"/candidates/{candidate_id}/drafts", json=_draft_body()).json()["id"]

    r = client.get(f"/candidates/{candidate_id}/drafts/{draft_id}")
    assert r.status_code == 200
    assert r.json()["id"] == draft_id
    assert r.json()["document"]["sections"][0]["entries"][0]["text"] == "Tailored summary."


def test_create_draft_persists_match_result_and_provenance(client):
    # Phase 20b: these used to be accepted nowhere near persistence — a
    # reopened tailored draft had no way to show which bullets were
    # AI-edited, or why. Confirmed here through the real create+get
    # routes, not just CandidateService directly.
    candidate_id = _create_candidate(client)
    body = _draft_body()
    body["match_result"] = {"matches": [], "gaps": [], "missing_keywords": ["Python"]}
    body["provenance"] = {
        "bullets": [
            {
                "evidence_id": "ev-1",
                "original_text": "Wrote code.",
                "rewritten_text": "Wrote production Python code.",
                "action": "enhance",
                "rationale": "Surfaced the Python keyword.",
                "locked": False,
            }
        ],
        "unused_evidence": [],
    }

    r = client.post(f"/candidates/{candidate_id}/drafts", json=body)
    assert r.status_code == 201
    created = r.json()
    assert created["match_result"]["missing_keywords"] == ["Python"]
    assert created["provenance"]["bullets"][0]["action"] == "enhance"

    fetched = client.get(f"/candidates/{candidate_id}/drafts/{created['id']}").json()
    assert fetched["match_result"]["missing_keywords"] == ["Python"]
    assert fetched["provenance"]["bullets"][0]["rewritten_text"] == "Wrote production Python code."


def test_create_draft_persists_timing(client):
    # Found live: api/routes/entity_crud.py's create-request schema is
    # built from CandidateService.add_cv_draft's own Python signature, not
    # from the CVDraft domain model — so `timing` being added to CVDraft/
    # CVDraftRow without also being added to add_cv_draft's signature meant
    # a real POST body's `timing` was silently dropped before ever
    # reaching that method, no error raised. Confirmed here through the
    # real create+get routes (test_add_cv_draft_persists_timing in
    # test_candidate_service.py covers the service layer directly).
    candidate_id = _create_candidate(client)
    body = _draft_body()
    body["timing"] = {
        "vacancy_analysis_seconds": 1.5,
        "matching_seconds": 2.5,
        "rewrite_planning_seconds": 3.5,
        "bullet_rewriting_seconds": 4.5,
        "quality_recheck_seconds": 5.5,
        "total_seconds": 17.5,
    }

    r = client.post(f"/candidates/{candidate_id}/drafts", json=body)
    assert r.status_code == 201
    created = r.json()
    assert created["timing"]["total_seconds"] == 17.5

    fetched = client.get(f"/candidates/{candidate_id}/drafts/{created['id']}").json()
    assert fetched["timing"]["total_seconds"] == 17.5


def test_create_draft_without_match_result_or_provenance_defaults_to_null(client):
    # The "export without tailoring" path never calls the LLM.
    candidate_id = _create_candidate(client)

    r = client.post(f"/candidates/{candidate_id}/drafts", json=_draft_body())
    assert r.status_code == 201
    assert r.json()["match_result"] is None
    assert r.json()["provenance"] is None


def test_create_draft_preserves_bullet_evidence_id_through_the_real_route(client):
    # Regression: PrintDocumentBlock had no evidence_id field at all until
    # this fix, so a document posted with it (exactly what
    # structuredDocument.ts's buildExperienceBullets sends) got it
    # silently stripped by Pydantic — no error, just gone — disabling the
    # frontend's "AI-edited bullet" Sparkles marker from the very first
    # draft save. Confirmed here through the real create+get routes, not
    # just the domain model directly.
    candidate_id = _create_candidate(client)
    body = _draft_body()
    body["document"] = {
        "sections": [
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
                            {"id": "b1", "text": "Shipped a feature", "included": True, "evidence_id": "ev-1"},
                        ],
                    }
                ],
            }
        ]
    }

    r = client.post(f"/candidates/{candidate_id}/drafts", json=body)
    assert r.status_code == 201
    created_bullet = r.json()["document"]["sections"][0]["entries"][0]["bullets"][0]
    assert created_bullet["evidence_id"] == "ev-1"

    fetched = client.get(f"/candidates/{candidate_id}/drafts/{r.json()['id']}").json()
    fetched_bullet = fetched["document"]["sections"][0]["entries"][0]["bullets"][0]
    assert fetched_bullet["evidence_id"] == "ev-1"


def test_get_missing_draft_returns_404(client):
    candidate_id = _create_candidate(client)

    r = client.get(f"/candidates/{candidate_id}/drafts/missing-id")
    assert r.status_code == 404


def test_list_drafts_returns_summaries(client):
    candidate_id = _create_candidate(client)
    client.post(f"/candidates/{candidate_id}/drafts", json=_draft_body())

    r = client.get(f"/candidates/{candidate_id}/drafts")
    assert r.status_code == 200
    [summary] = r.json()
    assert summary["vacancy_title"] == "Engineer"
    assert summary["vacancy_company"] == "Acme"
    # Summary shape only -- no full vacancy/assembled_cv/document blobs.
    assert "document" not in summary
    assert "assembled_cv" not in summary


def test_update_draft_document_only(client):
    candidate_id = _create_candidate(client)
    draft_id = client.post(f"/candidates/{candidate_id}/drafts", json=_draft_body()).json()["id"]

    edited_document = {
        "sections": [
            {
                "key": "summary",
                "title": "Summary",
                "included": True,
                "entries": [{"id": "summary", "text": "A further-edited summary.", "included": True}],
            }
        ]
    }
    r = client.put(f"/candidates/{candidate_id}/drafts/{draft_id}", json={"document": edited_document})
    assert r.status_code == 200
    assert r.json()["document"]["sections"][0]["entries"][0]["text"] == "A further-edited summary."
    assert r.json()["vacancy"]["title"] == "Engineer"  # untouched


def test_remove_draft(client):
    candidate_id = _create_candidate(client)
    draft_id = client.post(f"/candidates/{candidate_id}/drafts", json=_draft_body()).json()["id"]

    r = client.delete(f"/candidates/{candidate_id}/drafts/{draft_id}")
    assert r.status_code == 204

    r = client.get(f"/candidates/{candidate_id}/drafts/{draft_id}")
    assert r.status_code == 404


def test_drafts_are_scoped_to_their_own_candidate(client):
    candidate_a = _create_candidate(client)
    r = client.post("/candidates", json={"name": "Bea"})
    candidate_b = r.json()["id"]
    draft_id = client.post(f"/candidates/{candidate_a}/drafts", json=_draft_body()).json()["id"]

    r = client.get(f"/candidates/{candidate_b}/drafts/{draft_id}")
    assert r.status_code == 404
    assert client.get(f"/candidates/{candidate_b}/drafts").json() == []
