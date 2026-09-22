"""Migrates the two real, git-tracked profiles under data/candidates/
(33e010af — richly populated; 695d389b — minimal) into a throwaway SQLite
DB, and checks idempotency. No synthetic fixture: data/candidates/ is
tracked in git specifically so these two profiles double as this test's
fixture data (see docs/development_plan.md's Phase 13 plan).
"""

from __future__ import annotations

from pathlib import Path

from sqlmodel import SQLModel

from app.storage import load_candidate, load_evidence
from db.engine import get_engine
from scripts.migrate_json_to_sqlite import migrate

_REAL_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_REAL_CANDIDATE_IDS = ("33e010af", "695d389b")


def make_engine(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    return engine


def test_migrates_both_real_committed_profiles(tmp_path):
    engine = make_engine(tmp_path)

    summary = migrate(_REAL_DATA_DIR, engine)

    assert set(summary.migrated) == set(_REAL_CANDIDATE_IDS)
    assert summary.skipped == []
    assert summary.failed == []
    assert summary.ok


def test_migrated_data_matches_the_source_json(tmp_path):
    from app.candidate_service import CandidateService

    engine = make_engine(tmp_path)
    migrate(_REAL_DATA_DIR, engine)

    for candidate_id in _REAL_CANDIDATE_IDS:
        profile_dir = _REAL_DATA_DIR / "candidates" / candidate_id
        expected_candidate = load_candidate(profile_dir)
        expected_evidence = load_evidence(profile_dir)

        service = CandidateService(candidate_id=candidate_id, engine=engine)
        assert service.get() == expected_candidate
        assert service.get_evidence() == expected_evidence


def test_rerunning_is_idempotent_by_default(tmp_path):
    engine = make_engine(tmp_path)

    migrate(_REAL_DATA_DIR, engine)
    second_run = migrate(_REAL_DATA_DIR, engine)

    assert second_run.migrated == []
    assert set(second_run.skipped) == set(_REAL_CANDIDATE_IDS)
    assert second_run.failed == []


def test_overwrite_flag_re_migrates_already_present_profiles(tmp_path):
    engine = make_engine(tmp_path)

    migrate(_REAL_DATA_DIR, engine)
    second_run = migrate(_REAL_DATA_DIR, engine, overwrite=True)

    assert set(second_run.migrated) == set(_REAL_CANDIDATE_IDS)
    assert second_run.skipped == []
