from app.cv_markdown import (
    ENTRY_PAGE_BREAK_MARKER,
    SECTION_PAGE_BREAK_MARKER,
    SECTION_TITLES,
    assemble_markdown_from_sections,
    render_all_sections,
    render_awards_section,
    render_certifications_section,
    render_contacts_section,
    render_education_section,
    render_experience_section,
    render_full_markdown,
    render_header,
    render_languages_section,
    render_portfolio_links_section,
    render_projects_section,
    render_publications_section,
    render_sections_from_document,
    render_skills_section,
    render_summary_section,
    render_technologies_section,
    render_volunteer_experience_section,
)
from domain.models import (
    AssembledCV,
    AssembledExperienceEntry,
    Award,
    Certification,
    ContactItem,
    Education,
    Language,
    PortfolioLink,
    PrintDocument,
    Project,
    Publication,
    Skill,
    Technology,
    TailoredBullet,
    VolunteerExperience,
)


def make_cv(**overrides) -> AssembledCV:
    defaults = dict(name="Ada Lovelace", summary="A summary.")
    defaults.update(overrides)
    return AssembledCV(**defaults)


# ----- render_header ---------------------------------------------------


def test_render_header_includes_name_and_headline():
    cv = make_cv(headline="Analytical Engineer")

    assert render_header(cv) == "# Ada Lovelace\n*Analytical Engineer*"


def test_render_header_no_longer_includes_contacts():
    # Contacts moved out of the header into its own section (see
    # render_contacts_section below) so each contact can be independently
    # included/excluded like every other CV fact.
    cv = make_cv(contacts=[ContactItem(id="contact-1", label="Email", value="ada@example.com")])

    assert "Email" not in render_header(cv)


def test_render_header_omits_missing_fields():
    cv = make_cv()

    assert render_header(cv) == "# Ada Lovelace"


def test_render_header_includes_employment_types_sought():
    cv = make_cv(employment_types_sought=["Full-time", "Contract"])

    header = render_header(cv)

    assert "Seeking: Full-time, Contract" in header


# ----- render_contacts_section -------------------------------------------


def test_render_contacts_section_formats_one_bullet_per_contact():
    cv = make_cv(
        contacts=[
            ContactItem(id="contact-1", label="Email", value="ada@example.com"),
            ContactItem(id="contact-2", label="Phone", value="+44 1234"),
        ]
    )

    assert render_contacts_section(cv) == "- Email: ada@example.com\n- Phone: +44 1234"


def test_render_contacts_section_supports_arbitrary_labels():
    cv = make_cv(
        contacts=[
            ContactItem(id="contact-1", label="LinkedIn", value="linkedin.com/in/ada"),
            ContactItem(id="contact-2", label="Work Authorization", value="No visa support required"),
        ]
    )

    contacts = render_contacts_section(cv)

    assert "- LinkedIn: linkedin.com/in/ada" in contacts
    assert "- Work Authorization: No visa support required" in contacts


def test_render_contacts_section_empty_when_none():
    assert render_contacts_section(make_cv()) == ""


# ----- render_experience_section ----------------------------------------


def test_render_experience_section_formats_role_with_bullets():
    cv = make_cv(
        experience=[
            AssembledExperienceEntry(
                company="Acme",
                position="Engineer",
                period="2020-2023",
                bullets=[
                    TailoredBullet(text="Did a thing"),
                    TailoredBullet(text="Did another thing"),
                ],
            )
        ]
    )

    section = render_experience_section(cv)

    assert section == (
        "**Engineer** — Acme (2020-2023)\n- Did a thing\n- Did another thing"
    )


def test_render_experience_section_links_the_company_name_when_company_url_is_set():
    # Post-4.10 follow-up — closes a real ingestion gap: a source PDF
    # hyperlinking a company name to its own site had nowhere to put that
    # URL at all before company_url existed.
    cv = make_cv(
        experience=[
            AssembledExperienceEntry(
                company="Acme",
                company_url="https://acme.example/",
                position="Engineer",
                period="2020-2023",
            )
        ]
    )

    section = render_experience_section(cv)

    assert section == "**Engineer** — [Acme](https://acme.example/) (2020-2023)"


def test_render_experience_section_links_the_company_name_on_a_gap_entry_too():
    cv = make_cv(
        experience=[
            AssembledExperienceEntry(
                company="Acme",
                company_url="https://acme.example/",
                position="Sabbatical",
                period="2023-2024",
                is_gap=True,
            )
        ]
    )

    assert render_experience_section(cv) == "*Sabbatical*, [Acme](https://acme.example/) (2023-2024)"


def test_render_experience_section_leaves_company_plain_without_a_company_url():
    cv = make_cv(experience=[AssembledExperienceEntry(company="Acme", position="Engineer")])

    assert render_experience_section(cv) == "**Engineer** — Acme"


def test_render_experience_section_groups_location_with_period():
    cv = make_cv(
        experience=[
            AssembledExperienceEntry(
                company="Acme", position="Engineer", period="2020-2023", location="Berlin"
            )
        ]
    )

    section = render_experience_section(cv)

    assert section == "**Engineer** — Acme (2020-2023, Berlin)"


def test_render_experience_section_location_without_period():
    cv = make_cv(
        experience=[AssembledExperienceEntry(company="Acme", position="Engineer", location="Berlin")]
    )

    section = render_experience_section(cv)

    assert section == "**Engineer** — Acme (Berlin)"


def test_render_experience_section_groups_bullets_by_project():
    cv = make_cv(
        experience=[
            AssembledExperienceEntry(
                company="Agency Co",
                position="Consultant",
                bullets=[
                    TailoredBullet(text="Untagged bullet"),
                    TailoredBullet(text="Migrated billing system", project="Client A Migration"),
                    TailoredBullet(text="Cut deploy time in half", project="Client A Migration"),
                    TailoredBullet(text="Launched rollout", project="Client B Rollout"),
                ],
            )
        ]
    )

    section = render_experience_section(cv)

    assert section == (
        "**Consultant** — Agency Co\n"
        "- Untagged bullet\n"
        "*Client A Migration*\n"
        "- Migrated billing system\n"
        "- Cut deploy time in half\n"
        "*Client B Rollout*\n"
        "- Launched rollout"
    )


def test_render_experience_section_links_a_project_heading_when_project_urls_has_it():
    cv = make_cv(
        experience=[
            AssembledExperienceEntry(
                company="Agency Co",
                position="Consultant",
                bullets=[
                    TailoredBullet(text="Migrated billing system", project="Client A Migration"),
                    TailoredBullet(text="Launched rollout", project="Client B Rollout"),
                ],
                project_urls={"Client A Migration": "https://client-a.example/"},
            )
        ]
    )

    section = render_experience_section(cv)

    assert section == (
        "**Consultant** — Agency Co\n"
        "*[Client A Migration](https://client-a.example/)*\n"
        "- Migrated billing system\n"
        "*Client B Rollout*\n"
        "- Launched rollout"
    )


def test_render_experience_section_merges_interleaved_bullets_of_the_same_project():
    cv = make_cv(
        experience=[
            AssembledExperienceEntry(
                company="Agency Co",
                position="Consultant",
                bullets=[
                    TailoredBullet(text="First A bullet", project="Client A Migration"),
                    TailoredBullet(text="B bullet", project="Client B Rollout"),
                    TailoredBullet(text="Second A bullet", project="Client A Migration"),
                ],
            )
        ]
    )

    section = render_experience_section(cv)

    assert section == (
        "**Consultant** — Agency Co\n"
        "*Client A Migration*\n"
        "- First A bullet\n"
        "- Second A bullet\n"
        "*Client B Rollout*\n"
        "- B bullet"
    )


def test_render_experience_section_formats_gap_without_bullets():
    cv = make_cv(
        experience=[
            AssembledExperienceEntry(
                position="Maternity Leave", company="Acme", period="2023-2024", is_gap=True
            )
        ]
    )

    section = render_experience_section(cv)

    assert section == "*Maternity Leave*, Acme (2023-2024)"


def test_render_experience_section_gap_with_location():
    cv = make_cv(
        experience=[
            AssembledExperienceEntry(
                position="Sabbatical", period="2023-2024", location="Bali", is_gap=True
            )
        ]
    )

    assert render_experience_section(cv) == "*Sabbatical* (2023-2024, Bali)"


def test_render_experience_section_handles_missing_company():
    cv = make_cv(
        experience=[AssembledExperienceEntry(position="Career Break", is_gap=True)]
    )

    assert render_experience_section(cv) == "*Career Break*"


def test_render_experience_section_empty_when_no_experience():
    assert render_experience_section(make_cv()) == ""


def test_render_experience_section_separates_multiple_entries():
    cv = make_cv(
        experience=[
            AssembledExperienceEntry(
                company="Acme", position="Engineer", bullets=[TailoredBullet(text="A")]
            ),
            AssembledExperienceEntry(position="Career Break", is_gap=True),
            AssembledExperienceEntry(
                company="Globex", position="Lead", bullets=[TailoredBullet(text="B")]
            ),
        ]
    )

    section = render_experience_section(cv)

    assert section == (
        "**Engineer** — Acme\n- A\n\n*Career Break*\n\n**Lead** — Globex\n- B"
    )


# ----- render_volunteer_experience_section --------------------------------


def test_render_volunteer_experience_section_includes_period_and_description():
    cv = make_cv(
        volunteer_experience=[
            VolunteerExperience(
                id="vol-1",
                organization="Code.org",
                role="Mentor",
                period="2021-2022",
                description="Taught kids to code",
            )
        ]
    )

    assert render_volunteer_experience_section(cv) == (
        "- **Mentor** — Code.org (2021-2022): Taught kids to code"
    )


def test_render_volunteer_experience_section_handles_missing_period_and_description():
    cv = make_cv(
        volunteer_experience=[VolunteerExperience(id="vol-1", organization="Code.org", role="Mentor")]
    )

    assert render_volunteer_experience_section(cv) == "- **Mentor** — Code.org"


def test_render_volunteer_experience_section_empty_when_none():
    assert render_volunteer_experience_section(make_cv()) == ""


# ----- other sections -----------------------------------------------------


def test_render_summary_section_returns_summary_text():
    assert render_summary_section(make_cv(summary="Hello.")) == "Hello."


def test_render_education_section_formats_entries():
    cv = make_cv(
        education=[
            Education(id="edu-1", institution="MIT", degree="BSc", field="CS", period="2010-2014")
        ]
    )

    assert render_education_section(cv) == "- **MIT** — BSc, CS (2010-2014)"


def test_render_education_section_empty_when_none():
    assert render_education_section(make_cv()) == ""


def test_render_skills_section_formats_uncategorized_as_plain_bullets():
    cv = make_cv(skills=[Skill(id="s1", name="Python"), Skill(id="s2", name="SQL")])

    assert render_skills_section(cv) == "- Python\n- SQL"


def test_render_skills_section_groups_by_category():
    cv = make_cv(
        skills=[
            Skill(id="s1", name="Roadmapping", category="Expertise"),
            Skill(id="s2", name="Team Management", category="Expertise"),
            Skill(id="s3", name="Unity", category="Tools"),
        ]
    )

    assert render_skills_section(cv) == (
        "- **Expertise**: Roadmapping; Team Management\n- **Tools**: Unity"
    )


def test_render_skills_section_empty_when_no_skills():
    assert render_skills_section(make_cv()) == ""


def test_render_skills_section_includes_proficiency():
    # Regression: an earlier version of _render_grouped_by_category dropped
    # proficiency entirely for Skills.
    cv = make_cv(
        skills=[Skill(id="s1", name="Roadmapping", category="Expertise", proficiency="Expert")]
    )

    assert render_skills_section(cv) == "- **Expertise**: Roadmapping (Expert)"


def test_render_skills_section_single_item_category_has_no_trailing_semicolon():
    cv = make_cv(skills=[Skill(id="s1", name="Roadmapping", category="Expertise")])

    assert render_skills_section(cv) == "- **Expertise**: Roadmapping"


def test_render_skills_section_mixes_categorized_and_uncategorized():
    # A resume section can have some category-labeled lines and some bare
    # ones side by side — the categorized ones compact onto one line each,
    # the uncategorized ones stay individual plain bullets, in whatever
    # order they were extracted.
    cv = make_cv(
        skills=[
            Skill(id="s1", name="Mentoring"),
            Skill(id="s2", name="Roadmapping", category="Expertise"),
            Skill(id="s3", name="Team Management", category="Expertise"),
            Skill(id="s4", name="Public Speaking"),
        ]
    )

    assert render_skills_section(cv) == (
        "- Mentoring\n- **Expertise**: Roadmapping; Team Management\n- Public Speaking"
    )


def test_render_technologies_section_groups_by_category_with_proficiency():
    cv = make_cv(
        technologies=[
            Technology(id="tech-1", name="Python", category="Language", proficiency="Advanced"),
            Technology(id="tech-2", name="Unity", category="Tools"),
        ]
    )

    assert render_technologies_section(cv) == (
        "- **Language**: Python (Advanced)\n- **Tools**: Unity"
    )


def test_render_technologies_section_formats_uncategorized_as_plain_bullets():
    cv = make_cv(technologies=[Technology(id="tech-1", name="Python")])

    assert render_technologies_section(cv) == "- Python"


def test_render_technologies_section_empty_when_none():
    assert render_technologies_section(make_cv()) == ""


def test_render_languages_section_includes_proficiency():
    cv = make_cv(languages=[Language(id="lang-1", name="English", proficiency="Native")])

    assert render_languages_section(cv) == "- English (Native)"


def test_render_certifications_section_includes_issuer_and_date():
    cv = make_cv(
        certifications=[Certification(id="cert-1", name="PMP", issuer="PMI", date="2024")]
    )

    assert render_certifications_section(cv) == "- PMP — PMI, 2024"


def test_render_awards_section_includes_issuer_and_date():
    cv = make_cv(awards=[Award(id="award-1", name="Best in Show", issuer="GDC", date="2023")])

    assert render_awards_section(cv) == "- Best in Show — GDC, 2023"


def test_render_awards_section_handles_missing_issuer_and_date():
    cv = make_cv(awards=[Award(id="award-1", name="Best in Show")])

    assert render_awards_section(cv) == "- Best in Show"


def test_render_awards_section_empty_when_none():
    assert render_awards_section(make_cv()) == ""


def test_render_projects_section_includes_description_and_url():
    cv = make_cv(
        projects=[
            Project(
                id="proj-1",
                name="SuperCity",
                description="web & mobile (city building game)",
                url="https://example.com/supercity",
            )
        ]
    )

    assert render_projects_section(cv) == (
        "- **SuperCity** — web & mobile (city building game) (https://example.com/supercity)"
    )


def test_render_projects_section_handles_missing_description_and_url():
    cv = make_cv(projects=[Project(id="proj-1", name="Side Project")])

    assert render_projects_section(cv) == "- **Side Project**"


def test_render_projects_section_empty_when_no_projects():
    assert render_projects_section(make_cv()) == ""


# ----- render_publications_section ----------------------------------------


def test_render_publications_section_includes_venue_date_and_url():
    cv = make_cv(
        publications=[
            Publication(
                id="pub-1",
                title="Scaling LiveOps",
                venue="Medium",
                date="2023",
                url="https://medium.com/x",
            )
        ]
    )

    assert render_publications_section(cv) == (
        "- **Scaling LiveOps** — Medium, 2023 (https://medium.com/x)"
    )


def test_render_publications_section_handles_missing_venue_date_and_url():
    cv = make_cv(publications=[Publication(id="pub-1", title="Scaling LiveOps")])

    assert render_publications_section(cv) == "- **Scaling LiveOps**"


def test_render_publications_section_empty_when_none():
    assert render_publications_section(make_cv()) == ""


# ----- render_portfolio_links_section -----------------------------------


def test_render_portfolio_links_section_includes_description():
    cv = make_cv(
        portfolio_links=[
            PortfolioLink(id="link-1", url="https://artstation.com/ada", description="Concept art")
        ]
    )

    assert render_portfolio_links_section(cv) == "- Concept art — https://artstation.com/ada"


def test_render_portfolio_links_section_handles_missing_description():
    cv = make_cv(portfolio_links=[PortfolioLink(id="link-1", url="https://github.com/ada")])

    assert render_portfolio_links_section(cv) == "- https://github.com/ada"


def test_render_portfolio_links_section_empty_when_no_links():
    assert render_portfolio_links_section(make_cv()) == ""


# ----- render_all_sections / render_full_markdown / assemble_markdown_from_sections ----


def test_render_all_sections_covers_every_section_title_key():
    cv = make_cv()

    sections = render_all_sections(cv)

    assert set(sections.keys()) == set(SECTION_TITLES.keys())


def test_render_full_markdown_skips_empty_sections():
    cv = make_cv(summary="A summary.")  # no experience/education/skills/etc

    markdown = render_full_markdown(cv)

    assert "## Summary" in markdown
    assert "## Key Projects" not in markdown
    assert "## Experience" not in markdown
    assert "## Education" not in markdown
    assert "## Skills" not in markdown


def test_render_full_markdown_matches_reassembled_sections():
    cv = make_cv(
        headline="Engineer",
        experience=[
            AssembledExperienceEntry(
                company="Acme", position="Engineer", bullets=[TailoredBullet(text="A")]
            )
        ],
        skills=[Skill(id="s1", name="Python")],
        languages=[Language(id="lang-1", name="English")],
    )

    full = render_full_markdown(cv)
    header = render_header(cv)
    sections = render_all_sections(cv)
    reassembled = assemble_markdown_from_sections(header, sections)

    assert full == reassembled


def test_render_full_markdown_uses_russian_headings_for_a_russian_candidate():
    cv = make_cv(language="ru", summary="О себе.", skills=[Skill(id="s1", name="Python")])

    markdown = render_full_markdown(cv)

    assert "## О себе" in markdown
    assert "## Навыки" in markdown
    assert "## Summary" not in markdown


def test_render_full_markdown_falls_back_to_english_for_an_unknown_language():
    cv = make_cv(language="fr", summary="A summary.")

    markdown = render_full_markdown(cv)

    assert "## Summary" in markdown


def test_assemble_markdown_from_sections_uses_russian_headings_when_requested():
    markdown = assemble_markdown_from_sections(
        "# Иван Иванов", {"summary": "Текст."}, language="ru"
    )

    assert "## О себе" in markdown
    assert "## Summary" not in markdown


def test_assemble_markdown_from_sections_defaults_to_english_headings():
    markdown = assemble_markdown_from_sections("# Ada Lovelace", {"summary": "A summary."})

    assert "## Summary" in markdown


def test_assemble_markdown_from_sections_skips_blank_sections():
    markdown = assemble_markdown_from_sections(
        "# Ada Lovelace", {"summary": "A summary.", "experience": "   ", "skills": ""}
    )

    assert "## Summary" in markdown
    assert "## Experience" not in markdown
    assert "## Skills" not in markdown


def test_assemble_markdown_from_sections_uses_edited_text_verbatim():
    # Manual edits shouldn't be re-validated/re-parsed — just concatenated.
    markdown = assemble_markdown_from_sections(
        "# Ada Lovelace", {"summary": "Hand-edited summary with a typo fixed."}
    )

    assert "Hand-edited summary with a typo fixed." in markdown


class TestRenderSectionsFromDocument:
    """Phase 16c — the inverse of render_all_sections: PrintDocument (the
    A4 Preview tab's edited state) back into the same {key: text} shape,
    so assemble_markdown_from_sections/render_pdf/render_docx keep working
    unchanged."""

    def test_summary_is_bare_text_no_marker(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "summary",
                    "title": "Summary",
                    "included": True,
                    "entries": [{"id": "summary", "text": "A summary.", "included": True}],
                }
            ]
        )

        assert render_sections_from_document(document) == {"summary": "A summary."}

    def test_skills_category_and_its_members_become_one_compact_line(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading"},
                        {"id": "s1", "text": "Roadmapping (Expertise)", "included": True},
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == "- **Design**: Roadmapping (Expertise)"

    def test_skills_multiple_categories_each_get_their_own_compact_line(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading"},
                        {"id": "s1", "text": "Roadmapping", "included": True},
                        {"id": "s2", "text": "Level Design", "included": True},
                        {"id": "cat-2", "text": "Tools", "included": True, "kind": "subheading"},
                        {"id": "s3", "text": "Unity", "included": True},
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == (
            "- **Design**: Roadmapping; Level Design\n- **Tools**: Unity"
        )

    def test_skills_uncategorized_entries_stay_individually_bulleted(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {"id": "s0", "text": "Mentoring", "included": True},
                        {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading"},
                        {"id": "s1", "text": "Roadmapping", "included": True},
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == (
            "- Mentoring\n- **Design**: Roadmapping"
        )

    def test_skills_category_with_no_included_members_has_no_trailing_colon(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [{"id": "cat-1", "text": "Design", "included": True, "kind": "subheading"}],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == "- **Design**"

    def test_experience_role_bold_gap_italic_project_subheading_italic(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "experience",
                    "title": "Experience",
                    "included": True,
                    "entries": [
                        {
                            "id": "exp-1",
                            "text": "Engineer — Acme",
                            "included": True,
                            "locked": False,
                            "bullets": [
                                {"id": "b1", "text": "Shipped a feature", "included": True},
                                {"id": "proj-1", "text": "Internal tool", "included": True, "kind": "subheading"},
                                {"id": "b2", "text": "Owned the backend", "included": True},
                            ],
                        },
                        {"id": "exp-2", "text": "Career break", "included": True, "locked": True, "bullets": []},
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["experience"] == (
            "**Engineer — Acme**\n"
            "- Shipped a feature\n"
            "*Internal tool*\n"
            "- Owned the backend\n"
            "\n"
            "*Career break*"
        )

    def test_excluded_section_entry_and_bullet_produce_no_output(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "experience",
                    "title": "Experience",
                    "included": True,
                    "entries": [
                        {
                            "id": "exp-1",
                            "text": "Engineer — Acme",
                            "included": True,
                            "bullets": [
                                {"id": "b1", "text": "Included bullet", "included": True},
                                {"id": "b2", "text": "Excluded bullet", "included": False},
                            ],
                        },
                        {"id": "exp-2", "text": "Excluded role", "included": False},
                    ],
                },
                {
                    "key": "education",
                    "title": "Education",
                    "included": False,
                    "entries": [{"id": "edu-1", "text": "State University", "included": True}],
                },
            ]
        )

        result = render_sections_from_document(document)
        assert "Included bullet" in result["experience"]
        assert "Excluded bullet" not in result["experience"]
        assert "Excluded role" not in result["experience"]
        assert "education" not in result

    # ----- Phase 25: runs are authoritative over text, for Summary and
    # Experience only (see _block_markdown_text's docstring) -------------

    def test_summary_entry_with_runs_serializes_them_instead_of_text(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "summary",
                    "title": "Summary",
                    "included": True,
                    "entries": [
                        {
                            "id": "summary",
                            "text": "stale plain text",
                            "included": True,
                            "runs": [
                                {"text": "Ships "},
                                {"text": "quality", "bold": True},
                                {"text": " software."},
                            ],
                        }
                    ],
                }
            ]
        )

        assert render_sections_from_document(document) == {"summary": "Ships **quality** software."}

    def test_experience_role_with_runs_overrides_the_automatic_bold_wrapping(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "experience",
                    "title": "Experience",
                    "included": True,
                    "entries": [
                        {
                            "id": "exp-1",
                            "text": "stale plain text",
                            "included": True,
                            "runs": [{"text": "Engineer"}, {"text": " — Acme", "italic": True}],
                            "bullets": [],
                        }
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["experience"] == "Engineer* — Acme*"

    def test_adjacent_bold_then_italic_runs_get_a_zero_width_space_at_the_boundary(self):
        # Regression: found from a real hand-crafted export, not a
        # theoretical case. {"Engineer", bold} + {" — Acme", italic}
        # serializes to "**Engineer**" + "* — Acme*" — concatenated
        # naively that's "**Engineer*** — Acme*", three "*" in a row,
        # ambiguous to a human or a real Markdown renderer glancing at
        # the raw .md export (though never re-parsed by this app itself).
        document = PrintDocument(
            sections=[
                {
                    "key": "experience",
                    "title": "Experience",
                    "included": True,
                    "entries": [
                        {
                            "id": "exp-1",
                            "text": "stale plain text",
                            "included": True,
                            "runs": [
                                {"text": "Engineer", "bold": True},
                                {"text": " — Acme", "italic": True},
                            ],
                            "bullets": [],
                        }
                    ],
                }
            ]
        )

        result = render_sections_from_document(document)["experience"]
        zero_width_space = chr(0x200B)

        assert result == f"**Engineer**{zero_width_space}* — Acme*"
        assert "***" not in result

    def test_experience_gap_entry_with_runs_is_not_also_wrapped_in_the_default_italic(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "experience",
                    "title": "Experience",
                    "included": True,
                    "entries": [
                        {
                            "id": "exp-1",
                            "text": "stale plain text",
                            "included": True,
                            "locked": True,
                            "runs": [{"text": "Career break", "underline": True}],
                            "bullets": [],
                        }
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["experience"] == "__Career break__"

    def test_experience_bullet_with_runs_keeps_its_list_marker(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "experience",
                    "title": "Experience",
                    "included": True,
                    "entries": [
                        {
                            "id": "exp-1",
                            "text": "Engineer — Acme",
                            "included": True,
                            "bullets": [
                                {
                                    "id": "b1",
                                    "text": "stale plain text",
                                    "included": True,
                                    "runs": [{"text": "Shipped a ", "bold": True}, {"text": "feature"}],
                                }
                            ],
                        }
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["experience"] == (
            "**Engineer — Acme**\n- **Shipped a **feature"
        )

    def test_experience_project_subheading_with_runs_is_not_also_wrapped_in_the_default_italic(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "experience",
                    "title": "Experience",
                    "included": True,
                    "entries": [
                        {
                            "id": "exp-1",
                            "text": "Engineer — Acme",
                            "included": True,
                            "bullets": [
                                {
                                    "id": "proj-1",
                                    "text": "stale plain text",
                                    "included": True,
                                    "kind": "subheading",
                                    "runs": [{"text": "Internal tool", "link": "https://example.com"}],
                                }
                            ],
                        }
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["experience"] == (
            "**Engineer — Acme**\n[Internal tool](https://example.com)"
        )

    def test_education_entry_runs_are_honored(self):
        # Phase 31 widened runs support past Summary/Experience to every
        # section — a standalone (ungrouped) Education entry now renders
        # its own `runs` via the generic else-branch, same as Experience
        # already did (see _block_markdown_text's/RunsRenderable's own
        # docstrings for the still-legacy grouped-category exception this
        # doesn't cover).
        document = PrintDocument(
            sections=[
                {
                    "key": "education",
                    "title": "Education",
                    "included": True,
                    "entries": [
                        {
                            "id": "edu-1",
                            "text": "State University",
                            "included": True,
                            "runs": [{"text": "State University", "bold": True}],
                        }
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["education"] == "- **State University**"

    def test_entirely_empty_section_is_omitted_not_an_empty_string(self):
        document = PrintDocument(
            sections=[{"key": "certifications", "title": "Certifications", "included": True, "entries": []}]
        )

        assert render_sections_from_document(document) == {}

    def test_entries_appear_in_the_given_already_reordered_order(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "education",
                    "title": "Education",
                    "included": True,
                    "entries": [
                        {"id": "edu-2", "text": "Second entry", "included": True},
                        {"id": "edu-1", "text": "First entry", "included": True},
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["education"] == "- Second entry\n- First entry"

    def test_output_feeds_assemble_markdown_from_sections_unchanged(self):
        # Integration check: the serializer's output is exactly what
        # assemble_markdown_from_sections already expects — no new parsing
        # logic needed on that end.
        document = PrintDocument(
            sections=[
                {
                    "key": "summary",
                    "title": "Summary",
                    "included": True,
                    "entries": [{"id": "summary", "text": "A summary.", "included": True}],
                }
            ]
        )

        markdown = assemble_markdown_from_sections("# Ada Lovelace", render_sections_from_document(document))

        assert markdown == "# Ada Lovelace\n\n## Summary\nA summary.\n"

    # ----- Phase 30: manual pagination control -----------------------

    def test_section_page_break_before_emits_a_leading_marker_line(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "summary",
                    "title": "Summary",
                    "included": True,
                    "page_break_before": True,
                    "entries": [{"id": "summary", "text": "A summary.", "included": True}],
                }
            ]
        )

        assert render_sections_from_document(document)["summary"] == f"{SECTION_PAGE_BREAK_MARKER}\nA summary."

    def test_section_without_page_break_before_emits_no_marker(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "summary",
                    "title": "Summary",
                    "included": True,
                    "entries": [{"id": "summary", "text": "A summary.", "included": True}],
                }
            ]
        )

        assert render_sections_from_document(document)["summary"] == "A summary."

    def test_summary_entry_page_break_before_emits_a_marker_before_just_that_entry(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "summary",
                    "title": "Summary",
                    "included": True,
                    "entries": [
                        {"id": "s1", "text": "First.", "included": True},
                        {"id": "s2", "text": "Second.", "included": True, "page_break_before": True},
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["summary"] == f"First.\n{ENTRY_PAGE_BREAK_MARKER}\nSecond."

    def test_experience_entry_page_break_before_emits_a_marker_before_the_role_header(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "experience",
                    "title": "Experience",
                    "included": True,
                    "entries": [
                        {
                            "id": "exp-1",
                            "text": "Engineer — Acme",
                            "included": True,
                            "page_break_before": True,
                            "bullets": [{"id": "b1", "text": "Shipped a feature", "included": True}],
                        }
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["experience"] == (
            f"{ENTRY_PAGE_BREAK_MARKER}\n**Engineer — Acme**\n- Shipped a feature"
        )

    def test_skills_category_page_break_before_emits_a_marker_before_the_grouped_line(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading", "page_break_before": True},
                        {"id": "s1", "text": "Roadmapping", "included": True},
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == (
            f"{ENTRY_PAGE_BREAK_MARKER}\n- **Design**: Roadmapping"
        )

    def test_skills_multiple_flat_members_join_onto_one_line(self):
        # Post-30 — a flat (uncategorized) run of Skills/Technologies
        # members joins onto one `" · "`-separated `- ` line instead of
        # one bulleted line per member — reported directly, a long flat
        # skill list read as too many separate lines.
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {"id": "s0", "text": "Mentoring", "included": True},
                        {"id": "s1", "text": "Roadmapping", "included": True},
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == "- Mentoring · Roadmapping"

    def test_skills_first_flat_members_page_break_before_emits_a_marker_before_the_whole_joined_line(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {"id": "s0", "text": "Mentoring", "included": True, "page_break_before": True},
                        {"id": "s1", "text": "Roadmapping", "included": True},
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == (
            f"{ENTRY_PAGE_BREAK_MARKER}\n- Mentoring · Roadmapping"
        )

    def test_skills_a_later_flat_members_page_break_before_is_silently_absorbed(self):
        # The mirror case: a flag on anything but the *first* member has
        # no line of its own left to attach to once joined, and is
        # silently dropped rather than (wrongly) forcing a break before
        # the section's very first line.
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {"id": "s0", "text": "Mentoring", "included": True},
                        {"id": "s1", "text": "Roadmapping", "included": True, "page_break_before": True},
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == "- Mentoring · Roadmapping"

    # ----- Post-31: pre-rendered compact Skills/Technologies entries ----

    def test_compact_category_entry_renders_its_runs_as_real_bold_markdown_no_bullet(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {
                            "id": "skills-0",
                            "text": "Design: Roadmapping; UX Design",
                            "included": True,
                            "kind": "compact",
                            "runs": [
                                {"text": "Design", "bold": True},
                                {"text": ": Roadmapping; UX Design", "bold": False},
                            ],
                        }
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == "**Design**: Roadmapping; UX Design"

    def test_compact_flat_entry_renders_plain_with_no_bullet(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {
                            "id": "skills-0",
                            "text": "Mentoring · Team Management",
                            "included": True,
                            "kind": "compact",
                        }
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == "Mentoring · Team Management"

    def test_two_compact_entries_render_as_two_separate_lines_not_rejoined(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {
                            "id": "skills-0",
                            "text": "Mentoring",
                            "included": True,
                            "kind": "compact",
                        },
                        {
                            "id": "skills-1",
                            "text": "Design: Roadmapping",
                            "included": True,
                            "kind": "compact",
                            "runs": [
                                {"text": "Design", "bold": True},
                                {"text": ": Roadmapping", "bold": False},
                            ],
                        },
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == "Mentoring\n**Design**: Roadmapping"

    def test_compact_entry_page_break_before_emits_a_marker_before_just_that_entry(self):
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {"id": "skills-0", "text": "Mentoring", "included": True, "kind": "compact"},
                        {
                            "id": "skills-1",
                            "text": "Design: Roadmapping",
                            "included": True,
                            "kind": "compact",
                            "page_break_before": True,
                        },
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == (
            f"Mentoring\n{ENTRY_PAGE_BREAK_MARKER}\nDesign: Roadmapping"
        )

    def test_a_section_that_is_not_yet_fully_compact_still_uses_the_legacy_grouping_path(self):
        # Only reached once every included entry carries kind == "compact"
        # — a section with even one legacy-shape entry left (an old
        # subheading + member pair here) still goes through
        # group_entries_by_subheading, unaffected by this Phase.
        document = PrintDocument(
            sections=[
                {
                    "key": "skills",
                    "title": "Skills",
                    "included": True,
                    "entries": [
                        {"id": "skills-0", "text": "Mentoring", "included": True, "kind": "compact"},
                        {"id": "cat-1", "text": "Design", "included": True, "kind": "subheading"},
                        {"id": "s1", "text": "Roadmapping", "included": True},
                    ],
                }
            ]
        )

        assert render_sections_from_document(document)["skills"] == (
            "- Mentoring\n- **Design**: Roadmapping"
        )
