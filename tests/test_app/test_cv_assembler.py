import pytest

from app.cv_assembler import _rank_by_category, assemble_cv, build_untailored_projection
from app.errors import ValidationError
from domain.models import (
    Award,
    Candidate,
    Certification,
    ContactItem,
    CVProjection,
    Education,
    Experience,
    ExperienceProject,
    Language,
    PortfolioLink,
    Project,
    Publication,
    Skill,
    Technology,
    TailoredBullet,
    TailoredExperience,
    VolunteerExperience,
)


def make_candidate() -> Candidate:
    return Candidate(
        name="Ada Lovelace",
        headline="Analytical Engineer",
        employment_types_sought=["Full-time", "Contract"],
        contacts=[
            ContactItem(id="contact-1", label="Email", value="ada@example.com"),
            ContactItem(id="contact-2", label="Phone", value="+44 1234"),
        ],
        experience=[
            Experience(
                id="exp-1",
                company="Analytical Engines Ltd",
                position="Lead Engineer",
                period="1840-1845",
                location="London",
                responsibilities=["Design punched-card programs"],
                achievements=["Wrote the first published algorithm"],
            ),
            Experience(
                id="exp-2",
                position="Career Break",
                period="1838-1840",
                is_gap=True,
            ),
            Experience(id="exp-3", company="Royal Society", position="Fellow", period="1835-1838"),
        ],
        volunteer_experience=[
            VolunteerExperience(id="vol-1", organization="Code.org", role="Mentor")
        ],
        education=[Education(id="edu-1", institution="Self-taught", field="Mathematics")],
        skills=[Skill(id="skill-1", name="Analytical Engine programming")],
        languages=[Language(id="lang-1", name="English", proficiency="Native")],
        technologies=[Technology(id="tech-1", name="Difference Engine")],
        certifications=[Certification(id="cert-1", name="Royal Society Fellow")],
        awards=[Award(id="award-1", name="Best in Show")],
        projects=[Project(id="proj-1", name="Analytical Engine programs", url="https://example.com")],
        publications=[Publication(id="pub-1", title="Sketch of the Analytical Engine")],
        portfolio_links=[PortfolioLink(id="link-1", url="https://example.com/portfolio")],
    )


def test_assemble_cv_prefers_the_tailored_headline_over_the_candidates_own():
    candidate = make_candidate()
    projection = CVProjection(summary="...", headline="Senior Analytical Engineer")

    assembled = assemble_cv(candidate, projection)

    assert assembled.headline == "Senior Analytical Engineer"


def test_assemble_cv_falls_back_to_the_candidates_headline_when_untailored():
    # build_untailored_projection's zero-AI path leaves headline unset.
    candidate = make_candidate()
    projection = build_untailored_projection(candidate)

    assembled = assemble_cv(candidate, projection)

    assert assembled.headline == "Analytical Engineer"


def test_assemble_cv_copies_company_url_and_project_urls_onto_the_assembled_entry():
    # Post-4.10 follow-up — facts, merged in deterministically like every
    # other Experience fact, never asked of the Bullet Rewriting LLM call.
    candidate = Candidate(
        name="Ada Lovelace",
        experience=[
            Experience(
                id="exp-1",
                company="Analytical Engines Ltd",
                company_url="https://analytical-engines.example/",
                position="Lead Engineer",
                projects=[
                    ExperienceProject(id="exp-1-proj-1", name="Difference Engine No. 2", url="https://de2.example/"),
                    ExperienceProject(id="exp-1-proj-2", name="Undocumented Project"),  # no url
                ],
            )
        ],
    )
    projection = CVProjection(summary="...")

    assembled = assemble_cv(candidate, projection)

    entry = assembled.experience[0]
    assert entry.company_url == "https://analytical-engines.example/"
    assert entry.project_urls == {"Difference Engine No. 2": "https://de2.example/"}


def test_assemble_cv_copies_company_url_for_gap_entries_too():
    candidate = Candidate(
        name="Ada Lovelace",
        experience=[
            Experience(
                id="exp-1",
                company="Analytical Engines Ltd",
                company_url="https://analytical-engines.example/",
                position="Sabbatical",
                is_gap=True,
            )
        ],
    )
    projection = CVProjection(summary="...")

    assembled = assemble_cv(candidate, projection)

    assert assembled.experience[0].company_url == "https://analytical-engines.example/"


def test_assemble_cv_merges_candidate_facts_with_tailored_content():
    candidate = make_candidate()
    projection = CVProjection(
        summary="A pioneering analytical engineer.",
        experience=[
            TailoredExperience(
                experience_id="exp-1",
                bullets=[TailoredBullet(text="Wrote the first published algorithm")],
            )
        ],
        skills=["Analytical Engine programming"],
    )

    assembled = assemble_cv(candidate, projection)

    assert assembled.name == "Ada Lovelace"
    assert assembled.language == "en"
    assert assembled.headline == "Analytical Engineer"
    assert assembled.employment_types_sought == ["Full-time", "Contract"]
    assert assembled.contacts == candidate.contacts
    assert assembled.summary == "A pioneering analytical engineer."
    assert [s.name for s in assembled.skills] == ["Analytical Engine programming"]
    assert assembled.experience[0].location == "London"
    # Facts (education/languages/certifications/projects/...) pass through unchanged.
    assert assembled.volunteer_experience == candidate.volunteer_experience
    assert assembled.education == candidate.education
    assert assembled.languages == candidate.languages
    assert assembled.technologies == candidate.technologies
    assert assembled.certifications == candidate.certifications
    assert assembled.awards == candidate.awards
    assert assembled.projects == candidate.projects
    assert assembled.publications == candidate.publications
    assert assembled.portfolio_links == candidate.portfolio_links


def test_assemble_cv_copies_a_non_default_language():
    candidate = make_candidate().model_copy(update={"language": "ru"})
    projection = CVProjection(summary="A pioneering analytical engineer.")

    assembled = assemble_cv(candidate, projection)

    assert assembled.language == "ru"


def test_assemble_cv_looks_up_company_position_period_from_candidate():
    candidate = make_candidate()
    projection = CVProjection(
        summary="...",
        experience=[
            TailoredExperience(experience_id="exp-1", bullets=[TailoredBullet(text="A bullet")])
        ],
    )

    assembled = assemble_cv(candidate, projection)

    entry = next(e for e in assembled.experience if e.company == "Analytical Engines Ltd")
    assert entry.position == "Lead Engineer"
    assert entry.period == "1840-1845"
    assert entry.bullets == [TailoredBullet(text="A bullet")]
    assert entry.is_gap is False


def test_assemble_cv_always_includes_every_entry_even_when_projection_ignores_all_of_them():
    # Regression: assemble_cv used to drop any non-gap entry the
    # projection didn't reference entirely — a role vanishing from the CV
    # reads as an unexplained employment gap. Reported directly, from a
    # real tailored export where an early-career role the LLM judged not
    # relevant enough disappeared outright. Every entry must now appear,
    # non-gap ones with empty bullets when unreferenced — same treatment
    # gap entries always got.
    candidate = make_candidate()
    projection = CVProjection(summary="...", experience=[])

    assembled = assemble_cv(candidate, projection)

    assert [e.experience_id for e in assembled.experience] == ["exp-1", "exp-2", "exp-3"]
    assert all(e.bullets == [] for e in assembled.experience)

    gap_entry = assembled.experience[1]
    assert gap_entry.is_gap is True
    assert gap_entry.position == "Career Break"
    assert gap_entry.period == "1838-1840"
    assert gap_entry.company is None

    non_gap_entries = [e for e in assembled.experience if not e.is_gap]
    assert [e.position for e in non_gap_entries] == ["Lead Engineer", "Fellow"]


def test_assemble_cv_preserves_candidates_chronological_order_not_projections():
    candidate = make_candidate()
    # Projection lists exp-3 before exp-1 — reversed from the Candidate's
    # own order. The assembled CV must still follow the Candidate's order
    # (exp-1, gap exp-2, exp-3), i.e. a readable timeline, not AI relevance.
    projection = CVProjection(
        summary="...",
        experience=[
            TailoredExperience(experience_id="exp-3", bullets=[]),
            TailoredExperience(experience_id="exp-1", bullets=[]),
        ],
    )

    assembled = assemble_cv(candidate, projection)

    assert [e.position for e in assembled.experience] == ["Lead Engineer", "Career Break", "Fellow"]


def test_assemble_cv_still_includes_a_non_gap_entry_not_in_projection_with_empty_bullets():
    candidate = make_candidate()
    projection = CVProjection(
        summary="...",
        experience=[
            TailoredExperience(experience_id="exp-1", bullets=[TailoredBullet(text="Shipped it")])
        ],
    )

    assembled = assemble_cv(candidate, projection)

    non_gap_entries = {e.position: e for e in assembled.experience if not e.is_gap}
    assert set(non_gap_entries) == {"Lead Engineer", "Fellow"}
    assert [b.text for b in non_gap_entries["Lead Engineer"].bullets] == ["Shipped it"]
    # exp-3/"Fellow" isn't in the projection at all — still present, just
    # with no bullets, not dropped from the CV.
    assert non_gap_entries["Fellow"].bullets == []


def test_assemble_cv_passes_through_project_tagged_bullets_unchanged():
    candidate = make_candidate()
    projection = CVProjection(
        summary="...",
        experience=[
            TailoredExperience(
                experience_id="exp-1",
                bullets=[
                    TailoredBullet(text="Untagged bullet"),
                    TailoredBullet(text="Migrated billing system", project="Client A Migration"),
                ],
            )
        ],
    )

    assembled = assemble_cv(candidate, projection)

    entry = next(e for e in assembled.experience if e.company == "Analytical Engines Ltd")
    assert entry.bullets == [
        TailoredBullet(text="Untagged bullet"),
        TailoredBullet(text="Migrated billing system", project="Client A Migration"),
    ]


def test_assemble_cv_sets_experience_id_on_non_gap_and_gap_entries():
    candidate = make_candidate()
    projection = CVProjection(
        summary="...",
        experience=[TailoredExperience(experience_id="exp-1", bullets=[])],
    )

    assembled = assemble_cv(candidate, projection)

    by_id = {e.experience_id: e for e in assembled.experience}
    assert by_id["exp-1"].position == "Lead Engineer"
    assert by_id["exp-2"].position == "Career Break"  # the gap entry


def test_assemble_cv_raises_on_unknown_experience_id():
    candidate = make_candidate()
    projection = CVProjection(
        summary="...",
        experience=[
            TailoredExperience(
                experience_id="exp-does-not-exist", bullets=[TailoredBullet(text="x")]
            )
        ],
    )

    with pytest.raises(ValidationError):
        assemble_cv(candidate, projection)


# ----- _rank_by_category / assemble_cv's skill+technology ranking ----------
# Exercised via Skill below — Technology is shape-identical (name/category)
# and shares the exact same _rank_by_category code path (see
# app/cv_assembler.py's TypeVar), so it doesn't need a duplicate set of
# these same cases; test_assemble_cv_applies_technology_ranking at the end
# just confirms the second call site is wired up correctly.


def test_rank_by_category_sorts_within_category_by_ai_ranking():
    skills = [
        Skill(id="s1", name="Roadmapping", category="Expertise"),
        Skill(id="s2", name="Team Management", category="Expertise"),
    ]

    ranked = _rank_by_category(skills, ["Team Management", "Roadmapping"])

    assert [s.name for s in ranked] == ["Team Management", "Roadmapping"]


def test_rank_by_category_groups_by_category_in_candidates_own_order():
    skills = [
        Skill(id="s1", name="Roadmapping", category="Expertise"),
        Skill(id="s2", name="Unity", category="Tools"),
        Skill(id="s3", name="Team Management", category="Expertise"),
    ]

    # AI ranking crosses categories, but grouping stays fixed by Candidate.skills' order.
    ranked = _rank_by_category(skills, ["Unity", "Team Management", "Roadmapping"])

    assert [(s.name, s.category) for s in ranked] == [
        ("Team Management", "Expertise"),
        ("Roadmapping", "Expertise"),
        ("Unity", "Tools"),
    ]


def test_rank_by_category_keeps_an_item_the_ai_omitted_sorted_last_in_its_category():
    skills = [
        Skill(id="s1", name="Roadmapping", category="Expertise"),
        Skill(id="s2", name="Team Management", category="Expertise"),
    ]

    # "Roadmapping" never mentioned -> not dropped, just sorted last.
    ranked = _rank_by_category(skills, ["Team Management"])

    assert [s.name for s in ranked] == ["Team Management", "Roadmapping"]


def test_rank_by_category_ignores_an_ai_invented_name():
    skills = [Skill(id="s1", name="Roadmapping", category="Expertise")]

    ranked = _rank_by_category(skills, ["Roadmapping", "Time Travel"])

    assert [s.name for s in ranked] == ["Roadmapping"]


def test_rank_by_category_uncategorized_items_form_their_own_group():
    skills = [
        Skill(id="s1", name="Roadmapping", category="Expertise"),
        Skill(id="s2", name="Trivia Night Hosting"),
    ]

    ranked = _rank_by_category(skills, ["Roadmapping"])

    assert [s.category for s in ranked] == ["Expertise", None]


def test_rank_by_category_works_for_technology_too():
    technologies = [
        Technology(id="t1", name="Unity", category="Tools"),
        Technology(id="t2", name="Figma", category="Tools"),
    ]

    ranked = _rank_by_category(technologies, ["Figma", "Unity"])

    assert [t.name for t in ranked] == ["Figma", "Unity"]


def test_assemble_cv_applies_skill_ranking():
    candidate = make_candidate()
    candidate = candidate.model_copy(
        update={
            "skills": [
                Skill(id="s1", name="Roadmapping", category="Expertise"),
                Skill(id="s2", name="Team Management", category="Expertise"),
            ]
        }
    )
    projection = CVProjection(summary="...", skills=["Team Management", "Roadmapping"])

    assembled = assemble_cv(candidate, projection)

    assert [s.name for s in assembled.skills] == ["Team Management", "Roadmapping"]


def test_assemble_cv_applies_technology_ranking():
    candidate = make_candidate()
    candidate = candidate.model_copy(
        update={
            "technologies": [
                Technology(id="t1", name="Unity", category="Tools"),
                Technology(id="t2", name="Figma", category="Tools"),
            ]
        }
    )
    projection = CVProjection(summary="...", technologies=["Figma", "Unity"])

    assembled = assemble_cv(candidate, projection)

    assert [t.name for t in assembled.technologies] == ["Figma", "Unity"]


def test_assemble_cv_excludes_category_header_rows_from_skills_and_technologies():
    # Phase 21: Skill.is_category_header/Technology.is_category_header rows
    # are a Profile Explorer editing construct (a subheader in the same
    # list, not a real skill) — they must never leak into the exported CV.
    candidate = make_candidate()
    candidate = candidate.model_copy(
        update={
            "skills": [
                Skill(id="hdr-1", name="Expertise", is_category_header=True),
                Skill(id="s1", name="Roadmapping", category="Expertise"),
            ],
            "technologies": [
                Technology(id="hdr-2", name="Tools", is_category_header=True),
                Technology(id="t1", name="Unity", category="Tools"),
            ],
        }
    )
    projection = CVProjection(summary="...", skills=["Roadmapping"], technologies=["Unity"])

    assembled = assemble_cv(candidate, projection)

    assert [s.name for s in assembled.skills] == ["Roadmapping"]
    assert [t.name for t in assembled.technologies] == ["Unity"]


# ----- build_untailored_projection (CV export screen) ----------------------


def test_build_untailored_projection_uses_every_non_gap_roles_bullets_verbatim():
    candidate = make_candidate()

    projection = build_untailored_projection(candidate)

    by_id = {t.experience_id: t for t in projection.experience}
    assert set(by_id) == {"exp-1", "exp-3"}  # exp-2 is a gap, excluded
    assert [b.text for b in by_id["exp-1"].bullets] == [
        "Design punched-card programs",
        "Wrote the first published algorithm",
    ]
    assert all(b.project is None for b in by_id["exp-1"].bullets)
    assert by_id["exp-3"].bullets == []  # exp-3 has no bullets at all


def test_build_untailored_projection_tags_project_bullets_with_the_project_name():
    candidate = make_candidate()
    candidate = candidate.model_copy(
        update={
            "experience": [
                Experience(
                    id="exp-1",
                    company="Acme",
                    position="Engineer",
                    responsibilities=["Role-level responsibility"],
                    achievements=["Role-level achievement"],
                    projects=[
                        ExperienceProject(
                            id="proj-1",
                            name="Internal Tool",
                            responsibilities=["Project responsibility"],
                            achievements=["Project achievement"],
                        )
                    ],
                )
            ]
        }
    )

    projection = build_untailored_projection(candidate)

    [entry] = projection.experience
    assert entry.experience_id == "exp-1"
    role_level = [b for b in entry.bullets if b.project is None]
    project_level = [b for b in entry.bullets if b.project == "Internal Tool"]
    assert [b.text for b in role_level] == ["Role-level responsibility", "Role-level achievement"]
    assert [b.text for b in project_level] == ["Project responsibility", "Project achievement"]


def test_build_untailored_projection_keeps_skills_and_technologies_in_original_order_and_excludes_headers():
    candidate = make_candidate()
    candidate = candidate.model_copy(
        update={
            "skills": [
                Skill(id="hdr-1", name="Expertise", is_category_header=True),
                Skill(id="s1", name="Roadmapping", category="Expertise"),
                Skill(id="s2", name="Mentoring", category="Expertise"),
            ],
            "technologies": [Technology(id="t1", name="Unity"), Technology(id="t2", name="Figma")],
        }
    )

    projection = build_untailored_projection(candidate)

    assert projection.skills == ["Roadmapping", "Mentoring"]
    assert projection.technologies == ["Unity", "Figma"]


def test_build_untailored_projection_uses_candidate_summary_verbatim_or_blank():
    with_summary = make_candidate().model_copy(update={"summary": "Experienced engineer."})
    assert build_untailored_projection(with_summary).summary == "Experienced engineer."

    without_summary = make_candidate().model_copy(update={"summary": None})
    assert build_untailored_projection(without_summary).summary == ""


def test_assemble_cv_from_an_untailored_projection_still_includes_gap_entries_and_facts_untouched():
    # End-to-end: assemble_cv(candidate, build_untailored_projection(...))
    # is the whole "export without tailoring" path — confirms it produces
    # a real, complete AssembledCV with no LLM involvement at all.
    candidate = make_candidate()

    assembled = assemble_cv(candidate, build_untailored_projection(candidate))

    assert [e.experience_id for e in assembled.experience] == ["exp-1", "exp-2", "exp-3"]
    gap_entry = next(e for e in assembled.experience if e.experience_id == "exp-2")
    assert gap_entry.is_gap is True
    assert assembled.summary == ""
    assert [s.name for s in assembled.skills] == ["Analytical Engine programming"]
    assert assembled.education == candidate.education
    assert assembled.certifications == candidate.certifications
