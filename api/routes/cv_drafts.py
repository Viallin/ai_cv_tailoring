"""GET /candidates/{candidate_id}/drafts (list) + GET .../drafts/{draft_id}
(one, full) — Phase 20's CVDraft entity has no update/create/remove code
here at all; those go through api/routes/entity_crud.py's generic factory
(registered in `_ENTITY_REGISTRATIONS`) exactly like every entity since
Phase 15a. This module exists only because the factory has no GET verb
for any entity — same reasoning as candidates.py's hand-written bulk
Evidence GET.

`list_cv_drafts` (below) is deliberately not the raw CandidateService
method name pattern the factory expects (`add_X`/`update_X`/`remove_X`) —
"list" and "get one" don't fit that create/update/remove shape, so they
were never candidates for the generic factory to begin with.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_candidate_service
from app.candidate_service import CandidateService
from domain.models import CVDraft, CVDraftSummary

router = APIRouter(prefix="/candidates/{candidate_id}/drafts", tags=["cv-drafts"])


@router.get("")
def list_cv_drafts(service: CandidateService = Depends(get_candidate_service)) -> list[CVDraftSummary]:
    return service.list_cv_drafts()


@router.get("/{draft_id}")
def get_cv_draft(draft_id: str, service: CandidateService = Depends(get_candidate_service)) -> CVDraft:
    draft = service.get_cv_draft(draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail=f"CV draft {draft_id!r} not found.")
    return draft
