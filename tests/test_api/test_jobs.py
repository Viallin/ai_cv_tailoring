"""Mocked ingest job and mocked generate job, polled to completion via
GET /jobs/{id} — docs/development_plan.md's Phase 13 plan, minimum bar #3:
proves the async run_in_executor job pattern (api/routes/jobs.py) works
end to end, including the executor thread genuinely running independent
of the request/response cycle even under TestClient.
"""

from __future__ import annotations

import time

from contracts.schemas import (
    AnalyzeVacancyResponse,
    IngestResumeResponse,
    MatchResponse,
    QualityRecheckResponse,
    RelinkSkillEvidenceResponse,
    RewriteBulletsResponse,
    RewritePlanResponse,
    SkillEvidenceLink,
)
from domain.models import (
    Candidate,
    CVProjection,
    Evidence,
    Experience,
    MatchResult,
    Requirement,
    RequirementMatch,
    RewriteAction,
    RewritePlan,
    TailoredBullet,
    TailoredExperience,
)


def _poll_until_done(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/jobs/{job_id}")
        if r.json()["status"] in ("succeeded", "failed"):
            return r
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def test_ingest_job_succeeds_and_persists_the_candidate(client, provider):
    candidate = Candidate(
        name="Ada Lovelace",
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
    )
    evidence = [Evidence(id="ev-1", text="Did a thing", experience_id="exp-1")]
    provider.queue(IngestResumeResponse(candidate=candidate, evidence=evidence))

    r = client.post("/jobs", json={"type": "ingest", "resume_text": "Ada Lovelace's resume"})
    assert r.status_code == 202
    job_id = r.json()["id"]
    assert r.json()["status"] in ("pending", "running")

    r = _poll_until_done(client, job_id)
    body = r.json()
    assert body["status"] == "succeeded", body
    assert body["result"]["candidate"]["name"] == "Ada Lovelace"

    candidate_id = body["result"]["candidate_id"]
    r2 = client.get(f"/candidates/{candidate_id}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Ada Lovelace"


def test_generate_job_succeeds(client, provider):
    candidate_id = client.post("/candidates", json={"name": "Ada Lovelace"}).json()["id"]
    candidate_body = {
        "name": "Ada Lovelace",
        "experience": [{"id": "exp-1", "position": "Engineer", "company": "Acme"}],
        "skills": [{"id": "skill-1", "name": "Python"}],
    }
    evidence_body = [{"id": "ev-1", "text": "Did a thing", "experience_id": "exp-1"}]
    r = client.put(
        f"/candidates/{candidate_id}", json={"candidate": candidate_body, "evidence": evidence_body}
    )
    assert r.status_code == 200

    vacancy_response = AnalyzeVacancyResponse(
        title="Senior Engineer",
        company="Globex",
        requirements=[Requirement(text="Python")],
        keywords=["python"],
    )
    match_result = MatchResult(
        matches=[RequirementMatch(requirement_text="Python", evidence_ids=["ev-1"], strength="high")]
    )
    plan = RewritePlan(
        actions=[RewriteAction(evidence_id="ev-1", action="keep", reason="Strong as-is.")],
        priority_order=["ev-1"],
    )
    rewrite_response = RewriteBulletsResponse(
        cv=CVProjection(
            summary="Tailored summary.",
            experience=[
                TailoredExperience(
                    experience_id="exp-1",
                    bullets=[TailoredBullet(text="Did a thing", evidence_id="ev-1")],
                )
            ],
            skills=["Python"],
        )
    )
    for response in (
        vacancy_response,
        MatchResponse(match_result=match_result),
        RewritePlanResponse(plan=plan),
        rewrite_response,
        QualityRecheckResponse(cv=rewrite_response.cv),
    ):
        provider.queue(response)

    r = client.post(
        "/jobs",
        json={
            "type": "generate",
            "candidate_id": candidate_id,
            "vacancy_text": "Senior Engineer at Globex, needs Python",
        },
    )
    assert r.status_code == 202
    job_id = r.json()["id"]

    r = _poll_until_done(client, job_id)
    body = r.json()
    assert body["status"] == "succeeded", body
    assert body["result"]["assembled_cv"]["summary"] == "Tailored summary."
    assert body["result"]["match_result"]["matches"][0]["requirement_text"] == "Python"
    # Phase 16c: GenerateJobResult no longer pre-renders per-section text —
    # the frontend derives its own structured document client-side (see
    # frontend/src/lib/structuredDocument.ts) from assembled_cv directly.
    assert "sections" not in body["result"]
    assert body["result"]["assembled_cv"]["experience"][0]["bullets"][0]["text"] == "Did a thing"
    # Phase 17: bullet provenance is exposed alongside match_result/assembled_cv.
    provenance_bullet = body["result"]["provenance"]["bullets"][0]
    assert provenance_bullet["evidence_id"] == "ev-1"
    assert provenance_bullet["original_text"] == "Did a thing"
    assert provenance_bullet["action"] == "keep"
    assert body["result"]["provenance"]["unused_evidence"] == []
    # Progress reporting: the job record's own stage fields land on the
    # sixth (final) stage by the time it's done — see app/pipeline.py's
    # GENERATION_STAGES and _report_stage's own docstring.
    assert body["stage"] == "Assembling your CV"
    assert body["stage_number"] == 6
    assert body["stage_count"] == 6
    assert "timing" in body["result"] and body["result"]["timing"]["total_seconds"] >= 0


def test_generate_job_fails_for_missing_candidate(client):
    r = client.post(
        "/jobs",
        json={"type": "generate", "candidate_id": "does-not-exist", "vacancy_text": "JD text"},
    )
    job_id = r.json()["id"]

    r = _poll_until_done(client, job_id)
    body = r.json()
    assert body["status"] == "failed"
    assert body["error"]["category"] == "ValidationError"


def test_get_missing_job_returns_404(client):
    r = client.get("/jobs/does-not-exist")
    assert r.status_code == 404


def test_recheck_job_succeeds_and_excludes_the_given_evidence_ids(client, provider):
    candidate_id = client.post("/candidates", json={"name": "Ada Lovelace"}).json()["id"]
    candidate_body = {"name": "Ada Lovelace", "experience": [{"id": "exp-1", "position": "Engineer"}]}
    evidence_body = [
        {"id": "ev-1", "text": "Did a thing", "experience_id": "exp-1"},
        {"id": "ev-2", "text": "Did another thing", "experience_id": "exp-1"},
    ]
    r = client.put(
        f"/candidates/{candidate_id}", json={"candidate": candidate_body, "evidence": evidence_body}
    )
    assert r.status_code == 200

    match_result = MatchResult(missing_keywords=["AWS"])
    provider.queue(MatchResponse(match_result=match_result))

    r = client.post(
        "/jobs",
        json={
            "type": "recheck",
            "candidate_id": candidate_id,
            "requirements": [{"text": "AWS certification"}],
            "excluded_evidence_ids": ["ev-2"],
        },
    )
    assert r.status_code == 202
    job_id = r.json()["id"]

    r = _poll_until_done(client, job_id)
    body = r.json()
    assert body["status"] == "succeeded", body
    assert body["result"]["match_result"]["missing_keywords"] == ["AWS"]
    # Only the one API call for the Matching stage — no analyze/plan/rewrite.
    assert provider.calls == [MatchResponse]


def test_recheck_job_uses_edited_bullet_text_and_document_skills(client, provider):
    candidate_id = client.post("/candidates", json={"name": "Ada Lovelace"}).json()["id"]
    candidate_body = {"name": "Ada Lovelace", "experience": [{"id": "exp-1", "position": "Engineer"}]}
    evidence_body = [{"id": "ev-1", "text": "Did a thing", "experience_id": "exp-1"}]
    r = client.put(
        f"/candidates/{candidate_id}", json={"candidate": candidate_body, "evidence": evidence_body}
    )
    assert r.status_code == 200

    provider.queue(MatchResponse(match_result=MatchResult()))

    r = client.post(
        "/jobs",
        json={
            "type": "recheck",
            "candidate_id": candidate_id,
            "requirements": [{"text": "AI tools"}],
            "edited_bullet_text": {"ev-1": "Did a thing, using AI tools daily"},
            "manual_bullet_text": ["Explored a new AI-assisted workflow"],
            "document_skills": ["Python", "AI Tools"],
            "document_technologies": [],
        },
    )
    assert r.status_code == 202
    job_id = r.json()["id"]

    r = _poll_until_done(client, job_id)
    assert r.json()["status"] == "succeeded", r.json()
    prompt = provider.last_prompt
    assert "Did a thing, using AI tools daily" in prompt
    assert "Explored a new AI-assisted workflow" in prompt
    assert '"Python"' in prompt
    assert '"AI Tools"' in prompt


def test_recheck_job_fails_for_missing_candidate(client):
    r = client.post(
        "/jobs",
        json={"type": "recheck", "candidate_id": "does-not-exist", "requirements": []},
    )
    job_id = r.json()["id"]

    r = _poll_until_done(client, job_id)
    body = r.json()
    assert body["status"] == "failed"
    assert body["error"]["category"] == "ValidationError"


def test_relink_skill_evidence_job_succeeds_and_persists_the_links(client, provider):
    candidate_id = client.post("/candidates", json={"name": "Ada Lovelace"}).json()["id"]
    candidate_body = {
        "name": "Ada Lovelace",
        "skills": [{"id": "skill-1", "name": "Python"}],
        "technologies": [{"id": "tech-1", "name": "Django"}],
    }
    evidence_body = [{"id": "ev-1", "text": "Built a Python service using Django"}]
    r = client.put(
        f"/candidates/{candidate_id}", json={"candidate": candidate_body, "evidence": evidence_body}
    )
    assert r.status_code == 200

    provider.queue(
        RelinkSkillEvidenceResponse(
            skills=[SkillEvidenceLink(id="skill-1", evidence_ids=["ev-1"])],
            technologies=[SkillEvidenceLink(id="tech-1", evidence_ids=["ev-1"])],
        )
    )

    r = client.post("/jobs", json={"type": "relink_skill_evidence", "candidate_id": candidate_id})
    assert r.status_code == 202
    job_id = r.json()["id"]

    r = _poll_until_done(client, job_id)
    body = r.json()
    assert body["status"] == "succeeded", body
    assert body["result"] == {"updated_skill_count": 1, "updated_technology_count": 1}
    # Only the one API call for the linking pass.
    assert provider.calls == [RelinkSkillEvidenceResponse]

    r2 = client.get(f"/candidates/{candidate_id}")
    assert r2.json()["skills"][0]["evidence_ids"] == ["ev-1"]
    assert r2.json()["technologies"][0]["evidence_ids"] == ["ev-1"]


def test_relink_skill_evidence_job_fails_for_missing_candidate(client):
    r = client.post(
        "/jobs", json={"type": "relink_skill_evidence", "candidate_id": "does-not-exist"}
    )
    job_id = r.json()["id"]

    r = _poll_until_done(client, job_id)
    body = r.json()
    assert body["status"] == "failed"
    assert body["error"]["category"] == "ValidationError"


def test_post_job_rejects_unknown_type(client):
    r = client.post("/jobs", json={"type": "bogus"})
    assert r.status_code == 422


# Version 4, Phase 4.5: multipart-upload counterpart to the "type": "ingest"
# case already covered by test_ingest_job_succeeds_and_persists_the_candidate
# above — same job machinery, different way of getting resume_text in.
def test_ingest_upload_job_extracts_text_and_persists_the_candidate(client, provider):
    candidate = Candidate(
        name="Ada Lovelace",
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
    )
    evidence = [Evidence(id="ev-1", text="Did a thing", experience_id="exp-1")]
    provider.queue(IngestResumeResponse(candidate=candidate, evidence=evidence))

    r = client.post(
        "/jobs/ingest-upload",
        files={"file": ("resume.txt", b"Ada Lovelace's resume", "text/plain")},
    )
    assert r.status_code == 202
    job_id = r.json()["id"]

    r = _poll_until_done(client, job_id)
    body = r.json()
    assert body["status"] == "succeeded", body
    assert body["result"]["candidate"]["name"] == "Ada Lovelace"


def test_ingest_upload_job_rejects_unsupported_file_type(client):
    r = client.post(
        "/jobs/ingest-upload",
        files={"file": ("resume.odt", b"not a supported format", "application/octet-stream")},
    )
    assert r.status_code == 502
    assert r.json()["error"]["category"] == "ParsingError"
