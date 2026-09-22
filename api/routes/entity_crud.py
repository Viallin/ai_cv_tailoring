"""Generic CRUD route factory for the shape-identical entities nested
under one candidate (education, skills, technologies, languages,
certifications, awards, contacts, projects, publications, portfolio-links,
volunteer-experience, experience, and — Phase 15 — evidence) — one factory
call-site per entity instead of ~40 hand-written near-duplicate handlers.
The factory only requires matching CandidateService.add_X/update_X/
remove_X methods to exist; it doesn't care whether the entity lives inside
the Candidate JSON blob (eleven of these) or its own table (evidence).

Mirrors the precedent ui/graph_explorer.py's `_EntityListSection` already
set for the same shape-identical-CRUD problem on the desktop UI side.

Create/update request bodies are generated dynamically rather than
hand-written per entity:
* The create body's fields/defaults come from the real Python signature of
  CandidateService's own add_X() method (not "every domain model field
  minus id") — some add_X() methods deliberately don't accept every field
  their domain model has (e.g. add_experience_project() has no
  `responsibilities` param even though ExperienceProject does; add_X()'s
  signature is the authoritative contract for what creation accepts, and
  passing an unexpected kwarg would raise a TypeError add_X() itself
  wouldn't catch).
* The update body's fields come from the domain model directly (all
  Optional, default None) — update_X(id, **fields) is a generic
  dict-merge-then-revalidate, so any real field name is safe to accept.

The one nested case (Experience Projects, under one Experience) isn't
pushed through this factory — with only one nested entity in this phase's
scope, three explicit handlers are simpler than a generic n-level-nesting
parameterization would be.
"""

import inspect
from typing import Any, get_type_hints

# No `from __future__ import annotations` in this module, deliberately: the
# route handlers below take dynamically-created Pydantic models
# (create_request_model/update_request_model) as parameter annotations via
# closure variables, not module-level names. Postponed evaluation would turn
# those annotations into strings FastAPI can't resolve back to the real
# class (typing.get_type_hints only sees a function's __globals__, not its
# enclosing closure) — it would silently treat `body` as a query param
# instead of a request body. Real 3.11+ generics (`dict[str, ...]`, `X | Y`)
# work fine at runtime without the future import, so nothing else here needs it.

from fastapi import APIRouter, Depends
from pydantic import BaseModel, create_model

from api.deps import get_candidate_service
from app.candidate_service import CandidateService
from domain.models import (
    Award,
    Certification,
    ContactItem,
    CVDraft,
    Education,
    Evidence,
    Experience,
    ExperienceProject,
    Language,
    PortfolioLink,
    Project,
    Publication,
    Skill,
    Technology,
    VolunteerExperience,
)

router = APIRouter(prefix="/candidates/{candidate_id}", tags=["candidate-entities"])


def _create_request_fields(
    method: Any, skip: tuple[str, ...] = ()
) -> dict[str, tuple[Any, Any]]:
    hints = get_type_hints(method)
    hints.pop("return", None)
    sig = inspect.signature(method)
    fields: dict[str, tuple[Any, Any]] = {}
    for name, param in sig.parameters.items():
        if name == "self" or name in skip:
            continue
        annotation = hints.get(name, Any)
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[name] = (annotation, default)
    return fields


def _update_request_fields(domain_model: type[BaseModel]) -> dict[str, tuple[Any, Any]]:
    return {
        name: (info.annotation | None, None)
        for name, info in domain_model.model_fields.items()
        if name != "id"
    }


class ReorderRequest(BaseModel):
    ordered_ids: list[str]


def register_entity_crud_routes(
    *,
    path_segment: str,
    domain_model: type[BaseModel],
    method_prefix: str,
    # Only the 11 entities that live directly as a `list[X]` field on
    # Candidate (not `experience`, whose reorder is a different mechanism
    # bundled into ExperienceForm.tsx's own atomic save — see
    # CandidateService.reorder_entities' docstring — and not `evidence`/
    # CVDraft, neither of which is a Candidate attribute at all) pass this.
    list_field: str | None = None,
) -> None:
    add_method = getattr(CandidateService, f"add_{method_prefix}")
    update_method_name = f"update_{method_prefix}"
    remove_method_name = f"remove_{method_prefix}"

    create_request_model = create_model(
        f"{domain_model.__name__}CreateRequest", **_create_request_fields(add_method)
    )
    update_request_model = create_model(
        f"{domain_model.__name__}UpdateRequest", **_update_request_fields(domain_model)
    )

    base_path = f"/{path_segment}"
    item_path = f"{base_path}/{{item_id}}"

    @router.post(
        base_path,
        response_model=domain_model,
        status_code=201,
        name=f"create_{method_prefix}",
    )
    def create_entity(
        body: create_request_model,  # type: ignore[valid-type]
        service: CandidateService = Depends(get_candidate_service),
    ):
        # `getattr`, not `body.model_dump()` — .model_dump() recursively
        # flattens every nested Pydantic field into a plain dict, which
        # silently breaks any add_X() whose signature expects a real
        # nested model instance (e.g. CVDraft's `vacancy: Vacancy`, Phase
        # 20) rather than a dict. Every field on every entity registered
        # here so far happens to be a flat scalar, where the two are
        # equivalent — this is a latent-bug fix, not new behavior for
        # any of them.
        return add_method(service, **{name: getattr(body, name) for name in type(body).model_fields})

    @router.put(item_path, response_model=domain_model, name=f"update_{method_prefix}")
    def update_entity(
        item_id: str,
        body: update_request_model,  # type: ignore[valid-type]
        service: CandidateService = Depends(get_candidate_service),
    ):
        # Same nested-model reasoning as create_entity above;
        # `model_fields_set` (not `model_fields`) preserves the existing
        # exclude_unset partial-patch semantics.
        return getattr(service, update_method_name)(
            item_id, **{name: getattr(body, name) for name in body.model_fields_set}
        )

    @router.delete(item_path, status_code=204, name=f"remove_{method_prefix}")
    def remove_entity(item_id: str, service: CandidateService = Depends(get_candidate_service)) -> None:
        getattr(service, remove_method_name)(item_id)

    if list_field is not None:

        @router.post(
            f"{base_path}/reorder",
            response_model=list[domain_model],
            name=f"reorder_{method_prefix}",
        )
        def reorder_entity(
            body: ReorderRequest,
            service: CandidateService = Depends(get_candidate_service),
        ):
            return service.reorder_entities(list_field, body.ordered_ids)


_ENTITY_REGISTRATIONS = [
    dict(path_segment="education", domain_model=Education, method_prefix="education", list_field="education"),
    dict(path_segment="skills", domain_model=Skill, method_prefix="skill", list_field="skills"),
    dict(
        path_segment="technologies",
        domain_model=Technology,
        method_prefix="technology",
        list_field="technologies",
    ),
    dict(path_segment="languages", domain_model=Language, method_prefix="language", list_field="languages"),
    dict(
        path_segment="certifications",
        domain_model=Certification,
        method_prefix="certification",
        list_field="certifications",
    ),
    dict(path_segment="awards", domain_model=Award, method_prefix="award", list_field="awards"),
    dict(path_segment="contacts", domain_model=ContactItem, method_prefix="contact", list_field="contacts"),
    dict(path_segment="projects", domain_model=Project, method_prefix="project", list_field="projects"),
    dict(
        path_segment="publications",
        domain_model=Publication,
        method_prefix="publication",
        list_field="publications",
    ),
    dict(
        path_segment="portfolio-links",
        domain_model=PortfolioLink,
        method_prefix="portfolio_link",
        list_field="portfolio_links",
    ),
    dict(
        path_segment="volunteer-experience",
        domain_model=VolunteerExperience,
        method_prefix="volunteer_experience",
        list_field="volunteer_experience",
    ),
    # Experience deliberately has no list_field here — its reorder is a
    # different mechanism (nested Projects/bullets, bundled into
    # ExperienceForm.tsx's own atomic role save), not this generic one.
    dict(path_segment="experience", domain_model=Experience, method_prefix="experience"),
    # Evidence (Phase 15) lives in its own table (EvidenceRow), not inside
    # the Candidate JSON blob like the eleven entities above — but the
    # factory only needs CandidateService.add_X/update_X/remove_X to exist
    # with the right shape, so it slots in here with zero route changes.
    # GET /candidates/{id}/evidence (bulk list) stays hand-written in
    # candidates.py; this adds the missing POST/PUT/DELETE for one item.
    dict(path_segment="evidence", domain_model=Evidence, method_prefix="evidence"),
    # CVDraft (Phase 20) — same "own table, zero route changes" precedent
    # as Evidence above. GET (list summaries) and GET (one, full) stay
    # hand-written in api/routes/cv_drafts.py, mirroring Evidence's own
    # hand-written bulk-list precedent — the factory has no GET verb at
    # all for any entity today.
    dict(path_segment="drafts", domain_model=CVDraft, method_prefix="cv_draft"),
]

for _spec in _ENTITY_REGISTRATIONS:
    register_entity_crud_routes(**_spec)  # type: ignore[arg-type]


# ----- Experience Projects (nested inside one Experience entry) -----------
# Not run through the factory above: the parent Experience id is an extra
# path param the flat factory doesn't model, and there's only one such case
# in this phase's scope.

_experience_project_create_model = create_model(
    "ExperienceProjectCreateRequest",
    **_create_request_fields(CandidateService.add_experience_project, skip=("experience_id",)),
)
_experience_project_update_model = create_model(
    "ExperienceProjectUpdateRequest", **_update_request_fields(ExperienceProject)
)

_EXPERIENCE_PROJECTS_BASE = "/experience/{experience_id}/projects"
_EXPERIENCE_PROJECTS_ITEM = f"{_EXPERIENCE_PROJECTS_BASE}/{{item_id}}"


@router.post(
    _EXPERIENCE_PROJECTS_BASE,
    response_model=ExperienceProject,
    status_code=201,
    name="create_experience_project",
)
def create_experience_project(
    experience_id: str,
    body: _experience_project_create_model,  # type: ignore[valid-type]
    service: CandidateService = Depends(get_candidate_service),
):
    return service.add_experience_project(experience_id, **body.model_dump())


@router.put(
    _EXPERIENCE_PROJECTS_ITEM, response_model=ExperienceProject, name="update_experience_project"
)
def update_experience_project(
    experience_id: str,
    item_id: str,
    body: _experience_project_update_model,  # type: ignore[valid-type]
    service: CandidateService = Depends(get_candidate_service),
):
    return service.update_experience_project(
        experience_id, item_id, **body.model_dump(exclude_unset=True)
    )


@router.delete(_EXPERIENCE_PROJECTS_ITEM, status_code=204, name="remove_experience_project")
def remove_experience_project(
    experience_id: str, item_id: str, service: CandidateService = Depends(get_candidate_service)
) -> None:
    service.remove_experience_project(experience_id, item_id)
