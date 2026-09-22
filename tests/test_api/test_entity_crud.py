"""Entity CRUD: Skill in depth, plus a parametrized create+remove sweep
across all 12 factory-registered entities (docs/development_plan.md's
Phase 13 plan, minimum bar #2) — proves api/routes/entity_crud.py's
generic factory is wired correctly for every registration, not just one
hand-picked example. Experience Projects (the one nested case, not run
through the factory) get their own dedicated test.
"""

from __future__ import annotations

import pytest


def _create_candidate(client) -> str:
    r = client.post("/candidates", json={"name": "Ada Lovelace"})
    assert r.status_code == 201
    return r.json()["id"]


# ----- Skill in depth -------------------------------------------------------


def test_add_skill(client):
    candidate_id = _create_candidate(client)

    r = client.post(
        f"/candidates/{candidate_id}/skills", json={"name": "Python", "category": "Language"}
    )
    assert r.status_code == 201
    assert r.json()["name"] == "Python"
    assert r.json()["category"] == "Language"
    assert r.json()["proficiency"] is None


def test_add_skill_rejects_empty_name(client):
    candidate_id = _create_candidate(client)

    r = client.post(f"/candidates/{candidate_id}/skills", json={"name": ""})
    assert r.status_code == 422


def test_add_skill_as_a_category_header(client):
    # Phase 21: a category header is a normal Skill row with
    # is_category_header=True — created/updated through the exact same
    # generic routes as any other skill, no dedicated endpoint.
    candidate_id = _create_candidate(client)

    r = client.post(
        f"/candidates/{candidate_id}/skills",
        json={"name": "Leadership", "is_category_header": True},
    )
    assert r.status_code == 201
    assert r.json()["is_category_header"] is True
    assert r.json()["category"] is None

    skill_id = r.json()["id"]
    r = client.put(f"/candidates/{candidate_id}/skills/{skill_id}", json={"name": "Management"})
    assert r.status_code == 200
    assert r.json()["name"] == "Management"
    assert r.json()["is_category_header"] is True


def test_update_skill_patches_only_provided_fields(client):
    candidate_id = _create_candidate(client)
    skill_id = client.post(f"/candidates/{candidate_id}/skills", json={"name": "Python"}).json()["id"]

    r = client.put(f"/candidates/{candidate_id}/skills/{skill_id}", json={"proficiency": "Advanced"})
    assert r.status_code == 200
    assert r.json()["proficiency"] == "Advanced"
    assert r.json()["name"] == "Python"  # untouched


def test_update_missing_skill_returns_422(client):
    # Known accepted gap (api/errors.py): entity-not-found reuses
    # app.errors.ValidationError, so it maps to 422 rather than 404.
    candidate_id = _create_candidate(client)

    r = client.put(f"/candidates/{candidate_id}/skills/missing-id", json={"proficiency": "Advanced"})
    assert r.status_code == 422


def test_remove_skill(client):
    candidate_id = _create_candidate(client)
    skill_id = client.post(f"/candidates/{candidate_id}/skills", json={"name": "Python"}).json()["id"]

    r = client.delete(f"/candidates/{candidate_id}/skills/{skill_id}")
    assert r.status_code == 204

    r = client.get(f"/candidates/{candidate_id}")
    assert r.json()["skills"] == []


# ----- Parametrized sweep across all 12 factory-registered entities -------

_ENTITY_CASES = [
    ("education", "education", {"institution": "MIT"}),
    ("skills", "skills", {"name": "Python"}),
    ("technologies", "technologies", {"name": "Unity"}),
    ("languages", "languages", {"name": "French"}),
    ("certifications", "certifications", {"name": "PMP"}),
    ("awards", "awards", {"name": "Best in Show"}),
    ("contacts", "contacts", {"label": "Email", "value": "ada@example.com"}),
    ("projects", "projects", {"name": "SuperCity"}),
    ("publications", "publications", {"title": "Scaling LiveOps"}),
    ("portfolio-links", "portfolio_links", {"url": "https://artstation.com/ada"}),
    (
        "volunteer-experience",
        "volunteer_experience",
        {"organization": "Code.org", "role": "Mentor"},
    ),
    ("experience", "experience", {"position": "Engineer", "company": "Acme"}),
]


@pytest.mark.parametrize("path_segment,list_field,create_body", _ENTITY_CASES)
def test_create_and_remove_round_trip(client, path_segment, list_field, create_body):
    candidate_id = _create_candidate(client)

    r = client.post(f"/candidates/{candidate_id}/{path_segment}", json=create_body)
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]

    r = client.get(f"/candidates/{candidate_id}")
    assert any(item["id"] == item_id for item in r.json()[list_field])

    r = client.delete(f"/candidates/{candidate_id}/{path_segment}/{item_id}")
    assert r.status_code == 204

    r = client.get(f"/candidates/{candidate_id}")
    assert all(item["id"] != item_id for item in r.json()[list_field])


# ----- Reorder — every entity above except `experience` (its own, separate
# reorder mechanism lives inside ExperienceForm.tsx's atomic role save) ----

_REORDERABLE_ENTITY_CASES = [case for case in _ENTITY_CASES if case[0] != "experience"]


@pytest.mark.parametrize("path_segment,list_field,create_body", _REORDERABLE_ENTITY_CASES)
def test_reorder_round_trip(client, path_segment, list_field, create_body):
    candidate_id = _create_candidate(client)
    first = client.post(f"/candidates/{candidate_id}/{path_segment}", json=create_body).json()["id"]
    second = client.post(f"/candidates/{candidate_id}/{path_segment}", json=create_body).json()["id"]

    r = client.post(f"/candidates/{candidate_id}/{path_segment}/reorder", json={"ordered_ids": [second, first]})
    assert r.status_code == 200, r.text
    assert [item["id"] for item in r.json()] == [second, first]

    r = client.get(f"/candidates/{candidate_id}")
    assert [item["id"] for item in r.json()[list_field]] == [second, first]


def test_experience_has_no_reorder_route(client):
    candidate_id = _create_candidate(client)

    # No POST .../experience/reorder route exists — FastAPI matches the
    # path against PUT .../experience/{item_id} (treating "reorder" as an
    # item_id) and correctly rejects the method rather than the path.
    r = client.post(f"/candidates/{candidate_id}/experience/reorder", json={"ordered_ids": []})
    assert r.status_code == 405


# ----- Evidence (Phase 15) -------------------------------------------------
# Not part of the parametrized sweep above: evidence isn't a field on the
# Candidate response (`GET /candidates/{id}`) like the other 12 entities —
# it lives in its own table, read via GET /candidates/{id}/evidence — so it
# needs its own verification step, even though create/update/delete go
# through the exact same generic factory as everything else.


def test_evidence_create_update_and_remove_round_trip(client):
    candidate_id = _create_candidate(client)

    r = client.post(f"/candidates/{candidate_id}/evidence", json={"text": "Led a team of five engineers."})
    assert r.status_code == 201, r.text
    evidence_id = r.json()["id"]

    r = client.get(f"/candidates/{candidate_id}/evidence")
    assert [e["id"] for e in r.json()] == [evidence_id]

    r = client.put(
        f"/candidates/{candidate_id}/evidence/{evidence_id}", json={"source_context": "Acme Corp"}
    )
    assert r.status_code == 200
    assert r.json()["source_context"] == "Acme Corp"

    r = client.delete(f"/candidates/{candidate_id}/evidence/{evidence_id}")
    assert r.status_code == 204

    r = client.get(f"/candidates/{candidate_id}/evidence")
    assert r.json() == []


def test_evidence_create_rejects_empty_text(client):
    candidate_id = _create_candidate(client)

    r = client.post(f"/candidates/{candidate_id}/evidence", json={"text": ""})
    assert r.status_code == 422


# ----- Skill/Technology <-> Evidence linking (Phase 15) --------------------


def test_link_skill_to_evidence_via_update(client):
    candidate_id = _create_candidate(client)
    evidence_id = client.post(
        f"/candidates/{candidate_id}/evidence", json={"text": "Led a team of five engineers."}
    ).json()["id"]
    skill_id = client.post(f"/candidates/{candidate_id}/skills", json={"name": "Leadership"}).json()["id"]

    r = client.put(f"/candidates/{candidate_id}/skills/{skill_id}", json={"evidence_ids": [evidence_id]})
    assert r.status_code == 200
    assert r.json()["evidence_ids"] == [evidence_id]


def test_link_skill_to_unknown_evidence_returns_422(client):
    candidate_id = _create_candidate(client)
    skill_id = client.post(f"/candidates/{candidate_id}/skills", json={"name": "Leadership"}).json()["id"]

    r = client.put(f"/candidates/{candidate_id}/skills/{skill_id}", json={"evidence_ids": ["bogus-id"]})
    assert r.status_code == 422
    assert r.json()["error"]["category"] == "ValidationError"


def test_removing_evidence_unlinks_it_from_referencing_skills(client):
    candidate_id = _create_candidate(client)
    evidence_id = client.post(
        f"/candidates/{candidate_id}/evidence", json={"text": "Led a team of five engineers."}
    ).json()["id"]
    skill_id = client.post(f"/candidates/{candidate_id}/skills", json={"name": "Leadership"}).json()["id"]
    client.put(f"/candidates/{candidate_id}/skills/{skill_id}", json={"evidence_ids": [evidence_id]})

    client.delete(f"/candidates/{candidate_id}/evidence/{evidence_id}")

    r = client.get(f"/candidates/{candidate_id}")
    assert r.json()["skills"][0]["evidence_ids"] == []


# ----- Experience Projects (nested, not run through the factory) ----------


def test_experience_project_crud(client):
    candidate_id = _create_candidate(client)
    experience_id = client.post(
        f"/candidates/{candidate_id}/experience",
        json={"position": "Consultant", "company": "Agency Co"},
    ).json()["id"]

    r = client.post(
        f"/candidates/{candidate_id}/experience/{experience_id}/projects",
        json={"name": "Client A Migration"},
    )
    assert r.status_code == 201
    project_id = r.json()["id"]

    r = client.get(f"/candidates/{candidate_id}")
    assert [p["id"] for p in r.json()["experience"][0]["projects"]] == [project_id]

    r = client.put(
        f"/candidates/{candidate_id}/experience/{experience_id}/projects/{project_id}",
        json={"period": "2019-2020"},
    )
    assert r.status_code == 200
    assert r.json()["period"] == "2019-2020"

    r = client.delete(
        f"/candidates/{candidate_id}/experience/{experience_id}/projects/{project_id}"
    )
    assert r.status_code == 204

    r = client.get(f"/candidates/{candidate_id}")
    assert r.json()["experience"][0]["projects"] == []
