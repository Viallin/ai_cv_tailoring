"""Graph Explorer panel — Phase 12.3.

A read/edit UI surface over the Candidate graph fields that already exist
(Experience/Education/Skills/Languages/Certifications/Projects/Contacts) —
no new domain concepts, no backend work: app/candidate_service.py already
has full add/update/remove CRUD for every one of them, already unit-tested.
This module is UI-only.

Six of the seven collections (Education, Skill, Language, Certification,
Project, Contact) are shape-identical — a flat record with 2-4 optional
string fields, add/edit/remove against one CandidateService method triple
— so one generic pair of classes (FieldSpec/_ItemFormDialog/
_EntityListSection) handles all six. Experience is the exception: one
dialog manages Position/Company/Period/Is Gap, an in-memory Projects list,
and every Achievement/Responsibility as its own row that can optionally
link to one of those projects (_BulletRowsEditor) — replacing nested
ExperienceProjects being edited through a separate dialog, since a bullet
tied to a project was otherwise invisible from the role's own edit form.

Per docs/development_plan.md Phase 6/8's established pattern elsewhere in
this app (_reload_profiles, etc.): every mutation does a full rebuild of
its section afterward rather than a partial/live sync — simpler, and the
lists involved are always small (a person's own CV history).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable, get_args

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.candidate_service import CandidateService
from app.errors import AppError
from domain.models import EmploymentType, ExperienceProject

_EMPLOYMENT_TYPES: tuple[str, ...] = get_args(EmploymentType)


def _lines_to_text(items: list[str] | None) -> str:
    return "\n".join(items or [])


def _text_to_lines(text: str) -> list[str]:
    return [line.strip() for line in text.split("\n") if line.strip()]


@dataclass
class FieldSpec:
    name: str
    label: str
    multiline: bool = False


class _ItemFormDialog(QDialog):
    """Generic add/edit form built from a list of FieldSpecs. Pre-filled
    from `initial` (an item's model_dump()) when editing; empty when
    adding."""

    def __init__(
        self,
        title: str,
        field_specs: list[FieldSpec],
        initial: dict[str, Any] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._field_specs = field_specs
        self._widgets: dict[str, QLineEdit | QPlainTextEdit] = {}

        layout = QVBoxLayout(self)
        for spec in field_specs:
            layout.addWidget(QLabel(spec.label))
            value = (initial or {}).get(spec.name)
            if spec.multiline:
                widget = QPlainTextEdit()
                widget.setPlainText(_lines_to_text(value))
            else:
                widget = QLineEdit()
                widget.setText(value or "")
            layout.addWidget(widget)
            self._widgets[spec.name] = widget

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for spec in self._field_specs:
            widget = self._widgets[spec.name]
            if spec.multiline:
                result[spec.name] = _text_to_lines(widget.toPlainText())
            else:
                text = widget.text().strip()
                result[spec.name] = text or None
        return result


class _EntityListSection(QWidget):
    """Title + one row per item (a summary label, Edit/Delete buttons) +
    an Add button. `list_fn`/`add_fn`/`update_fn`/`remove_fn` are bound to
    the active CandidateService; `summarize` formats one item into its
    one-line row text. `field_specs` builds a generic _ItemFormDialog, or
    pass `make_dialog(initial) -> dialog with .exec()/.values()` for a
    custom one (Experience)."""

    changed = Signal()

    def __init__(
        self,
        title: str,
        summarize: Callable[[Any], str],
        list_fn: Callable[[], list[Any]],
        add_fn: Callable[..., Any],
        update_fn: Callable[..., Any],
        remove_fn: Callable[[str], None],
        field_specs: list[FieldSpec] | None = None,
        make_dialog: Callable[[dict[str, Any] | None], QDialog] | None = None,
        extra_row_widget: Callable[[Any], QWidget] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._summarize = summarize
        self._list_fn = list_fn
        self._add_fn = add_fn
        self._update_fn = update_fn
        self._remove_fn = remove_fn
        self._field_specs = field_specs
        self._make_dialog = make_dialog
        self._extra_row_widget = extra_row_widget
        self._title = title

        self._layout = QVBoxLayout(self)
        self._layout.addWidget(QLabel(f"<b>{title}</b>"))
        self._rows_layout = QVBoxLayout()
        self._layout.addLayout(self._rows_layout)

        add_button = QPushButton(f"+ Add {title}")
        add_button.clicked.connect(self._on_add_clicked)
        self._layout.addWidget(add_button)

        self.refresh()

    def _open_dialog(self, initial: dict[str, Any] | None) -> QDialog:
        if self._make_dialog is not None:
            return self._make_dialog(initial)
        return _ItemFormDialog(self._title, self._field_specs, initial, parent=self)

    def _on_add_clicked(self) -> None:
        dialog = self._open_dialog(None)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._add_fn(**dialog.values())
        except AppError as exc:
            QMessageBox.warning(self, f"Could not add {self._title}", str(exc))
            return
        self.changed.emit()
        self.refresh()

    def _on_edit_clicked(self, item: Any) -> None:
        dialog = self._open_dialog(item.model_dump())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._update_fn(item.id, **dialog.values())
        except AppError as exc:
            QMessageBox.warning(self, f"Could not update {self._title}", str(exc))
            return
        self.changed.emit()
        self.refresh()

    def _on_remove_clicked(self, item: Any) -> None:
        try:
            self._remove_fn(item.id)
        except AppError as exc:
            QMessageBox.warning(self, f"Could not remove {self._title}", str(exc))
            return
        self.changed.emit()
        self.refresh()

    def refresh(self) -> None:
        while self._rows_layout.count():
            child = self._rows_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for item in self._list_fn():
            row = QHBoxLayout()
            label = QLabel(self._summarize(item))
            label.setWordWrap(True)
            row.addWidget(label, 1)
            if self._extra_row_widget is not None:
                row.addWidget(self._extra_row_widget(item))
            edit_button = QPushButton("Edit")
            edit_button.clicked.connect(lambda checked=False, item=item: self._on_edit_clicked(item))
            row.addWidget(edit_button)
            delete_button = QPushButton("Delete")
            delete_button.clicked.connect(lambda checked=False, item=item: self._on_remove_clicked(item))
            row.addWidget(delete_button)
            row_widget = QWidget()
            row_widget.setLayout(row)
            self._rows_layout.addWidget(row_widget)


def _new_local_id() -> str:
    # Same scheme as app/candidate_service.py's _new_id() — a project
    # built up inside this not-yet-saved dialog needs *some* id so
    # pydantic validation of the in-progress ExperienceProject-shaped dict
    # succeeds; this becomes the real persisted id once the dialog is
    # accepted and its values() are handed to add_experience/
    # update_experience, no different from the service assigning one.
    return uuid.uuid4().hex[:8]


class _BulletRowsEditor(QWidget):
    """One flat, freely-editable list of bullet rows — each a small text
    box plus a dropdown linking it to one of the current projects (or
    "(none)" for role-level) — plus an Add button. Shared verbatim by the
    Achievements and Responsibilities sections of _ExperienceFormDialog,
    which are otherwise structurally identical.

    `get_projects` is a callable (not a static list) so a project renamed/
    added/removed elsewhere in the same dialog is reflected without this
    widget needing to know about that directly."""

    def __init__(
        self,
        title: str,
        initial_rows: list[tuple[str, str | None]],
        get_projects: Callable[[], list[dict[str, Any]]],
        parent=None,
    ):
        super().__init__(parent)
        self._get_projects = get_projects
        self._rows: list[dict[str, Any]] = []

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<b>{title}</b>"))
        self._rows_layout = QVBoxLayout()
        layout.addLayout(self._rows_layout)

        for text, project_id in initial_rows:
            self._add_row(text, project_id)

        add_button = QPushButton(f"+ Add {title.rstrip('s')}")
        add_button.clicked.connect(lambda: self._add_row("", None))
        layout.addWidget(add_button)

    def _add_row(self, text: str, project_id: str | None) -> None:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)

        text_edit = QPlainTextEdit(text)
        text_edit.setFixedHeight(50)
        row_layout.addWidget(text_edit, 1)

        combo = QComboBox()
        row_layout.addWidget(combo)

        delete_button = QPushButton("Delete")
        row_layout.addWidget(delete_button)

        row = {"widget": row_widget, "text": text_edit, "combo": combo}
        delete_button.clicked.connect(lambda: self._remove_row(row))
        self._rows.append(row)
        self._rows_layout.addWidget(row_widget)
        self._refresh_row_options(row, selected_id=project_id)

    def _remove_row(self, row: dict[str, Any]) -> None:
        self._rows.remove(row)
        row["widget"].deleteLater()

    def _refresh_row_options(self, row: dict[str, Any], selected_id: str | None = None) -> None:
        combo = row["combo"]
        current = selected_id if selected_id is not None else combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("(none)", None)
        for project in self._get_projects():
            combo.addItem(project["name"], project["id"])
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def refresh_project_options(self) -> None:
        """Call after the Projects list changes (add/rename/delete) — a
        row whose linked project no longer exists falls back to "(none)"
        rather than losing its text (per your call: unlink, don't drop)."""
        for row in self._rows:
            self._refresh_row_options(row)

    def values(self) -> list[tuple[str, str | None]]:
        result = []
        for row in self._rows:
            text = row["text"].toPlainText().strip()
            if text:
                result.append((text, row["combo"].currentData()))
        return result


class _ExperienceFormDialog(QDialog):
    """Experience's own dialog: Position/Company/Period/Is Gap, an
    in-memory Projects list (name+period only — purely local until this
    dialog is accepted, since a not-yet-saved Experience has no id to
    attach real ExperienceProjects to), and every Achievement/
    Responsibility as its own row that can optionally link to one of
    those projects. Replaces the old flat-multiline-text + separate
    "Manage Projects" dialog design."""

    def __init__(self, initial: dict[str, Any] | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Experience")
        self.resize(600, 700)
        initial = initial or {}
        self._projects: list[dict[str, Any]] = [
            {"id": p["id"], "name": p["name"], "period": p.get("period")}
            for p in (initial.get("projects") or [])
        ]

        # Position/Company/Period/Is Gap + Projects + Achievements +
        # Responsibilities can add up to a lot more vertical space than
        # the dialog's default size — a role with several projects and
        # bullets shouldn't grow the window off-screen, so everything but
        # the OK/Cancel buttons scrolls (same pattern as
        # ui/main_window.py's _build_input_panel/_build_output_panel).
        outer_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer_layout.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(QLabel("Position"))
        self._position = QLineEdit(initial.get("position") or "")
        layout.addWidget(self._position)

        layout.addWidget(QLabel("Company"))
        self._company = QLineEdit(initial.get("company") or "")
        layout.addWidget(self._company)

        layout.addWidget(QLabel("Period"))
        self._period = QLineEdit(initial.get("period") or "")
        layout.addWidget(self._period)

        layout.addWidget(QLabel("Location"))
        self._location = QLineEdit(initial.get("location") or "")
        layout.addWidget(self._location)

        self._is_gap = QCheckBox("This is an employment gap (no company required)")
        self._is_gap.setChecked(bool(initial.get("is_gap")))
        layout.addWidget(self._is_gap)

        layout.addWidget(QLabel("<b>Projects</b>"))
        self._projects_rows_layout = QVBoxLayout()
        layout.addLayout(self._projects_rows_layout)
        add_project_button = QPushButton("+ Add Project")
        add_project_button.clicked.connect(self._on_add_project_clicked)
        layout.addWidget(add_project_button)

        initial_achievement_rows = [(text, None) for text in initial.get("achievements") or []]
        initial_responsibility_rows = [(text, None) for text in initial.get("responsibilities") or []]
        for project in initial.get("projects") or []:
            initial_achievement_rows += [(text, project["id"]) for text in project.get("achievements") or []]
            initial_responsibility_rows += [
                (text, project["id"]) for text in project.get("responsibilities") or []
            ]

        self._achievements_editor = _BulletRowsEditor(
            "Achievements", initial_achievement_rows, self._get_projects, parent=self
        )
        layout.addWidget(self._achievements_editor)

        self._responsibilities_editor = _BulletRowsEditor(
            "Responsibilities", initial_responsibility_rows, self._get_projects, parent=self
        )
        layout.addWidget(self._responsibilities_editor)

        scroll.setWidget(content)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer_layout.addWidget(buttons)

        self._refresh_projects_rows()

    def _get_projects(self) -> list[dict[str, Any]]:
        return self._projects

    def _refresh_projects_rows(self) -> None:
        while self._projects_rows_layout.count():
            child = self._projects_rows_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        achievement_counts: dict[str, int] = {}
        for _text, project_id in self._achievements_editor.values():
            if project_id:
                achievement_counts[project_id] = achievement_counts.get(project_id, 0) + 1

        for project in self._projects:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            count = achievement_counts.get(project["id"], 0)
            period = f" ({project['period']})" if project.get("period") else ""
            label = QLabel(f"{project['name']}{period} — {count} achievement(s)")
            label.setWordWrap(True)
            row_layout.addWidget(label, 1)

            edit_button = QPushButton("Edit")
            edit_button.clicked.connect(lambda checked=False, p=project: self._on_edit_project_clicked(p))
            row_layout.addWidget(edit_button)

            delete_button = QPushButton("Delete")
            delete_button.clicked.connect(lambda checked=False, p=project: self._on_delete_project_clicked(p))
            row_layout.addWidget(delete_button)

            self._projects_rows_layout.addWidget(row_widget)

    def _on_add_project_clicked(self) -> None:
        dialog = _ItemFormDialog(
            "Project", [FieldSpec("name", "Name"), FieldSpec("period", "Period")], parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if not values.get("name"):
            QMessageBox.warning(self, "Could not add Project", "Project name must not be empty.")
            return
        self._projects.append({"id": _new_local_id(), "name": values["name"], "period": values.get("period")})
        self._on_projects_changed()

    def _on_edit_project_clicked(self, project: dict[str, Any]) -> None:
        dialog = _ItemFormDialog(
            "Project",
            [FieldSpec("name", "Name"), FieldSpec("period", "Period")],
            initial=project,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if not values.get("name"):
            QMessageBox.warning(self, "Could not update Project", "Project name must not be empty.")
            return
        project["name"] = values["name"]
        project["period"] = values.get("period")
        self._on_projects_changed()

    def _on_delete_project_clicked(self, project: dict[str, Any]) -> None:
        self._projects.remove(project)
        self._on_projects_changed()

    def _on_projects_changed(self) -> None:
        self._achievements_editor.refresh_project_options()
        self._responsibilities_editor.refresh_project_options()
        self._refresh_projects_rows()

    def values(self) -> dict[str, Any]:
        achievement_pairs = self._achievements_editor.values()
        responsibility_pairs = self._responsibilities_editor.values()

        # Real ExperienceProject instances, not plain dicts: Experience.
        # model_copy(update={"projects": [...]}) (app/candidate_service.py's
        # update_experience) doesn't coerce/validate nested values the way
        # the constructor or model_validate() does, so handing it raw
        # dicts triggers a Pydantic serializer warning on the next
        # model_dump() even though the final save ends up correct.
        projects_out = []
        for project in self._projects:
            projects_out.append(
                ExperienceProject(
                    id=project["id"],
                    name=project["name"],
                    period=project.get("period"),
                    achievements=[text for text, pid in achievement_pairs if pid == project["id"]],
                    responsibilities=[
                        text for text, pid in responsibility_pairs if pid == project["id"]
                    ],
                )
            )

        return {
            "position": self._position.text().strip(),
            "company": self._company.text().strip() or None,
            "period": self._period.text().strip() or None,
            "location": self._location.text().strip() or None,
            "is_gap": self._is_gap.isChecked(),
            "responsibilities": [text for text, pid in responsibility_pairs if pid is None],
            "achievements": [text for text, pid in achievement_pairs if pid is None],
            "projects": projects_out,
        }


def _summarize_experience(entry) -> str:
    company = f" — {entry.company}" if entry.company else ""
    period_and_location = ", ".join(bit for bit in (entry.period, entry.location) if bit)
    period = f" ({period_and_location})" if period_and_location else ""
    gap = " [GAP]" if entry.is_gap else ""
    return f"{entry.position}{company}{period}{gap}"


_ENTITY_SPECS: dict[str, list[FieldSpec]] = {
    "education": [
        FieldSpec("institution", "Institution"),
        FieldSpec("degree", "Degree"),
        FieldSpec("field", "Field"),
        FieldSpec("period", "Period"),
    ],
    "skills": [
        FieldSpec("name", "Name"),
        FieldSpec("category", "Category"),
        FieldSpec("proficiency", "Proficiency (e.g. Beginner/Intermediate/Advanced/Expert)"),
    ],
    "technologies": [
        FieldSpec("name", "Name"),
        FieldSpec("category", "Category"),
        FieldSpec("proficiency", "Proficiency (e.g. Beginner/Intermediate/Advanced/Expert)"),
    ],
    "languages": [FieldSpec("name", "Name"), FieldSpec("proficiency", "Proficiency")],
    "certifications": [
        FieldSpec("name", "Name"),
        FieldSpec("issuer", "Issuer"),
        FieldSpec("date", "Date"),
    ],
    "awards": [
        FieldSpec("name", "Name"),
        FieldSpec("issuer", "Issuer"),
        FieldSpec("date", "Date"),
    ],
    "projects": [
        FieldSpec("name", "Name"),
        FieldSpec("description", "Description"),
        FieldSpec("url", "URL"),
    ],
    "publications": [
        FieldSpec("title", "Title"),
        FieldSpec("venue", "Venue"),
        FieldSpec("date", "Date"),
        FieldSpec("url", "URL"),
    ],
    "volunteer_experience": [
        FieldSpec("organization", "Organization"),
        FieldSpec("role", "Role"),
        FieldSpec("period", "Period"),
        FieldSpec("description", "Description"),
    ],
    "contacts": [FieldSpec("label", "Label"), FieldSpec("value", "Value")],
    "portfolio_links": [FieldSpec("url", "URL"), FieldSpec("description", "Description")],
}


def _summarize_education(entry) -> str:
    details = ", ".join(bit for bit in (entry.degree, entry.field) if bit)
    period = f" ({entry.period})" if entry.period else ""
    return f"{entry.institution}" + (f" — {details}" if details else "") + period


def _summarize_skill_like(entry) -> str:
    details = ", ".join(bit for bit in (entry.category, entry.proficiency) if bit)
    return f"{entry.name}" + (f" ({details})" if details else "")


def _summarize_language(entry) -> str:
    return f"{entry.name}" + (f" ({entry.proficiency})" if entry.proficiency else "")


def _summarize_certification_like(entry) -> str:
    details = ", ".join(bit for bit in (entry.issuer, entry.date) if bit)
    return f"{entry.name}" + (f" — {details}" if details else "")


def _summarize_project(entry) -> str:
    return f"{entry.name}" + (f" — {entry.description}" if entry.description else "")


def _summarize_publication(entry) -> str:
    details = ", ".join(bit for bit in (entry.venue, entry.date) if bit)
    return f"{entry.title}" + (f" — {details}" if details else "")


def _summarize_volunteer_experience(entry) -> str:
    header = f"{entry.role} — {entry.organization}"
    if entry.period:
        header += f" ({entry.period})"
    return header


def _summarize_contact(entry) -> str:
    return f"{entry.label}: {entry.value}"


def _summarize_portfolio_link(entry) -> str:
    return f"{entry.description} — {entry.url}" if entry.description else entry.url


_SUMMARIZERS: dict[str, Callable[[Any], str]] = {
    "education": _summarize_education,
    "skills": _summarize_skill_like,
    "technologies": _summarize_skill_like,
    "languages": _summarize_language,
    "certifications": _summarize_certification_like,
    "awards": _summarize_certification_like,
    "projects": _summarize_project,
    "publications": _summarize_publication,
    "volunteer_experience": _summarize_volunteer_experience,
    "contacts": _summarize_contact,
    "portfolio_links": _summarize_portfolio_link,
}

_TITLES = {
    "education": "Education",
    "skills": "Skill",
    "technologies": "Tool/Technology",
    "languages": "Language",
    "certifications": "Certification",
    "awards": "Award",
    "projects": "Key Project",
    "publications": "Publication",
    "volunteer_experience": "Volunteer Experience",
    "contacts": "Contact",
    "portfolio_links": "Portfolio Link",
}


class GraphExplorerPanel(QWidget):
    """The whole Graph Explorer: profile-level fields plus one list
    section per Candidate collection. `set_candidate_service(None)` shows
    an empty/disabled state (no profile selected yet)."""

    candidate_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._service: CandidateService | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Candidate Profile</b>"))

        layout.addWidget(QLabel("Name"))
        self._name = QLineEdit()
        layout.addWidget(self._name)

        layout.addWidget(QLabel("Headline"))
        self._headline = QLineEdit()
        layout.addWidget(self._headline)

        layout.addWidget(QLabel("Summary"))
        self._summary = QPlainTextEdit()
        layout.addWidget(self._summary)

        layout.addWidget(QLabel("Seeking (employment type)"))
        self._employment_type_checkboxes: dict[str, QCheckBox] = {}
        employment_types_row = QHBoxLayout()
        for employment_type in _EMPLOYMENT_TYPES:
            checkbox = QCheckBox(employment_type)
            self._employment_type_checkboxes[employment_type] = checkbox
            employment_types_row.addWidget(checkbox)
        layout.addLayout(employment_types_row)

        self._save_profile_button = QPushButton("Save Profile Info")
        self._save_profile_button.clicked.connect(self._on_save_profile_clicked)
        layout.addWidget(self._save_profile_button)

        self._sections: dict[str, _EntityListSection] = {}
        for key in (
            "education",
            "skills",
            "technologies",
            "languages",
            "certifications",
            "awards",
            "projects",
            "publications",
            "volunteer_experience",
            "contacts",
            "portfolio_links",
        ):
            section = _EntityListSection(
                title=_TITLES[key],
                summarize=_SUMMARIZERS[key],
                list_fn=self._list_factory(key),
                add_fn=self._add_factory(key),
                update_fn=self._update_factory(key),
                remove_fn=self._remove_factory(key),
                field_specs=_ENTITY_SPECS[key],
                parent=self,
            )
            section.changed.connect(self.candidate_changed.emit)
            layout.addWidget(section)
            self._sections[key] = section

        self._experience_section = _EntityListSection(
            title="Experience",
            summarize=_summarize_experience,
            list_fn=lambda: self._service.get().experience if self._service else [],
            add_fn=self._add_experience,
            update_fn=lambda experience_id, **fields: self._service.update_experience(
                experience_id, **fields
            ),
            remove_fn=lambda experience_id: self._service.remove_experience(experience_id),
            make_dialog=lambda initial: _ExperienceFormDialog(initial, parent=self),
            parent=self,
        )
        self._experience_section.changed.connect(self.candidate_changed.emit)
        layout.addWidget(self._experience_section)

        self.setEnabled(False)

    # ----- generic CRUD factories, one per simple entity key ------------

    def _list_factory(self, key: str) -> Callable[[], list[Any]]:
        return lambda: getattr(self._service.get(), key) if self._service else []

    def _add_factory(self, key: str) -> Callable[..., Any]:
        return lambda **fields: getattr(self._service, f"add_{_singular(key)}")(**fields)

    def _update_factory(self, key: str) -> Callable[..., Any]:
        return lambda item_id, **fields: getattr(self._service, f"update_{_singular(key)}")(
            item_id, **fields
        )

    def _remove_factory(self, key: str) -> Callable[[str], None]:
        return lambda item_id: getattr(self._service, f"remove_{_singular(key)}")(item_id)

    def _add_experience(self, **fields: Any) -> None:
        """add_experience() has no `projects` param (a brand-new Experience
        has no id yet to attach ExperienceProjects to) — so a role built up
        with projects already attached in _ExperienceFormDialog needs a
        follow-up update_experience() call once the entry exists. Two
        writes, but no CandidateService signature change needed."""
        projects = fields.pop("projects", None)
        entry = self._service.add_experience(**fields)
        if projects:
            self._service.update_experience(entry.id, projects=projects)

    # ----- profile-level fields -------------------------------------------

    def _on_save_profile_clicked(self) -> None:
        employment_types_sought = [
            employment_type
            for employment_type, checkbox in self._employment_type_checkboxes.items()
            if checkbox.isChecked()
        ]
        try:
            self._service.update(
                name=self._name.text().strip(),
                headline=self._headline.text().strip() or None,
                summary=self._summary.toPlainText().strip() or None,
                employment_types_sought=employment_types_sought,
            )
        except AppError as exc:
            QMessageBox.warning(self, "Could not save profile info", str(exc))
            return
        self.candidate_changed.emit()

    # ----- switching the active candidate --------------------------------

    def set_candidate_service(self, service: CandidateService | None) -> None:
        self._service = service
        self.setEnabled(service is not None)
        if service is None:
            self._name.clear()
            self._headline.clear()
            self._summary.clear()
            for checkbox in self._employment_type_checkboxes.values():
                checkbox.setChecked(False)
            for section in (*self._sections.values(), self._experience_section):
                section.refresh()
            return

        candidate = service.get()
        self._name.setText(candidate.name)
        self._headline.setText(candidate.headline or "")
        self._summary.setPlainText(candidate.summary or "")
        sought = set(candidate.employment_types_sought)
        for employment_type, checkbox in self._employment_type_checkboxes.items():
            checkbox.setChecked(employment_type in sought)
        for section in (*self._sections.values(), self._experience_section):
            section.refresh()


def _singular(key: str) -> str:
    # Matches app/candidate_service.py's method names (add_education,
    # add_skill, add_project, ...) — "education" has no trailing "s" to
    # strip, most others do. "technologies" needs the "-ies" -> "-y" rule
    # (plain rstrip("s") would give "technologie", not "technology").
    if key.endswith("ies"):
        return key[:-3] + "y"
    return key.rstrip("s")
