"""UI Tests (docs/architecture.md Testing Strategy).

Phase 12.2 decision: plain PySide6 (a shared `QApplication` + calling
slots/`.click()` directly), no `pytest-qt` dependency — the app only needs
a handful of UI tests, not a full GUI test framework. `_CallableWorker` is
a QThread (QtCore), not a widget, so it doesn't even need a QApplication;
calling `.run()` directly (rather than `.start()`) executes it
synchronously on the test thread, and Qt signal emission calls connected
slots synchronously in that case too.

The export-dispatch and save-flow-error tests below formalize the manual
smoke scripts written and hand-verified in Phase 10 and Phase 12.1 into
permanent regression tests.
"""

import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from sqlmodel import SQLModel

from app.config import Config
from app.errors import ValidationError
from app.graph_writeback import WritebackProposal
from app.pipeline import PipelineResult
from app.services import build_services
from db.engine import get_engine
from domain.models import (
    AssembledCV,
    BulletProvenanceReport,
    Candidate,
    GenerationTiming,
    MatchResult,
    Vacancy,
)
from ui.main_window import MainWindow, _CallableWorker

_app = QApplication.instance() or QApplication(sys.argv)


def _make_config(tmp_path: Path) -> Config:
    database_url = f"sqlite:///{tmp_path / 'data' / 'test.db'}"
    # get_engine() creates the parent dir on first connect (db/engine.py);
    # table creation still needs its own call — build_services() deliberately
    # doesn't do this itself (would bypass Alembic's migration history in a
    # real environment), so tests stand in for `alembic upgrade head`.
    SQLModel.metadata.create_all(get_engine(database_url))
    return Config(
        llm_provider="gemini",
        llm_fallback_providers=(),
        llm_model="gemini-2.0-flash",
        gemini_api_key="fake-key",
        llm_max_retries=0,
        llm_retry_base_delay_seconds=0.0,
        prompts_dir=Path("prompts"),
        data_dir=tmp_path / "data",
        log_level="INFO",
        database_url=database_url,
    )


def test_unexpected_error_is_logged_with_a_stack_trace(caplog):
    def boom():
        raise RuntimeError("boom")

    worker = _CallableWorker(boom)
    failures = []
    worker.failed.connect(failures.append)

    with caplog.at_level(logging.ERROR, logger="ui.main_window"):
        worker.run()

    assert failures == ["Unexpected error: boom"]
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "ERROR"
    assert caplog.records[0].exc_info is not None


def test_app_error_is_reported_without_logging(caplog):
    from app.errors import ValidationError

    def boom():
        raise ValidationError("Name must not be empty.")

    worker = _CallableWorker(boom)
    failures = []
    worker.failed.connect(failures.append)

    with caplog.at_level(logging.ERROR, logger="ui.main_window"):
        worker.run()

    assert failures == ["Name must not be empty."]
    assert caplog.records == []  # expected/categorized errors aren't logged as unexpected


# ----- shared MainWindow fixture -------------------------------------------


@pytest.fixture
def window(tmp_path):
    config = _make_config(tmp_path)
    services = build_services(config)
    win = MainWindow(services)

    candidate_service = services.candidate_registry.service_for("ada")
    candidate_service.create(name="Ada Lovelace")
    win._active_candidate_service = candidate_service
    win._last_result_candidate_service = candidate_service

    cv = AssembledCV(name="Ada Lovelace", headline="Engineer", summary="A summary.")
    win._last_result = PipelineResult(
        candidate=Candidate(name="Ada Lovelace"),
        vacancy=Vacancy(raw_text="some JD"),
        match_result=MatchResult(),
        assembled_cv=cv,
        provenance=BulletProvenanceReport(),
        timing=GenerationTiming(
            vacancy_analysis_seconds=0,
            matching_seconds=0,
            rewrite_planning_seconds=0,
            bullet_rewriting_seconds=0,
            quality_recheck_seconds=0,
            total_seconds=0,
        ),
    )
    win._current_header_markdown = "# Ada Lovelace\n*Engineer*"
    win.section_edits["summary"].setPlainText("A summary.")
    return win


# ----- export dispatch (Phase 10) ------------------------------------------


@pytest.mark.parametrize(
    "suffix,expected_prefix",
    [(".pdf", b"%PDF"), (".docx", b"PK"), (".md", b"# Ada")],
)
def test_export_dispatches_by_file_suffix(window, tmp_path, suffix, expected_prefix):
    out_path = str(tmp_path / f"out{suffix}")
    with patch("ui.main_window.QFileDialog.getSaveFileName", return_value=(out_path, "")):
        window._on_export_clicked()

    data = Path(out_path).read_bytes()
    assert data[: len(expected_prefix)] == expected_prefix
    assert "Exported to" in window.status_label.text()


def test_export_cancelled_dialog_writes_nothing(window, tmp_path):
    with patch("ui.main_window.QFileDialog.getSaveFileName", return_value=("", "")):
        window._on_export_clicked()

    assert list(tmp_path.iterdir()) == [tmp_path / "data"]


# ----- write-back save error guard (Phase 12.1) ----------------------------


def test_save_section_shows_warning_instead_of_raising_on_apply_error(window):
    def boom(service):
        raise ValidationError("Simulated validation failure.")

    proposal = WritebackProposal(label="Update candidate summary", enabled=True, apply=boom)

    warnings = []
    with patch("ui.main_window._WritebackDialog") as MockDialog:
        instance = MockDialog.return_value
        instance.exec.return_value = QDialog.DialogCode.Accepted
        instance.selected_proposals.return_value = [proposal]
        with patch.object(QMessageBox, "warning", side_effect=lambda *a: warnings.append(a[1:])):
            window._on_save_section_clicked("summary")

    assert warnings == [("Save failed", "Simulated validation failure.")]


# ----- Graph Explorer integration (Phase 12.3) ------------------------------


def test_resume_input_starts_blank(tmp_path):
    config = _make_config(tmp_path)
    win = MainWindow(build_services(config))

    assert win.resume_input.toPlainText() == ""


def test_switching_profile_selector_updates_the_graph_explorer(tmp_path):
    config = _make_config(tmp_path)
    services = build_services(config)
    services.candidate_registry.service_for("a").create(name="Ada Lovelace")
    services.candidate_registry.service_for("b").create(name="Bob Babbage")

    win = MainWindow(services)
    win._reload_profiles()

    for index in range(win.profile_selector.count()):
        win.profile_selector.setCurrentIndex(index)
        candidate_id = win.profile_selector.itemData(index)
        expected_name = services.candidate_registry.service_for(candidate_id).get().name
        assert win.graph_explorer._name.text() == expected_name
