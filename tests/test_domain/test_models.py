import pytest
from pydantic import ValidationError as PydanticValidationError

from domain.models import (
    AssembledCV,
    AssembledExperienceEntry,
    Award,
    Candidate,
    Certification,
    ContactItem,
    CVProjection,
    Education,
    Evidence,
    Experience,
    ExperienceProject,
    Gap,
    Language,
    MatchResult,
    PortfolioLink,
    PrintDocumentBlock,
    PrintDocumentEntry,
    Project,
    Publication,
    Requirement,
    RequirementMatch,
    RewriteAction,
    RewritePlan,
    Skill,
    TailoredBullet,
    TailoredExperience,
    Technology,
    TextRun,
    Vacancy,
    VolunteerExperience,
)


def test_candidate_defaults_to_empty_profile_sections():
    candidate = Candidate(name="Ada Lovelace")

    assert candidate.headline is None
    assert candidate.summary is None
    assert candidate.contacts == []
    assert candidate.experience == []
    assert candidate.education == []
    assert candidate.skills == []
    assert candidate.languages == []
    assert candidate.certifications == []
    assert candidate.projects == []


def test_candidate_round_trips_nested_entries():
    candidate = Candidate(
        name="Ada Lovelace",
        headline="Analytical Engineer",
        summary="Analytical engineer with a track record of mechanical computation.",
        contacts=[
            ContactItem(id="contact-1", label="Email", value="ada@example.com"),
            ContactItem(id="contact-2", label="Location", value="London, UK"),
        ],
        experience=[
            Experience(
                id="exp-1",
                company="Analytical Engines Ltd",
                position="Lead Engineer",
                period="1840-1845",
                responsibilities=["Design punched-card programs"],
                achievements=["Wrote the first published algorithm"],
            )
        ],
        education=[
            Education(
                id="edu-1",
                institution="Self-taught",
                degree=None,
                field="Mathematics",
                period="1830-1840",
            )
        ],
        skills=[Skill(id="skill-1", name="Analytical Engine programming")],
        languages=[Language(id="lang-1", name="English", proficiency="Native")],
        certifications=[
            Certification(id="cert-1", name="Royal Society Fellow", issuer="Royal Society", date="1835")
        ],
        projects=[
            Project(
                id="proj-1",
                name="Analytical Engine programs",
                description="Punched-card program design",
                url="https://example.com/analytical-engine",
            )
        ],
    )

    dumped = candidate.model_dump_json()
    restored = Candidate.model_validate_json(dumped)

    assert restored == candidate


def test_experience_defaults_responsibilities_and_achievements_to_empty_lists():
    experience = Experience(id="exp-1", company="Acme", position="Engineer")

    assert experience.responsibilities == []
    assert experience.achievements == []
    assert experience.projects == []


def test_experience_round_trips_nested_projects():
    experience = Experience(
        id="exp-1",
        company="Agency Co",
        position="Consultant",
        period="2019-2022",
        projects=[
            ExperienceProject(
                id="exp-1-proj-1",
                name="Client A Migration",
                period="2019-2020",
                achievements=["Migrated legacy billing system"],
            ),
            ExperienceProject(id="exp-1-proj-2", name="Client B Rollout"),
        ],
    )

    restored = Experience.model_validate_json(experience.model_dump_json())

    assert restored == experience
    assert restored.projects[0].achievements == ["Migrated legacy billing system"]
    assert restored.projects[1].achievements == []


def test_experience_project_responsibilities_default_to_empty_list():
    project = ExperienceProject(id="exp-1-proj-1", name="Client A Migration")

    assert project.responsibilities == []

    with_responsibilities = ExperienceProject(
        id="exp-1-proj-2", name="Client B Rollout", responsibilities=["Owned the rollout plan"]
    )
    assert with_responsibilities.responsibilities == ["Owned the rollout plan"]


def test_experience_company_url_defaults_to_none():
    # Post-4.10 follow-up — closes a real ingestion gap: a source PDF
    # hyperlinking a company name to its own site (rather than writing the
    # URL out as visible text) had nowhere to put that URL at all.
    experience = Experience(id="exp-1", company="Acme", position="Engineer")

    assert experience.company_url is None

    with_url = Experience(
        id="exp-2", company="Acme", position="Engineer", company_url="https://acme.example/"
    )
    assert with_url.company_url == "https://acme.example/"


def test_experience_project_url_defaults_to_none():
    project = ExperienceProject(id="exp-1-proj-1", name="Client A Migration")

    assert project.url is None

    with_url = ExperienceProject(
        id="exp-1-proj-2", name="Client B Rollout", url="https://client-b.example/"
    )
    assert with_url.url == "https://client-b.example/"


def test_evidence_experience_and_project_links_default_to_none():
    evidence = Evidence(id="ev-1", text="Migrated legacy billing system")

    assert evidence.source_context is None
    assert evidence.experience_id is None
    assert evidence.experience_project_id is None


def test_evidence_can_link_to_an_experience_project():
    evidence = Evidence(
        id="ev-1",
        text="Migrated legacy billing system",
        experience_id="exp-1",
        experience_project_id="exp-1-proj-1",
    )

    assert evidence.experience_id == "exp-1"
    assert evidence.experience_project_id == "exp-1-proj-1"


def test_experience_is_gap_defaults_to_false():
    experience = Experience(id="exp-1", company="Acme", position="Engineer")

    assert experience.is_gap is False


def test_experience_company_is_optional_for_gaps_not_tied_to_an_employer():
    gap = Experience(id="exp-2", position="Career Break", period="2019-2020", is_gap=True)

    assert gap.company is None
    assert gap.is_gap is True


def test_assembled_experience_entry_defaults():
    entry = AssembledExperienceEntry(position="Maternity Leave")

    assert entry.company is None
    assert entry.company_url is None
    assert entry.period is None
    assert entry.bullets == []
    assert entry.is_gap is False
    assert entry.project_urls == {}


def test_language_proficiency_defaults_to_none():
    language = Language(id="lang-1", name="French")

    assert language.proficiency is None


def test_certification_issuer_and_date_default_to_none():
    certification = Certification(id="cert-1", name="PMP")

    assert certification.issuer is None
    assert certification.date is None


def test_contact_item_requires_label_and_value():
    contact = ContactItem(id="contact-1", label="LinkedIn", value="linkedin.com/in/ada")

    assert contact.label == "LinkedIn"
    assert contact.value == "linkedin.com/in/ada"


def test_project_description_and_url_default_to_none():
    project = Project(id="proj-1", name="Side Project")

    assert project.description is None
    assert project.url is None


def test_portfolio_link_description_defaults_to_none():
    link = PortfolioLink(id="link-1", url="https://artstation.com/ada")

    assert link.description is None


def test_candidate_and_assembled_cv_default_portfolio_links_to_empty_list():
    candidate = Candidate(name="Ada")
    cv = AssembledCV(name="Ada", summary="A summary.")

    assert candidate.portfolio_links == []
    assert cv.portfolio_links == []


def test_experience_location_defaults_to_none():
    experience = Experience(id="exp-1", company="Acme", position="Engineer")

    assert experience.location is None

    with_location = Experience(id="exp-2", company="Acme", position="Engineer", location="Berlin")
    assert with_location.location == "Berlin"


def test_skill_proficiency_defaults_to_none():
    skill = Skill(id="skill-1", name="Python")

    assert skill.proficiency is None

    with_proficiency = Skill(id="skill-2", name="Python", proficiency="Advanced")
    assert with_proficiency.proficiency == "Advanced"


def test_skill_evidence_ids_defaults_to_empty_list_and_round_trips():
    skill = Skill(id="skill-1", name="Python")
    assert skill.evidence_ids == []

    linked = Skill(id="skill-2", name="Leadership", evidence_ids=["ev-1", "ev-2"])
    assert linked.evidence_ids == ["ev-1", "ev-2"]


def test_award_optional_fields_default_to_none():
    award = Award(id="award-1", name="Best in Show")

    assert award.issuer is None
    assert award.date is None


def test_publication_optional_fields_default_to_none():
    publication = Publication(id="pub-1", title="Scaling LiveOps")

    assert publication.venue is None
    assert publication.date is None
    assert publication.url is None


def test_volunteer_experience_optional_fields_default_to_none():
    entry = VolunteerExperience(id="vol-1", organization="Code.org", role="Mentor")

    assert entry.period is None
    assert entry.description is None


def test_technology_optional_fields_default_to_none():
    tech = Technology(id="tech-1", name="Python")

    assert tech.category is None
    assert tech.proficiency is None
    assert tech.evidence_ids == []


def test_technology_evidence_ids_round_trips():
    tech = Technology(id="tech-1", name="Kubernetes", evidence_ids=["ev-1"])
    assert tech.evidence_ids == ["ev-1"]


def test_candidate_and_assembled_cv_default_new_collections_to_empty():
    candidate = Candidate(name="Ada")
    cv = AssembledCV(name="Ada", summary="A summary.")

    for collection in (
        candidate.employment_types_sought,
        candidate.awards,
        candidate.publications,
        candidate.volunteer_experience,
        candidate.technologies,
    ):
        assert collection == []
    for collection in (
        cv.employment_types_sought,
        cv.awards,
        cv.publications,
        cv.volunteer_experience,
        cv.technologies,
    ):
        assert collection == []


def test_candidate_employment_types_sought_rejects_invalid_value():
    with pytest.raises(PydanticValidationError):
        Candidate(name="Ada", employment_types_sought=["Gig work"])


def test_requirement_keywords_defaults_to_empty_list():
    requirement = Requirement(text="5+ years Python")

    assert requirement.keywords == []


def test_requirement_priority_defaults_to_required():
    # Backward compatibility: a Vacancy persisted before this field existed
    # must not have its requirements silently treated as optional.
    requirement = Requirement(text="5+ years Python")

    assert requirement.priority == "required"


def test_requirement_priority_accepts_nice_to_have():
    requirement = Requirement(text="B2 English", priority="nice_to_have")

    assert requirement.priority == "nice_to_have"


def test_requirement_priority_rejects_invalid_value():
    with pytest.raises(PydanticValidationError):
        Requirement(text="5+ years Python", priority="optional")


def test_vacancy_round_trips_with_requirements_and_keywords():
    vacancy = Vacancy(
        title="Senior Engineer",
        company="Acme Corp",
        raw_text="We are hiring a Senior Engineer...",
        requirements=[Requirement(text="5+ years Python", keywords=["Python"])],
        keywords=["Python", "SQL"],
    )

    restored = Vacancy.model_validate_json(vacancy.model_dump_json())

    assert restored == vacancy


def test_vacancy_title_and_company_default_to_none():
    vacancy = Vacancy(raw_text="some JD text")

    assert vacancy.title is None
    assert vacancy.company is None
    assert vacancy.requirements == []
    assert vacancy.keywords == []


def test_tailored_experience_bullets_defaults_to_empty_list():
    tailored = TailoredExperience(experience_id="exp-1")

    assert tailored.bullets == []


def test_tailored_bullet_project_defaults_to_none():
    bullet = TailoredBullet(text="Did a thing")

    assert bullet.project is None


def test_tailored_bullet_text_collapses_embedded_whitespace():
    # Caught live: a Gemini response for a tougher, more technical vacancy
    # came back with leading blank lines in a bullet/summary. Every
    # renderer downstream (app/cv_pdf.py, app/cv_markdown.py) assumes one
    # of these fields is exactly one line — app/cv_pdf.py:compute_page_breaks
    # raised IndexError reading past a line_ids list sized for one line
    # once such a value's embedded newlines turned it into several. See
    # domain.models._collapse_to_single_line's docstring for the full story.
    bullet = TailoredBullet(text="  Line one\nLine two  ")

    assert bullet.text == "Line one Line two"


def test_cv_projection_summary_collapses_embedded_whitespace():
    projection = CVProjection(summary="\n\n\n\nActual summary text.")

    assert projection.summary == "Actual summary text."


def test_cv_projection_headline_defaults_to_none():
    # app/cv_assembler.py:assemble_cv relies on this to fall back to
    # Candidate.headline for build_untailored_projection's zero-AI path.
    projection = CVProjection(summary="A summary.")

    assert projection.headline is None


def test_cv_projection_headline_collapses_embedded_whitespace():
    projection = CVProjection(summary="A summary.", headline="\n\nSenior Character Artist\n")

    assert projection.headline == "Senior Character Artist"


def test_cv_projection_round_trips_tailored_experience():
    projection = CVProjection(
        summary="A summary.",
        experience=[
            TailoredExperience(
                experience_id="exp-1",
                bullets=[
                    TailoredBullet(text="Did a thing"),
                    TailoredBullet(text="Shipped client A migration", project="Client A Migration"),
                ],
            )
        ],
        skills=["Python"],
    )

    restored = CVProjection.model_validate_json(projection.model_dump_json())

    assert restored == projection


def test_assembled_cv_round_trips_full_structure():
    cv = AssembledCV(
        name="Ada Lovelace",
        headline="Analytical Engineer",
        contacts=[
            ContactItem(id="contact-1", label="Email", value="ada@example.com"),
            ContactItem(id="contact-2", label="Phone", value="+44 1234"),
        ],
        summary="A summary.",
        experience=[
            AssembledExperienceEntry(
                company="Analytical Engines Ltd",
                position="Lead Engineer",
                period="1840-1845",
                bullets=[TailoredBullet(text="Wrote the first published algorithm")],
            )
        ],
        education=[Education(id="edu-1", institution="Self-taught", field="Mathematics")],
        skills=[Skill(id="skill-1", name="Mathematics")],
        languages=[Language(id="lang-1", name="English", proficiency="Native")],
        certifications=[Certification(id="cert-1", name="Royal Society Fellow")],
        projects=[Project(id="proj-1", name="Analytical Engine programs")],
    )

    restored = AssembledCV.model_validate_json(cv.model_dump_json())

    assert restored == cv


def test_assembled_cv_defaults_optional_sections_to_empty():
    cv = AssembledCV(name="Ada Lovelace", summary="A summary.")

    assert cv.headline is None
    assert cv.contacts == []
    assert cv.experience == []
    assert cv.education == []
    assert cv.skills == []
    assert cv.languages == []
    assert cv.certifications == []
    assert cv.projects == []


def test_requirement_match_accepts_valid_strengths():
    match = RequirementMatch(
        requirement_text="5+ years Python", evidence_ids=["ev-1", "ev-2"], strength="high"
    )

    assert match.evidence_ids == ["ev-1", "ev-2"]
    assert match.strength == "high"


def test_requirement_match_rejects_invalid_strength():
    with pytest.raises(PydanticValidationError):
        RequirementMatch(requirement_text="5+ years Python", strength="extremely high")


def test_requirement_match_evidence_ids_defaults_to_empty_list():
    match = RequirementMatch(requirement_text="5+ years Python", strength="low")

    assert match.evidence_ids == []


def test_gap_round_trips():
    gap = Gap(
        requirement_text="AWS certification",
        description="No cloud certification found.",
        severity="high",
        suggested_action="If you hold an AWS certification, add it to your Certifications section.",
    )

    restored = Gap.model_validate_json(gap.model_dump_json())

    assert restored == gap


def test_gap_suggested_action_defaults_to_none():
    gap = Gap(requirement_text="AWS certification", description="No cloud certification found.", severity="low")

    assert gap.suggested_action is None


def test_gap_rejects_invalid_severity():
    with pytest.raises(PydanticValidationError):
        Gap(requirement_text="AWS certification", description="No cloud certification found.", severity="urgent")


def test_match_result_defaults_to_empty():
    result = MatchResult()

    assert result.matches == []
    assert result.gaps == []
    assert result.missing_keywords == []


def test_match_result_round_trips_matches_and_gaps():
    result = MatchResult(
        matches=[
            RequirementMatch(requirement_text="5+ years Python", evidence_ids=["ev-1"], strength="high")
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

    restored = MatchResult.model_validate_json(result.model_dump_json())

    assert restored == result


def test_rewrite_action_defaults_target_keywords_and_new_angle():
    action = RewriteAction(evidence_id="ev-1", action="keep", reason="Strongly relevant as-is.")

    assert action.target_keywords == []
    assert action.new_angle is None


def test_rewrite_action_rejects_invalid_action():
    with pytest.raises(PydanticValidationError):
        RewriteAction(evidence_id="ev-1", action="merge", reason="Combine with ev-2.")


def test_rewrite_plan_defaults_to_empty():
    plan = RewritePlan()

    assert plan.actions == []
    assert plan.priority_order == []


def test_rewrite_plan_round_trips():
    plan = RewritePlan(
        actions=[
            RewriteAction(
                evidence_id="ev-1",
                action="rewrite",
                reason="Weak phrasing, strong underlying fact.",
                target_keywords=["Python"],
                new_angle="Emphasize ownership.",
            ),
            RewriteAction(evidence_id="ev-2", action="remove", reason="Irrelevant to this role."),
        ],
        priority_order=["ev-1", "ev-2"],
    )

    restored = RewritePlan.model_validate_json(plan.model_dump_json())

    assert restored == plan


def test_print_document_block_evidence_id_defaults_to_none():
    block = PrintDocumentBlock(id="b1", text="A bullet with no link.", included=True)

    assert block.evidence_id is None


def test_print_document_block_evidence_id_round_trips():
    # Regression: this field was missing entirely until Phase 20b's
    # follow-up, so the frontend's DocumentBlock.evidence_id (see
    # structuredDocument.ts) was silently dropped by Pydantic on every
    # save (an unrecognized field is ignored, not an error) — the
    # AI-edited bullet Sparkles marker never had anything to key its
    # lookup on, from the very first draft save onward, not just on a
    # reopen. Confirmed here at the model level: a JSON payload shaped
    # exactly like what the frontend actually sends must preserve
    # evidence_id through a full serialize/deserialize round trip.
    block = PrintDocumentBlock.model_validate_json(
        '{"id": "b1", "text": "A rewritten bullet.", "included": true, "evidence_id": "ev-1"}'
    )

    assert block.evidence_id == "ev-1"
    assert PrintDocumentBlock.model_validate_json(block.model_dump_json()).evidence_id == "ev-1"


def test_print_document_entry_bullets_preserve_evidence_id():
    entry = PrintDocumentEntry(
        id="exp-1",
        text="Engineer — Acme",
        included=True,
        bullets=[
            PrintDocumentBlock(id="b1", text="Shipped a feature", included=True, evidence_id="ev-1"),
            PrintDocumentBlock(id="b2", text="Hand-typed, no link", included=True),
        ],
    )

    restored = PrintDocumentEntry.model_validate_json(entry.model_dump_json())

    assert restored.bullets[0].evidence_id == "ev-1"
    assert restored.bullets[1].evidence_id is None


# ----- Phase 25: TextRun / PrintDocumentBlock.runs / .alignment -----------


def test_text_run_defaults_to_no_styling():
    run = TextRun(text="Plain")

    assert run.bold is False
    assert run.italic is False
    assert run.underline is False
    assert run.link is None


def test_print_document_block_runs_and_alignment_default_to_none():
    block = PrintDocumentBlock(id="b1", text="A bullet with no explicit runs.", included=True)

    assert block.runs is None
    assert block.alignment is None


def test_print_document_block_runs_and_alignment_round_trip():
    # Same regression shape as evidence_id above: a field that's silently
    # dropped on save (Pydantic ignores unrecognized fields by default)
    # would disable Phase 31's rich-text formatting from the very first
    # save, not just on reopen — confirmed here at the model level.
    block = PrintDocumentBlock(
        id="b1",
        text="Shipped a rewritten feature",
        included=True,
        alignment="center",
        runs=[
            TextRun(text="Shipped a ", bold=False),
            TextRun(text="rewritten", bold=True, italic=True),
            TextRun(text=" feature", link="https://example.com"),
        ],
    )

    restored = PrintDocumentBlock.model_validate_json(block.model_dump_json())

    assert restored.alignment == "center"
    assert restored.runs == block.runs
    assert restored.runs[1].bold is True
    assert restored.runs[1].italic is True
    assert restored.runs[2].link == "https://example.com"


def test_print_document_entry_bullets_preserve_runs_and_alignment():
    entry = PrintDocumentEntry(
        id="exp-1",
        text="Engineer — Acme",
        included=True,
        bullets=[
            PrintDocumentBlock(
                id="b1",
                text="Owned the backend",
                included=True,
                alignment="right",
                runs=[TextRun(text="Owned the backend", underline=True)],
            ),
            PrintDocumentBlock(id="b2", text="No runs at all", included=True),
        ],
    )

    restored = PrintDocumentEntry.model_validate_json(entry.model_dump_json())

    assert restored.bullets[0].alignment == "right"
    assert restored.bullets[0].runs == [TextRun(text="Owned the backend", underline=True)]
    assert restored.bullets[1].runs is None
    assert restored.bullets[1].alignment is None
