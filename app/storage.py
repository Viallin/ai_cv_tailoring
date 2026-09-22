"""Local storage — prototype scope.

Flat JSON files on disk, per docs/development_plan.md Phase 2. Replaced with a
structured CareerGraph store in Phase 7. Kept behind simple functions so
callers don't need to change when the backing storage changes.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.errors import StorageError
from domain.models import Candidate, CareerGraph, Evidence


def save_candidate(candidate: Candidate, data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "candidate.json"
    try:
        path.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")
    except OSError as exc:
        raise StorageError(f"Failed to write candidate profile: {exc}") from exc
    return path


def load_candidate(data_dir: Path) -> Candidate | None:
    path = data_dir / "candidate.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"Failed to read candidate profile: {exc}") from exc
    return Candidate.model_validate(data)


def delete_candidate(data_dir: Path) -> bool:
    path = data_dir / "candidate.json"
    if not path.exists():
        return False
    try:
        path.unlink()
    except OSError as exc:
        raise StorageError(f"Failed to delete candidate profile: {exc}") from exc
    return True


def save_evidence(evidence: list[Evidence], data_dir: Path) -> Path:
    """Persists the flat Evidence[] list from resume ingestion (Phase 8) —
    a sibling of candidate.json, not merged into it, so Candidate CRUD and
    Evidence never need to touch the same file. Deliberately not
    save_career_graph()/CareerGraph below: that would duplicate the
    Candidate into a second file that could drift from candidate.json.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "evidence.json"
    try:
        payload = json.dumps([item.model_dump(mode="json") for item in evidence], indent=2)
        path.write_text(payload, encoding="utf-8")
    except OSError as exc:
        raise StorageError(f"Failed to write evidence: {exc}") from exc
    return path


def load_evidence(data_dir: Path) -> list[Evidence]:
    path = data_dir / "evidence.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"Failed to read evidence: {exc}") from exc
    return [Evidence.model_validate(item) for item in data]


def list_candidate_ids(data_dir: Path) -> list[str]:
    """Lists ids of saved candidate profiles under `data_dir/candidates/`
    (Phase 8.1) — each id is a subdirectory containing its own
    candidate.json/evidence.json, per app/candidate_registry.py. Sorted by
    that candidate.json's mtime, most-recently-active first, so the UI can
    default to the profile the person was last working with.
    """
    candidates_dir = data_dir / "candidates"
    if not candidates_dir.exists():
        return []
    entries = [
        p.parent
        for p in candidates_dir.glob("*/candidate.json")
        if p.is_file()
    ]
    entries.sort(key=lambda p: (p / "candidate.json").stat().st_mtime, reverse=True)
    return [p.name for p in entries]


def save_career_graph(graph: CareerGraph, data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "career_graph.json"
    try:
        path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    except OSError as exc:
        raise StorageError(f"Failed to write career graph: {exc}") from exc
    return path


def load_career_graph(data_dir: Path) -> CareerGraph | None:
    path = data_dir / "career_graph.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"Failed to read career graph: {exc}") from exc
    return CareerGraph.model_validate(data)
