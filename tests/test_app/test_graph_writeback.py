from sqlmodel import SQLModel

from app.candidate_service import CandidateService
from app.graph_writeback import (
    build_experience_proposals,
    build_proposals_from_document,
    build_skills_proposals,
    build_summary_proposal,
)
from db.engine import get_engine
from domain.models import (
    AssembledExperienceEntry,
    Candidate,
    PrintDocument,
    Skill,
    TailoredBullet,
)


def make_service(tmp_path) -> CandidateService:
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    return CandidateService(candidate_id="test-candidate", engine=engine)


# ----- build_summary_proposal ---------------------------------------------


def test_summary_proposal_is_always_enabled_and_updates_candidate(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    proposal = build_summary_proposal("A refined positioning statement.\n")

    assert proposal.enabled is True
    proposal.apply(service)

    assert service.get().summary == "A refined positioning statement."


# ----- build_skills_proposals ----------------------------------------------


def test_skills_proposals_only_include_new_names(tmp_path):
    candidate = Candidate(name="Ada", skills=[Skill(id="skill-1", name="Python")])

    proposals = build_skills_proposals(candidate, "- Python\n- SQL\n- Leadership")

    assert [p.label for p in proposals] == ["Add skill: SQL", "Add skill: Leadership"]


def test_skills_proposals_dedup_case_insensitively(tmp_path):
    candidate = Candidate(name="Ada", skills=[Skill(id="skill-1", name="python")])

    proposals = build_skills_proposals(candidate, "- Python\n- SQL")

    assert [p.label for p in proposals] == ["Add skill: SQL"]


def test_skills_proposals_match_existing_name_despite_a_proficiency_suffix(tmp_path):
    # Real bug found via actual pipeline output: app/cv_markdown.py's
    # _render_grouped_by_category appends "(Proficiency)" to a skill line
    # when set, so a stored skill with a proficiency (e.g. "Roadmapping
    # (Expertise)") never matched its own bare name and was proposed as a
    # brand-new skill on every write-back.
    candidate = Candidate(
        name="Ada", skills=[Skill(id="skill-1", name="Roadmapping", proficiency="Expertise")]
    )

    proposals = build_skills_proposals(candidate, "- Roadmapping (Expertise)\n- SQL (Advanced)")

    assert [p.label for p in proposals] == ["Add skill: SQL (Advanced)"]


def test_skills_proposals_set_proficiency_on_a_genuinely_new_skill(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    proposals = build_skills_proposals(Candidate(name="Ada"), "- SQL (Advanced)")
    assert len(proposals) == 1
    proposals[0].apply(service)

    added = service.get().skills[0]
    assert added.name == "SQL"
    assert added.proficiency == "Advanced"


def test_skills_proposals_expand_a_compact_category_line_into_one_per_member(tmp_path):
    # Regression: an earlier version treated a whole compact
    # "**Category**: item1; item2" line as one bogus skill name (literal
    # asterisks, colon and all) instead of one proposal per member.
    proposals = build_skills_proposals(
        Candidate(name="Ada"),
        "- **Vendor & Pipeline Management**: outsourcing management; documentation",
    )

    assert [p.label for p in proposals] == [
        "Add skill: outsourcing management",
        "Add skill: documentation",
    ]


def test_skills_proposals_apply_carries_the_category_through(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")

    proposals = build_skills_proposals(
        Candidate(name="Ada"), "- **Vendor & Pipeline Management**: outsourcing management"
    )
    proposals[0].apply(service)

    added = service.get().skills[0]
    assert added.name == "outsourcing management"
    assert added.category == "Vendor & Pipeline Management"


def test_skills_proposals_handle_proficiency_inside_a_category_line(tmp_path):
    proposals = build_skills_proposals(
        Candidate(name="Ada"), "- **Language**: Python (Advanced); Unity"
    )

    assert [p.label for p in proposals] == ["Add skill: Python (Advanced)", "Add skill: Unity"]


def test_skills_proposals_skip_a_category_line_with_no_members(tmp_path):
    proposals = build_skills_proposals(Candidate(name="Ada"), "- **Vendor & Pipeline Management**")

    assert proposals == []


def test_skills_proposals_dedup_a_category_member_against_an_existing_skill(tmp_path):
    candidate = Candidate(
        name="Ada", skills=[Skill(id="skill-1", name="documentation")]
    )

    proposals = build_skills_proposals(
        candidate, "- **Vendor & Pipeline Management**: outsourcing management; documentation"
    )

    assert [p.label for p in proposals] == ["Add skill: outsourcing management"]


def test_skills_proposals_empty_when_nothing_new(tmp_path):
    candidate = Candidate(name="Ada", skills=[Skill(id="skill-1", name="Python")])

    proposals = build_skills_proposals(candidate, "- Python")

    assert proposals == []


def test_skills_proposal_apply_adds_the_skill(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    candidate = service.get()

    proposals = build_skills_proposals(candidate, "- Leadership")
    proposals[0].apply(service)

    assert [s.name for s in service.get().skills] == ["Leadership"]


# ----- build_experience_proposals ------------------------------------------


def test_experience_proposals_skip_gap_entries():
    assembled = [
        AssembledExperienceEntry(
            experience_id="exp-1", position="Career Break", is_gap=True, bullets=[]
        ),
    ]
    edited_text = "*Career Break*"

    proposals = build_experience_proposals(assembled, edited_text)

    assert proposals == []


def test_experience_proposals_parse_role_level_bullets(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(company="Acme", position="Engineer")

    assembled = [
        AssembledExperienceEntry(experience_id=entry.id, position="Engineer", company="Acme", bullets=[])
    ]
    edited_text = "**Engineer** — Acme\n- Did a thing\n- Did another thing"

    proposals = build_experience_proposals(assembled, edited_text)

    assert len(proposals) == 1
    assert proposals[0].enabled is True
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert updated.achievements == ["Did a thing", "Did another thing"]


def test_experience_proposals_parse_project_grouped_bullets_and_create_new_project(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(company="Agency Co", position="Consultant")

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id, position="Consultant", company="Agency Co", bullets=[]
        )
    ]
    edited_text = (
        "**Consultant** — Agency Co\n"
        "- Untagged bullet\n"
        "*Client A Migration*\n"
        "- Migrated billing system\n"
        "- Cut deploy time in half"
    )

    proposals = build_experience_proposals(assembled, edited_text)
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert updated.achievements == ["Untagged bullet"]
    assert len(updated.projects) == 1
    assert updated.projects[0].name == "Client A Migration"
    assert updated.projects[0].achievements == ["Migrated billing system", "Cut deploy time in half"]


def test_experience_proposals_update_an_existing_project_by_name(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(company="Agency Co", position="Consultant")
    service.add_experience_project(entry.id, name="Client A Migration", achievements=["Old bullet"])

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id, position="Consultant", company="Agency Co", bullets=[]
        )
    ]
    edited_text = (
        "**Consultant** — Agency Co\n"
        "*Client A Migration*\n"
        "- New bullet"
    )

    proposals = build_experience_proposals(assembled, edited_text)
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert len(updated.projects) == 1  # updated in place, not duplicated
    assert updated.projects[0].achievements == ["New bullet"]


def test_experience_proposals_editing_a_hyperlinked_companys_bullets_does_not_corrupt_company(tmp_path):
    # Post-4.10 follow-up regression: a company with a known company_url
    # renders as "**Position** — [Company](url)" — editing the bullets
    # below it and saving must not write the literal "[Acme](url)" string
    # into Experience.company.
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(
        company="Acme", company_url="https://acme.example/", position="Engineer"
    )

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id,
            position="Engineer",
            company="Acme",
            company_url="https://acme.example/",
            bullets=[],
        )
    ]
    edited_text = "**Engineer** — [Acme](https://acme.example/) (2020-2023)\n- Did a thing"

    proposals = build_experience_proposals(assembled, edited_text)
    assert len(proposals) == 1
    assert proposals[0].enabled is True
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert updated.company == "Acme"
    assert updated.period == "2020-2023"
    assert updated.achievements == ["Did a thing"]


def test_experience_proposals_editing_a_hyperlinked_projects_bullets_updates_it_in_place(tmp_path):
    # Same regression as the company one above, for a project heading
    # rendered as "*[Project Name](url)*" — must update the existing
    # project by its plain name, not create a duplicate keyed by the
    # literal "[Name](url)" string.
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(company="Agency Co", position="Consultant")
    service.add_experience_project(
        entry.id, name="Client A Migration", url="https://client-a.example/", achievements=["Old bullet"]
    )

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id, position="Consultant", company="Agency Co", bullets=[]
        )
    ]
    edited_text = (
        "**Consultant** — Agency Co\n"
        "*[Client A Migration](https://client-a.example/)*\n"
        "- New bullet"
    )

    proposals = build_experience_proposals(assembled, edited_text)
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert len(updated.projects) == 1  # updated in place, not duplicated
    assert updated.projects[0].name == "Client A Migration"
    assert updated.projects[0].url == "https://client-a.example/"
    assert updated.projects[0].achievements == ["New bullet"]


def test_experience_proposals_returns_disabled_proposal_on_block_count_mismatch():
    assembled = [
        AssembledExperienceEntry(experience_id="exp-1", position="Engineer", company="Acme", bullets=[]),
        AssembledExperienceEntry(experience_id="exp-2", position="Lead", company="Globex", bullets=[]),
    ]
    edited_text = "**Engineer** — Acme\n- Only one block now"

    proposals = build_experience_proposals(assembled, edited_text)

    assert len(proposals) == 1
    assert proposals[0].enabled is False
    assert proposals[0].apply is None


def test_experience_proposals_skip_entry_with_unchanged_bullets():
    assembled = [
        AssembledExperienceEntry(
            experience_id="exp-1",
            position="Engineer",
            company="Acme",
            bullets=[TailoredBullet(text="Did a thing")],
        ),
    ]
    edited_text = "**Engineer** — Acme\n- Did a thing"

    proposals = build_experience_proposals(assembled, edited_text)

    assert proposals == []


def test_experience_proposals_only_include_entries_whose_bullets_changed():
    assembled = [
        AssembledExperienceEntry(
            experience_id="exp-1",
            position="Engineer",
            company="Acme",
            bullets=[TailoredBullet(text="Did a thing")],
        ),
        AssembledExperienceEntry(
            experience_id="exp-2",
            position="Lead",
            company="Globex",
            bullets=[TailoredBullet(text="Did another thing")],
        ),
    ]
    edited_text = (
        "**Engineer** — Acme\n- Did a thing\n\n"
        "**Lead** — Globex\n- Did another thing, tweaked"
    )

    proposals = build_experience_proposals(assembled, edited_text)

    assert [p.label for p in proposals] == ["Lead — Globex"]


def test_experience_proposals_include_entry_when_project_bullets_changed():
    assembled = [
        AssembledExperienceEntry(
            experience_id="exp-1",
            position="Consultant",
            company="Agency Co",
            bullets=[TailoredBullet(text="Old bullet", project="Client A Migration")],
        ),
    ]
    edited_text = (
        "**Consultant** — Agency Co\n"
        "*Client A Migration*\n"
        "- New bullet"
    )

    proposals = build_experience_proposals(assembled, edited_text)

    assert len(proposals) == 1


# ----- Phase 11: header facts (position/company/period) -------------------


def test_experience_proposals_detect_title_only_edit_with_unchanged_bullets(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(company="Acme", position="Engineer")

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id,
            position="Engineer",
            company="Acme",
            bullets=[TailoredBullet(text="Did a thing")],
        )
    ]
    edited_text = "**Lead Engineer** — Acme\n- Did a thing"

    proposals = build_experience_proposals(assembled, edited_text)

    assert len(proposals) == 1
    assert proposals[0].label == "Lead Engineer — Acme"
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert updated.position == "Lead Engineer"
    assert updated.company == "Acme"
    assert updated.achievements == ["Did a thing"]


def test_experience_proposals_apply_combined_facts_and_bullet_edit(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(company="Acme", position="Engineer", period="2020-2022")

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id, position="Engineer", company="Globex", period="2020-2022", bullets=[]
        )
    ]
    edited_text = "**Engineer** — Acme (2020-2023)\n- New bullet"

    proposals = build_experience_proposals(assembled, edited_text)
    assert len(proposals) == 1
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert updated.company == "Acme"
    assert updated.period == "2020-2023"
    assert updated.achievements == ["New bullet"]


def test_experience_proposals_detect_and_apply_location_change(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(company="Acme", position="Engineer", period="2020-2023")

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id, position="Engineer", company="Acme", period="2020-2023", bullets=[]
        )
    ]
    edited_text = "**Engineer** — Acme (2020-2023, Berlin)\n- New bullet"

    proposals = build_experience_proposals(assembled, edited_text)
    assert len(proposals) == 1
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert updated.location == "Berlin"
    assert updated.period == "2020-2023"


def test_experience_proposals_removing_location_clears_it(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(
        company="Acme", position="Engineer", period="2020-2023", location="Berlin"
    )

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id,
            position="Engineer",
            company="Acme",
            period="2020-2023",
            location="Berlin",
            bullets=[],
        )
    ]
    edited_text = "**Engineer** — Acme (2020-2023)\n- New bullet"

    proposals = build_experience_proposals(assembled, edited_text)
    assert len(proposals) == 1
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert updated.location is None


def test_experience_proposals_leave_facts_alone_when_header_is_unparseable(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(company="Acme", position="Engineer")

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id,
            position="Engineer",
            company="Acme",
            bullets=[TailoredBullet(text="Old bullet")],
        )
    ]
    # Bold markers removed -> _parse_header can't recover position/company.
    edited_text = "Engineer — Acme\n- New bullet"

    proposals = build_experience_proposals(assembled, edited_text)
    assert len(proposals) == 1
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert updated.position == "Engineer"
    assert updated.company == "Acme"
    assert updated.achievements == ["New bullet"]


# ----- Phase 11: project rename --------------------------------------------


def test_experience_proposals_rename_project_in_place_not_duplicated(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(company="Agency Co", position="Consultant")
    service.add_experience_project(entry.id, name="Client A", achievements=["Old bullet"])

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id, position="Consultant", company="Agency Co", bullets=[]
        )
    ]
    edited_text = "**Consultant** — Agency Co\n*Client A Migration*\n- Old bullet"

    proposals = build_experience_proposals(assembled, edited_text)
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert len(updated.projects) == 1  # renamed, not duplicated
    assert updated.projects[0].name == "Client A Migration"
    assert updated.projects[0].achievements == ["Old bullet"]


def test_experience_proposals_ambiguous_project_rename_falls_back_to_additive(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(company="Agency Co", position="Consultant")
    service.add_experience_project(entry.id, name="Client A", achievements=["A bullet"])

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id, position="Consultant", company="Agency Co", bullets=[]
        )
    ]
    # One removed ("Client A") but two added -> ambiguous, no rename guess.
    edited_text = (
        "**Consultant** — Agency Co\n"
        "*Client B*\n- B bullet\n"
        "*Client C*\n- C bullet"
    )

    proposals = build_experience_proposals(assembled, edited_text)
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    names = {p.name for p in updated.projects}
    assert names == {"Client A", "Client B", "Client C"}  # old one left untouched


def test_experience_proposals_add_project_to_role_with_none_yet(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    entry = service.add_experience(company="Agency Co", position="Consultant")

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id, position="Consultant", company="Agency Co", bullets=[]
        )
    ]
    edited_text = "**Consultant** — Agency Co\n*New Client*\n- First bullet"

    proposals = build_experience_proposals(assembled, edited_text)
    proposals[0].apply(service)

    updated = next(e for e in service.get().experience if e.id == entry.id)
    assert len(service.get().experience) == 1  # no new Experience/role created
    assert len(updated.projects) == 1
    assert updated.projects[0].name == "New Client"
    assert updated.projects[0].achievements == ["First bullet"]


def test_experience_proposals_positionally_match_multiple_roles_including_gaps(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    exp1 = service.add_experience(company="Acme", position="Engineer")
    gap = service.add_experience(position="Career Break", is_gap=True)
    exp2 = service.add_experience(company="Globex", position="Lead")

    assembled = [
        AssembledExperienceEntry(experience_id=exp1.id, position="Engineer", company="Acme", bullets=[]),
        AssembledExperienceEntry(experience_id=gap.id, position="Career Break", is_gap=True, bullets=[]),
        AssembledExperienceEntry(experience_id=exp2.id, position="Lead", company="Globex", bullets=[]),
    ]
    edited_text = (
        "**Engineer** — Acme\n- Bullet A\n\n"
        "*Career Break*\n\n"
        "**Lead** — Globex\n- Bullet B"
    )

    proposals = build_experience_proposals(assembled, edited_text)

    assert len(proposals) == 2  # gap entry excluded
    proposals[0].apply(service)
    proposals[1].apply(service)

    candidate = service.get()
    assert next(e for e in candidate.experience if e.id == exp1.id).achievements == ["Bullet A"]
    assert next(e for e in candidate.experience if e.id == exp2.id).achievements == ["Bullet B"]


# ----- Phase 19: build_proposals_from_document (structured PrintDocument) --


def test_parse_header_handles_both_bold_conventions():
    # render_experience_section() (desktop) bolds only Position; Phase 16c's
    # render_sections_from_document() (web) bolds the whole header line —
    # both must resolve to the same parsed facts.
    from app.graph_writeback import _parse_header

    assert _parse_header("**Engineer** — Acme (2020-2023)") == (
        "Engineer",
        "Acme",
        "2020-2023",
        None,
    )
    assert _parse_header("**Engineer — Acme (2020-2023)**") == (
        "Engineer",
        "Acme",
        "2020-2023",
        None,
    )


def test_parse_header_still_fails_safe_when_desktop_markers_are_missing():
    from app.graph_writeback import _parse_header

    assert _parse_header("Engineer — Acme (2020-2023)") is None


def test_parse_header_strips_a_hyperlinked_company_name_down_to_plain_text():
    # Post-4.10 follow-up: app/cv_markdown.py:render_experience_section now
    # renders a company with a known company_url as "[Acme](url)" — without
    # stripping this back down, _parse_header's lenient `.+?` capture would
    # happily swallow the whole "[Acme](https://acme.example/)" literal as
    # if it were the company name itself, corrupting Experience.company the
    # next time any other part of this block gets hand-edited and saved.
    from app.graph_writeback import _parse_header

    assert _parse_header("**Engineer** — [Acme](https://acme.example/) (2020-2023)") == (
        "Engineer",
        "Acme",
        "2020-2023",
        None,
    )
    # Both bold conventions (see test_parse_header_handles_both_bold_conventions).
    assert _parse_header("**Engineer — [Acme](https://acme.example/) (2020-2023)**") == (
        "Engineer",
        "Acme",
        "2020-2023",
        None,
    )


def test_strip_markdown_link_leaves_plain_text_unchanged():
    from app.graph_writeback import _strip_markdown_link

    assert _strip_markdown_link("Acme") == "Acme"
    assert _strip_markdown_link("[Acme](https://acme.example/)") == "Acme"


def test_build_proposals_from_document_detects_an_edited_bullet(tmp_path):
    service = make_service(tmp_path)
    service.create(name="Ada Lovelace")
    service.add_skill(name="Python")
    entry = service.add_experience(company="Acme", position="Engineer", period="2020-2023")
    service.update_experience(entry.id, achievements=["Did a thing"])
    candidate = service.get()

    assembled = [
        AssembledExperienceEntry(
            experience_id=entry.id,
            position="Engineer",
            company="Acme",
            period="2020-2023",
            bullets=[TailoredBullet(text="Did a thing")],
        )
    ]
    document = PrintDocument.model_validate(
        {
            "sections": [
                {
                    "key": "summary",
                    "title": "Summary",
                    "included": True,
                    "entries": [{"id": "summary", "text": "A tailored summary.", "included": True}],
                },
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {"id": "s0", "text": "Python", "included": True},
                        {"id": "s1", "text": "Go", "included": True},
                    ],
                },
                {
                    "key": "experience",
                    "title": "Experience",
                    "included": True,
                    "entries": [
                        {
                            "id": entry.id,
                            "text": "Engineer — Acme (2020-2023)",
                            "included": True,
                            "bullets": [
                                {"id": "b0", "text": "Did a bigger thing", "included": True}
                            ],
                        }
                    ],
                },
            ]
        }
    )

    proposals = build_proposals_from_document(candidate, assembled, document)

    labels = [p.label for p in proposals]
    assert labels[0] == "Update candidate summary"
    assert "Add skill: Go" in labels
    assert any(label.startswith("Engineer") for label in labels)

    for proposal in proposals:
        proposal.apply(service)

    updated = service.get()
    assert updated.summary == "A tailored summary."
    assert {s.name for s in updated.skills} == {"Python", "Go"}
    assert next(e for e in updated.experience if e.id == entry.id).achievements == [
        "Did a bigger thing"
    ]
