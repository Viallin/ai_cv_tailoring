from app.prompt_loader import PromptLoader
from app.use_cases import (
    BulletRewriteService,
    MatchingService,
    QualityRecheckService,
    RewritePlannerService,
    SkillEvidenceLinkingService,
    VacancyAnalysisService,
)
from contracts.schemas import (
    AnalyzeVacancyResponse,
    MatchRequest,
    MatchResponse,
    QualityRecheckRequest,
    QualityRecheckResponse,
    RelinkSkillEvidenceRequest,
    RelinkSkillEvidenceResponse,
    RewriteBulletsRequest,
    RewriteBulletsResponse,
    RewritePlanRequest,
    RewritePlanResponse,
    SkillEvidenceLink,
)
from domain.models import (
    CVProjection,
    Evidence,
    Experience,
    Gap,
    MatchResult,
    Requirement,
    RequirementMatch,
    RewriteAction,
    RewritePlan,
    Skill,
    TailoredBullet,
    TailoredExperience,
    Technology,
    Vacancy,
)


class _FakeProvider:
    """Minimal ILLMProvider stand-in that returns a canned response.

    A real mock would also work, but this makes the "what the LLM would have
    returned" input explicit and easy to read in each test.
    """

    def __init__(self, response):
        self.response = response
        self.last_prompt = None
        self.last_schema = None
        self.last_thinking_budget = None

    def generate_structured(self, prompt, response_schema, thinking_budget=None):
        self.last_prompt = prompt
        self.last_schema = response_schema
        self.last_thinking_budget = thinking_budget
        return self.response


def make_vacancy_prompt_loader(tmp_path) -> PromptLoader:
    # A minimal stand-in for the real 02_jd_parser_v1.md — decoupled from its
    # actual wording so prompt-copy edits don't break this unit test. The
    # real prompt's *content* is covered by prompt-rendering tests, not here.
    (tmp_path / "02_jd_parser_v1.md").write_text(
        "Analyze: $vacancy_text", encoding="utf-8"
    )
    return PromptLoader(prompts_dir=tmp_path)


def make_matching_prompt_loader(tmp_path) -> PromptLoader:
    # Ditto for 03_cv_jd_matcher_v1.md — a minimal stand-in decoupled from
    # the real prompt's wording.
    (tmp_path / "03_cv_jd_matcher_v1.md").write_text(
        "Experience: $experience_json | Evidence: $evidence_json | "
        "Skills: $candidate_skills_json | Technologies: $candidate_technologies_json | "
        "Languages: $candidate_languages_json | Certifications: $candidate_certifications_json | "
        "Education: $candidate_education_json | Contacts: $candidate_contacts_json | "
        "Requirements: $requirements_json",
        encoding="utf-8",
    )
    return PromptLoader(prompts_dir=tmp_path)


def make_rewrite_planner_prompt_loader(tmp_path) -> PromptLoader:
    # Ditto for 04_rewrite_planner_v1.md — a minimal stand-in decoupled from
    # the real prompt's wording.
    (tmp_path / "04_rewrite_planner_v1.md").write_text(
        "Experience: $experience_json | Evidence: $evidence_json | "
        "Requirements: $requirements_json | Match: $match_result_json",
        encoding="utf-8",
    )
    return PromptLoader(prompts_dir=tmp_path)


def make_bullet_rewrite_prompt_loader(tmp_path) -> PromptLoader:
    # Ditto for 05_rewrite_bullets_v1.md — a minimal stand-in decoupled from
    # the real prompt's wording.
    (tmp_path / "05_rewrite_bullets_v1.md").write_text(
        "Summary: $candidate_summary | Headline: $candidate_headline | "
        "Vacancy title: $vacancy_title | Experience: $experience_json | "
        "Evidence: $evidence_json | Requirements: $requirements_json | "
        "Plan: $plan_json | Skills: $candidate_skills_json | "
        "Technologies: $candidate_technologies_json",
        encoding="utf-8",
    )
    return PromptLoader(prompts_dir=tmp_path)


def make_quality_recheck_prompt_loader(tmp_path) -> PromptLoader:
    # Ditto for 07_bullet_quality_recheck_v1.md — a minimal stand-in
    # decoupled from the real prompt's wording.
    (tmp_path / "07_bullet_quality_recheck_v1.md").write_text(
        "CV: $cv_json | Requirements: $requirements_json",
        encoding="utf-8",
    )
    return PromptLoader(prompts_dir=tmp_path)


def make_skill_evidence_linker_prompt_loader(tmp_path) -> PromptLoader:
    # Ditto for 06_skill_evidence_linker_v1.md — a minimal stand-in decoupled
    # from the real prompt's wording.
    (tmp_path / "06_skill_evidence_linker_v1.md").write_text(
        "Skills: $skills_json | Technologies: $technologies_json | Evidence: $evidence_json",
        encoding="utf-8",
    )
    return PromptLoader(prompts_dir=tmp_path)


# ----- VacancyAnalysisService --------------------------------------------


def test_analyze_returns_vacancy_with_original_raw_text_preserved(tmp_path):
    llm_response = AnalyzeVacancyResponse(
        title="Senior Engineer",
        company="Acme Corp",
        requirements=[Requirement(text="5+ years Python", keywords=["Python"])],
        keywords=["Python", "SQL"],
    )
    provider = _FakeProvider(llm_response)
    service = VacancyAnalysisService(provider, make_vacancy_prompt_loader(tmp_path))

    vacancy = service.analyze("We are hiring a Senior Engineer at Acme Corp...")

    assert isinstance(vacancy, Vacancy)
    assert vacancy.title == "Senior Engineer"
    assert vacancy.company == "Acme Corp"
    assert vacancy.raw_text == "We are hiring a Senior Engineer at Acme Corp..."
    assert vacancy.requirements == [Requirement(text="5+ years Python", keywords=["Python"])]
    assert vacancy.keywords == ["Python", "SQL"]


def test_analyze_does_not_trust_llm_for_raw_text(tmp_path):
    # Even if response_schema had a raw_text-like field, analyze() must use
    # the caller's original input, never anything derived from the LLM.
    llm_response = AnalyzeVacancyResponse(requirements=[], keywords=[])
    provider = _FakeProvider(llm_response)
    service = VacancyAnalysisService(provider, make_vacancy_prompt_loader(tmp_path))

    vacancy = service.analyze("original JD text")

    assert vacancy.raw_text == "original JD text"


def test_analyze_disables_thinking(tmp_path):
    # See VacancyAnalysisService.analyze's docstring: this is one of the
    # two stages (Quality Recheck is the other) tried with thinking
    # disabled outright, based on real thoughts-token logging showing this
    # stage spending more on hidden thinking than on its visible output.
    llm_response = AnalyzeVacancyResponse(requirements=[], keywords=[])
    provider = _FakeProvider(llm_response)
    service = VacancyAnalysisService(provider, make_vacancy_prompt_loader(tmp_path))

    service.analyze("some JD text")

    assert provider.last_thinking_budget == 0


def test_analyze_defaults_title_and_company_to_none_when_not_found(tmp_path):
    llm_response = AnalyzeVacancyResponse(requirements=[], keywords=[])
    provider = _FakeProvider(llm_response)
    service = VacancyAnalysisService(provider, make_vacancy_prompt_loader(tmp_path))

    vacancy = service.analyze("a JD with no title or company mentioned")

    assert vacancy.title is None
    assert vacancy.company is None


def test_analyze_renders_prompt_with_vacancy_text_substituted(tmp_path):
    provider = _FakeProvider(AnalyzeVacancyResponse(requirements=[], keywords=[]))
    service = VacancyAnalysisService(provider, make_vacancy_prompt_loader(tmp_path))

    service.analyze("some JD text")

    assert provider.last_prompt == "Analyze: some JD text"


# ----- MatchingService ------------------------------------------------------


def test_match_returns_the_providers_match_result(tmp_path):
    llm_response = MatchResponse(
        match_result=MatchResult(
            matches=[
                RequirementMatch(
                    requirement_text="5+ years Python", evidence_ids=["ev-1"], strength="high"
                )
            ],
            gaps=[
                Gap(
                    requirement_text="AWS certification",
                    description="No cloud cert found.",
                    severity="high",
                )
            ],
            missing_keywords=["AWS"],
        )
    )
    provider = _FakeProvider(llm_response)
    service = MatchingService(provider, make_matching_prompt_loader(tmp_path))

    request = MatchRequest(
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
        evidence=[Evidence(id="ev-1", text="Led a team of five designers.")],
        requirements=[Requirement(text="5+ years Python", keywords=["Python"])],
    )
    response = service.match(request)

    assert response == llm_response
    assert provider.last_schema is MatchResponse


def test_match_renders_prompt_with_experience_evidence_and_requirements(tmp_path):
    provider = _FakeProvider(MatchResponse(match_result=MatchResult()))
    service = MatchingService(provider, make_matching_prompt_loader(tmp_path))

    request = MatchRequest(
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
        evidence=[Evidence(id="ev-1", text="Led a team of five designers.")],
        requirements=[Requirement(text="5+ years Python")],
    )
    service.match(request)

    assert '"id": "exp-1"' in provider.last_prompt
    assert '"id": "ev-1"' in provider.last_prompt
    assert '"text": "5+ years Python"' in provider.last_prompt


def test_match_renders_prompt_with_candidate_skills_languages_and_certifications(tmp_path):
    # Phase 8.4: a requirement satisfied only by a stated language/
    # certification (never mentioned in Evidence) previously showed up as
    # a gap even though the candidate stated it directly — these flat
    # profile facts must reach the matching prompt too, not just Evidence.
    provider = _FakeProvider(MatchResponse(match_result=MatchResult()))
    service = MatchingService(provider, make_matching_prompt_loader(tmp_path))

    request = MatchRequest(
        experience=[],
        evidence=[],
        requirements=[],
        candidate_skills=["Python"],
        candidate_technologies=["Figma"],
        candidate_languages=["English (C1)"],
        candidate_certifications=["AWS Solutions Architect — Amazon, 2022"],
        candidate_education=["MIT — B.S., Computer Science"],
    )
    service.match(request)

    assert '"Python"' in provider.last_prompt
    assert '"Figma"' in provider.last_prompt
    assert '"English (C1)"' in provider.last_prompt
    assert '"AWS Solutions Architect' in provider.last_prompt
    assert '"MIT' in provider.last_prompt


def test_match_renders_prompt_with_candidate_contacts(tmp_path):
    # Reported directly: a vacancy requiring relocation, stated as such in
    # the vacancy description, whose candidate had a "Relocation: Willing
    # to relocate" Contacts entry, was still reported as a Gap — this stage
    # was never given Contacts at all, the same class of bug
    # candidate_skills/_languages/_certifications/_education were already
    # fixed for.
    provider = _FakeProvider(MatchResponse(match_result=MatchResult()))
    service = MatchingService(provider, make_matching_prompt_loader(tmp_path))

    request = MatchRequest(
        experience=[],
        evidence=[],
        requirements=[],
        candidate_contacts=["Relocation: Willing to relocate"],
    )
    service.match(request)

    assert '"Relocation: Willing to relocate"' in provider.last_prompt


def test_match_renders_prompt_with_requirement_priority(tmp_path):
    # Requirement.priority (Version 4, Phase 4.11) rides along inside the
    # same serialized Requirement object already sent as requirements_json
    # — no dedicated template variable needed, just the field being on the
    # model and actually reaching the prompt.
    provider = _FakeProvider(MatchResponse(match_result=MatchResult()))
    service = MatchingService(provider, make_matching_prompt_loader(tmp_path))

    request = MatchRequest(
        experience=[],
        evidence=[],
        requirements=[Requirement(text="B2 English", priority="nice_to_have")],
    )
    service.match(request)

    assert '"priority": "nice_to_have"' in provider.last_prompt


def test_match_excludes_gap_entries_from_the_prompt(tmp_path):
    provider = _FakeProvider(MatchResponse(match_result=MatchResult()))
    service = MatchingService(provider, make_matching_prompt_loader(tmp_path))

    request = MatchRequest(
        experience=[
            Experience(id="exp-1", company="Acme", position="Engineer"),
            Experience(id="exp-2", position="Career Break", is_gap=True),
        ],
        evidence=[],
        requirements=[],
    )
    service.match(request)

    assert '"id": "exp-1"' in provider.last_prompt
    assert '"id": "exp-2"' not in provider.last_prompt
    assert "Career Break" not in provider.last_prompt


# ----- RewritePlannerService -------------------------------------------------


def test_plan_returns_the_providers_rewrite_plan(tmp_path):
    llm_response = RewritePlanResponse(
        plan=RewritePlan(
            actions=[
                RewriteAction(evidence_id="ev-1", action="rewrite", reason="Weak phrasing.")
            ],
            priority_order=["ev-1"],
        )
    )
    provider = _FakeProvider(llm_response)
    service = RewritePlannerService(provider, make_rewrite_planner_prompt_loader(tmp_path))

    request = RewritePlanRequest(
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
        evidence=[Evidence(id="ev-1", text="Led a team of five designers.")],
        requirements=[Requirement(text="5+ years Python", keywords=["Python"])],
        match_result=MatchResult(),
    )
    response = service.plan(request)

    assert response == llm_response
    assert provider.last_schema is RewritePlanResponse


def test_plan_uses_a_reduced_thinking_budget(tmp_path):
    # See the module-level _REWRITE_PLANNING_THINKING_BUDGET comment in
    # app/use_cases.py — a more conservative first experiment than JD
    # Parsing/Quality Recheck's outright thinking_budget=0.
    provider = _FakeProvider(RewritePlanResponse(plan=RewritePlan()))
    service = RewritePlannerService(provider, make_rewrite_planner_prompt_loader(tmp_path))

    service.plan(
        RewritePlanRequest(
            experience=[],
            evidence=[],
            requirements=[],
            match_result=MatchResult(),
        )
    )

    assert provider.last_thinking_budget == 4096


def test_plan_renders_prompt_with_experience_evidence_requirements_and_match_result(tmp_path):
    provider = _FakeProvider(RewritePlanResponse(plan=RewritePlan()))
    service = RewritePlannerService(provider, make_rewrite_planner_prompt_loader(tmp_path))

    request = RewritePlanRequest(
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
        evidence=[Evidence(id="ev-1", text="Led a team of five designers.")],
        requirements=[Requirement(text="5+ years Python")],
        match_result=MatchResult(missing_keywords=["AWS"]),
    )
    service.plan(request)

    assert '"id": "exp-1"' in provider.last_prompt
    assert '"id": "ev-1"' in provider.last_prompt
    assert '"text": "5+ years Python"' in provider.last_prompt
    assert '"AWS"' in provider.last_prompt


def test_plan_excludes_gap_entries_from_the_prompt(tmp_path):
    provider = _FakeProvider(RewritePlanResponse(plan=RewritePlan()))
    service = RewritePlannerService(provider, make_rewrite_planner_prompt_loader(tmp_path))

    request = RewritePlanRequest(
        experience=[
            Experience(id="exp-1", company="Acme", position="Engineer"),
            Experience(id="exp-2", position="Career Break", is_gap=True),
        ],
        evidence=[],
        requirements=[],
        match_result=MatchResult(),
    )
    service.plan(request)

    assert '"id": "exp-1"' in provider.last_prompt
    assert '"id": "exp-2"' not in provider.last_prompt
    assert "Career Break" not in provider.last_prompt


# ----- BulletRewriteService --------------------------------------------------


def test_rewrite_returns_the_providers_cv_projection(tmp_path):
    llm_response = RewriteBulletsResponse(
        cv=CVProjection(
            summary="A summary.",
            experience=[
                TailoredExperience(
                    experience_id="exp-1", bullets=[TailoredBullet(text="A bullet")]
                )
            ],
            skills=["Python"],
        )
    )
    provider = _FakeProvider(llm_response)
    service = BulletRewriteService(provider, make_bullet_rewrite_prompt_loader(tmp_path))

    request = RewriteBulletsRequest(
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
        evidence=[Evidence(id="ev-1", text="Led a team of five designers.")],
        requirements=[Requirement(text="5+ years Python", keywords=["Python"])],
        plan=RewritePlan(),
    )
    response = service.rewrite(request)

    assert response == llm_response
    assert provider.last_schema is RewriteBulletsResponse


def test_rewrite_uses_its_own_intermediate_thinking_budget(tmp_path):
    # A higher, separate budget than Rewrite Planning's — see the
    # module-level _REWRITE_PLANNING_THINKING_BUDGET/
    # _BULLET_REWRITING_THINKING_BUDGET comment in app/use_cases.py for why
    # they're no longer the same constant.
    provider = _FakeProvider(RewriteBulletsResponse(cv=CVProjection(summary="...")))
    service = BulletRewriteService(provider, make_bullet_rewrite_prompt_loader(tmp_path))

    service.rewrite(
        RewriteBulletsRequest(
            experience=[],
            evidence=[],
            requirements=[],
            plan=RewritePlan(),
        )
    )

    assert provider.last_thinking_budget == 8192


def test_rewrite_renders_prompt_with_experience_evidence_requirements_and_plan(tmp_path):
    provider = _FakeProvider(RewriteBulletsResponse(cv=CVProjection(summary="...")))
    service = BulletRewriteService(provider, make_bullet_rewrite_prompt_loader(tmp_path))

    plan = RewritePlan(
        actions=[RewriteAction(evidence_id="ev-1", action="keep", reason="Strong as-is.")]
    )
    request = RewriteBulletsRequest(
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
        evidence=[Evidence(id="ev-1", text="Led a team of five designers.")],
        requirements=[Requirement(text="5+ years Python")],
        plan=plan,
    )
    service.rewrite(request)

    assert '"id": "exp-1"' in provider.last_prompt
    assert '"id": "ev-1"' in provider.last_prompt
    assert '"text": "5+ years Python"' in provider.last_prompt
    assert '"action": "keep"' in provider.last_prompt


def test_rewrite_passes_candidate_headline_and_vacancy_title_into_the_prompt(tmp_path):
    # Both are read-only context for the tailored CVProjection.headline (see
    # that field's docstring) — passed through unlabeled, verbatim.
    provider = _FakeProvider(RewriteBulletsResponse(cv=CVProjection(summary="...")))
    service = BulletRewriteService(provider, make_bullet_rewrite_prompt_loader(tmp_path))

    service.rewrite(
        RewriteBulletsRequest(
            experience=[],
            evidence=[],
            requirements=[],
            plan=RewritePlan(),
            candidate_headline="Character Art Supervisor",
            vacancy_title="Senior 3D Character Artist",
        )
    )

    assert "Character Art Supervisor" in provider.last_prompt
    assert "Senior 3D Character Artist" in provider.last_prompt


def test_rewrite_defaults_missing_headline_and_vacancy_title_to_empty(tmp_path):
    # Unlike candidate_summary (which renders an explicit "(No summary
    # provided.)" placeholder sentence), a missing headline/vacancy title
    # just renders as empty — the prompt's own Input section already
    # documents empty as "profile/JD has none", so there's no need for a
    # placeholder sentence here.
    provider = _FakeProvider(RewriteBulletsResponse(cv=CVProjection(summary="...")))
    service = BulletRewriteService(provider, make_bullet_rewrite_prompt_loader(tmp_path))

    service.rewrite(
        RewriteBulletsRequest(experience=[], evidence=[], requirements=[], plan=RewritePlan())
    )

    assert "Headline:  |" in provider.last_prompt
    assert "Vacancy title:  |" in provider.last_prompt


def test_rewrite_excludes_gap_entries_from_the_prompt(tmp_path):
    provider = _FakeProvider(RewriteBulletsResponse(cv=CVProjection(summary="...")))
    service = BulletRewriteService(provider, make_bullet_rewrite_prompt_loader(tmp_path))

    request = RewriteBulletsRequest(
        experience=[
            Experience(id="exp-1", company="Acme", position="Engineer"),
            Experience(id="exp-2", position="Career Break", is_gap=True),
        ],
        evidence=[],
        requirements=[],
        plan=RewritePlan(),
    )
    service.rewrite(request)

    assert '"id": "exp-1"' in provider.last_prompt
    assert '"id": "exp-2"' not in provider.last_prompt
    assert "Career Break" not in provider.last_prompt


def test_rewrite_passes_candidate_summary_into_the_prompt(tmp_path):
    provider = _FakeProvider(RewriteBulletsResponse(cv=CVProjection(summary="...")))
    service = BulletRewriteService(provider, make_bullet_rewrite_prompt_loader(tmp_path))

    request = RewriteBulletsRequest(
        experience=[],
        evidence=[],
        requirements=[],
        plan=RewritePlan(),
        candidate_summary="Analytical engineer open to new roles.",
    )
    service.rewrite(request)

    assert "Analytical engineer open to new roles." in provider.last_prompt


def test_rewrite_uses_fallback_text_when_candidate_summary_is_none(tmp_path):
    provider = _FakeProvider(RewriteBulletsResponse(cv=CVProjection(summary="...")))
    service = BulletRewriteService(provider, make_bullet_rewrite_prompt_loader(tmp_path))

    request = RewriteBulletsRequest(
        experience=[], evidence=[], requirements=[], plan=RewritePlan(), candidate_summary=None
    )
    service.rewrite(request)

    assert "Summary: (No summary provided.)" in provider.last_prompt
    assert "Summary: None" not in provider.last_prompt


def test_rewrite_passes_candidate_skills_into_the_prompt(tmp_path):
    provider = _FakeProvider(RewriteBulletsResponse(cv=CVProjection(summary="...")))
    service = BulletRewriteService(provider, make_bullet_rewrite_prompt_loader(tmp_path))

    request = RewriteBulletsRequest(
        experience=[],
        evidence=[],
        requirements=[],
        plan=RewritePlan(),
        candidate_skills=["Python", "SQL"],
    )
    service.rewrite(request)

    assert '["Python", "SQL"]' in provider.last_prompt


def test_rewrite_passes_candidate_technologies_into_the_prompt(tmp_path):
    provider = _FakeProvider(RewriteBulletsResponse(cv=CVProjection(summary="...")))
    service = BulletRewriteService(provider, make_bullet_rewrite_prompt_loader(tmp_path))

    request = RewriteBulletsRequest(
        experience=[],
        evidence=[],
        requirements=[],
        plan=RewritePlan(),
        candidate_technologies=["Figma", "Unity"],
    )
    service.rewrite(request)

    assert '["Figma", "Unity"]' in provider.last_prompt


# ----- QualityRecheckService -------------------------------------------------


def test_recheck_returns_the_providers_cv_projection(tmp_path):
    llm_response = QualityRecheckResponse(
        cv=CVProjection(
            summary="A cleaned summary.",
            experience=[
                TailoredExperience(
                    experience_id="exp-1", bullets=[TailoredBullet(text="A cleaned bullet.")]
                )
            ],
            skills=["Python"],
        )
    )
    provider = _FakeProvider(llm_response)
    service = QualityRecheckService(provider, make_quality_recheck_prompt_loader(tmp_path))

    request = QualityRecheckRequest(
        cv=CVProjection(
            summary="A summary, demonstrating filler.",
            experience=[
                TailoredExperience(
                    experience_id="exp-1",
                    bullets=[TailoredBullet(text="A bullet, demonstrating filler.")],
                )
            ],
        ),
        requirements=[Requirement(text="5+ years Python")],
    )
    response = service.recheck(request)

    assert response == llm_response
    assert provider.last_schema is QualityRecheckResponse


def test_recheck_disables_thinking(tmp_path):
    # See QualityRecheckService.recheck's docstring for why.
    provider = _FakeProvider(QualityRecheckResponse(cv=CVProjection(summary="...")))
    service = QualityRecheckService(provider, make_quality_recheck_prompt_loader(tmp_path))

    service.recheck(
        QualityRecheckRequest(
            cv=CVProjection(summary="..."),
            requirements=[],
        )
    )

    assert provider.last_thinking_budget == 0


def test_recheck_renders_prompt_with_the_cv_and_requirements(tmp_path):
    provider = _FakeProvider(QualityRecheckResponse(cv=CVProjection(summary="...")))
    service = QualityRecheckService(provider, make_quality_recheck_prompt_loader(tmp_path))

    request = QualityRecheckRequest(
        cv=CVProjection(
            summary="Raw summary.",
            experience=[
                TailoredExperience(
                    experience_id="exp-1", bullets=[TailoredBullet(text="Raw bullet.", evidence_id="ev-1")]
                )
            ],
        ),
        requirements=[Requirement(text="5+ years Python")],
    )
    service.recheck(request)

    assert '"summary": "Raw summary."' in provider.last_prompt
    assert '"experience_id": "exp-1"' in provider.last_prompt
    assert '"evidence_id": "ev-1"' in provider.last_prompt
    assert '"text": "5+ years Python"' in provider.last_prompt


# ----- SkillEvidenceLinkingService -----------------------------------------


def test_relink_returns_the_providers_response(tmp_path):
    llm_response = RelinkSkillEvidenceResponse(
        skills=[SkillEvidenceLink(id="skill-1", evidence_ids=["ev-1"])],
        technologies=[SkillEvidenceLink(id="tech-1", evidence_ids=[])],
    )
    provider = _FakeProvider(llm_response)
    service = SkillEvidenceLinkingService(provider, make_skill_evidence_linker_prompt_loader(tmp_path))

    request = RelinkSkillEvidenceRequest(
        skills=[Skill(id="skill-1", name="Python")],
        technologies=[Technology(id="tech-1", name="Django")],
        evidence=[Evidence(id="ev-1", text="Built a Python service")],
    )
    response = service.relink(request)

    assert response == llm_response
    assert provider.last_schema is RelinkSkillEvidenceResponse


def test_relink_renders_prompt_with_skill_technology_and_evidence_ids_and_names_only(tmp_path):
    provider = _FakeProvider(RelinkSkillEvidenceResponse())
    service = SkillEvidenceLinkingService(provider, make_skill_evidence_linker_prompt_loader(tmp_path))

    request = RelinkSkillEvidenceRequest(
        skills=[Skill(id="skill-1", name="Python", category="Language", proficiency="Expert")],
        technologies=[Technology(id="tech-1", name="Django")],
        evidence=[Evidence(id="ev-1", text="Built a Python service")],
    )
    service.relink(request)

    assert '{"id": "skill-1", "name": "Python"}' in provider.last_prompt
    assert '{"id": "tech-1", "name": "Django"}' in provider.last_prompt
    assert '"id": "ev-1"' in provider.last_prompt
    # Only id+name are sent for skills/technologies — category/proficiency
    # aren't part of the linking task and would just be noise.
    assert "Language" not in provider.last_prompt
    assert "Expert" not in provider.last_prompt


def test_relink_excludes_category_header_rows_from_the_prompt(tmp_path):
    # Phase 21's category header rows (Skill/Technology.is_category_header)
    # are a Profile Explorer editing construct, not real skills — must
    # never reach the linking prompt as if they were one.
    provider = _FakeProvider(RelinkSkillEvidenceResponse())
    service = SkillEvidenceLinkingService(provider, make_skill_evidence_linker_prompt_loader(tmp_path))

    request = RelinkSkillEvidenceRequest(
        skills=[
            Skill(id="hdr-1", name="Leadership", is_category_header=True),
            Skill(id="skill-1", name="Python"),
        ],
        technologies=[
            Technology(id="hdr-2", name="Tools", is_category_header=True),
            Technology(id="tech-1", name="Django"),
        ],
        evidence=[],
    )
    service.relink(request)

    assert '"skill-1"' in provider.last_prompt
    assert '"tech-1"' in provider.last_prompt
    assert "hdr-1" not in provider.last_prompt
    assert "hdr-2" not in provider.last_prompt
    assert "Leadership" not in provider.last_prompt
    assert '"Tools"' not in provider.last_prompt
