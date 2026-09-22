import time

import pytest

from app.errors import StorageError
from app.storage import (
    delete_candidate,
    list_candidate_ids,
    load_candidate,
    load_evidence,
    save_candidate,
    save_evidence,
)
from domain.models import Candidate, Evidence


def test_load_candidate_returns_none_when_no_file_exists(tmp_path):
    assert load_candidate(tmp_path) is None


def test_save_then_load_round_trips_candidate(tmp_path):
    candidate = Candidate(name="Ada Lovelace", headline="Analytical Engineer")

    save_candidate(candidate, tmp_path)
    loaded = load_candidate(tmp_path)

    assert loaded == candidate


def test_save_candidate_creates_data_dir_if_missing(tmp_path):
    data_dir = tmp_path / "nested" / "data"
    candidate = Candidate(name="Ada Lovelace")

    path = save_candidate(candidate, data_dir)

    assert path.exists()
    assert path.parent == data_dir


def test_load_candidate_raises_storage_error_on_invalid_json(tmp_path):
    (tmp_path / "candidate.json").write_text("not json", encoding="utf-8")

    with pytest.raises(StorageError):
        load_candidate(tmp_path)


def test_delete_candidate_returns_false_when_nothing_to_delete(tmp_path):
    assert delete_candidate(tmp_path) is False


def test_delete_candidate_removes_file_and_returns_true(tmp_path):
    candidate = Candidate(name="Ada Lovelace")
    save_candidate(candidate, tmp_path)

    assert delete_candidate(tmp_path) is True
    assert load_candidate(tmp_path) is None


def test_load_evidence_returns_empty_list_when_no_file_exists(tmp_path):
    assert load_evidence(tmp_path) == []


def test_save_then_load_round_trips_evidence(tmp_path):
    evidence = [
        Evidence(id="ev-1", text="Led a team of five designers."),
        Evidence(
            id="ev-2",
            text="Migrated legacy billing system.",
            experience_id="exp-1",
            experience_project_id="exp-1-proj-1",
        ),
    ]

    save_evidence(evidence, tmp_path)
    loaded = load_evidence(tmp_path)

    assert loaded == evidence


def test_save_evidence_creates_data_dir_if_missing(tmp_path):
    data_dir = tmp_path / "nested" / "data"

    path = save_evidence([Evidence(id="ev-1", text="Did a thing")], data_dir)

    assert path.exists()
    assert path.parent == data_dir


def test_load_evidence_raises_storage_error_on_invalid_json(tmp_path):
    (tmp_path / "evidence.json").write_text("not json", encoding="utf-8")

    with pytest.raises(StorageError):
        load_evidence(tmp_path)


def test_save_evidence_overwrites_previous_contents(tmp_path):
    save_evidence([Evidence(id="ev-1", text="First")], tmp_path)
    save_evidence([Evidence(id="ev-2", text="Second")], tmp_path)

    assert load_evidence(tmp_path) == [Evidence(id="ev-2", text="Second")]


def test_list_candidate_ids_returns_empty_list_when_no_candidates_dir(tmp_path):
    assert list_candidate_ids(tmp_path) == []


def test_list_candidate_ids_returns_empty_list_when_candidates_dir_is_empty(tmp_path):
    (tmp_path / "candidates").mkdir()

    assert list_candidate_ids(tmp_path) == []


def test_list_candidate_ids_finds_profile_subdirectories(tmp_path):
    save_candidate(Candidate(name="Ada Lovelace"), tmp_path / "candidates" / "ada")
    save_candidate(Candidate(name="Charles Babbage"), tmp_path / "candidates" / "charles")

    assert set(list_candidate_ids(tmp_path)) == {"ada", "charles"}


def test_list_candidate_ids_ignores_subdirectories_without_a_candidate_json(tmp_path):
    save_candidate(Candidate(name="Ada Lovelace"), tmp_path / "candidates" / "ada")
    (tmp_path / "candidates" / "empty-dir").mkdir()

    assert list_candidate_ids(tmp_path) == ["ada"]


def test_list_candidate_ids_sorts_most_recently_active_first(tmp_path):
    save_candidate(Candidate(name="Ada Lovelace"), tmp_path / "candidates" / "ada")
    time.sleep(0.01)  # ensure a distinct mtime on most filesystems
    save_candidate(Candidate(name="Charles Babbage"), tmp_path / "candidates" / "charles")

    assert list_candidate_ids(tmp_path) == ["charles", "ada"]
