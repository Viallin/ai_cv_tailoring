"""Profile-level routes: GET/POST /candidates,
GET/PUT/PATCH/DELETE /candidates/{candidate_id},
GET /candidates/{candidate_id}/evidence.

Each has different semantics (list vs. mint-new vs. full-replace vs.
partial-patch) — hand-written rather than run through
api/routes/entity_crud.py's generic factory, which is only for the 12
shape-identical entity CRUD triads nested under one candidate.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_candidate_service, get_services
from api.schemas import (
    CandidateCreateRequest,
    CandidateCreateResponse,
    CandidateUpdateRequest,
    ReplaceCandidateRequest,
)
from app.candidate_registry import CandidateProfileSummary
from app.candidate_service import CandidateService
from app.cv_assembler import assemble_cv, build_untailored_projection
from app.services import Services
from domain.models import AssembledCV, Candidate, Evidence

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("")
def list_candidates(services: Services = Depends(get_services)) -> list[CandidateProfileSummary]:
    return services.candidate_registry.list_profiles()


@router.post("", status_code=201)
def create_candidate(
    body: CandidateCreateRequest, services: Services = Depends(get_services)
) -> CandidateCreateResponse:
    candidate_id = services.candidate_registry.new_profile_id()
    service = services.candidate_registry.service_for(candidate_id)
    candidate = service.create(name=body.name, headline=body.headline, language=body.language)
    return CandidateCreateResponse(id=candidate_id, candidate=candidate)


@router.get("/{candidate_id}")
def get_candidate(service: CandidateService = Depends(get_candidate_service)) -> Candidate:
    candidate = service.get()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return candidate


@router.put("/{candidate_id}")
def replace_candidate(
    body: ReplaceCandidateRequest, service: CandidateService = Depends(get_candidate_service)
) -> Candidate:
    return service.replace(body.candidate, evidence=body.evidence)


@router.patch("/{candidate_id}")
def update_candidate(
    body: CandidateUpdateRequest, service: CandidateService = Depends(get_candidate_service)
) -> Candidate:
    return service.update(**body.model_dump(exclude_unset=True))


@router.delete("/{candidate_id}", status_code=204)
def delete_candidate(service: CandidateService = Depends(get_candidate_service)) -> None:
    if not service.delete():
        raise HTTPException(status_code=404, detail="Candidate not found.")


@router.get("/{candidate_id}/evidence")
def get_candidate_evidence(service: CandidateService = Depends(get_candidate_service)) -> list[Evidence]:
    return service.get_evidence()


@router.post("/{candidate_id}/export-untailored")
def export_candidate_untailored(
    service: CandidateService = Depends(get_candidate_service),
) -> AssembledCV:
    """CV export screen's "export without tailoring" path: assembles a
    full CV straight from the Candidate Profile, with zero AI tailoring —
    see app.cv_assembler.build_untailored_projection's docstring.
    Deliberately synchronous, not an async job (api/routes/jobs.py):
    there's no LLM call here, so none of that machinery applies. The
    frontend turns the returned AssembledCV into a CVDraft itself via the
    existing generic POST .../drafts route, the same way a real generate
    job's result does.
    """
    candidate = service.get()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return assemble_cv(candidate, build_untailored_projection(candidate))
