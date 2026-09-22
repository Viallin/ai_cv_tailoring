"""POST /candidates/{candidate_id}/writeback/{preview,apply} — Phase 19's
web-app entry point into app/graph_writeback.py, adapted to the A4 editor's
structured PrintDocument via build_proposals_from_document().
"""

from __future__ import annotations


def _create_candidate_with_experience_and_skill(client) -> str:
    r = client.post("/candidates", json={"name": "Ada Lovelace"})
    candidate_id = r.json()["id"]

    candidate = {
        "name": "Ada Lovelace",
        "skills": [{"id": "skill-1", "name": "Python"}],
        "experience": [
            {
                "id": "exp-1",
                "company": "Acme",
                "position": "Engineer",
                "period": "2020-2023",
                "achievements": ["Did a thing"],
            }
        ],
    }
    r = client.put(f"/candidates/{candidate_id}", json={"candidate": candidate})
    assert r.status_code == 200
    return candidate_id


def _assembled_cv(summary: str = "A tailored summary.") -> dict:
    return {
        "name": "Ada Lovelace",
        "summary": summary,
        "experience": [
            {
                "experience_id": "exp-1",
                "company": "Acme",
                "position": "Engineer",
                "period": "2020-2023",
                "bullets": [{"text": "Did a thing"}],
                "is_gap": False,
            }
        ],
    }


def _document(summary_text: str, skill_names: list[str], bullet_text: str) -> dict:
    return {
        "sections": [
            {
                "key": "summary",
                "title": "Summary",
                "included": True,
                "entries": [{"id": "summary", "text": summary_text, "included": True}],
            },
            {
                "key": "skills",
                "title": "Skills",
                "included": True,
                "entries": [
                    {"id": f"s{i}", "text": name, "included": True}
                    for i, name in enumerate(skill_names)
                ],
            },
            {
                "key": "experience",
                "title": "Experience",
                "included": True,
                "entries": [
                    {
                        "id": "exp-1",
                        "text": "Engineer — Acme (2020-2023)",
                        "included": True,
                        "bullets": [{"id": "exp-1-bullet-0", "text": bullet_text, "included": True}],
                    }
                ],
            },
        ]
    }


def test_preview_lists_one_proposal_per_new_skill_and_edited_role(client):
    candidate_id = _create_candidate_with_experience_and_skill(client)
    body = {
        "assembled_cv": _assembled_cv(),
        "document": _document(
            summary_text="A fresh tailored summary.",
            skill_names=["Python", "Go"],
            bullet_text="Did a bigger thing",
        ),
    }

    r = client.post(f"/candidates/{candidate_id}/writeback/preview", json=body)
    assert r.status_code == 200
    proposals = r.json()

    labels = [p["label"] for p in proposals]
    assert "Update candidate summary" in labels
    assert "Add skill: Go" in labels
    assert any(label.startswith("Engineer") for label in labels)
    assert all(p["enabled"] for p in proposals)
    # Python was already on the profile — additive-only, no proposal for it.
    assert sum(1 for label in labels if label.startswith("Add skill:")) == 1


def test_preview_omits_experience_proposal_when_nothing_changed(client):
    candidate_id = _create_candidate_with_experience_and_skill(client)
    body = {
        "assembled_cv": _assembled_cv(),
        "document": _document(
            summary_text="unchanged",
            skill_names=["Python"],
            bullet_text="Did a thing",  # identical to the stored achievement
        ),
    }

    r = client.post(f"/candidates/{candidate_id}/writeback/preview", json=body)
    labels = [p["label"] for p in r.json()]
    assert not any(label.startswith("Engineer") for label in labels)
    assert not any(label.startswith("Add skill:") for label in labels)
    assert labels == ["Update candidate summary"]


def test_apply_only_writes_back_selected_proposals(client):
    candidate_id = _create_candidate_with_experience_and_skill(client)
    body = {
        "assembled_cv": _assembled_cv(),
        "document": _document(
            summary_text="A fresh tailored summary.",
            skill_names=["Python", "Go"],
            bullet_text="Did a bigger thing",
        ),
    }

    preview = client.post(f"/candidates/{candidate_id}/writeback/preview", json=body).json()
    skill_key = next(p["key"] for p in preview if p["label"] == "Add skill: Go")

    r = client.post(
        f"/candidates/{candidate_id}/writeback/apply",
        json={**body, "selected_keys": [skill_key]},
    )
    assert r.status_code == 200
    assert r.json()["applied_keys"] == [skill_key]

    candidate = client.get(f"/candidates/{candidate_id}").json()
    assert {s["name"] for s in candidate["skills"]} == {"Python", "Go"}
    # Not selected — summary and the role's achievements stay untouched.
    assert candidate["summary"] is None
    assert candidate["experience"][0]["achievements"] == ["Did a thing"]


def test_apply_reports_a_disabled_proposal_as_not_applied_even_if_selected(client):
    candidate_id = _create_candidate_with_experience_and_skill(client)
    # A whole extra role block with no matching Candidate entry produces the
    # block-count-mismatch disabled proposal (app/graph_writeback.py).
    document = _document(
        summary_text="unchanged", skill_names=["Python"], bullet_text="Did a thing"
    )
    document["sections"][2]["entries"].append(
        {
            "id": "exp-2",
            "text": "Extra Role — Someone (2019-2020)",
            "included": True,
            "bullets": [{"id": "exp-2-bullet-0", "text": "Extra bullet", "included": True}],
        }
    )
    body = {"assembled_cv": _assembled_cv(), "document": document}

    preview = client.post(f"/candidates/{candidate_id}/writeback/preview", json=body).json()
    mismatch = next(p for p in preview if not p["enabled"])

    r = client.post(
        f"/candidates/{candidate_id}/writeback/apply",
        json={**body, "selected_keys": [mismatch["key"]]},
    )
    assert r.json()["applied_keys"] == []
