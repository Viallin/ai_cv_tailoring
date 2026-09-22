"""Prompt Tests (docs/architecture.md Testing Strategy): render the real,
wired-up files in prompts/ — not synthetic stand-ins (that's
tests/test_app/test_prompt_loader.py's job, testing the loader mechanism
itself) — with the exact placeholder kwargs app/use_cases.py passes for
each stage. Catches a broken/renamed placeholder in a real prompt file
before it only shows up as a runtime PromptError against a live LLM call.
"""

from pathlib import Path

import pytest

from app.prompt_loader import PromptLoader

_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_STRUCTURAL_MARKERS = ["## Role", "## Task", "## Rules", "## Input", "## Output format"]

# (filename, placeholder kwargs) — mirrors each app/use_cases.py .render() call exactly.
_CASES = [
    ("01_cv_parser_v1.md", {"resume_text": "resume_text-marker"}),
    ("02_jd_parser_v1.md", {"vacancy_text": "vacancy_text-marker"}),
    (
        "03_cv_jd_matcher_v1.md",
        {
            "experience_json": "experience_json-marker",
            "evidence_json": "evidence_json-marker",
            "requirements_json": "requirements_json-marker",
            "candidate_skills_json": "candidate_skills_json-marker",
            "candidate_technologies_json": "candidate_technologies_json-marker",
            "candidate_languages_json": "candidate_languages_json-marker",
            "candidate_certifications_json": "candidate_certifications_json-marker",
            "candidate_education_json": "candidate_education_json-marker",
            "candidate_contacts_json": "candidate_contacts_json-marker",
            "language": "language-marker",
        },
    ),
    (
        "04_rewrite_planner_v1.md",
        {
            "experience_json": "experience_json-marker",
            "evidence_json": "evidence_json-marker",
            "requirements_json": "requirements_json-marker",
            "match_result_json": "match_result_json-marker",
            "language": "language-marker",
        },
    ),
    (
        "05_rewrite_bullets_v1.md",
        {
            "experience_json": "experience_json-marker",
            "evidence_json": "evidence_json-marker",
            "requirements_json": "requirements_json-marker",
            "plan_json": "plan_json-marker",
            "gaps_json": "gaps_json-marker",
            "candidate_summary": "candidate_summary-marker",
            "candidate_headline": "candidate_headline-marker",
            "vacancy_title": "vacancy_title-marker",
            "candidate_skills_json": "candidate_skills_json-marker",
            "candidate_technologies_json": "candidate_technologies_json-marker",
            "language": "language-marker",
        },
    ),
    (
        "06_skill_evidence_linker_v1.md",
        {
            "skills_json": "skills_json-marker",
            "technologies_json": "technologies_json-marker",
            "evidence_json": "evidence_json-marker",
        },
    ),
    (
        "07_bullet_quality_recheck_v1.md",
        {
            "cv_json": "cv_json-marker",
            "requirements_json": "requirements_json-marker",
            "language": "language-marker",
        },
    ),
]


@pytest.fixture
def loader() -> PromptLoader:
    return PromptLoader(prompts_dir=_PROMPTS_DIR)


@pytest.mark.parametrize("filename,placeholders", _CASES)
def test_renders_with_the_placeholders_its_use_case_provides(loader, filename, placeholders):
    rendered = loader.render(filename, **placeholders)

    for value in placeholders.values():
        assert value in rendered


@pytest.mark.parametrize("filename,placeholders", _CASES)
def test_structural_sections_are_present(loader, filename, placeholders):
    rendered = loader.render(filename, **placeholders)

    for marker in _STRUCTURAL_MARKERS:
        assert marker in rendered
