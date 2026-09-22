"""Profile CRUD round-trip through the real API + a real (tmp) SQLite DB —
docs/development_plan.md's Phase 13 plan, minimum bar #1.
"""

from __future__ import annotations


def test_create_then_get_candidate(client):
    r = client.post("/candidates", json={"name": "Ada Lovelace", "headline": "Engineer"})
    assert r.status_code == 201
    candidate_id = r.json()["id"]
    assert r.json()["candidate"]["name"] == "Ada Lovelace"

    r = client.get(f"/candidates/{candidate_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Ada Lovelace"


def test_create_defaults_language_to_en(client):
    r = client.post("/candidates", json={"name": "Ada Lovelace"})
    assert r.json()["candidate"]["language"] == "en"


def test_create_accepts_an_explicit_language(client):
    r = client.post("/candidates", json={"name": "Ada Lovelace", "language": "ru"})
    assert r.json()["candidate"]["language"] == "ru"

    candidate_id = r.json()["id"]
    r = client.get(f"/candidates/{candidate_id}")
    assert r.json()["language"] == "ru"


def test_get_missing_candidate_returns_404(client):
    r = client.get("/candidates/does-not-exist")
    assert r.status_code == 404


def test_list_candidates_reflects_created_profiles(client):
    client.post("/candidates", json={"name": "Ada Lovelace"})
    client.post("/candidates", json={"name": "Charles Babbage"})

    r = client.get("/candidates")
    assert r.status_code == 200
    assert {p["name"] for p in r.json()} == {"Ada Lovelace", "Charles Babbage"}


def test_list_candidates_includes_headline_and_language(client):
    client.post("/candidates", json={"name": "Ada Lovelace", "headline": "Engineer", "language": "en"})

    r = client.get("/candidates")
    assert r.status_code == 200
    body = next(p for p in r.json() if p["name"] == "Ada Lovelace")
    assert body["headline"] == "Engineer"
    assert body["language"] == "en"


def test_patch_updates_only_provided_fields(client):
    candidate_id = client.post(
        "/candidates", json={"name": "Ada Lovelace", "headline": "Engineer"}
    ).json()["id"]

    r = client.patch(f"/candidates/{candidate_id}", json={"summary": "A summary."})
    assert r.status_code == 200
    assert r.json()["summary"] == "A summary."
    assert r.json()["headline"] == "Engineer"  # untouched


def test_patch_rejects_blanking_out_name(client):
    candidate_id = client.post("/candidates", json={"name": "Ada Lovelace"}).json()["id"]

    r = client.patch(f"/candidates/{candidate_id}", json={"name": ""})
    assert r.status_code == 422


def test_put_replaces_the_whole_profile(client):
    candidate_id = client.post("/candidates", json={"name": "Ada Lovelace"}).json()["id"]

    new_candidate = {
        "name": "Ada Lovelace",
        "headline": "Analytical Engineer",
        "experience": [
            {"id": "exp-1", "position": "Lead", "company": "Analytical Engines Ltd"}
        ],
    }
    r = client.put(f"/candidates/{candidate_id}", json={"candidate": new_candidate})
    assert r.status_code == 200
    assert r.json()["headline"] == "Analytical Engineer"
    assert [e["company"] for e in r.json()["experience"]] == ["Analytical Engines Ltd"]


def test_put_with_evidence_persists_it(client):
    candidate_id = client.post("/candidates", json={"name": "Ada Lovelace"}).json()["id"]

    body = {
        "candidate": {"name": "Ada Lovelace"},
        "evidence": [{"id": "ev-1", "text": "Led a team of five designers."}],
    }
    r = client.put(f"/candidates/{candidate_id}", json=body)
    assert r.status_code == 200

    r = client.get(f"/candidates/{candidate_id}/evidence")
    assert r.status_code == 200
    assert r.json() == [
        {
            "id": "ev-1",
            "text": "Led a team of five designers.",
            "source_context": None,
            "experience_id": None,
            "experience_project_id": None,
            "locked": False,
            "locked_text": None,
        }
    ]


def test_delete_removes_the_profile(client):
    candidate_id = client.post("/candidates", json={"name": "Ada Lovelace"}).json()["id"]

    r = client.delete(f"/candidates/{candidate_id}")
    assert r.status_code == 204

    r = client.get(f"/candidates/{candidate_id}")
    assert r.status_code == 404


def test_delete_missing_candidate_returns_404(client):
    r = client.delete("/candidates/does-not-exist")
    assert r.status_code == 404


def test_export_untailored_assembles_the_full_cv_with_no_llm_call(client):
    # CV export screen's "export without tailoring" path — synchronous,
    # no job, no provider call at all.
    candidate_id = client.post("/candidates", json={"name": "Ada Lovelace"}).json()["id"]
    candidate_body = {
        "name": "Ada Lovelace",
        "summary": "Experienced engineer.",
        "experience": [
            {
                "id": "exp-1",
                "company": "Acme",
                "position": "Engineer",
                "responsibilities": ["Did a thing"],
                "achievements": ["Shipped a thing"],
            },
            {"id": "exp-2", "position": "Career Break", "is_gap": True},
        ],
        "skills": [{"id": "skill-1", "name": "Python"}],
    }
    r = client.put(f"/candidates/{candidate_id}", json={"candidate": candidate_body})
    assert r.status_code == 200

    r = client.post(f"/candidates/{candidate_id}/export-untailored")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"] == "Experienced engineer."
    assert [e["experience_id"] for e in body["experience"]] == ["exp-1", "exp-2"]
    non_gap = next(e for e in body["experience"] if e["experience_id"] == "exp-1")
    assert [b["text"] for b in non_gap["bullets"]] == ["Did a thing", "Shipped a thing"]
    gap = next(e for e in body["experience"] if e["experience_id"] == "exp-2")
    assert gap["is_gap"] is True
    assert [s["name"] for s in body["skills"]] == ["Python"]


def test_export_untailored_returns_404_for_a_missing_candidate(client):
    r = client.post("/candidates/does-not-exist/export-untailored")
    assert r.status_code == 404
