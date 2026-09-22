import pytest
from sqlmodel import SQLModel

from app.candidate_service import CandidateService
from app.errors import ValidationError
from db.engine import get_engine
from domain.models import (
    AssembledCV,
    BulletProvenance,
    BulletProvenanceReport,
    GenerationTiming,
    MatchResult,
    PrintDocument,
    Vacancy,
)


def make_service(tmp_path) -> CandidateService:
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    return CandidateService(candidate_id="test-candidate", engine=engine)


# ----- Profile-level CRUD ---------------------------------------------


def test_get_returns_none_before_create(tmp_path):
    service = make_service(tmp_path)
    assert service.get() is None


def test_create_persists_and_returns_candidate(tmp_path):
    service = make_service(tmp_path)

    candidate = service.create(name="Ada Lovelace", headline="Analytical Engineer")

    assert candidate.name == "Ada Lovelace"
    assert service.get() == candidate


def test_create_defaults_language_to_en(tmp_path):
    service = make_service(tmp_path)

    candidate = service.create(name="Ada Lovelace")

    assert candidate.language == "en"


def test_create_persists_an_explicit_language(tmp_path):
    service = make_service(tmp_path)

    candidate = service.create(name="Ada Lovelace", language="ru")

    assert candidate.language == "ru"
    assert service.get().language == "ru"


def test_create_rejects_empty_name(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValidationError):
        service.create(name="   ")


def test_create_rejects_second_profile(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    with pytest.raises(ValidationError):
        service.create(name="Charles Babbage")


def test_update_patches_fields(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    updated = service.update(headline="Mathematician")

    assert updated.headline == "Mathematician"
    assert service.get().headline == "Mathematician"


def test_update_patches_summary(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    updated = service.update(summary="Analytical engineer open to new roles.")

    assert updated.summary == "Analytical engineer open to new roles."
    assert service.get().summary == "Analytical engineer open to new roles."


def test_update_without_existing_profile_raises(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValidationError):
        service.update(headline="Mathematician")


def test_update_rejects_blanking_out_name(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    with pytest.raises(ValidationError):
        service.update(name="")


def test_delete_removes_profile(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    assert service.delete() is True
    assert service.get() is None


# ----- Experience CRUD --------------------------------------------------


def test_add_experience_requires_existing_profile(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValidationError):
        service.add_experience(company="Acme", position="Engineer")


def test_add_update_remove_experience_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_experience(
        company="Analytical Engines Ltd",
        position="Lead Engineer",
        responsibilities=["Design programs"],
    )
    assert service.get().experience == [entry]

    updated = service.update_experience(entry.id, position="Chief Engineer")
    assert updated.position == "Chief Engineer"
    assert service.get().experience[0].position == "Chief Engineer"

    service.remove_experience(entry.id)
    assert service.get().experience == []


def test_add_experience_accepts_optional_location(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_experience(company="Acme", position="Engineer", location="Berlin")
    assert entry.location == "Berlin"

    updated = service.update_experience(entry.id, location="Offenburg")
    assert updated.location == "Offenburg"


def test_add_experience_accepts_optional_company_url(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_experience(
        company="Acme", position="Engineer", company_url="https://acme.example/"
    )
    assert entry.company_url == "https://acme.example/"

    updated = service.update_experience(entry.id, company_url="https://acme.example/careers")
    assert updated.company_url == "https://acme.example/careers"


def test_add_experience_rejects_empty_company(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_experience(company="", position="Engineer")


def test_add_experience_allows_gap_without_company(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_experience(position="Career Break", period="2019-2020", is_gap=True)

    assert entry.company is None
    assert entry.is_gap is True
    assert service.get().experience == [entry]


def test_add_experience_still_requires_company_when_not_a_gap(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_experience(position="Engineer", is_gap=False)


def test_add_experience_rejects_empty_position_even_for_gaps(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_experience(position="", is_gap=True)


def test_update_experience_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.update_experience("missing-id", position="Engineer")


# ----- Experience Project CRUD (nested inside one Experience entry) -----


def test_add_experience_project_requires_existing_experience(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_experience_project("missing-exp-id", name="Client A Migration")


def test_add_update_remove_experience_project_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    experience = service.add_experience(company="Agency Co", position="Consultant")

    project = service.add_experience_project(
        experience.id,
        name="Client A Migration",
        achievements=["Migrated legacy billing system"],
    )
    assert service.get().experience[0].projects == [project]

    updated = service.update_experience_project(experience.id, project.id, period="2019-2020")
    assert updated.period == "2019-2020"
    assert service.get().experience[0].projects[0].period == "2019-2020"

    service.remove_experience_project(experience.id, project.id)
    assert service.get().experience[0].projects == []


def test_add_experience_project_accepts_optional_url(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    experience = service.add_experience(company="Agency Co", position="Consultant")

    project = service.add_experience_project(
        experience.id, name="Client A Migration", url="https://client-a.example/"
    )
    assert project.url == "https://client-a.example/"

    updated = service.update_experience_project(
        experience.id, project.id, url="https://client-a.example/case-study"
    )
    assert updated.url == "https://client-a.example/case-study"


def test_add_experience_project_rejects_empty_name(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    experience = service.add_experience(company="Agency Co", position="Consultant")

    with pytest.raises(ValidationError):
        service.add_experience_project(experience.id, name="")


def test_update_experience_project_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    experience = service.add_experience(company="Agency Co", position="Consultant")

    with pytest.raises(ValidationError):
        service.update_experience_project(experience.id, "missing-project-id", period="2020")


def test_remove_experience_project_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    experience = service.add_experience(company="Agency Co", position="Consultant")

    with pytest.raises(ValidationError):
        service.remove_experience_project(experience.id, "missing-project-id")


def test_experience_projects_do_not_leak_across_experience_entries(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    exp_a = service.add_experience(company="Agency Co", position="Consultant")
    exp_b = service.add_experience(company="Other Co", position="Engineer")

    service.add_experience_project(exp_a.id, name="Client A Migration")

    with pytest.raises(ValidationError):
        service.update_experience_project(exp_b.id, "does-not-matter", period="2020")
    assert service.get().experience[1].projects == []


# ----- Evidence sync on Experience save -----------------------------------
# Manually editing Achievements/Responsibilities used to leave Evidence (the
# read-only ExperienceEvidencePanel + every future CV generate's source
# data) permanently stale, since the two layers otherwise don't sync (see
# docs/domain-model.md). update_experience/update_experience_project now
# reconcile Evidence to match on every save.


def test_add_experience_creates_matching_evidence(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_experience(
        company="Acme",
        position="Engineer",
        responsibilities=["Wrote code"],
        achievements=["Shipped a feature"],
    )

    texts = {e.text for e in service.get_evidence()}
    assert texts == {"Wrote code", "Shipped a feature"}
    assert all(e.experience_id == entry.id for e in service.get_evidence())


def test_update_experience_achievements_syncs_evidence(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(
        company="Acme", position="Engineer", achievements=["Old bullet"]
    )

    service.update_experience(entry.id, achievements=["New bullet"])

    texts = {e.text for e in service.get_evidence()}
    assert texts == {"New bullet"}


def test_update_experience_preserves_evidence_id_for_unchanged_bullet(tmp_path):
    # A bullet whose text is untouched by the edit keeps its Evidence row's
    # id -- and therefore its locked/locked_text -- rather than being
    # replaced by a fresh row with a new id.
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(
        company="Acme", position="Engineer", achievements=["Keep me", "Drop me"]
    )
    kept = next(e for e in service.get_evidence() if e.text == "Keep me")
    service.update_evidence(kept.id, locked=True, locked_text="Keep me (locked)")

    service.update_experience(entry.id, achievements=["Keep me", "Added"])

    evidence = service.get_evidence()
    texts = {e.text for e in evidence}
    assert texts == {"Keep me", "Added"}
    still_kept = next(e for e in evidence if e.text == "Keep me")
    assert still_kept.id == kept.id
    assert still_kept.locked is True
    assert still_kept.locked_text == "Keep me (locked)"


def test_update_experience_removing_bullet_unlinks_evidence_from_skill(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(
        company="Acme", position="Engineer", achievements=["Removable bullet"]
    )
    removable = next(e for e in service.get_evidence() if e.text == "Removable bullet")
    skill = service.add_skill(name="SQL")
    service.update_skill(skill.id, evidence_ids=[removable.id])

    service.update_experience(entry.id, achievements=[])

    assert service.get_evidence() == []
    assert service.get().skills[0].evidence_ids == []
    assert service.get().skills[0].id == skill.id


def test_update_experience_project_achievements_syncs_evidence(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    experience = service.add_experience(company="Agency Co", position="Consultant")
    project = service.add_experience_project(
        experience.id, name="Client A Migration", achievements=["Old project bullet"]
    )

    service.update_experience_project(experience.id, project.id, achievements=["New project bullet"])

    evidence = service.get_evidence()
    assert [e.text for e in evidence] == ["New project bullet"]
    assert evidence[0].experience_project_id == project.id


def test_update_experience_dropped_project_evidence_moves_to_role_level(tmp_path):
    # ExperienceForm.tsx's toExperienceRequestBody reassigns a deleted
    # project's bullets to role-level before the PUT ever reaches the
    # backend, so a full-overwrite update_experience() call that omits a
    # previously-existing project id should leave that project's old
    # Evidence cleaned up rather than orphaned under a project id that no
    # longer exists.
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    experience = service.add_experience(company="Agency Co", position="Consultant")
    service.add_experience_project(
        experience.id, name="Client A Migration", achievements=["Reassigned bullet"]
    )

    service.update_experience(
        experience.id,
        achievements=["Reassigned bullet"],
        responsibilities=[],
        projects=[],
    )

    evidence = service.get_evidence()
    assert [e.text for e in evidence] == ["Reassigned bullet"]
    assert evidence[0].experience_project_id is None


# ----- Education CRUD ----------------------------------------------------


def test_add_update_remove_education_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_education(institution="Self-taught", field="Mathematics")
    assert service.get().education == [entry]

    updated = service.update_education(entry.id, degree="Honorary")
    assert updated.degree == "Honorary"

    service.remove_education(entry.id)
    assert service.get().education == []


# ----- Skill CRUD ----------------------------------------------------------


def test_add_update_remove_skill_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_skill(name="Analytical Engine programming")
    assert service.get().skills == [entry]

    updated = service.update_skill(entry.id, category="Historical computing")
    assert updated.category == "Historical computing"

    service.remove_skill(entry.id)
    assert service.get().skills == []


def test_remove_skill_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_skill("missing-id")


def test_add_skill_accepts_optional_proficiency(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_skill(name="Python", proficiency="Advanced")
    assert entry.proficiency == "Advanced"


def test_update_skill_links_to_existing_evidence(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    evidence = service.add_evidence(text="Led a team of five engineers.")
    skill = service.add_skill(name="Leadership")

    updated = service.update_skill(skill.id, evidence_ids=[evidence.id])

    assert updated.evidence_ids == [evidence.id]
    assert service.get().skills[0].evidence_ids == [evidence.id]


def test_update_skill_rejects_unknown_evidence_id(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    skill = service.add_skill(name="Leadership")

    with pytest.raises(ValidationError):
        service.update_skill(skill.id, evidence_ids=["does-not-exist"])


def test_update_technology_links_to_existing_evidence(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    evidence = service.add_evidence(text="Deployed services on Kubernetes.")
    tech = service.add_technology(name="Kubernetes")

    updated = service.update_technology(tech.id, evidence_ids=[evidence.id])

    assert updated.evidence_ids == [evidence.id]


def test_update_technology_rejects_unknown_evidence_id(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    tech = service.add_technology(name="Kubernetes")

    with pytest.raises(ValidationError):
        service.update_technology(tech.id, evidence_ids=["does-not-exist"])


# ----- Evidence CRUD (Phase 15) -------------------------------------------


def test_add_update_remove_evidence_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_evidence(text="Led a team of five engineers.")
    assert service.get_evidence() == [entry]

    updated = service.update_evidence(entry.id, source_context="Analytical Engines Ltd")
    assert updated.source_context == "Analytical Engines Ltd"
    assert service.get_evidence()[0].source_context == "Analytical Engines Ltd"

    service.remove_evidence(entry.id)
    assert service.get_evidence() == []


def test_update_evidence_locked_and_locked_text_round_trip(tmp_path):
    # Phase 19: persisted durably (not per-generate), so a person can lock
    # a bullet once and have it reused verbatim across every future
    # generate for any vacancy.
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_evidence(text="Led a team of five engineers.")
    assert entry.locked is False
    assert entry.locked_text is None

    updated = service.update_evidence(entry.id, locked=True, locked_text="Led a team of 5 engineers.")
    assert updated.locked is True
    assert updated.locked_text == "Led a team of 5 engineers."
    assert service.get_evidence()[0].locked is True
    assert service.get_evidence()[0].locked_text == "Led a team of 5 engineers."

    unlocked = service.update_evidence(entry.id, locked=False)
    assert unlocked.locked is False
    # locked_text is left in place, not cleared -- unlocking is meant to be
    # a light toggle (see BulletRow's Unlock affordance), and the stashed
    # approved wording is exactly what re-locking later would want back.
    assert unlocked.locked_text == "Led a team of 5 engineers."


def test_add_evidence_rejects_empty_text(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_evidence(text="")


def test_add_evidence_requires_existing_profile(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ValidationError):
        service.add_evidence(text="Led a team of five engineers.")


def test_add_evidence_accepts_experience_link(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    experience = service.add_experience(company="Acme", position="Engineer")

    entry = service.add_evidence(text="Shipped a REST API.", experience_id=experience.id)
    assert entry.experience_id == experience.id


def test_add_evidence_appends_after_existing_evidence(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    first = service.add_evidence(text="First bullet.")
    second = service.add_evidence(text="Second bullet.")

    assert [e.id for e in service.get_evidence()] == [first.id, second.id]


def test_update_evidence_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.update_evidence("missing-id", text="x")


def test_remove_evidence_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_evidence("missing-id")


def test_remove_evidence_strips_dangling_references_from_skills_and_technologies(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    evidence = service.add_evidence(text="Led a team using Python and Kubernetes.")
    skill = service.add_skill(name="Leadership")
    tech = service.add_technology(name="Kubernetes")
    service.update_skill(skill.id, evidence_ids=[evidence.id])
    service.update_technology(tech.id, evidence_ids=[evidence.id])

    service.remove_evidence(evidence.id)

    candidate = service.get()
    assert candidate.skills[0].evidence_ids == []
    assert candidate.technologies[0].evidence_ids == []


# ----- replace() (resume-ingestion import path) -------------------------


def test_replace_creates_profile_when_none_exists(tmp_path):
    from domain.models import Candidate, Experience

    service = make_service(tmp_path)
    candidate = Candidate(
        name="Ada Lovelace",
        experience=[Experience(id="exp-1", company="Acme", position="Engineer")],
    )

    result = service.replace(candidate)

    assert result == candidate
    assert service.get() == candidate


def test_replace_overwrites_existing_profile_wholesale(tmp_path):
    from domain.models import Candidate, Experience

    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    service.add_experience(company="Acme", position="Engineer")

    incoming = Candidate(
        name="Ada Lovelace",
        headline="Analytical Engineer",
        experience=[Experience(id="exp-9", company="Analytical Engines Ltd", position="Lead")],
    )
    result = service.replace(incoming)

    assert result == incoming
    assert service.get() == incoming
    assert [e.company for e in service.get().experience] == ["Analytical Engines Ltd"]


def test_replace_rejects_empty_name(tmp_path):
    from domain.models import Candidate

    service = make_service(tmp_path)
    with pytest.raises(ValidationError):
        service.replace(Candidate(name=""))


def test_get_evidence_returns_empty_list_before_any_ingestion(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    assert service.get_evidence() == []


def test_replace_with_evidence_persists_it(tmp_path):
    from domain.models import Candidate, Evidence

    service = make_service(tmp_path)
    candidate = Candidate(name="Ada Lovelace")
    evidence = [Evidence(id="ev-1", text="Led a team of five designers.")]

    service.replace(candidate, evidence=evidence)

    assert service.get_evidence() == evidence


def test_replace_without_evidence_leaves_previously_saved_evidence_untouched(tmp_path):
    from domain.models import Candidate, Evidence

    service = make_service(tmp_path)
    first_evidence = [Evidence(id="ev-1", text="Led a team of five designers.")]
    service.replace(Candidate(name="Ada Lovelace"), evidence=first_evidence)

    # A later replace() call that doesn't pass evidence= (e.g. a manual
    # profile edit via update()) must not wipe out Evidence from a previous
    # ingestion.
    service.replace(Candidate(name="Ada Lovelace", headline="Mathematician"))

    assert service.get_evidence() == first_evidence


# ----- Language CRUD --------------------------------------------------


def test_add_update_remove_language_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_language(name="French", proficiency="B2")
    assert service.get().languages == [entry]

    updated = service.update_language(entry.id, proficiency="C1")
    assert updated.proficiency == "C1"

    service.remove_language(entry.id)
    assert service.get().languages == []


def test_add_language_rejects_empty_name(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_language(name="")


def test_remove_language_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_language("missing-id")


# ----- Certification CRUD ----------------------------------------------


def test_add_update_remove_certification_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_certification(name="PMP", issuer="PMI")
    assert service.get().certifications == [entry]

    updated = service.update_certification(entry.id, date="2024")
    assert updated.date == "2024"

    service.remove_certification(entry.id)
    assert service.get().certifications == []


def test_add_certification_rejects_empty_name(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_certification(name="")


def test_remove_certification_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_certification("missing-id")


# ----- Contact CRUD --------------------------------------------------


def test_add_update_remove_contact_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_contact(label="LinkedIn", value="linkedin.com/in/ada")
    assert service.get().contacts == [entry]

    updated = service.update_contact(entry.id, value="linkedin.com/in/ada-lovelace")
    assert updated.value == "linkedin.com/in/ada-lovelace"
    assert updated.label == "LinkedIn"

    service.remove_contact(entry.id)
    assert service.get().contacts == []


def test_add_contact_accepts_arbitrary_labels(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_contact(label="Work Authorization", value="No visa support required")

    assert entry.label == "Work Authorization"
    assert entry.value == "No visa support required"


def test_add_contact_rejects_empty_label_or_value(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_contact(label="", value="ada@example.com")
    with pytest.raises(ValidationError):
        service.add_contact(label="Email", value="")


def test_remove_contact_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_contact("missing-id")


# ----- Project CRUD --------------------------------------------------


def test_add_update_remove_project_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_project(name="SuperCity", description="City building game")
    assert service.get().projects == [entry]

    updated = service.update_project(entry.id, url="https://example.com/supercity")
    assert updated.url == "https://example.com/supercity"

    service.remove_project(entry.id)
    assert service.get().projects == []


def test_add_project_rejects_empty_name(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_project(name="")


def test_remove_project_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_project("missing-id")


# ----- Portfolio Link CRUD --------------------------------------------


def test_add_update_remove_portfolio_link_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_portfolio_link(url="https://artstation.com/ada", description="Concept art")
    assert service.get().portfolio_links == [entry]

    updated = service.update_portfolio_link(entry.id, description="Updated description")
    assert updated.description == "Updated description"

    service.remove_portfolio_link(entry.id)
    assert service.get().portfolio_links == []


def test_add_portfolio_link_rejects_empty_url(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_portfolio_link(url="")


def test_remove_portfolio_link_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_portfolio_link("missing-id")


# ----- Award CRUD -------------------------------------------------------


def test_add_update_remove_award_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_award(name="Best in Show", issuer="GDC")
    assert service.get().awards == [entry]

    updated = service.update_award(entry.id, date="2023")
    assert updated.date == "2023"

    service.remove_award(entry.id)
    assert service.get().awards == []


def test_add_award_rejects_empty_name(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_award(name="")


def test_remove_award_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_award("missing-id")


# ----- Publication CRUD --------------------------------------------------


def test_add_update_remove_publication_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_publication(title="Scaling LiveOps", venue="Medium")
    assert service.get().publications == [entry]

    updated = service.update_publication(entry.id, url="https://medium.com/x")
    assert updated.url == "https://medium.com/x"

    service.remove_publication(entry.id)
    assert service.get().publications == []


def test_add_publication_rejects_empty_title(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_publication(title="")


def test_remove_publication_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_publication("missing-id")


# ----- Volunteer Experience CRUD -----------------------------------------


def test_add_update_remove_volunteer_experience_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_volunteer_experience(organization="Code.org", role="Mentor")
    assert service.get().volunteer_experience == [entry]

    updated = service.update_volunteer_experience(entry.id, period="2021-2022")
    assert updated.period == "2021-2022"

    service.remove_volunteer_experience(entry.id)
    assert service.get().volunteer_experience == []


def test_add_volunteer_experience_rejects_empty_organization_or_role(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_volunteer_experience(organization="", role="Mentor")
    with pytest.raises(ValidationError):
        service.add_volunteer_experience(organization="Code.org", role="")


def test_remove_volunteer_experience_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_volunteer_experience("missing-id")


# ----- Technology CRUD ----------------------------------------------------


def test_add_update_remove_technology_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    entry = service.add_technology(name="Python", category="Language")
    assert service.get().technologies == [entry]

    updated = service.update_technology(entry.id, proficiency="Advanced")
    assert updated.proficiency == "Advanced"

    service.remove_technology(entry.id)
    assert service.get().technologies == []


def test_add_technology_rejects_empty_name(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.add_technology(name="")


def test_remove_technology_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_technology("missing-id")


# ----- CVDraft CRUD (Phase 20) ---------------------------------------------


def _draft_inputs():
    vacancy = Vacancy(title="Engineer", company="Acme", raw_text="jd text", requirements=[])
    assembled_cv = AssembledCV(name="Ada Lovelace", summary="Tailored summary.")
    document = PrintDocument(
        sections=[
            {
                "key": "summary",
                "title": "Summary",
                "included": True,
                "entries": [{"id": "summary", "text": "Tailored summary.", "included": True}],
            }
        ]
    )
    return vacancy, assembled_cv, document


def test_add_get_update_remove_cv_draft_round_trip(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    vacancy, assembled_cv, document = _draft_inputs()

    draft = service.add_cv_draft(vacancy=vacancy, assembled_cv=assembled_cv, document=document)
    assert draft.candidate_id == "test-candidate"
    assert draft.vacancy == vacancy
    assert draft.created_at == draft.updated_at

    fetched = service.get_cv_draft(draft.id)
    assert fetched == draft

    edited_document = PrintDocument(
        sections=[
            {
                "key": "summary",
                "title": "Summary",
                "included": True,
                "entries": [{"id": "summary", "text": "A further-edited summary.", "included": True}],
            }
        ]
    )
    updated = service.update_cv_draft(draft.id, document=edited_document)
    assert updated.document == edited_document
    # Untouched fields survive the partial patch.
    assert updated.vacancy == vacancy
    assert updated.assembled_cv == assembled_cv
    assert updated.updated_at > draft.updated_at

    service.remove_cv_draft(draft.id)
    assert service.get_cv_draft(draft.id) is None


def test_add_cv_draft_persists_match_result_and_provenance(tmp_path):
    # Phase 20b: reported directly — a reopened tailored draft showed
    # genuinely-edited bullet text with no way to tell which bullets were
    # AI-edited or why, since match_result/provenance were never
    # persisted, only carried through the very first navigation.
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    vacancy, assembled_cv, document = _draft_inputs()
    match_result = MatchResult(matches=[], gaps=[], missing_keywords=["Python"])
    provenance = BulletProvenanceReport(
        bullets=[
            BulletProvenance(
                evidence_id="ev-1",
                original_text="Wrote code.",
                rewritten_text="Wrote production Python code.",
                action="enhance",
                rationale="Surfaced the Python keyword.",
                locked=False,
            )
        ],
        unused_evidence=[],
    )

    draft = service.add_cv_draft(
        vacancy=vacancy,
        assembled_cv=assembled_cv,
        document=document,
        match_result=match_result,
        provenance=provenance,
    )

    assert draft.match_result == match_result
    assert draft.provenance == provenance
    # A fresh fetch (a "reopen") round-trips both from storage, not from
    # in-memory state — the actual bug scenario.
    fetched = service.get_cv_draft(draft.id)
    assert fetched.match_result == match_result
    assert fetched.provenance == provenance


def test_add_cv_draft_match_result_and_provenance_default_to_none(tmp_path):
    # The "export without tailoring" path never calls the LLM — nothing
    # to persist, and reading it back shouldn't fabricate empty reports.
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    vacancy, assembled_cv, document = _draft_inputs()

    draft = service.add_cv_draft(vacancy=vacancy, assembled_cv=assembled_cv, document=document)

    assert draft.match_result is None
    assert draft.provenance is None
    assert service.get_cv_draft(draft.id).match_result is None


def test_update_cv_draft_can_replace_match_result_and_provenance(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    vacancy, assembled_cv, document = _draft_inputs()
    draft = service.add_cv_draft(vacancy=vacancy, assembled_cv=assembled_cv, document=document)
    assert draft.match_result is None

    new_match_result = MatchResult(matches=[], gaps=[], missing_keywords=["SQL"])
    updated = service.update_cv_draft(draft.id, match_result=new_match_result)

    assert updated.match_result == new_match_result
    assert service.get_cv_draft(draft.id).match_result == new_match_result


def test_add_cv_draft_persists_timing(tmp_path):
    # Found live: `timing` was added to CVDraft/CVDraftRow but not to
    # add_cv_draft's own signature (the create-request schema's actual
    # source, per api/routes/entity_crud.py's docstring) or to the
    # row<->model mapping below — every real generation silently lost its
    # timing data on save. This test (and the two below) pin the full
    # round trip so that regressing any one of the three pieces again
    # fails here instead of only being found by inspecting a real draft.
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    vacancy, assembled_cv, document = _draft_inputs()
    timing = GenerationTiming(
        vacancy_analysis_seconds=1.5,
        matching_seconds=2.5,
        rewrite_planning_seconds=3.5,
        bullet_rewriting_seconds=4.5,
        quality_recheck_seconds=5.5,
        total_seconds=17.5,
    )

    draft = service.add_cv_draft(vacancy=vacancy, assembled_cv=assembled_cv, document=document, timing=timing)

    assert draft.timing == timing
    # A fresh fetch (a "reopen") round-trips it from storage, not from
    # in-memory state — the actual bug scenario.
    assert service.get_cv_draft(draft.id).timing == timing


def test_add_cv_draft_timing_defaults_to_none(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    vacancy, assembled_cv, document = _draft_inputs()

    draft = service.add_cv_draft(vacancy=vacancy, assembled_cv=assembled_cv, document=document)

    assert draft.timing is None
    assert service.get_cv_draft(draft.id).timing is None


def test_update_cv_draft_can_replace_timing(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    vacancy, assembled_cv, document = _draft_inputs()
    draft = service.add_cv_draft(vacancy=vacancy, assembled_cv=assembled_cv, document=document)
    assert draft.timing is None

    new_timing = GenerationTiming(
        vacancy_analysis_seconds=0,
        matching_seconds=0,
        rewrite_planning_seconds=0,
        bullet_rewriting_seconds=0,
        quality_recheck_seconds=0,
        total_seconds=42,
    )
    updated = service.update_cv_draft(draft.id, timing=new_timing)

    assert updated.timing == new_timing
    assert service.get_cv_draft(draft.id).timing == new_timing


def test_update_cv_draft_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.update_cv_draft("missing-id", document=_draft_inputs()[2])


def test_remove_cv_draft_missing_id_raises(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    with pytest.raises(ValidationError):
        service.remove_cv_draft("missing-id")


def test_get_cv_draft_returns_none_when_missing(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    assert service.get_cv_draft("missing-id") is None


def test_list_cv_drafts_returns_summaries_most_recently_updated_first(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    vacancy, assembled_cv, document = _draft_inputs()

    first = service.add_cv_draft(vacancy=vacancy, assembled_cv=assembled_cv, document=document)
    second = service.add_cv_draft(vacancy=vacancy, assembled_cv=assembled_cv, document=document)
    # Touch `first` again so it becomes the most recently updated.
    service.update_cv_draft(first.id, document=document)

    summaries = service.list_cv_drafts()
    assert [s.id for s in summaries] == [first.id, second.id]
    assert summaries[0].vacancy_title == "Engineer"
    assert summaries[0].vacancy_company == "Acme"


def test_cv_drafts_are_scoped_to_their_own_candidate(tmp_path):
    from db.engine import get_engine as _get_engine

    engine = _get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    service_a = CandidateService(candidate_id="cand-a", engine=engine)
    service_b = CandidateService(candidate_id="cand-b", engine=engine)
    service_a.create(name="Ada")
    service_b.create(name="Bea")
    vacancy, assembled_cv, document = _draft_inputs()

    draft = service_a.add_cv_draft(vacancy=vacancy, assembled_cv=assembled_cv, document=document)

    assert service_b.get_cv_draft(draft.id) is None
    assert service_b.list_cv_drafts() == []


# ----- reorder_entities (generic) -------------------------------------------


def test_reorder_entities_applies_the_given_order(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    a = service.add_skill(name="Python")
    b = service.add_skill(name="SQL")
    c = service.add_skill(name="Go")

    result = service.reorder_entities("skills", [c.id, a.id, b.id])

    assert [s.id for s in result] == [c.id, a.id, b.id]
    assert [s.id for s in service.get().skills] == [c.id, a.id, b.id]


def test_reorder_entities_appends_ids_missing_from_the_new_order_instead_of_dropping_them(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    a = service.add_skill(name="Python")
    b = service.add_skill(name="SQL")
    c = service.add_skill(name="Go")

    # A stale client that doesn't know about `c` yet only reorders a/b.
    result = service.reorder_entities("skills", [b.id, a.id])

    assert [s.id for s in result] == [b.id, a.id, c.id]


def test_reorder_entities_ignores_unknown_ids(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    a = service.add_skill(name="Python")

    result = service.reorder_entities("skills", ["missing-id", a.id])

    assert [s.id for s in result] == [a.id]
