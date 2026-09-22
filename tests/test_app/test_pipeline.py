from app.pipeline import (
    GENERATION_STAGES,
    VACANCY_REUSED_STAGE_LABEL,
    PipelineResult,
    run_cv_generation,
    run_gap_recheck,
    run_resume_ingestion,
    run_skill_evidence_relink,
)
from app.services import Services
from contracts.schemas import (
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
    Certification,
    ContactItem,
    CVProjection,
    Education,
    Evidence,
    Experience,
    Gap,
    Language,
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


class _FakeResumeService:
    def __init__(self, response: IngestResumeResponse):
        self.response = response
        self.last_raw_text = None

    def ingest(self, raw_text):
        self.last_raw_text = raw_text
        return self.response


class _FakeVacancyService:
    def __init__(self, vacancy: Vacancy):
        self.vacancy = vacancy
        self.last_raw_text = None

    def analyze(self, raw_text):
        self.last_raw_text = raw_text
        return self.vacancy


class _FakeMatchingService:
    def __init__(self, response: MatchResponse):
        self.response = response
        self.last_request = None

    def match(self, request):
        self.last_request = request
        return self.response


class _FakeRewritePlannerService:
    def __init__(self, response: RewritePlanResponse):
        self.response = response
        self.last_request = None

    def plan(self, request):
        self.last_request = request
        return self.response


class _FakeBulletRewriteService:
    def __init__(self, response: RewriteBulletsResponse):
        self.response = response
        self.last_request = None

    def rewrite(self, request):
        self.last_request = request
        return self.response


class _FakeQualityRecheckService:
    """Defaults to an identity pass (echoes back whatever `cv` it was given)
    so tests that don't care about the Quality Recheck stage can assert
    against the Bullet Rewriting stage's response unchanged, same as
    before this stage existed. Pass `response` to pin a specific
    (possibly different) recheck output instead."""

    def __init__(self, response: QualityRecheckResponse | None = None):
        self.response = response
        self.last_request = None

    def recheck(self, request):
        self.last_request = request
        return self.response or QualityRecheckResponse(cv=request.cv)


class _FakeSkillEvidenceLinkingService:
    def __init__(self, response: RelinkSkillEvidenceResponse):
        self.response = response
        self.last_request = None

    def relink(self, request):
        self.last_request = request
        return self.response


class _FakeCandidateService:
    def __init__(self):
        self.saved = None
        self.saved_evidence = None
        self.updated_skills: list[tuple[str, list[str]]] = []
        self.updated_technologies: list[tuple[str, list[str]]] = []

    def replace(self, candidate, evidence=None):
        self.saved = candidate
        if evidence is not None:
            self.saved_evidence = evidence
        return candidate

    def get(self):
        return self.saved

    def get_evidence(self):
        return self.saved_evidence or []

    def update_skill(self, skill_id, **fields):
        self.updated_skills.append((skill_id, fields.get("evidence_ids")))

    def update_technology(self, technology_id, **fields):
        self.updated_technologies.append((technology_id, fields.get("evidence_ids")))


class _FakeCandidateRegistry:
    """Fake for app.candidate_registry.CandidateRegistry — always hands out
    the same fixed id for new profiles (predictable for assertions) and
    memoizes one _FakeCandidateService per id, same as the real
    service_for()."""

    def __init__(self, new_id="new-profile-id"):
        self.new_id = new_id
        self._services: dict[str, _FakeCandidateService] = {}

    def new_profile_id(self):
        return self.new_id

    def service_for(self, candidate_id):
        return self._services.setdefault(candidate_id, _FakeCandidateService())


def make_services(
    resume_response=None,
    vacancy=None,
    rewrite_response=None,
    match_response=None,
    plan_response=None,
    recheck_response=None,
    relink_response=None,
) -> Services:
    return Services(
        resume=_FakeResumeService(resume_response) if resume_response else None,
        vacancy=_FakeVacancyService(vacancy) if vacancy else None,
        matching=_FakeMatchingService(
            match_response or MatchResponse(match_result=MatchResult())
        ),
        rewrite_planner=_FakeRewritePlannerService(
            plan_response or RewritePlanResponse(plan=RewritePlan())
        ),
        bullet_rewriter=_FakeBulletRewriteService(rewrite_response)
        if rewrite_response
        else None,
        quality_recheck=_FakeQualityRecheckService(recheck_response),
        skill_evidence_linker=_FakeSkillEvidenceLinkingService(
            relink_response or RelinkSkillEvidenceResponse()
        ),
        candidate_registry=_FakeCandidateRegistry(),
    )


# ----- run_resume_ingestion ----------------------------------------------


def test_run_resume_ingestion_persists_candidate_and_evidence_under_a_new_profile():
    candidate = Candidate(
        name="Ada Lovelace",
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
    )
    evidence = [Evidence(id="ev-1", text="Did a thing")]
    resume_response = IngestResumeResponse(candidate=candidate, evidence=evidence)
    services = make_services(resume_response=resume_response)

    candidate_id, result = run_resume_ingestion("resume text", services)

    assert result == candidate
    assert candidate_id == services.candidate_registry.new_id
    saved_service = services.candidate_registry.service_for(candidate_id)
    assert saved_service.saved == candidate
    assert saved_service.saved_evidence == evidence


def test_run_resume_ingestion_passes_original_text_to_the_resume_service():
    resume_response = IngestResumeResponse(candidate=Candidate(name="Ada"), evidence=[])
    services = make_services(resume_response=resume_response)

    run_resume_ingestion("resume text", services)

    assert services.resume.last_raw_text == "resume text"


# ----- run_cv_generation ---------------------------------------------------


def test_run_cv_generation_uses_the_evidence_it_was_given_not_a_fresh_parse():
    candidate = Candidate(
        name="Ada Lovelace",
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
    )
    evidence = [Evidence(id="ev-1", text="Did a thing")]
    vacancy = Vacancy(raw_text="a JD", requirements=[Requirement(text="5+ years Python")])
    rewrite_response = RewriteBulletsResponse(
        cv=CVProjection(
            summary="A summary.",
            experience=[
                TailoredExperience(
                    experience_id="exp-1", bullets=[TailoredBullet(text="Did a thing")]
                )
            ],
            skills=["Python"],
        )
    )
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    result = run_cv_generation(candidate, evidence, "vacancy text", services)

    assert isinstance(result, PipelineResult)
    assert result.candidate == candidate
    assert result.vacancy == vacancy
    assert result.assembled_cv.name == "Ada Lovelace"
    assert result.assembled_cv.summary == "A summary."
    assert result.assembled_cv.experience[0].bullets == [TailoredBullet(text="Did a thing")]
    assert services.matching.last_request.evidence == evidence
    assert services.rewrite_planner.last_request.evidence == evidence
    assert services.bullet_rewriter.last_request.evidence == evidence


def test_run_cv_generation_passes_candidates_experience_and_requirements_through_every_stage():
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    vacancy = Vacancy(raw_text="jd", requirements=[Requirement(text="Python")])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    for fake in (services.matching, services.rewrite_planner, services.bullet_rewriter):
        assert fake.last_request.experience == candidate.experience
        assert fake.last_request.requirements == vacancy.requirements


def test_run_cv_generation_passes_candidates_language_through_every_stage():
    candidate = Candidate(name="Ada", language="ru")
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    for fake in (
        services.matching,
        services.rewrite_planner,
        services.bullet_rewriter,
        services.quality_recheck,
    ):
        assert fake.last_request.language == "ru"


def test_run_gap_recheck_passes_candidates_language_to_the_matcher():
    candidate = Candidate(name="Ada", language="ru")
    services = make_services()

    run_gap_recheck(candidate, [], [Requirement(text="Python")], set(), services)

    assert services.matching.last_request.language == "ru"


def test_run_cv_generation_passes_candidate_summary_to_the_bullet_rewriter():
    candidate = Candidate(name="Ada", summary="Analytical engineer open to new roles.")
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.bullet_rewriter.last_request.candidate_summary == (
        "Analytical engineer open to new roles."
    )


def test_run_cv_generation_passes_none_when_candidate_has_no_summary():
    candidate = Candidate(name="Ada")  # no summary captured
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.bullet_rewriter.last_request.candidate_summary is None


def test_run_cv_generation_passes_candidate_headline_and_vacancy_title_to_the_bullet_rewriter():
    candidate = Candidate(name="Ada", headline="Character Art Supervisor")
    vacancy = Vacancy(raw_text="jd", title="Senior 3D Character Artist", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.bullet_rewriter.last_request.candidate_headline == "Character Art Supervisor"
    assert services.bullet_rewriter.last_request.vacancy_title == "Senior 3D Character Artist"


def test_run_cv_generation_passes_candidate_skill_names_to_the_bullet_rewriter():
    candidate = Candidate(
        name="Ada", skills=[Skill(id="s1", name="Python"), Skill(id="s2", name="SQL")]
    )
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.bullet_rewriter.last_request.candidate_skills == ["Python", "SQL"]


def test_run_cv_generation_passes_candidate_technology_names_to_the_bullet_rewriter():
    candidate = Candidate(
        name="Ada",
        technologies=[Technology(id="t1", name="Figma"), Technology(id="t2", name="Unity")],
    )
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.bullet_rewriter.last_request.candidate_technologies == ["Figma", "Unity"]


def test_run_cv_generation_passes_candidate_skill_and_technology_names_to_the_matcher():
    candidate = Candidate(
        name="Ada",
        skills=[Skill(id="s1", name="Python")],
        technologies=[Technology(id="t1", name="Figma")],
    )
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.matching.last_request.candidate_skills == ["Python"]
    assert services.matching.last_request.candidate_technologies == ["Figma"]


def test_run_cv_generation_excludes_category_header_rows_from_skill_and_technology_names():
    # Phase 21: Skill/Technology.is_category_header rows are a Profile
    # Explorer editing construct, not real skills — must never reach an
    # LLM prompt as if they were one.
    candidate = Candidate(
        name="Ada",
        skills=[
            Skill(id="hdr-1", name="Expertise", is_category_header=True),
            Skill(id="s1", name="Python"),
        ],
        technologies=[
            Technology(id="hdr-2", name="Tools", is_category_header=True),
            Technology(id="t1", name="Figma"),
        ],
    )
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.matching.last_request.candidate_skills == ["Python"]
    assert services.matching.last_request.candidate_technologies == ["Figma"]
    assert services.bullet_rewriter.last_request.candidate_skills == ["Python"]
    assert services.bullet_rewriter.last_request.candidate_technologies == ["Figma"]


def test_run_cv_generation_passes_candidate_languages_to_the_matcher_with_proficiency_formatted():
    # Phase 8.4: a requirement satisfied only by a stated language/
    # certification (never mentioned in an Evidence bullet) was previously
    # reported as a gap even though the candidate stated it directly — see
    # docs/development_plan.md's Phase 8.4 note.
    candidate = Candidate(
        name="Ada",
        languages=[
            Language(id="l1", name="English", proficiency="C1"),
            Language(id="l2", name="French"),
        ],
    )
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.matching.last_request.candidate_languages == ["English (C1)", "French"]


def test_run_cv_generation_passes_candidate_certifications_to_the_matcher_with_issuer_and_date_formatted():
    candidate = Candidate(
        name="Ada",
        certifications=[
            Certification(id="c1", name="AWS Solutions Architect", issuer="Amazon", date="2022"),
            Certification(id="c2", name="Scrum Master"),
        ],
    )
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.matching.last_request.candidate_certifications == [
        "AWS Solutions Architect — Amazon, 2022",
        "Scrum Master",
    ]


def test_run_cv_generation_passes_candidate_education_to_the_matcher_with_degree_and_period_formatted():
    # Reported directly: a Requirement asking for a specific degree was
    # always flagged as a Gap regardless of the candidate's real Education
    # entries, because the Matching stage was never given them at all —
    # the same class of bug candidate_languages/candidate_certifications
    # already fixed, just never extended to Education.
    candidate = Candidate(
        name="Ada",
        education=[
            Education(
                id="edu-1",
                institution="Altai State Technical University",
                degree="Software Engineering",
                period="2005 – 2010",
            ),
            Education(id="edu-2", institution="Some College"),
        ],
    )
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.matching.last_request.candidate_education == [
        "Altai State Technical University — Software Engineering (2005 – 2010)",
        "Some College",
    ]


def test_run_cv_generation_passes_candidate_contacts_to_the_matcher_with_label_and_value_formatted():
    # Reported directly: a vacancy that required relocation and stated it
    # in the vacancy description was still flagged as a Gap even though the
    # candidate's own Contacts held a "Relocation" entry saying so, because
    # the Matching stage was never given Contacts at all — the same class
    # of bug candidate_languages/_certifications/_education already fixed.
    candidate = Candidate(
        name="Ada",
        contacts=[
            ContactItem(id="c1", label="Relocation", value="Willing to relocate"),
        ],
    )
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.matching.last_request.candidate_contacts == [
        "Relocation: Willing to relocate",
    ]


def test_run_cv_generation_filters_email_and_phone_contacts_out_of_the_matcher_request():
    # Follow-up to the fix above: once Contacts reached the Matching prompt
    # at all, the candidate's raw email/phone started reaching a
    # third-party LLM API on every generate/recheck for zero matching
    # benefit (an email address never satisfies a Requirement the way a
    # Relocation/Work Authorization/Location entry can) — see
    # app.pipeline._is_sensitive_contact_value's own docstring. Every other
    # Contact (including one with a short, non-phone digit run) still
    # passes through unfiltered.
    candidate = Candidate(
        name="Ada",
        contacts=[
            ContactItem(id="c1", label="Relocation", value="Willing to relocate"),
            ContactItem(id="c2", label="Email", value="ada@example.com"),
            ContactItem(id="c3", label="Phone", value="+1 (555) 123-4567"),
            ContactItem(id="c4", label="Location", value="Berlin, 10115"),
        ],
    )
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.matching.last_request.candidate_contacts == [
        "Relocation: Willing to relocate",
        "Location: Berlin, 10115",
    ]


def test_run_cv_generation_passes_original_vacancy_text_to_the_vacancy_service():
    candidate = Candidate(name="Ada")
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.vacancy.last_raw_text == "vacancy text"


def test_run_cv_generation_returns_the_matching_stages_result():
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    evidence = [Evidence(id="ev-1", text="Did a thing")]
    vacancy = Vacancy(raw_text="jd", requirements=[Requirement(text="AWS certification")])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    match_result = MatchResult(
        matches=[
            RequirementMatch(requirement_text="AWS certification", evidence_ids=["ev-1"], strength="low")
        ],
        gaps=[
            Gap(
                requirement_text="AWS certification",
                description="No cloud certification found.",
                severity="high",
            )
        ],
        missing_keywords=["AWS"],
    )
    services = make_services(
        vacancy=vacancy,
        rewrite_response=rewrite_response,
        match_response=MatchResponse(match_result=match_result),
    )

    result = run_cv_generation(candidate, evidence, "vacancy text", services)

    assert result.match_result == match_result
    assert services.matching.last_request.experience == candidate.experience
    assert services.matching.last_request.requirements == vacancy.requirements
    assert services.matching.last_request.evidence == evidence


def test_run_cv_generation_passes_matching_result_into_the_rewrite_plan_request():
    candidate = Candidate(name="Ada")
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    match_result = MatchResult(missing_keywords=["AWS"])
    services = make_services(
        vacancy=vacancy,
        rewrite_response=rewrite_response,
        match_response=MatchResponse(match_result=match_result),
    )

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.rewrite_planner.last_request.match_result == match_result


def test_run_cv_generation_passes_the_matching_stages_gaps_into_the_bullet_rewrite_request():
    # Found live: the summary asserted "quickly prototypes in Unity" in
    # the same generation whose own Matching stage had just written "no
    # explicit mention of fast Unity prototyping" as an open Gap for that
    # identical Requirement — Bullet Rewriting had no way to know, since
    # it never received the Matching stage's own Gaps at all.
    candidate = Candidate(name="Ada")
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    gaps = [
        Gap(
            requirement_text="Fast prototyping in Unity",
            description="No explicit mention of fast Unity prototyping.",
            severity="medium",
        )
    ]
    services = make_services(
        vacancy=vacancy,
        rewrite_response=rewrite_response,
        match_response=MatchResponse(match_result=MatchResult(gaps=gaps)),
    )

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.bullet_rewriter.last_request.gaps == gaps


def test_run_cv_generation_builds_a_provenance_report_from_the_plan_and_assembled_cv():
    # Phase 17: PipelineResult.provenance is built deterministically from
    # the evidence/plan already in hand — no new LLM call.
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    evidence = [
        Evidence(id="ev-1", text="Original evidence text."),
        Evidence(id="ev-2", text="Never made the cut."),
    ]
    vacancy = Vacancy(raw_text="jd", requirements=[])
    plan = RewritePlan(
        actions=[
            RewriteAction(evidence_id="ev-1", action="rewrite", reason="Sharpen the wording."),
            RewriteAction(evidence_id="ev-2", action="remove", reason="Not relevant to this vacancy."),
        ]
    )
    rewrite_response = RewriteBulletsResponse(
        cv=CVProjection(
            summary="...",
            experience=[
                TailoredExperience(
                    experience_id="exp-1",
                    bullets=[TailoredBullet(text="Sharpened wording.", evidence_id="ev-1")],
                )
            ],
        )
    )
    services = make_services(
        vacancy=vacancy,
        rewrite_response=rewrite_response,
        plan_response=RewritePlanResponse(plan=plan),
    )

    result = run_cv_generation(candidate, evidence, "vacancy text", services)

    assert len(result.provenance.bullets) == 1
    provenance = result.provenance.bullets[0]
    assert provenance.evidence_id == "ev-1"
    assert provenance.original_text == "Original evidence text."
    assert provenance.rewritten_text == "Sharpened wording."
    assert provenance.action == "rewrite"
    assert [item.id for item in result.provenance.unused_evidence] == ["ev-2"]


def test_run_cv_generation_passes_the_rewrite_plan_into_the_bullet_rewrite_request():
    candidate = Candidate(name="Ada")
    evidence = [Evidence(id="ev-1", text="Some evidence.")]
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    plan = RewritePlan(
        actions=[RewriteAction(evidence_id="ev-1", action="keep", reason="Strong as-is.")],
        priority_order=["ev-1"],
    )
    services = make_services(
        vacancy=vacancy,
        rewrite_response=rewrite_response,
        plan_response=RewritePlanResponse(plan=plan),
    )

    run_cv_generation(candidate, evidence, "vacancy text", services)

    # ev-1 is unlocked, so nothing gets filtered out of the plan it receives.
    assert services.bullet_rewriter.last_request.plan == plan


# ----- run_cv_generation: Quality Recheck stage -----------------------------


def test_run_cv_generation_sends_the_bullet_rewriters_output_to_quality_recheck():
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    vacancy = Vacancy(raw_text="jd", requirements=[Requirement(text="Python")])
    rewrite_response = RewriteBulletsResponse(
        cv=CVProjection(
            summary="Raw summary.",
            experience=[
                TailoredExperience(
                    experience_id="exp-1",
                    bullets=[TailoredBullet(text="Raw bullet.", evidence_id="ev-1")],
                )
            ],
        )
    )
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    run_cv_generation(candidate, [], "vacancy text", services)

    assert services.quality_recheck.last_request.cv == rewrite_response.cv
    assert services.quality_recheck.last_request.requirements == vacancy.requirements


def test_run_cv_generation_uses_the_quality_rechecks_output_not_the_raw_rewrite():
    # The whole point of the stage: what ends up in the assembled CV is
    # whatever Quality Recheck returned, not Bullet Rewriting's own text —
    # otherwise the recheck stage would be wired in but have no effect.
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(
        cv=CVProjection(
            summary="Raw summary, demonstrating filler.",
            experience=[
                TailoredExperience(
                    experience_id="exp-1",
                    bullets=[TailoredBullet(text="Raw bullet, demonstrating filler.", evidence_id="ev-1")],
                )
            ],
        )
    )
    recheck_response = QualityRecheckResponse(
        cv=CVProjection(
            summary="Cleaned summary.",
            experience=[
                TailoredExperience(
                    experience_id="exp-1",
                    bullets=[TailoredBullet(text="Cleaned bullet.", evidence_id="ev-1")],
                )
            ],
        )
    )
    services = make_services(
        vacancy=vacancy, rewrite_response=rewrite_response, recheck_response=recheck_response
    )

    result = run_cv_generation(candidate, [], "vacancy text", services)

    assert result.assembled_cv.summary == "Cleaned summary."
    assert result.assembled_cv.experience[0].bullets == [
        TailoredBullet(text="Cleaned bullet.", evidence_id="ev-1")
    ]


def test_run_cv_generation_preserves_the_tailored_headline_through_quality_recheck():
    # 07_bullet_quality_recheck_v1.md only ever sees/edits summary+bullets —
    # it has no idea `headline` exists, so a real recheck response always
    # comes back with headline=None. Without re-attaching Bullet Rewriting's
    # own headline afterwards, every tailored headline would be silently
    # wiped by this later stage.
    candidate = Candidate(name="Ada", headline="Character Art Supervisor")
    vacancy = Vacancy(raw_text="jd", title="Senior 3D Character Artist", requirements=[])
    rewrite_response = RewriteBulletsResponse(
        cv=CVProjection(summary="...", headline="Senior Character Artist")
    )
    recheck_response = QualityRecheckResponse(cv=CVProjection(summary="Cleaned summary."))
    services = make_services(
        vacancy=vacancy, rewrite_response=rewrite_response, recheck_response=recheck_response
    )

    result = run_cv_generation(candidate, [], "vacancy text", services)

    assert result.assembled_cv.headline == "Senior Character Artist"


# ----- run_cv_generation: bullet locking (Phase 19) -------------------------


def test_run_cv_generation_excludes_locked_evidence_from_rewriting_but_not_planning():
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    evidence = [
        Evidence(id="ev-1", text="Unlocked bullet."),
        Evidence(
            id="ev-2",
            text="Locked bullet original.",
            experience_id="exp-1",
            locked=True,
            locked_text="Locked bullet, approved wording.",
        ),
    ]
    vacancy = Vacancy(raw_text="jd", requirements=[])
    plan = RewritePlan(
        actions=[
            RewriteAction(evidence_id="ev-1", action="keep", reason="Strong as-is."),
            RewriteAction(evidence_id="ev-2", action="rewrite", reason="Would sharpen this if unlocked."),
        ],
        priority_order=["ev-1", "ev-2"],
    )
    rewrite_response = RewriteBulletsResponse(
        cv=CVProjection(
            summary="...",
            experience=[
                TailoredExperience(
                    experience_id="exp-1",
                    bullets=[TailoredBullet(text="Unlocked bullet.", evidence_id="ev-1")],
                )
            ],
        )
    )
    services = make_services(
        vacancy=vacancy, rewrite_response=rewrite_response, plan_response=RewritePlanResponse(plan=plan)
    )

    result = run_cv_generation(candidate, evidence, "vacancy text", services)

    # Matching sees everything -- still real Gap-analysis signal.
    assert [item.id for item in services.matching.last_request.evidence] == ["ev-1", "ev-2"]
    # Planning also sees everything -- its priority_order is what keeps a
    # locked bullet from always landing last (see splice_locked_bullets).
    assert [item.id for item in services.rewrite_planner.last_request.evidence] == ["ev-1", "ev-2"]
    # Rewriting is the actual cost saving: it never sees the locked item,
    # and its plan's actions are filtered down to only what it *was* given
    # -- an action for evidence it has no text for would be confusing.
    assert [item.id for item in services.bullet_rewriter.last_request.evidence] == ["ev-1"]
    assert [a.evidence_id for a in services.bullet_rewriter.last_request.plan.actions] == ["ev-1"]

    # The locked bullet is spliced back into the assembled CV verbatim.
    bullets = result.assembled_cv.experience[0].bullets
    assert {b.text for b in bullets} == {"Unlocked bullet.", "Locked bullet, approved wording."}


def test_run_cv_generation_orders_a_locked_bullet_by_the_plans_priority_not_always_last():
    # The real gap this pins: locking is something a person does to a
    # wording they've already approved -- usually their *strongest*
    # content, not their weakest -- so it should never be forced to the
    # bottom of the list just because it skipped Bullet Rewriting.
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    evidence = [
        Evidence(id="ev-1", text="Weaker unlocked bullet."),
        Evidence(
            id="ev-2",
            text="Original.",
            experience_id="exp-1",
            locked=True,
            locked_text="Strongest, previously-approved bullet.",
        ),
    ]
    vacancy = Vacancy(raw_text="jd", requirements=[])
    plan = RewritePlan(
        actions=[RewriteAction(evidence_id="ev-1", action="keep", reason="Fine as-is.")],
        # ev-2 (locked) ranks ABOVE ev-1 -- the plan considers it more important.
        priority_order=["ev-2", "ev-1"],
    )
    rewrite_response = RewriteBulletsResponse(
        cv=CVProjection(
            summary="...",
            experience=[
                TailoredExperience(
                    experience_id="exp-1",
                    bullets=[TailoredBullet(text="Weaker unlocked bullet.", evidence_id="ev-1")],
                )
            ],
        )
    )
    services = make_services(
        vacancy=vacancy, rewrite_response=rewrite_response, plan_response=RewritePlanResponse(plan=plan)
    )

    result = run_cv_generation(candidate, evidence, "vacancy text", services)

    bullets = result.assembled_cv.experience[0].bullets
    assert [b.evidence_id for b in bullets] == ["ev-2", "ev-1"]


def test_run_cv_generation_marks_a_locked_bullets_provenance():
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    evidence = [
        Evidence(
            id="ev-1",
            text="Original text.",
            experience_id="exp-1",
            locked=True,
            locked_text="Approved wording.",
        )
    ]
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    result = run_cv_generation(candidate, evidence, "vacancy text", services)

    [provenance] = result.provenance.bullets
    assert provenance.evidence_id == "ev-1"
    assert provenance.original_text == "Original text."
    assert provenance.rewritten_text == "Approved wording."
    assert provenance.action == "keep"
    assert provenance.locked is True


def test_run_cv_generation_creates_a_tailored_experience_when_a_whole_role_is_locked():
    # The real bug app/bullet_locking.py:splice_locked_bullets guards
    # against: if EVERY Evidence item for a role is locked, the Bullet
    # Rewriting call never sees any evidence for that role at all and
    # returns no TailoredExperience for it -- without splicing creating
    # one, the role would silently vanish from the assembled CV (see
    # app/cv_assembler.py's `if tailored is None: continue`).
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    evidence = [
        Evidence(
            id="ev-1",
            text="Original.",
            experience_id="exp-1",
            locked=True,
            locked_text="Locked wording.",
        )
    ]
    vacancy = Vacancy(raw_text="jd", requirements=[])
    # The LLM had nothing left to say about exp-1 (its only evidence was
    # excluded) -- CVProjection.experience is empty.
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    result = run_cv_generation(candidate, evidence, "vacancy text", services)

    [entry] = result.assembled_cv.experience
    assert entry.experience_id == "exp-1"
    assert [b.text for b in entry.bullets] == ["Locked wording."]


# ----- run_cv_generation: GenerationTiming ----------------------------------


def test_run_cv_generation_returns_a_non_negative_duration_for_every_stage_and_the_total():
    candidate = Candidate(name="Ada")
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    result = run_cv_generation(candidate, [], "vacancy text", services)

    timing = result.timing
    assert timing.vacancy_analysis_seconds >= 0
    assert timing.matching_seconds >= 0
    assert timing.rewrite_planning_seconds >= 0
    assert timing.bullet_rewriting_seconds >= 0
    assert timing.quality_recheck_seconds >= 0
    assert timing.total_seconds >= 0


def test_run_cv_generation_total_duration_covers_at_least_the_sum_of_every_stage():
    # total_seconds wraps the *whole* call, not just the five LLM stages —
    # it must never be shorter than their sum (the local deterministic work
    # between them — locking partition/splice, assembly, provenance — only
    # ever adds to it).
    candidate = Candidate(name="Ada")
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    result = run_cv_generation(candidate, [], "vacancy text", services)

    timing = result.timing
    stage_sum = (
        timing.vacancy_analysis_seconds
        + timing.matching_seconds
        + timing.rewrite_planning_seconds
        + timing.bullet_rewriting_seconds
        + timing.quality_recheck_seconds
    )
    assert timing.total_seconds >= stage_sum


# ----- run_cv_generation: on_stage progress callback ------------------------


def test_run_cv_generation_reports_all_six_stages_in_order_before_they_start():
    candidate = Candidate(name="Ada")
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)
    calls: list[tuple[str, int, int]] = []

    run_cv_generation(candidate, [], "vacancy text", services, on_stage=lambda label, n, total: calls.append((label, n, total)))

    assert calls == [(label, index + 1, len(GENERATION_STAGES)) for index, label in enumerate(GENERATION_STAGES)]


def test_run_cv_generation_calls_the_vacancy_analysis_stage_before_analyzing():
    # on_stage fires *before* its stage runs, not after — a caller updating
    # a progress display from it should see "Analyzing job description"
    # while that call is actually in flight, not only once it's done.
    candidate = Candidate(name="Ada")
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)
    order: list[str] = []
    original_analyze = services.vacancy.analyze

    def tracking_analyze(text):
        order.append("analyze")
        return original_analyze(text)

    services.vacancy.analyze = tracking_analyze

    run_cv_generation(
        candidate, [], "vacancy text", services, on_stage=lambda label, n, total: order.append(f"stage:{label}")
    )

    assert order[0] == f"stage:{GENERATION_STAGES[0]}"
    assert order[1] == "analyze"


def test_run_cv_generation_defaults_to_a_no_op_on_stage_callback():
    # Every existing caller (tests above, run_pipeline.py) omits on_stage —
    # must not raise just because nobody's listening.
    candidate = Candidate(name="Ada")
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    result = run_cv_generation(candidate, [], "vacancy text", services)

    assert isinstance(result, PipelineResult)


# ----- run_cv_generation: existing_vacancy reuse -----------------------------


def test_run_cv_generation_reuses_existing_vacancy_when_raw_text_is_unchanged():
    candidate = Candidate(name="Ada")
    existing_vacancy = Vacancy(raw_text="jd", requirements=[Requirement(text="Python")], title="Engineer")
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    # No `vacancy=` fixture given to make_services -- services.vacancy is
    # `None`, so any attempt to actually re-parse would raise AttributeError,
    # proving the skip genuinely happened rather than just returning the
    # right-looking result by coincidence.
    services = make_services(rewrite_response=rewrite_response)

    result = run_cv_generation(candidate, [], "jd", services, existing_vacancy=existing_vacancy)

    assert result.vacancy == existing_vacancy
    assert result.vacancy.requirements == [Requirement(text="Python")]


def test_run_cv_generation_reports_the_reuse_label_for_stage_one_when_reusing():
    candidate = Candidate(name="Ada")
    existing_vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(rewrite_response=rewrite_response)
    calls: list[tuple[str, int, int]] = []

    run_cv_generation(
        candidate,
        [],
        "jd",
        services,
        existing_vacancy=existing_vacancy,
        on_stage=lambda label, n, total: calls.append((label, n, total)),
    )

    assert calls[0] == (VACANCY_REUSED_STAGE_LABEL, 1, len(GENERATION_STAGES))


def test_run_cv_generation_reparses_when_vacancy_text_differs_from_existing_vacancy():
    candidate = Candidate(name="Ada")
    existing_vacancy = Vacancy(raw_text="old jd", requirements=[Requirement(text="Old requirement")])
    fresh_vacancy = Vacancy(raw_text="new jd", requirements=[Requirement(text="New requirement")])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=fresh_vacancy, rewrite_response=rewrite_response)

    result = run_cv_generation(candidate, [], "new jd", services, existing_vacancy=existing_vacancy)

    assert result.vacancy == fresh_vacancy
    assert services.vacancy.last_raw_text == "new jd"


def test_run_cv_generation_reparses_when_no_existing_vacancy_is_given():
    candidate = Candidate(name="Ada")
    vacancy = Vacancy(raw_text="jd", requirements=[])
    rewrite_response = RewriteBulletsResponse(cv=CVProjection(summary="..."))
    services = make_services(vacancy=vacancy, rewrite_response=rewrite_response)

    result = run_cv_generation(candidate, [], "jd", services)  # existing_vacancy defaults to None

    assert result.vacancy == vacancy
    assert services.vacancy.last_raw_text == "jd"


# ----- run_gap_recheck (Phase 18) -------------------------------------------


def test_run_gap_recheck_calls_matching_with_the_given_requirements_and_full_experience():
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    evidence = [Evidence(id="ev-1", text="Did a thing")]
    requirements = [Requirement(text="5+ years Python")]
    match_result = MatchResult(missing_keywords=["Python"])
    services = make_services(match_response=MatchResponse(match_result=match_result))

    result = run_gap_recheck(candidate, evidence, requirements, set(), services)

    assert result == match_result
    assert services.matching.last_request.experience == candidate.experience
    assert services.matching.last_request.requirements == requirements
    assert services.matching.last_request.evidence == evidence


def test_run_gap_recheck_excludes_evidence_whose_bullet_was_toggled_off():
    candidate = Candidate(name="Ada")
    evidence = [
        Evidence(id="ev-1", text="Kept"),
        Evidence(id="ev-2", text="Excluded"),
    ]
    services = make_services(match_response=MatchResponse(match_result=MatchResult()))

    run_gap_recheck(candidate, evidence, [], {"ev-2"}, services)

    assert [item.id for item in services.matching.last_request.evidence] == ["ev-1"]


def test_run_gap_recheck_with_no_excluded_ids_behaves_like_a_full_recheck():
    candidate = Candidate(name="Ada")
    evidence = [Evidence(id="ev-1", text="Kept"), Evidence(id="ev-2", text="Also kept")]
    services = make_services(match_response=MatchResponse(match_result=MatchResult()))

    run_gap_recheck(candidate, evidence, [], set(), services)

    assert services.matching.last_request.evidence == evidence


def test_run_gap_recheck_passes_candidate_facts_to_the_matcher():
    candidate = Candidate(
        name="Ada",
        skills=[Skill(id="s1", name="Python")],
        technologies=[Technology(id="t1", name="Figma")],
        languages=[Language(id="l1", name="English", proficiency="C1")],
        certifications=[Certification(id="c1", name="AWS Solutions Architect", issuer="Amazon", date="2022")],
        education=[Education(id="edu-1", institution="Altai State Technical University", degree="Software Engineering")],
        contacts=[ContactItem(id="ct1", label="Relocation", value="Willing to relocate")],
    )
    services = make_services(match_response=MatchResponse(match_result=MatchResult()))

    run_gap_recheck(candidate, [], [], set(), services)

    assert services.matching.last_request.candidate_skills == ["Python"]
    assert services.matching.last_request.candidate_technologies == ["Figma"]
    assert services.matching.last_request.candidate_languages == ["English (C1)"]
    assert services.matching.last_request.candidate_certifications == [
        "AWS Solutions Architect — Amazon, 2022"
    ]
    assert services.matching.last_request.candidate_education == [
        "Altai State Technical University — Software Engineering"
    ]
    assert services.matching.last_request.candidate_contacts == [
        "Relocation: Willing to relocate"
    ]


def test_run_gap_recheck_filters_email_and_phone_contacts_out_of_the_matcher_request():
    # Same filtering as run_cv_generation's own version of this test — the
    # recheck path (run on every autosave-triggered gap check, not just
    # once at generation) is exactly where the exposure this filter
    # closes would otherwise repeat most often.
    candidate = Candidate(
        name="Ada",
        contacts=[
            ContactItem(id="c1", label="Relocation", value="Willing to relocate"),
            ContactItem(id="c2", label="Email", value="ada@example.com"),
            ContactItem(id="c3", label="Phone", value="+1 (555) 123-4567"),
        ],
    )
    services = make_services(match_response=MatchResponse(match_result=MatchResult()))

    run_gap_recheck(candidate, [], [], set(), services)

    assert services.matching.last_request.candidate_contacts == [
        "Relocation: Willing to relocate"
    ]


def test_run_gap_recheck_overrides_evidence_text_with_the_edited_bullet_text():
    # Reported directly: rewriting a bullet by hand in the A4 editor (to
    # cover a gap the AI's own wording missed) was silently ignored by a
    # subsequent re-check, because it always matched against the stored
    # Evidence text, never what the document currently says.
    candidate = Candidate(name="Ada")
    evidence = [Evidence(id="ev-1", text="Did a thing"), Evidence(id="ev-2", text="Untouched")]
    services = make_services(match_response=MatchResponse(match_result=MatchResult()))

    run_gap_recheck(
        candidate, evidence, [], set(), services, edited_bullet_text={"ev-1": "Did a thing, using AI tools daily"}
    )

    sent = {item.id: item.text for item in services.matching.last_request.evidence}
    assert sent == {"ev-1": "Did a thing, using AI tools daily", "ev-2": "Untouched"}
    # The caller's own Evidence objects are never mutated.
    assert evidence[0].text == "Did a thing"


def test_run_gap_recheck_ignores_edited_text_for_an_excluded_bullet():
    candidate = Candidate(name="Ada")
    evidence = [Evidence(id="ev-1", text="Original")]
    services = make_services(match_response=MatchResponse(match_result=MatchResult()))

    run_gap_recheck(
        candidate, evidence, [], {"ev-1"}, services, edited_bullet_text={"ev-1": "Edited but excluded"}
    )

    assert services.matching.last_request.evidence == []


def test_run_gap_recheck_folds_manual_bullet_text_into_synthetic_evidence():
    # A hand-typed bullet (no evidence_id at all) can't be represented by
    # edited_bullet_text's id-keyed override — it gets its own synthetic,
    # unpersisted Evidence item instead so its content still reaches the
    # matcher.
    candidate = Candidate(name="Ada")
    services = make_services(match_response=MatchResponse(match_result=MatchResult()))

    run_gap_recheck(
        candidate, [], [], set(), services, manual_bullet_text=["Explored new AI-assisted workflows weekly"]
    )

    sent = services.matching.last_request.evidence
    assert len(sent) == 1
    assert sent[0].text == "Explored new AI-assisted workflows weekly"


def test_run_gap_recheck_uses_document_skills_and_technologies_when_given():
    # A person can add/remove a skill line directly in the draft without
    # touching their saved Candidate profile — the recheck should see what
    # the document currently shows, not the stale profile list.
    candidate = Candidate(name="Ada", skills=[Skill(id="s1", name="Python")])
    services = make_services(match_response=MatchResponse(match_result=MatchResult()))

    run_gap_recheck(
        candidate, [], [], set(), services, document_skills=["Python", "AI Tools"], document_technologies=[]
    )

    assert services.matching.last_request.candidate_skills == ["Python", "AI Tools"]
    assert services.matching.last_request.candidate_technologies == []


def test_run_gap_recheck_falls_back_to_the_profile_when_document_skills_omitted():
    candidate = Candidate(name="Ada", skills=[Skill(id="s1", name="Python")])
    services = make_services(match_response=MatchResponse(match_result=MatchResult()))

    run_gap_recheck(candidate, [], [], set(), services)

    assert services.matching.last_request.candidate_skills == ["Python"]


# ----- run_skill_evidence_relink --------------------------------------------


def test_run_skill_evidence_relink_applies_returned_links_via_update_skill_and_technology():
    candidate = Candidate(
        name="Ada",
        skills=[Skill(id="skill-1", name="Python"), Skill(id="skill-2", name="Leadership")],
        technologies=[Technology(id="tech-1", name="Django")],
    )
    evidence = [Evidence(id="ev-1", text="Led a Python team")]
    relink_response = RelinkSkillEvidenceResponse(
        skills=[
            SkillEvidenceLink(id="skill-1", evidence_ids=["ev-1"]),
            SkillEvidenceLink(id="skill-2", evidence_ids=["ev-1"]),
        ],
        technologies=[SkillEvidenceLink(id="tech-1", evidence_ids=["ev-1"])],
    )
    services = make_services(relink_response=relink_response)
    candidate_service = services.candidate_registry.service_for("cand-1")

    skill_count, technology_count = run_skill_evidence_relink(candidate_service, candidate, evidence, services)

    assert skill_count == 2
    assert technology_count == 1
    assert candidate_service.updated_skills == [("skill-1", ["ev-1"]), ("skill-2", ["ev-1"])]
    assert candidate_service.updated_technologies == [("tech-1", ["ev-1"])]


def test_run_skill_evidence_relink_applies_an_empty_list_when_the_llm_finds_no_evidence():
    candidate = Candidate(name="Ada", skills=[Skill(id="skill-1", name="Communication")])
    relink_response = RelinkSkillEvidenceResponse(skills=[SkillEvidenceLink(id="skill-1", evidence_ids=[])])
    services = make_services(relink_response=relink_response)
    candidate_service = services.candidate_registry.service_for("cand-1")

    run_skill_evidence_relink(candidate_service, candidate, [], services)

    assert candidate_service.updated_skills == [("skill-1", [])]


def test_run_skill_evidence_relink_passes_the_candidates_skills_technologies_and_evidence_to_the_linker():
    candidate = Candidate(
        name="Ada",
        skills=[Skill(id="skill-1", name="Python")],
        technologies=[Technology(id="tech-1", name="Django")],
    )
    evidence = [Evidence(id="ev-1", text="Did a thing")]
    services = make_services()
    candidate_service = services.candidate_registry.service_for("cand-1")

    run_skill_evidence_relink(candidate_service, candidate, evidence, services)

    assert services.skill_evidence_linker.last_request.skills == candidate.skills
    assert services.skill_evidence_linker.last_request.technologies == candidate.technologies
    assert services.skill_evidence_linker.last_request.evidence == evidence
