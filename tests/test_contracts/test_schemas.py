import pytest
from pydantic import ValidationError as PydanticValidationError

from contracts.schemas import (
    AnalyzeVacancyResponse,
    IngestResumeResponse,
    MatchRequest,
    MatchResponse,
    RewriteBulletsRequest,
    RewriteBulletsResponse,
    RewritePlanRequest,
    RewritePlanResponse,
)
from domain.models import (
    Candidate,
    Evidence,
    Experience,
    Requirement,
    RewritePlan,
    TailoredBullet,
    TailoredExperience,
)


def test_ingest_resume_response_validates_candidate_and_evidence():
    response = IngestResumeResponse.model_validate(
        {
            "candidate": {"name": "Ada Lovelace"},
            "evidence": [{"id": "ev-1", "text": "Led a team of five designers."}],
        }
    )
    assert response.candidate == Candidate(name="Ada Lovelace")
    assert response.evidence == [Evidence(id="ev-1", text="Led a team of five designers.")]


def test_ingest_resume_response_parses_experience_project_nesting_and_evidence_links():
    response = IngestResumeResponse.model_validate(
        {
            "candidate": {
                "name": "Ada Lovelace",
                "experience": [
                    {
                        "id": "exp-1",
                        "company": "Agency Co",
                        "position": "Consultant",
                        "projects": [
                            {
                                "id": "exp-1-proj-1",
                                "name": "Client A Migration",
                                "achievements": ["Migrated legacy billing system"],
                            }
                        ],
                    }
                ],
            },
            "evidence": [
                {
                    "id": "ev-1",
                    "text": "Migrated legacy billing system",
                    "experience_id": "exp-1",
                    "experience_project_id": "exp-1-proj-1",
                }
            ],
        }
    )
    assert response.candidate.experience[0].projects[0].name == "Client A Migration"
    assert response.evidence[0].experience_id == "exp-1"
    assert response.evidence[0].experience_project_id == "exp-1-proj-1"


def test_ingest_resume_response_defaults_evidence_to_empty_list():
    response = IngestResumeResponse.model_validate({"candidate": {"name": "Ada Lovelace"}})
    assert response.evidence == []


def test_ingest_resume_response_requires_candidate():
    with pytest.raises(PydanticValidationError):
        IngestResumeResponse.model_validate({"evidence": []})


def test_analyze_vacancy_response_validates_full_shape():
    response = AnalyzeVacancyResponse.model_validate(
        {
            "title": "Senior Engineer",
            "company": "Acme Corp",
            "requirements": [{"text": "5+ years Python", "keywords": ["Python"]}],
            "keywords": ["Python", "SQL"],
        }
    )
    assert response.title == "Senior Engineer"
    assert response.company == "Acme Corp"
    assert response.requirements == [Requirement(text="5+ years Python", keywords=["Python"])]
    assert response.keywords == ["Python", "SQL"]


def test_analyze_vacancy_response_defaults_all_fields():
    response = AnalyzeVacancyResponse.model_validate({})
    assert response.title is None
    assert response.company is None
    assert response.requirements == []
    assert response.keywords == []


def test_analyze_vacancy_response_has_no_raw_text_field():
    # raw_text is deliberately not part of what the LLM produces; it's added
    # by VacancyAnalysisService from the caller's original input.
    assert "raw_text" not in AnalyzeVacancyResponse.model_fields


def test_requirement_keywords_defaults_to_empty_list():
    assert Requirement(text="Some requirement").keywords == []


def test_match_request_requires_experience_evidence_and_requirements():
    request = MatchRequest.model_validate(
        {
            "experience": [{"id": "exp-1", "company": "Acme", "position": "Engineer"}],
            "evidence": [{"id": "ev-1", "text": "Led a team of five designers."}],
            "requirements": [{"text": "5+ years Python", "keywords": ["Python"]}],
        }
    )
    assert request.experience == [Experience(id="exp-1", company="Acme", position="Engineer")]
    assert request.evidence == [Evidence(id="ev-1", text="Led a team of five designers.")]
    assert request.requirements == [Requirement(text="5+ years Python", keywords=["Python"])]


def test_match_request_missing_experience_raises():
    with pytest.raises(PydanticValidationError):
        MatchRequest.model_validate({"evidence": [], "requirements": []})


def test_match_request_candidate_facts_default_to_empty_lists():
    request = MatchRequest.model_validate({"experience": [], "evidence": [], "requirements": []})
    assert request.candidate_skills == []
    assert request.candidate_technologies == []
    assert request.candidate_languages == []
    assert request.candidate_certifications == []


def test_match_response_validates_match_result_shape():
    response = MatchResponse.model_validate(
        {
            "match_result": {
                "matches": [
                    {"requirement_text": "5+ years Python", "evidence_ids": ["ev-1"], "strength": "high"}
                ],
                "gaps": [
                    {
                        "requirement_text": "AWS certification",
                        "description": "No cloud cert found.",
                        "severity": "high",
                        "suggested_action": "Add an AWS certification if you have one.",
                    }
                ],
                "missing_keywords": ["AWS"],
            }
        }
    )
    assert response.match_result.matches[0].requirement_text == "5+ years Python"
    assert response.match_result.matches[0].strength == "high"
    assert response.match_result.gaps[0].description == "No cloud cert found."
    assert response.match_result.gaps[0].severity == "high"
    assert response.match_result.gaps[0].suggested_action == "Add an AWS certification if you have one."
    assert response.match_result.missing_keywords == ["AWS"]


def test_match_response_rejects_invalid_strength():
    with pytest.raises(PydanticValidationError):
        MatchResponse.model_validate(
            {
                "match_result": {
                    "matches": [
                        {"requirement_text": "5+ years Python", "strength": "extremely high"}
                    ]
                }
            }
        )


def test_match_response_rejects_invalid_gap_severity():
    with pytest.raises(PydanticValidationError):
        MatchResponse.model_validate(
            {
                "match_result": {
                    "gaps": [
                        {
                            "requirement_text": "AWS certification",
                            "description": "No cloud cert found.",
                            "severity": "urgent",
                        }
                    ]
                }
            }
        )


def test_rewrite_plan_request_requires_experience_evidence_requirements_and_match_result():
    request = RewritePlanRequest.model_validate(
        {
            "experience": [{"id": "exp-1", "company": "Acme", "position": "Engineer"}],
            "evidence": [{"id": "ev-1", "text": "Led a team of five designers."}],
            "requirements": [{"text": "5+ years Python", "keywords": ["Python"]}],
            "match_result": {
                "matches": [
                    {"requirement_text": "5+ years Python", "evidence_ids": ["ev-1"], "strength": "high"}
                ]
            },
        }
    )
    assert request.experience == [Experience(id="exp-1", company="Acme", position="Engineer")]
    assert request.match_result.matches[0].requirement_text == "5+ years Python"


def test_rewrite_plan_request_missing_match_result_raises():
    with pytest.raises(PydanticValidationError):
        RewritePlanRequest.model_validate({"experience": [], "evidence": [], "requirements": []})


def test_rewrite_plan_response_validates_plan_shape():
    response = RewritePlanResponse.model_validate(
        {
            "plan": {
                "actions": [
                    {
                        "evidence_id": "ev-1",
                        "action": "rewrite",
                        "reason": "Weak phrasing.",
                        "target_keywords": ["Python"],
                    }
                ],
                "priority_order": ["ev-1"],
            }
        }
    )
    assert response.plan.actions[0].action == "rewrite"
    assert response.plan.priority_order == ["ev-1"]


def test_rewrite_plan_response_rejects_invalid_action():
    with pytest.raises(PydanticValidationError):
        RewritePlanResponse.model_validate(
            {"plan": {"actions": [{"evidence_id": "ev-1", "action": "merge", "reason": "x"}]}}
        )


def test_rewrite_bullets_request_requires_plan():
    request = RewriteBulletsRequest.model_validate(
        {
            "experience": [],
            "evidence": [],
            "requirements": [],
            "plan": {"actions": [], "priority_order": []},
        }
    )
    assert request.plan == RewritePlan()
    assert request.candidate_summary is None
    assert request.candidate_skills == []
    assert request.candidate_technologies == []


def test_rewrite_bullets_request_accepts_candidate_skills():
    request = RewriteBulletsRequest.model_validate(
        {
            "experience": [],
            "evidence": [],
            "requirements": [],
            "plan": {"actions": [], "priority_order": []},
            "candidate_skills": ["Python", "SQL"],
        }
    )
    assert request.candidate_skills == ["Python", "SQL"]


def test_rewrite_bullets_request_accepts_candidate_technologies():
    request = RewriteBulletsRequest.model_validate(
        {
            "experience": [],
            "evidence": [],
            "requirements": [],
            "plan": {"actions": [], "priority_order": []},
            "candidate_technologies": ["Figma", "Unity"],
        }
    )
    assert request.candidate_technologies == ["Figma", "Unity"]


def test_rewrite_bullets_request_accepts_candidate_summary():
    request = RewriteBulletsRequest.model_validate(
        {
            "experience": [],
            "evidence": [],
            "requirements": [],
            "plan": {"actions": [], "priority_order": []},
            "candidate_summary": "Analytical engineer open to new roles.",
        }
    )
    assert request.candidate_summary == "Analytical engineer open to new roles."


def test_rewrite_bullets_response_cv_is_a_cv_projection_not_full_cv():
    response = RewriteBulletsResponse.model_validate(
        {
            "cv": {
                "summary": "A summary.",
                "experience": [
                    {"experience_id": "exp-1", "bullets": [{"text": "A bullet"}]}
                ],
                "skills": ["Python"],
            }
        }
    )
    assert response.cv.summary == "A summary."
    assert response.cv.experience == [
        TailoredExperience(experience_id="exp-1", bullets=[TailoredBullet(text="A bullet")])
    ]
    # CVProjection deliberately has no identity/contact/date fields.
    assert "name" not in type(response.cv).model_fields
    assert "email" not in type(response.cv).model_fields
