"""Phase 6/8 UI — single window: pick/create a candidate profile -> ingest
resume -> generate tailored CV per vacancy -> editable output -> Export
Markdown (docs/development_plan.md Phase 6, Phase 8/8.1).

Per docs/architecture.md, the UI never talks to the LLM or a provider
directly. It only calls into app/pipeline.py (which itself only calls
app/use_cases.py + app/cv_assembler.py) and app/cv_markdown.py for
rendering. All actual work happens off the GUI thread in a background
QThread, since a Gemini call (plus retries, see app/config.py's
LLM_MAX_RETRIES) can take several seconds and would otherwise freeze the
window.

Manual edit scope (Phase 6): one editable QPlainTextEdit per CV section, no
diffing/versioning — edited text is never re-parsed back into the Candidate
Profile or CVProjection, it's only used for the Markdown export. No Resume
Graph Explorer or AI Suggestions panel yet — those need the richer
Evidence/Claim/Variant model from later phases.

Ingest/Generate split (Phase 8): ingesting a resume and generating a CV for
a vacancy used to be one "Generate" click that re-parsed the pasted resume
every time. They're now separate buttons — Ingest Resume parses+saves the
Candidate Profile (and its Evidence) once; Generate CV can then be clicked
repeatedly against different job descriptions without re-parsing.

Multiple Candidate Profiles (Phase 8.1): the app used to assume exactly one
local profile. It now supports several, switchable via `profile_selector` —
see app/candidate_registry.py. Ingesting a resume always creates a *new*
profile rather than overwriting the active one; see
docs/phase_8_wireframes_spec.md for the UI spec this was built from.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.candidate_registry import CandidateProfileSummary
from app.candidate_service import CandidateService
from app.cv_docx import render_docx
from app.cv_markdown import (
    SECTION_TITLES,
    assemble_markdown_from_sections,
    render_all_sections,
    render_header,
)
from app.cv_pdf import render_pdf
from app.errors import AppError
from app.graph_writeback import (
    WritebackProposal,
    build_experience_proposals,
    build_skills_proposals,
    build_summary_proposal,
)
from app.logging_setup import get_logger
from app.pipeline import PipelineResult, run_cv_generation, run_resume_ingestion
from app.services import Services
from domain.models import AssembledCV, Candidate, Evidence, MatchResult
from ui.graph_explorer import GraphExplorerPanel

logger = get_logger(__name__)

# Phase 8.3: sections whose edited text can be saved back to the Candidate
# Profile — not Education/Languages/Certifications/Key Projects, which are
# already deterministic 1:1 mirrors of Candidate facts (see
# docs/development_plan.md Phase 8 notes), so there's no edit-vs-source
# divergence there to save back.
_WRITEBACK_SECTION_KEYS = ("summary", "experience", "skills")

# Same project-root convention as run_pipeline.py's --vacancy default, so a
# file dropped there shows up in both entry points. Resume text has no
# equivalent pre-load (Phase 12.3) — candidate profiles persist across
# restarts now (Phase 8.1), and the Graph Explorer covers manual entry, so
# there's no need to keep re-populating the paste box from a local file.
DEFAULT_VACANCY_PATH = Path("vacancy.txt")


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _ingest_hint_text(active_candidate: Candidate | None) -> str:
    if active_candidate is None:
        return "Ingesting creates a new candidate profile."
    return (
        "Ingesting creates a new candidate profile — "
        f"it won't overwrite '{active_candidate.name}'."
    )


# Phase 8.2: severity display, per docs/phase_8_wireframes_spec.md — sort
# order (high first) and the colored HIGH/MED tags shown for each gap.
# Low-severity gaps are intentionally not tagged/colored: they're collapsed
# into a single count line instead, never shown individually.
_GAP_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_GAP_SEVERITY_TAG_HTML = {
    "high": '<span style="color:#e05252; font-weight:bold;">HIGH</span>',
    "medium": '<span style="color:#d9a441; font-weight:bold;">MED</span>',
}


def _gaps_html(match_result: MatchResult) -> str:
    """Renders a Phase 8/8.2 MatchResult's Gaps/missing keywords as HTML for
    the read-only Gaps panel — informational only, never exported (see
    domain.models.MatchResult's docstring). High/medium-severity gaps are
    shown individually, most important first, each with a colored severity
    tag and its suggested_action (if any); low-severity gaps are summarized
    as a single trailing count line rather than listed one by one, per
    docs/phase_8_wireframes_spec.md's Phase 8.2 spec (a static count, not
    click-to-expand, for this pass).
    """
    if not match_result.gaps and not match_result.missing_keywords:
        return "No notable gaps found for this vacancy."

    shown = sorted(
        (gap for gap in match_result.gaps if gap.severity in ("high", "medium")),
        key=lambda gap: _GAP_SEVERITY_ORDER[gap.severity],
    )
    low_count = sum(1 for gap in match_result.gaps if gap.severity == "low")

    lines: list[str] = []
    for gap in shown:
        tag = _GAP_SEVERITY_TAG_HTML[gap.severity]
        lines.append(
            f"{tag} {html.escape(gap.description)} "
            f"(for: {html.escape(gap.requirement_text)})"
        )
        if gap.suggested_action:
            lines.append(
                '<span style="color:gray; font-size:11px;">'
                f"&nbsp;&nbsp;→ {html.escape(gap.suggested_action)}</span>"
            )

    if low_count:
        lines.append(
            f'<span style="color:gray;">+ {low_count} more, low priority · collapsed</span>'
        )

    if match_result.missing_keywords:
        lines.append(
            '<span style="color:gray;">Missing keywords: '
            + html.escape(", ".join(match_result.missing_keywords))
            + "</span>"
        )

    return "<br>".join(lines)


def _header_html(cv: AssembledCV) -> str:
    """Renders just the identity block as HTML for on-screen display.

    Separate from app/cv_markdown.py's render_header(), which produces
    Markdown for the export file — QLabel needs real HTML, not Markdown
    syntax with newlines swapped for <br>.
    """
    parts = [f"<h2>{html.escape(cv.name)}</h2>"]
    if cv.headline:
        parts.append(f"<i>{html.escape(cv.headline)}</i><br>")
    if cv.contacts:
        contact_line = " | ".join(f"{c.label}: {c.value}" for c in cv.contacts)
        parts.append(html.escape(contact_line))
    return "".join(parts)


class _CallableWorker(QThread):
    """Runs a zero-arg callable off the GUI thread and reports the result.

    Shared by both the Ingest and Generate buttons (Phase 8) instead of two
    near-duplicate QThread subclasses — the two operations differ only in
    which app/pipeline.py function they call.
    """

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], Any], parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:  # noqa: D102 - QThread override
        try:
            result = self._fn()
        except AppError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - last-resort guard so the UI never hangs silently
            # Unlike AppError (an expected, already-categorized failure),
            # reaching here means something wasn't translated per
            # docs/architecture.md's Error Propagation — log the full
            # stack trace so it's diagnosable, not just the message shown
            # to the user.
            logger.exception("Unexpected error in background worker")
            self.failed.emit(f"Unexpected error: {exc}")
            return
        self.succeeded.emit(result)


class _WritebackDialog(QDialog):
    """Confirm dialog for Phase 8.3 graph write-backs — one QCheckBox per
    WritebackProposal, pre-checked when enabled, per
    docs/phase_8_wireframes_spec.md. Disabled/warning-colored rows
    (`proposal.enabled=False`, e.g. a block-count mismatch — see
    app/graph_writeback.py:build_experience_proposals) are shown but can't
    be checked: visible, not silently dropped.
    """

    def __init__(self, title: str, proposals: list[WritebackProposal], parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._checkboxes: list[tuple[QCheckBox, WritebackProposal]] = []

        layout = QVBoxLayout(self)
        if not proposals:
            layout.addWidget(QLabel("Nothing new to save."))
        for proposal in proposals:
            checkbox = QCheckBox(proposal.label)
            checkbox.setChecked(proposal.enabled)
            checkbox.setEnabled(proposal.enabled)
            if not proposal.enabled:
                checkbox.setStyleSheet("color: #d9a441;")
            layout.addWidget(checkbox)
            self._checkboxes.append((checkbox, proposal))

        buttons = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        save_button = QPushButton("Save selected")
        save_button.clicked.connect(self.accept)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

    def selected_proposals(self) -> list[WritebackProposal]:
        return [
            proposal
            for checkbox, proposal in self._checkboxes
            if checkbox.isChecked() and proposal.enabled
        ]


class MainWindow(QMainWindow):
    def __init__(self, services: Services):
        super().__init__()
        self._services = services
        self._worker: _CallableWorker | None = None
        self._current_header_markdown = ""

        # Active-profile state (Phase 8.1) — kept in sync with
        # profile_selector by _load_profile()/_reload_profiles().
        self._profiles: list[CandidateProfileSummary] = []
        self._active_candidate_id: str | None = None
        self._active_candidate_service: CandidateService | None = None
        self._candidate: Candidate | None = None
        self._evidence: list[Evidence] = []

        # Phase 8.3: the profile a save should target and the dirty-check
        # baselines are captured at generate-success time, not read live
        # from profile_selector — the user can switch profiles after
        # generating, and a save must still land in the profile that
        # actually produced the CV being edited.
        self._last_result: PipelineResult | None = None
        self._last_result_candidate_service: CandidateService | None = None
        self._last_generated_section_text: dict[str, str] = {}

        self.setWindowTitle("AI CV Builder (prototype)")
        self.resize(1150, 780)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_input_panel())
        splitter.addWidget(self._build_output_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._reload_profiles()

    # ----- panel construction -------------------------------------------

    def _build_input_panel(self) -> QWidget:
        """Left column. Phase 12.3 order: Candidate selector -> Graph
        Explorer (ui/graph_explorer.py) -> Resume ingestion -> Job
        Description. Wrapped in a QScrollArea (matching
        _build_output_panel's existing pattern) since the Graph Explorer
        makes this column much taller than the two paste boxes it used to
        be."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        panel = QWidget()
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("<b>Candidate Profile</b>"))
        self.profile_selector = QComboBox()
        self.profile_selector.currentIndexChanged.connect(self._on_profile_selected)
        layout.addWidget(self.profile_selector)

        self.graph_explorer = GraphExplorerPanel()
        self.graph_explorer.candidate_changed.connect(self._on_graph_explorer_changed)
        layout.addWidget(self.graph_explorer)

        layout.addWidget(QLabel("<b>Resume</b>"))
        self.resume_input = QPlainTextEdit()
        self.resume_input.setPlaceholderText("Paste your resume text here...")
        layout.addWidget(self.resume_input, 1)

        self.ingest_button = QPushButton("Ingest Resume")
        self.ingest_button.clicked.connect(self._on_ingest_clicked)
        layout.addWidget(self.ingest_button)

        self.ingest_hint_label = QLabel("")
        self.ingest_hint_label.setWordWrap(True)
        self.ingest_hint_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.ingest_hint_label)

        layout.addWidget(QLabel("<b>Job Description</b>"))
        self.vacancy_input = QPlainTextEdit()
        self.vacancy_input.setPlaceholderText("Paste the job description here...")
        self.vacancy_input.setPlainText(_read_text_if_exists(DEFAULT_VACANCY_PATH))
        layout.addWidget(self.vacancy_input, 1)

        self.generate_button = QPushButton("Generate CV")
        self.generate_button.setEnabled(False)
        self.generate_button.clicked.connect(self._on_generate_clicked)
        layout.addWidget(self.generate_button)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        scroll.setWidget(panel)
        return scroll

    def _build_output_panel(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        layout = QVBoxLayout(container)

        self.header_label = QLabel("")
        self.header_label.setTextFormat(Qt.TextFormat.RichText)
        self.header_label.setWordWrap(True)
        layout.addWidget(self.header_label)

        # One editable field per CV section (Phase 6 scope — no diffing/
        # versioning between the edited text and the exported Markdown).
        # Phase 8.3 adds an explicit, separate "Save edits to profile" path
        # for the sections where writing back to the Candidate Profile is
        # unambiguous — see _WRITEBACK_SECTION_KEYS and app/graph_writeback.py.
        self.section_edits: dict[str, QPlainTextEdit] = {}
        self.save_buttons: dict[str, QPushButton] = {}
        for key, title in SECTION_TITLES.items():
            layout.addWidget(QLabel(f"<b>{title}</b>"))
            edit = QPlainTextEdit()
            edit.setPlaceholderText(f"({title} will appear here after Generate)")
            layout.addWidget(edit)
            self.section_edits[key] = edit

            if key in _WRITEBACK_SECTION_KEYS:
                save_button = QPushButton("Save edits to profile")
                save_button.setEnabled(False)
                save_button.clicked.connect(
                    lambda checked=False, key=key: self._on_save_section_clicked(key)
                )
                layout.addWidget(save_button)
                self.save_buttons[key] = save_button
                edit.textChanged.connect(lambda key=key: self._on_section_text_changed(key))

        # Phase 8: matching/gap analysis is informational, surfaced to the
        # user as-is — deliberately not one of the section_edits above, so
        # it's never editable and never included in the Markdown export
        # (see domain.models.MatchResult's docstring).
        layout.addWidget(QLabel("<b>Gaps</b> (not exported — informational only)"))
        self.gaps_label = QLabel("")
        self.gaps_label.setTextFormat(Qt.TextFormat.RichText)
        self.gaps_label.setWordWrap(True)
        layout.addWidget(self.gaps_label)

        self.export_button = QPushButton("Export CV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._on_export_clicked)
        layout.addWidget(self.export_button)

        scroll.setWidget(container)
        return scroll

    # ----- candidate profiles (Phase 8.1) ------------------------------------

    def _reload_profiles(self, select_id: str | None = None) -> None:
        """Repopulates profile_selector from the registry and loads one of
        them as active — `select_id` if given and still present, otherwise
        the first (most-recently-active, see CandidateRegistry.
        list_profiles()). Called on startup and after a successful ingest.
        """
        self._profiles = self._services.candidate_registry.list_profiles()

        target_index = 0
        if select_id is not None:
            for i, profile in enumerate(self._profiles):
                if profile.id == select_id:
                    target_index = i
                    break

        self.profile_selector.blockSignals(True)
        self.profile_selector.clear()
        for profile in self._profiles:
            self.profile_selector.addItem(
                f"{profile.name} — {profile.experience_count} entries", profile.id
            )
        if self._profiles:
            self.profile_selector.setCurrentIndex(target_index)
        self.profile_selector.blockSignals(False)

        self._load_profile(self._profiles[target_index].id if self._profiles else None)

    def _on_profile_selected(self, index: int) -> None:
        if index < 0 or index >= len(self._profiles):
            return
        self._load_profile(self._profiles[index].id)

    def _load_profile(self, candidate_id: str | None) -> None:
        if candidate_id is None:
            self._active_candidate_id = None
            self._active_candidate_service = None
            self._candidate = None
            self._evidence = []
        else:
            service = self._services.candidate_registry.service_for(candidate_id)
            self._active_candidate_id = candidate_id
            self._active_candidate_service = service
            self._candidate = service.get()
            self._evidence = service.get_evidence()

        self.generate_button.setEnabled(self._candidate is not None)
        self.ingest_hint_label.setText(_ingest_hint_text(self._candidate))
        self.graph_explorer.set_candidate_service(self._active_candidate_service)

    def _on_graph_explorer_changed(self) -> None:
        """A Graph Explorer edit (Phase 12.3) changed the active candidate
        on disk — refresh profile_selector's "N entries" label and
        self._candidate from it. Reuses _reload_profiles rather than
        duplicating that refresh logic; it already re-triggers
        _load_profile, which re-points the Graph Explorer at the (now
        current) active service too."""
        self._reload_profiles(select_id=self._active_candidate_id)

    # ----- ingest ---------------------------------------------------------

    def _on_ingest_clicked(self) -> None:
        resume_text = self.resume_input.toPlainText().strip()
        if not resume_text:
            self.status_label.setText("Paste a resume first.")
            return

        self.ingest_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.profile_selector.setEnabled(False)
        self.status_label.setText(
            "Ingesting resume... this calls the LLM and can take a bit."
        )

        # Kept as an attribute so the QThread isn't garbage-collected mid-run.
        self._worker = _CallableWorker(
            lambda: run_resume_ingestion(resume_text, self._services), parent=self
        )
        self._worker.succeeded.connect(self._on_ingest_succeeded)
        self._worker.failed.connect(self._on_ingest_failed)
        self._worker.start()

    def _on_ingest_succeeded(self, result: tuple[str, Candidate]) -> None:
        candidate_id, _candidate = result
        self._reload_profiles(select_id=candidate_id)
        self.ingest_button.setEnabled(True)
        self.profile_selector.setEnabled(True)
        self.status_label.setText(
            "Resume ingested as a new profile. You can now Generate a CV for a vacancy."
        )

    def _on_ingest_failed(self, message: str) -> None:
        self.ingest_button.setEnabled(True)
        self.profile_selector.setEnabled(True)
        self.generate_button.setEnabled(self._candidate is not None)
        self.status_label.setText(f"Ingestion failed: {message}")
        QMessageBox.warning(self, "Ingestion failed", message)

    # ----- generate ---------------------------------------------------------

    def _on_generate_clicked(self) -> None:
        if self._candidate is None:
            self.status_label.setText("Ingest a resume first.")
            return
        vacancy_text = self.vacancy_input.toPlainText().strip()
        if not vacancy_text:
            self.status_label.setText("Paste a job description first.")
            return

        self.ingest_button.setEnabled(False)
        self.generate_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.profile_selector.setEnabled(False)
        self.status_label.setText(
            "Generating... this calls the LLM a few times and can take a bit."
        )

        candidate = self._candidate
        evidence = self._evidence

        # Kept as an attribute so the QThread isn't garbage-collected mid-run.
        self._worker = _CallableWorker(
            lambda: run_cv_generation(candidate, evidence, vacancy_text, self._services),
            parent=self,
        )
        self._worker.succeeded.connect(self._on_generate_succeeded)
        self._worker.failed.connect(self._on_generate_failed)
        self._worker.start()

    def _on_generate_succeeded(self, result: PipelineResult) -> None:
        cv = result.assembled_cv

        self._current_header_markdown = render_header(cv)
        self.header_label.setText(_header_html(cv))

        sections = render_all_sections(cv)
        for key, edit in self.section_edits.items():
            edit.setPlainText(sections.get(key, ""))

        self.gaps_label.setText(_gaps_html(result.match_result))

        # Phase 8.3: freshly generated text is the new dirty-check
        # baseline, and this profile is the one a save should target,
        # regardless of what the user does with profile_selector next.
        self._last_result = result
        self._last_result_candidate_service = self._active_candidate_service
        self._last_generated_section_text = {
            key: sections.get(key, "") for key in _WRITEBACK_SECTION_KEYS
        }
        for key in _WRITEBACK_SECTION_KEYS:
            self.save_buttons[key].setEnabled(False)

        self.ingest_button.setEnabled(True)
        self.generate_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self.profile_selector.setEnabled(True)
        self.status_label.setText("Done. Review and edit any section, then Export CV.")

    def _on_generate_failed(self, message: str) -> None:
        self.ingest_button.setEnabled(True)
        self.generate_button.setEnabled(True)
        self.profile_selector.setEnabled(True)
        self.status_label.setText(f"Generation failed: {message}")
        QMessageBox.warning(self, "Generation failed", message)

    # ----- export -----------------------------------------------------------

    def _on_export_clicked(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export CV",
            "cv_output.pdf",
            "PDF (*.pdf);;Word Document (*.docx);;Markdown (*.md)",
        )
        if not path:
            return  # user cancelled

        suffix = Path(path).suffix.lower()
        sections = {key: edit.toPlainText() for key, edit in self.section_edits.items()}

        try:
            if suffix == ".pdf":
                data = render_pdf(self._last_result.assembled_cv, sections)
            elif suffix == ".docx":
                data = render_docx(self._last_result.assembled_cv, sections)
            elif suffix == ".md":
                data = assemble_markdown_from_sections(
                    self._current_header_markdown, sections
                ).encode("utf-8")
            else:
                QMessageBox.warning(
                    self, "Export failed", f"Unsupported export file type: '{suffix}'."
                )
                return
        except AppError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return

        try:
            with open(path, "wb") as f:
                f.write(data)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return

        self.status_label.setText(f"Exported to {path}")

    # ----- save edits to profile (Phase 8.3) ---------------------------------

    def _on_section_text_changed(self, key: str) -> None:
        baseline = self._last_generated_section_text.get(key)
        button = self.save_buttons.get(key)
        if button is None:
            return
        current = self.section_edits[key].toPlainText()
        button.setEnabled(baseline is not None and current != baseline)

    def _on_save_section_clicked(self, key: str) -> None:
        if self._last_result is None or self._last_result_candidate_service is None:
            QMessageBox.warning(self, "Nothing to save", "Generate a CV first.")
            return

        edited_text = self.section_edits[key].toPlainText()
        if key == "summary":
            title = "Save Summary edits to profile?"
            proposals = [build_summary_proposal(edited_text)]
        elif key == "skills":
            title = "Save Skills edits to profile?"
            proposals = build_skills_proposals(self._last_result.candidate, edited_text)
        elif key == "experience":
            title = "Save Experience edits to profile?"
            proposals = build_experience_proposals(
                self._last_result.assembled_cv.experience, edited_text
            )
        else:
            return

        dialog = _WritebackDialog(title, proposals, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        service = self._last_result_candidate_service
        try:
            for proposal in dialog.selected_proposals():
                proposal.apply(service)
        except AppError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))
            return

        self._last_generated_section_text[key] = edited_text
        self.save_buttons[key].setEnabled(False)
        self.status_label.setText(f"Saved {SECTION_TITLES[key]} edits to the master profile.")

        # Refreshes the switcher/active-profile state from disk in case
        # anything relevant changed — doesn't touch the CV currently shown.
        self._reload_profiles(select_id=self._active_candidate_id)


def run(services: Services) -> None:
    app = QApplication(sys.argv)
    window = MainWindow(services)
    window.show()
    sys.exit(app.exec())
