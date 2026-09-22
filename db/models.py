"""SQLModel table definitions.

Two tables, not a 1:1 relational mirror of every nested list in
domain.models — see docs/development_plan.md's Phase 13 plan for the
reasoning: CandidateService already does "load whole Candidate, mutate
in-memory, save whole Candidate" for every method, with no cross-candidate
SQL queries needed anywhere in this phase's scope. CandidateRow.data holds
the full Candidate (every nested list — experience, skills, education, ...)
as one JSON blob. Evidence gets its own real table because Phase 15 needs a
real, FK-able Skill<->Evidence link; pulling it out later would be a second,
redundant migration on the same rows.

domain.models.Candidate itself gets no id field — the primary key here is a
storage-layer-only concept, never surfacing on the Pydantic domain model.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CandidateRow(SQLModel, table=True):
    __tablename__ = "candidate"

    id: str = Field(primary_key=True)
    data: dict = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class CVDraftRow(SQLModel, table=True):
    __tablename__ = "cv_draft"

    # Composite PK, same collision-safety precedent as EvidenceRow's own
    # docstring: the id itself (uuid.uuid4().hex[:8], mirroring
    # CandidateRegistry.new_profile_id()) is only ever guaranteed unique
    # within one candidate's own drafts.
    candidate_id: str = Field(foreign_key="candidate.id", primary_key=True, ondelete="CASCADE")
    id: str = Field(primary_key=True)
    vacancy: dict = Field(sa_column=Column(JSON, nullable=False))
    assembled_cv: dict = Field(sa_column=Column(JSON, nullable=False))
    document: dict = Field(sa_column=Column(JSON, nullable=False))
    # Nullable: None for an untailored draft (no LLM call happened), and
    # for any draft created before this column existed — see
    # domain.models.CVDraft's docstring for why these are persisted at all.
    match_result: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    provenance: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    # Same nullable-for-the-same-two-reasons precedent as match_result/
    # provenance above — added after those two, in its own migration,
    # because domain.models.CVDraft.timing was added later (see that
    # field's own docstring).
    timing: dict | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class EvidenceRow(SQLModel, table=True):
    __tablename__ = "evidence"

    # Composite PK, not a single `id` column: Evidence.id (e.g. "ev-1") is
    # only ever generated/validated unique *within* one candidate's list —
    # nothing before Phase 13 required it to be globally unique, and two
    # different candidates legitimately reuse the same id (real bug hit
    # during the JSON->SQLite migration script's own testing, not a
    # hypothetical).
    candidate_id: str = Field(foreign_key="candidate.id", primary_key=True, ondelete="CASCADE")
    id: str = Field(primary_key=True)
    position: int
    text: str
    source_context: str | None = None
    experience_id: str | None = None
    experience_project_id: str | None = None
    locked: bool = False
    locked_text: str | None = None
