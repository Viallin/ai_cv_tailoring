"""POST /candidates/{candidate_id}/writeback/preview + /apply — the web
app's entry point into Phase 8.3/11's write-back-to-the-graph feature
(app/graph_writeback.py), which until now only `ui/main_window.py` (the
desktop app) ever called.

Stateless, mirroring api/routes/export.py's own reasoning: the client
resends its own `assembled_cv`/`document` (exactly what `CvWorkflowView`
already holds after a generate) rather than anything being looked up
server-side — there's nothing durable to look up by job id, same as
export. `build_proposals_from_document()` is a pure function of
`(candidate, assembled_experience, document)`, so /preview and /apply
independently rebuild the *same* ordered proposal list from the same
input; /apply just also applies the ones the client selected. This is a
two-step, bespoke route (not api/routes/entity_crud.py's generic factory)
because it doesn't map onto that factory's single-entity CRUD shape.

Proposal identity across the two calls is positional: `key` is just the
proposal's index, stable because both endpoints build the list the same
deterministic way from the same input. No AppError handling here — the
app-wide handler (api/errors.py) already catches everything
CandidateService/graph_writeback can raise.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_candidate_service
from app.candidate_service import CandidateService
from app.graph_writeback import WritebackProposal, build_proposals_from_document
from domain.models import AssembledCV, PrintDocument

router = APIRouter(prefix="/candidates/{candidate_id}/writeback", tags=["writeback"])


class WritebackPreviewRequest(BaseModel):
    assembled_cv: AssembledCV
    document: PrintDocument


class WritebackApplyRequest(WritebackPreviewRequest):
    selected_keys: list[str]


class WritebackProposalOut(BaseModel):
    key: str
    label: str
    enabled: bool


class WritebackApplyResult(BaseModel):
    applied_keys: list[str]


def _build_proposals(
    service: CandidateService, assembled_cv: AssembledCV, document: PrintDocument
) -> list[WritebackProposal]:
    candidate = service.get()
    return build_proposals_from_document(candidate, assembled_cv.experience, document)


@router.post("/preview", response_model=list[WritebackProposalOut])
def preview_writeback(
    body: WritebackPreviewRequest, service: CandidateService = Depends(get_candidate_service)
) -> list[WritebackProposalOut]:
    proposals = _build_proposals(service, body.assembled_cv, body.document)
    return [
        WritebackProposalOut(key=str(index), label=proposal.label, enabled=proposal.enabled)
        for index, proposal in enumerate(proposals)
    ]


@router.post("/apply")
def apply_writeback(
    body: WritebackApplyRequest, service: CandidateService = Depends(get_candidate_service)
) -> WritebackApplyResult:
    proposals = _build_proposals(service, body.assembled_cv, body.document)
    selected = set(body.selected_keys)

    applied_keys: list[str] = []
    for index, proposal in enumerate(proposals):
        key = str(index)
        if key in selected and proposal.enabled and proposal.apply is not None:
            proposal.apply(service)
            applied_keys.append(key)

    return WritebackApplyResult(applied_keys=applied_keys)
