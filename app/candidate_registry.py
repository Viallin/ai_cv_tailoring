"""Multiple Candidate Profiles — Phase 8.1, storage migrated to SQLite in
Phase 13.

`CandidateService` (app/candidate_service.py) needs no changes for this:
every one of its methods is already scoped to whatever candidate_id it was
constructed with. The single-profile constraint used to live entirely in
*which* directory got passed to it (one fixed data_dir per app.services.
build_services() call, pre-Phase-13) — this module is what turns that into
"one of several," by giving each profile its own row (keyed by candidate_id)
and providing a `CandidateService` scoped to whichever one is currently
active. There is still no server-side "active profile" concept — every
caller passes candidate_id explicitly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Engine
from sqlmodel import select

from app.candidate_service import CandidateService
from db.models import CandidateRow
from db.session import session_scope


@dataclass
class CandidateProfileSummary:
    id: str
    name: str
    experience_count: int
    # Version 4, Phase 4.6: the new start-screen candidate table
    # (frontend/src/components/CandidateTable.tsx) shows Role and Language
    # columns without a separate GET per row — both already live on every
    # row's own CandidateRow.data JSON blob, so this is a free read, not an
    # extra query.
    headline: str | None = None
    language: str = "en"


class CandidateRegistry:
    def __init__(self, engine: Engine):
        self._engine = engine

    def list_profiles(self) -> list[CandidateProfileSummary]:
        """Returns saved profiles, most-recently-active first (by
        CandidateRow.updated_at — the SQLite equivalent of the old
        candidate.json mtime ordering)."""
        with session_scope(self._engine) as session:
            rows = session.exec(select(CandidateRow).order_by(CandidateRow.updated_at.desc())).all()
            return [
                CandidateProfileSummary(
                    id=row.id,
                    name=row.data.get("name", ""),
                    experience_count=len(row.data.get("experience", [])),
                    headline=row.data.get("headline"),
                    language=row.data.get("language", "en"),
                )
                for row in rows
            ]

    def new_profile_id(self) -> str:
        return uuid.uuid4().hex[:8]

    def service_for(self, candidate_id: str) -> CandidateService:
        return CandidateService(candidate_id=candidate_id, engine=self._engine)
