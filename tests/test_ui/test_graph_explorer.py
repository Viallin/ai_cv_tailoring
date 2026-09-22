"""Phase 12.3 UI Tests for ui/graph_explorer.py — plain PySide6, no
pytest-qt (same tooling decision as tests/test_ui/test_main_window.py).

_EntityListSection is tested thoroughly once, against Skills as the
representative simple entity — Education/Languages/Certifications/
Projects/Contacts/Portfolio Links/Awards/Publications/Volunteer Experience/
Technologies all share the exact same generic code path (see
GraphExplorerPanel's construction loop in ui/graph_explorer.py), so this
covers all eleven without duplicating near-identical tests per entity type
— each of the newer ones gets one add/list test below, just to catch a
wiring mistake in its own _ENTITY_SPECS/_SUMMARIZERS/_TITLES/_singular
entries (this is exactly the kind of mistake _singular("technologies")
had before it was fixed to handle "-ies" plurals).
Experience gets its own cases since it's the one genuinely different
section (checkbox, bullet lists, nested Projects).
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from sqlmodel import SQLModel

from app.candidate_service import CandidateService
from db.engine import get_engine
from ui.graph_explorer import GraphExplorerPanel, _ExperienceFormDialog, _ItemFormDialog

_app = QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def service(tmp_path) -> CandidateService:
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    svc = CandidateService(candidate_id="test-candidate", engine=engine)
    svc.create(name="Ada Lovelace", headline="Engineer")
    return svc


@pytest.fixture
def panel(service) -> GraphExplorerPanel:
    p = GraphExplorerPanel()
    p.set_candidate_service(service)
    return p


def _accept_with(dialog_cls, values):
    return (
        patch.object(dialog_cls, "exec", return_value=QDialog.DialogCode.Accepted),
        patch.object(dialog_cls, "values", return_value=values),
    )


# ----- generic _EntityListSection, via Skills -------------------------------


def test_set_candidate_service_shows_existing_items(service):
    service.add_skill(name="Python")
    panel = GraphExplorerPanel()

    panel.set_candidate_service(service)

    assert panel._sections["skills"]._rows_layout.count() == 1


def test_add_item_calls_the_service_and_refreshes(panel, service):
    with_exec, with_values = _accept_with(_ItemFormDialog, {"name": "Python", "category": None})
    with with_exec, with_values:
        panel._sections["skills"]._on_add_clicked()

    assert [s.name for s in service.get().skills] == ["Python"]
    assert panel._sections["skills"]._rows_layout.count() == 1


def test_edit_item_prefills_and_updates(panel, service):
    skill = service.add_skill(name="Python")
    panel._sections["skills"].refresh()

    with_exec, with_values = _accept_with(_ItemFormDialog, {"name": "SQL", "category": None})
    with with_exec, with_values:
        panel._sections["skills"]._on_edit_clicked(skill)

    assert [s.name for s in service.get().skills] == ["SQL"]


def test_remove_item_calls_the_service_and_refreshes(panel, service):
    skill = service.add_skill(name="Python")
    panel._sections["skills"].refresh()

    panel._sections["skills"]._on_remove_clicked(skill)

    assert service.get().skills == []
    assert panel._sections["skills"]._rows_layout.count() == 0


def test_validation_error_shows_warning_instead_of_crashing(panel, service):
    warnings = []
    with_exec, with_values = _accept_with(_ItemFormDialog, {"name": "", "category": None})
    with with_exec, with_values:
        with patch.object(QMessageBox, "warning", side_effect=lambda *a: warnings.append(a[1:])):
            panel._sections["skills"]._on_add_clicked()

    assert service.get().skills == []
    assert warnings and "empty" in warnings[0][1]


def test_portfolio_links_section_add_and_list(panel, service):
    with_exec, with_values = _accept_with(
        _ItemFormDialog, {"url": "https://artstation.com/ada", "description": "Concept art"}
    )
    with with_exec, with_values:
        panel._sections["portfolio_links"]._on_add_clicked()

    links = service.get().portfolio_links
    assert len(links) == 1
    assert links[0].url == "https://artstation.com/ada"
    assert links[0].description == "Concept art"
    assert panel._sections["portfolio_links"]._rows_layout.count() == 1


def test_awards_section_add_and_list(panel, service):
    with_exec, with_values = _accept_with(
        _ItemFormDialog, {"name": "Best in Show", "issuer": "GDC", "date": "2023"}
    )
    with with_exec, with_values:
        panel._sections["awards"]._on_add_clicked()

    awards = service.get().awards
    assert len(awards) == 1
    assert awards[0].name == "Best in Show"
    assert panel._sections["awards"]._rows_layout.count() == 1


def test_publications_section_add_and_list(panel, service):
    with_exec, with_values = _accept_with(
        _ItemFormDialog,
        {"title": "Scaling LiveOps", "venue": "Medium", "date": None, "url": "https://medium.com/x"},
    )
    with with_exec, with_values:
        panel._sections["publications"]._on_add_clicked()

    publications = service.get().publications
    assert len(publications) == 1
    assert publications[0].title == "Scaling LiveOps"
    assert panel._sections["publications"]._rows_layout.count() == 1


def test_volunteer_experience_section_add_and_list(panel, service):
    with_exec, with_values = _accept_with(
        _ItemFormDialog,
        {"organization": "Code.org", "role": "Mentor", "period": None, "description": None},
    )
    with with_exec, with_values:
        panel._sections["volunteer_experience"]._on_add_clicked()

    entries = service.get().volunteer_experience
    assert len(entries) == 1
    assert entries[0].organization == "Code.org"
    assert panel._sections["volunteer_experience"]._rows_layout.count() == 1


def test_technologies_section_add_and_list(panel, service):
    with_exec, with_values = _accept_with(
        _ItemFormDialog, {"name": "Python", "category": "Language", "proficiency": "Advanced"}
    )
    with with_exec, with_values:
        panel._sections["technologies"]._on_add_clicked()

    technologies = service.get().technologies
    assert len(technologies) == 1
    assert technologies[0].name == "Python"
    assert technologies[0].proficiency == "Advanced"
    assert panel._sections["technologies"]._rows_layout.count() == 1


def test_skills_section_supports_proficiency_field(panel, service):
    with_exec, with_values = _accept_with(
        _ItemFormDialog, {"name": "Python", "category": None, "proficiency": "Advanced"}
    )
    with with_exec, with_values:
        panel._sections["skills"]._on_add_clicked()

    skills = service.get().skills
    assert len(skills) == 1
    assert skills[0].proficiency == "Advanced"


def test_employment_preferences_checkboxes_save_and_load(panel, service):
    panel._employment_type_checkboxes["Full-time"].setChecked(True)
    panel._employment_type_checkboxes["Contract"].setChecked(True)

    panel._on_save_profile_clicked()

    assert set(service.get().employment_types_sought) == {"Full-time", "Contract"}

    # Switching away and back reloads the checkbox state from the service.
    panel.set_candidate_service(None)
    assert panel._employment_type_checkboxes["Full-time"].isChecked() is False

    panel.set_candidate_service(service)
    assert panel._employment_type_checkboxes["Full-time"].isChecked() is True
    assert panel._employment_type_checkboxes["Contract"].isChecked() is True
    assert panel._employment_type_checkboxes["Freelance"].isChecked() is False


# ----- Experience: unified Position/Projects/Achievements/Responsibilities
# dialog (achievements and responsibilities are each freely-editable rows
# that can optionally link to one of the role's projects) ------------------


def test_add_experience_round_trips_role_level_bullets(panel, service):
    values = {
        "position": "Senior Engineer",
        "company": "Acme",
        "period": "2020-2023",
        "is_gap": False,
        "responsibilities": ["Led a team"],
        "achievements": ["Shipped X", "Shipped Y"],
        "projects": [],
    }
    with_exec, with_values = _accept_with(_ExperienceFormDialog, values)
    with with_exec, with_values:
        panel._experience_section._on_add_clicked()

    entry = service.get().experience[0]
    assert entry.position == "Senior Engineer"
    assert entry.responsibilities == ["Led a team"]
    assert entry.achievements == ["Shipped X", "Shipped Y"]
    assert entry.projects == []


def test_add_experience_round_trips_location(panel, service):
    values = {
        "position": "Senior Engineer",
        "company": "Acme",
        "period": "2020-2023",
        "location": "Berlin",
        "is_gap": False,
        "responsibilities": [],
        "achievements": [],
        "projects": [],
    }
    with_exec, with_values = _accept_with(_ExperienceFormDialog, values)
    with with_exec, with_values:
        panel._experience_section._on_add_clicked()

    entry = service.get().experience[0]
    assert entry.location == "Berlin"


def test_experience_dialog_location_field_prefills_and_returns():
    dialog = _ExperienceFormDialog({"position": "Engineer", "location": "Berlin"})

    assert dialog._location.text() == "Berlin"
    assert dialog.values()["location"] == "Berlin"


def test_add_experience_gap_does_not_require_a_company(panel, service):
    values = {
        "position": "Career Break",
        "company": None,
        "period": "2022",
        "is_gap": True,
        "responsibilities": [],
        "achievements": [],
        "projects": [],
    }
    with_exec, with_values = _accept_with(_ExperienceFormDialog, values)
    with with_exec, with_values:
        panel._experience_section._on_add_clicked()

    entry = service.get().experience[0]
    assert entry.is_gap is True
    assert entry.company is None


def test_add_experience_with_a_project_linked_achievement_and_responsibility(panel, service):
    """The dialog builds the whole role — including its projects and which
    bullets link to them — before anything is persisted; add_experience()
    has no `projects` param (a brand-new role has no id yet), so this also
    exercises the add-then-update follow-up in
    GraphExplorerPanel._add_experience."""
    dialog = _ExperienceFormDialog()
    dialog._position.setText("Senior Game Designer")
    dialog._company.setText("Playkot")
    dialog._projects.append({"id": "local-1", "name": "Expedition and Meta", "period": None})
    dialog._on_projects_changed()
    dialog._achievements_editor._add_row("Grew revenue 30%", "local-1")
    dialog._achievements_editor._add_row("Role-level achievement", None)
    dialog._responsibilities_editor._add_row("Owned the roadmap", "local-1")
    values = dialog.values()

    with_exec, with_values = _accept_with(_ExperienceFormDialog, values)
    with with_exec, with_values:
        panel._experience_section._on_add_clicked()

    entry = service.get().experience[0]
    assert entry.achievements == ["Role-level achievement"]
    assert entry.responsibilities == []
    assert len(entry.projects) == 1
    assert entry.projects[0].name == "Expedition and Meta"
    assert entry.projects[0].achievements == ["Grew revenue 30%"]
    assert entry.projects[0].responsibilities == ["Owned the roadmap"]


def test_edit_dialog_prefills_project_linked_bullets():
    initial = {
        "position": "Senior Game Designer",
        "company": "Playkot",
        "period": None,
        "is_gap": False,
        "responsibilities": [],
        "achievements": ["Role-level achievement"],
        "projects": [
            {
                "id": "p1",
                "name": "Expedition and Meta",
                "period": None,
                "achievements": ["Grew revenue 30%"],
                "responsibilities": ["Owned the roadmap"],
            }
        ],
    }

    dialog = _ExperienceFormDialog(initial)

    achievement_values = dialog._achievements_editor.values()
    responsibility_values = dialog._responsibilities_editor.values()
    assert ("Role-level achievement", None) in achievement_values
    assert ("Grew revenue 30%", "p1") in achievement_values
    assert ("Owned the roadmap", "p1") in responsibility_values


def test_deleting_a_project_unlinks_rather_than_drops_its_bullets():
    initial = {
        "position": "Senior Game Designer",
        "company": "Playkot",
        "period": None,
        "is_gap": False,
        "responsibilities": [],
        "achievements": [],
        "projects": [
            {
                "id": "p1",
                "name": "Expedition and Meta",
                "period": None,
                "achievements": ["Grew revenue 30%"],
                "responsibilities": ["Owned the roadmap"],
            }
        ],
    }
    dialog = _ExperienceFormDialog(initial)
    project = dialog._projects[0]

    dialog._on_delete_project_clicked(project)

    assert dialog._projects == []
    assert ("Grew revenue 30%", None) in dialog._achievements_editor.values()
    assert ("Owned the roadmap", None) in dialog._responsibilities_editor.values()


def test_blank_bullet_rows_are_dropped_from_values():
    dialog = _ExperienceFormDialog()
    dialog._position.setText("Engineer")
    dialog._achievements_editor._add_row("   ", None)  # never filled in
    dialog._achievements_editor._add_row("Did a thing", None)

    values = dialog.values()

    assert values["achievements"] == ["Did a thing"]


# ----- profile-level fields and switching candidates ------------------------


def test_save_profile_info_updates_name_headline_and_summary(panel, service):
    panel._name.setText("Ada L. Lovelace")
    panel._headline.setText("Lead Engineer")
    panel._summary.setPlainText("A great summary.")

    panel._on_save_profile_clicked()

    updated = service.get()
    assert updated.name == "Ada L. Lovelace"
    assert updated.headline == "Lead Engineer"
    assert updated.summary == "A great summary."


def test_switching_candidate_service_refreshes_all_fields(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    service_a = CandidateService(candidate_id="a", engine=engine)
    service_a.create(name="Ada Lovelace")
    service_b = CandidateService(candidate_id="b", engine=engine)
    service_b.create(name="Bob Babbage")
    service_b.add_skill(name="COBOL")

    panel = GraphExplorerPanel()
    panel.set_candidate_service(service_a)
    assert panel._name.text() == "Ada Lovelace"
    assert panel._sections["skills"]._rows_layout.count() == 0

    panel.set_candidate_service(service_b)
    assert panel._name.text() == "Bob Babbage"
    assert panel._sections["skills"]._rows_layout.count() == 1


def test_set_candidate_service_none_disables_and_clears(panel):
    panel.set_candidate_service(None)

    assert panel.isEnabled() is False
    assert panel._name.text() == ""
