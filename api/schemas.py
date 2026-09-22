"""HTTP-transport-only request/response models.

Distinct from contracts/schemas.py (internal LLM-call contracts) and
domain/models.py (business entities) — the API reuses those two directly
wherever they already fit (per docs/development_plan.md Phase 13: "reusing
contracts/schemas.py Pydantic models as request/response bodies directly").
Models here exist only because profile-level create/update needs shapes
that don't otherwise exist (e.g. Candidate has no id field to return
alongside a newly created profile — see db/models.py).

Per-entity create/update request models (Skill, Experience, ...) are NOT
here — api/routes/entity_crud.py generates those dynamically from
CandidateService's own add_X()/domain model field shapes, so 12+ near-
identical hand-written classes never have to be kept in sync by hand.
"""

from __future__ import annotations

from pydantic import BaseModel

from domain.models import Candidate, ContactItem, EmploymentType, Evidence


class CandidateCreateRequest(BaseModel):
    name: str
    headline: str | None = None
    # Version 4, Phase 4.2: an explicit choice for an empty profile (no
    # resume text to detect it from) — see domain.models.Candidate.language.
    language: str = "en"


class CandidateCreateResponse(BaseModel):
    id: str
    candidate: Candidate


class CandidateUpdateRequest(BaseModel):
    """All fields optional — only fields the client actually set are
    applied (api/routes/candidates.py uses exclude_unset=True), matching
    CandidateService.update()'s partial-patch semantics. For `contacts`,
    passing it here still replaces the whole list wholesale — same caveat
    as CandidateService.update()'s own docstring."""

    name: str | None = None
    headline: str | None = None
    summary: str | None = None
    employment_types_sought: list[EmploymentType] | None = None
    contacts: list[ContactItem] | None = None


class ReplaceCandidateRequest(BaseModel):
    candidate: Candidate
    evidence: list[Evidence] | None = None
