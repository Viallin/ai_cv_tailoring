"""Candidate Profile CRUD — Phase 2, storage migrated to SQLite in Phase 13.

Application-layer service for creating, reading, updating, and deleting the
candidate profile and its nested Experience / Education / Skill / Language /
Certification / Contact / Project entries.

Persistence is delegated to db.session/db.models (SQLite via SQLModel, per
Phase 13 of docs/development_plan.md — flat JSON on disk before this). This
module owns validation and identifier assignment, per the "Application
Services" layer described in docs/architecture.md — it never talks to
storage internals directly and never contains UI logic.

Every mutating method still follows the same "load whole Candidate, mutate
the in-memory Pydantic model, save whole Candidate" pattern as the old
flat-JSON version (see db/models.py's module docstring for why that shape
carried over into the SQLite schema) — only the load/save internals changed
from file I/O to a scoped CandidateRow lookup.

Identity: since Phase 8.1, a candidate_id is assigned by
app.candidate_registry.CandidateRegistry and passed into the constructor —
domain.models.Candidate itself still carries no id field (see db/models.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, delete
from sqlmodel import Session, select

from app.errors import ValidationError
from db.models import CandidateRow, CVDraftRow, EvidenceRow
from db.session import session_scope
from domain.models import (
    AssembledCV,
    Award,
    BulletProvenanceReport,
    Candidate,
    Certification,
    ContactItem,
    CVDraft,
    CVDraftSummary,
    Education,
    Evidence,
    Experience,
    ExperienceProject,
    GenerationTiming,
    Language,
    MatchResult,
    PortfolioLink,
    PrintDocument,
    Project,
    Publication,
    Skill,
    Technology,
    Vacancy,
    VolunteerExperience,
)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _as_utc(value: datetime) -> datetime:
    """SQLite's DateTime column round-trips a stored value as *naive*,
    even though everything here is always written via `_utcnow()`-style
    tz-aware UTC datetimes (db/models.py) — SQLite has no native
    timezone-aware storage, so SQLAlchemy's generic DateTime type drops
    tzinfo on read. Harmless everywhere `created_at`/`updated_at` never
    leave the storage layer (CandidateRow/EvidenceRow), but CVDraft.
    created_at/.updated_at ARE part of the domain model surfaced to the
    API, so this re-attaches UTC before they're ever compared/serialized."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class CandidateService:
    def __init__(self, candidate_id: str, engine: Engine):
        self._candidate_id = candidate_id
        self._engine = engine

    # ----- Profile-level CRUD -----------------------------------------

    def get(self) -> Candidate | None:
        """Return the candidate profile, or None if it hasn't been created yet."""
        with session_scope(self._engine) as session:
            row = session.get(CandidateRow, self._candidate_id)
            return Candidate.model_validate(row.data) if row is not None else None

    def create(self, name: str, headline: str | None = None, language: str = "en") -> Candidate:
        if self.get() is not None:
            raise ValidationError(
                "Candidate profile already exists; use update() instead."
            )
        if not name or not name.strip():
            raise ValidationError("Candidate name must not be empty.")

        candidate = Candidate(name=name, headline=headline, language=language)
        self._save(candidate)
        return candidate

    def replace(
        self, candidate: Candidate, evidence: list[Evidence] | None = None
    ) -> Candidate:
        """Overwrite the entire profile with a freshly-parsed Candidate.

        This is the import path used after resume ingestion (see
        contracts.schemas.IngestResumeResponse.candidate): unlike create(), it
        succeeds even when a profile already exists, and unlike update(), it
        replaces the experience/education/skills lists wholesale rather than
        patching individual fields.

        This does NOT merge with existing manually-added entries — a repeat
        import overwrites them. Merge-on-import is intentionally out of scope
        for this prototype (see docs/development_plan.md, "Future Ideas" >
        Version history); callers who need to preserve manual additions
        should read them via get() before calling replace() and re-add them
        afterwards with add_experience()/add_education()/add_skill().

        `evidence` (Phase 8) is optional and, when given, is persisted in the
        same call — see get_evidence(). Kept atomic with the Candidate save
        (one transaction) so the two can never drift: a resume re-import
        always replaces both together, never just one. Omitting it leaves
        any previously saved Evidence untouched.
        """
        if not candidate.name or not candidate.name.strip():
            raise ValidationError("Candidate name must not be empty.")
        with session_scope(self._engine) as session:
            self._upsert_candidate_row(session, candidate)
            if evidence is not None:
                self._replace_evidence_rows(session, evidence)
        return candidate

    def get_evidence(self) -> list[Evidence]:
        """Return the Evidence[] saved alongside the Candidate profile by the
        most recent replace(..., evidence=...) call, or [] if none has been
        saved yet (e.g. a profile built entirely by manual CRUD)."""
        with session_scope(self._engine) as session:
            rows = session.exec(
                select(EvidenceRow)
                .where(EvidenceRow.candidate_id == self._candidate_id)
                .order_by(EvidenceRow.position)
            ).all()
            return [self._evidence_from_row(row) for row in rows]

    # ----- Evidence CRUD (Phase 15) ---------------------------------------
    # Individual Evidence CRUD, distinct from replace()'s bulk
    # wholesale-replace-all-evidence path (used only by resume ingestion).
    # Evidence is the one entity that lives in its own table (EvidenceRow,
    # see db/models.py) rather than inside the Candidate JSON blob, so
    # these query EvidenceRow directly by its composite (candidate_id, id)
    # primary key instead of searching a list on the in-memory Candidate.

    def add_evidence(
        self,
        text: str,
        source_context: str | None = None,
        experience_id: str | None = None,
        experience_project_id: str | None = None,
    ) -> Evidence:
        """Appended after any existing Evidence (position = max + 1). Does
        not cross-validate experience_id/experience_project_id against real
        Experience/ExperienceProject entries — same "no eager validation"
        stance Evidence.experience_id has always had (only checked later,
        at CV-assembly time; see update_skill()'s docstring for why
        evidence_ids links are treated differently)."""
        self._require_existing()
        if not text or not text.strip():
            raise ValidationError("Evidence text must not be empty.")

        entry = Evidence(
            id=_new_id(),
            text=text,
            source_context=source_context,
            experience_id=experience_id,
            experience_project_id=experience_project_id,
        )
        with session_scope(self._engine) as session:
            existing_positions = session.exec(
                select(EvidenceRow.position).where(EvidenceRow.candidate_id == self._candidate_id)
            ).all()
            position = (max(existing_positions) + 1) if existing_positions else 0
            session.add(
                EvidenceRow(
                    id=entry.id,
                    candidate_id=self._candidate_id,
                    position=position,
                    text=entry.text,
                    source_context=entry.source_context,
                    experience_id=entry.experience_id,
                    experience_project_id=entry.experience_project_id,
                )
            )
        return entry

    def update_evidence(self, evidence_id: str, **fields: Any) -> Evidence:
        with session_scope(self._engine) as session:
            row = session.get(EvidenceRow, (self._candidate_id, evidence_id))
            if row is None:
                raise ValidationError(f"Evidence with id {evidence_id!r} not found.")
            updated = Evidence.model_validate({**self._evidence_from_row(row).model_dump(), **fields})
            row.text = updated.text
            row.source_context = updated.source_context
            row.experience_id = updated.experience_id
            row.experience_project_id = updated.experience_project_id
            row.locked = updated.locked
            row.locked_text = updated.locked_text
            session.add(row)
        return updated

    def remove_evidence(self, evidence_id: str) -> None:
        """Deletes the Evidence item, then strips its id from any Skill/
        Technology.evidence_ids that reference it — the one place a
        dangling reference could otherwise appear, since evidence_ids is
        the only link pointing AT Evidence from elsewhere (Evidence's own
        experience_id points the other way, and is deliberately not
        cleaned up on Experience removal either — a pre-existing, unrelated
        gap this method doesn't also need to fix)."""
        with session_scope(self._engine) as session:
            row = session.get(EvidenceRow, (self._candidate_id, evidence_id))
            if row is None:
                raise ValidationError(f"Evidence with id {evidence_id!r} not found.")
            session.delete(row)

        self._strip_evidence_ids([evidence_id])

    # ----- CVDraft CRUD (Phase 20) ------------------------------------------
    # A persisted generate-and-refine session (domain.models.CVDraft's own
    # docstring). Lives in its own table (CVDraftRow, db/models.py) for the
    # same reason Evidence does — no relation to the Candidate JSON blob,
    # queried directly by its composite (candidate_id, id) primary key.

    def add_cv_draft(
        self,
        vacancy: Vacancy,
        assembled_cv: AssembledCV,
        document: PrintDocument,
        match_result: MatchResult | None = None,
        provenance: BulletProvenanceReport | None = None,
        timing: GenerationTiming | None = None,
    ) -> CVDraft:
        """Created once, right after a generate finishes — see the
        `CVDraft` docstring for why this is the *only* creation path (no
        separate "Save Draft" action): the phase's routed flow needs one
        persisted row per generate-and-refine session to survive
        navigation/refresh, and that row already *is* "a CV draft linked
        to a JD" — a second, independent save mechanism would just be two
        ways to make the same kind of row.

        `match_result`/`provenance`/`timing` are all optional (`None` for
        the "export without tailoring" path, which never calls the LLM) —
        persisted so a reopened tailored draft can still show its Gaps/
        AI-edit highlighting/generation timing, per `CVDraft`'s own
        docstring. `timing` must be accepted as an explicit parameter here
        (not just added to `CVDraft`/`CVDraftRow`) because
        `api/routes/entity_crud.py`'s generic factory builds this route's
        create-request schema from *this method's own signature*, not
        from the domain model — a field missing here is silently dropped
        from the request body before it ever reaches this method (found
        live: exactly what happened when `timing` was added to `CVDraft`/
        `CVDraftRow` without also adding it here)."""
        self._require_existing()
        now = datetime.now(timezone.utc)
        draft = CVDraft(
            id=_new_id(),
            candidate_id=self._candidate_id,
            vacancy=vacancy,
            assembled_cv=assembled_cv,
            document=document,
            match_result=match_result,
            provenance=provenance,
            timing=timing,
            created_at=now,
            updated_at=now,
        )
        with session_scope(self._engine) as session:
            session.add(
                CVDraftRow(
                    id=draft.id,
                    candidate_id=self._candidate_id,
                    vacancy=vacancy.model_dump(mode="json"),
                    assembled_cv=assembled_cv.model_dump(mode="json"),
                    document=document.model_dump(mode="json"),
                    match_result=match_result.model_dump(mode="json") if match_result is not None else None,
                    provenance=provenance.model_dump(mode="json") if provenance is not None else None,
                    timing=timing.model_dump(mode="json") if timing is not None else None,
                    created_at=now,
                    updated_at=now,
                )
            )
        return draft

    def update_cv_draft(self, draft_id: str, **fields: Any) -> CVDraft:
        """Generic partial-patch, same `**fields` merge-then-revalidate
        shape as `update_evidence` — this is what lets the frontend's
        debounced autosave be a plain `PUT {document: ...}` with no new
        mechanism. `updated_at` always refreshes, even if the caller also
        passed it (unlikely, but `fields` wins over nothing here only by
        omission — set last, deliberately)."""
        with session_scope(self._engine) as session:
            row = session.get(CVDraftRow, (self._candidate_id, draft_id))
            if row is None:
                raise ValidationError(f"CV draft with id {draft_id!r} not found.")
            updated = CVDraft.model_validate({**self._cv_draft_from_row(row).model_dump(), **fields})
            updated.updated_at = datetime.now(timezone.utc)
            row.vacancy = updated.vacancy.model_dump(mode="json")
            row.assembled_cv = updated.assembled_cv.model_dump(mode="json")
            row.document = updated.document.model_dump(mode="json")
            row.match_result = updated.match_result.model_dump(mode="json") if updated.match_result is not None else None
            row.provenance = updated.provenance.model_dump(mode="json") if updated.provenance is not None else None
            row.timing = updated.timing.model_dump(mode="json") if updated.timing is not None else None
            row.updated_at = updated.updated_at
            session.add(row)
        return updated

    def remove_cv_draft(self, draft_id: str) -> None:
        with session_scope(self._engine) as session:
            row = session.get(CVDraftRow, (self._candidate_id, draft_id))
            if row is None:
                raise ValidationError(f"CV draft with id {draft_id!r} not found.")
            session.delete(row)

    def list_cv_drafts(self) -> list[CVDraftSummary]:
        """Lightweight summaries only (domain.models.CVDraftSummary) — not
        the full vacancy/assembled_cv/document blobs, so listing stays
        cheap regardless of how large any one draft has grown. Most
        recently updated first, so the session someone was just editing
        is always at the top."""
        with session_scope(self._engine) as session:
            rows = session.exec(
                select(CVDraftRow)
                .where(CVDraftRow.candidate_id == self._candidate_id)
                .order_by(CVDraftRow.updated_at.desc())
            ).all()
            return [
                CVDraftSummary(
                    id=row.id,
                    vacancy_title=row.vacancy.get("title"),
                    vacancy_company=row.vacancy.get("company"),
                    created_at=_as_utc(row.created_at),
                    updated_at=_as_utc(row.updated_at),
                )
                for row in rows
            ]

    def get_cv_draft(self, draft_id: str) -> CVDraft | None:
        with session_scope(self._engine) as session:
            row = session.get(CVDraftRow, (self._candidate_id, draft_id))
            return self._cv_draft_from_row(row) if row is not None else None

    @staticmethod
    def _cv_draft_from_row(row: CVDraftRow) -> CVDraft:
        return CVDraft(
            id=row.id,
            candidate_id=row.candidate_id,
            vacancy=Vacancy.model_validate(row.vacancy),
            assembled_cv=AssembledCV.model_validate(row.assembled_cv),
            document=PrintDocument.model_validate(row.document),
            match_result=MatchResult.model_validate(row.match_result) if row.match_result is not None else None,
            provenance=(
                BulletProvenanceReport.model_validate(row.provenance) if row.provenance is not None else None
            ),
            timing=GenerationTiming.model_validate(row.timing) if row.timing is not None else None,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
        )

    def reorder_entities(self, list_field: str, ordered_ids: list[str]) -> list[Any]:
        """Generic reorder for any of the 11 flat Candidate list fields
        (skills, technologies, education, ...) — the same "one factory
        instead of eleven near-duplicate handlers" precedent
        api/routes/entity_crud.py already set for create/update/remove,
        now for reordering. Deliberately NOT used for `experience`
        (its own nested Projects/bullets reorder as part of one atomic
        role save, ExperienceForm.tsx — a different mechanism already
        covers it) or `evidence`/CVDraft (neither lives in this JSON blob
        at all, so there's no Candidate attribute for `getattr` to find).

        `ordered_ids` only has to name the ids whose *relative* order
        changed — any existing item missing from it (a stale client, a
        concurrent add racing this request) is appended at the end in its
        prior relative order rather than silently dropped, same
        fail-safe precedent app/cv_assembler.py's `_rank_by_category`
        already set for an unrecognized name.
        """
        candidate = self._require_existing()
        items = getattr(candidate, list_field)
        by_id = {item.id: item for item in items}
        wanted = set(ordered_ids)
        reordered = [by_id[item_id] for item_id in ordered_ids if item_id in by_id]
        remaining = [item for item in items if item.id not in wanted]
        setattr(candidate, list_field, reordered + remaining)
        self._save(candidate)
        return getattr(candidate, list_field)

    def update(self, **fields: Any) -> Candidate:
        """Patch top-level profile fields (name, headline, summary). For
        `contacts`, prefer add_contact()/update_contact()/remove_contact() —
        passing `contacts=[...]` here replaces the whole list wholesale."""
        candidate = self._require_existing()
        merged = candidate.model_dump()
        merged.update(fields)
        updated = Candidate.model_validate(merged)  # re-validates the full model
        if not updated.name or not updated.name.strip():
            raise ValidationError("Candidate name must not be empty.")
        self._save(updated)
        return updated

    def delete(self) -> bool:
        with session_scope(self._engine) as session:
            row = session.get(CandidateRow, self._candidate_id)
            if row is None:
                return False
            session.delete(row)  # EvidenceRow cascade — see db/engine.py's FK pragma
            return True

    # ----- Experience CRUD ----------------------------------------------

    def add_experience(
        self,
        *,
        position: str,
        company: str | None = None,
        company_url: str | None = None,
        period: str | None = None,
        location: str | None = None,
        responsibilities: list[str] | None = None,
        achievements: list[str] | None = None,
        is_gap: bool = False,
    ) -> Experience:
        candidate = self._require_existing()
        if not position or not position.strip():
            raise ValidationError("Experience position must not be empty.")
        if not is_gap and (not company or not company.strip()):
            raise ValidationError(
                "Experience company must not be empty (unless is_gap=True)."
            )

        entry = Experience(
            id=_new_id(),
            company=company,
            company_url=company_url,
            position=position,
            period=period,
            location=location,
            responsibilities=list(responsibilities or []),
            achievements=list(achievements or []),
            is_gap=is_gap,
        )
        candidate.experience.append(entry)
        self._save(candidate)
        if entry.responsibilities or entry.achievements:
            with session_scope(self._engine) as session:
                self._sync_evidence_for_scope(
                    session, entry.id, None, [*entry.responsibilities, *entry.achievements]
                )
        return entry

    def update_experience(self, experience_id: str, **fields: Any) -> Experience:
        candidate = self._require_existing()
        index, entry = self._find(candidate.experience, experience_id, "Experience")
        updated = entry.model_copy(update=fields)
        # Re-validate the merged entry rather than trusting model_copy alone.
        updated = Experience.model_validate(updated.model_dump())
        candidate.experience[index] = updated
        self._save(candidate)

        # Keep Evidence in sync with whatever bullet text this call just
        # persisted — see _sync_evidence_for_scope's docstring. Scoped to
        # only the fields actually sent: a PATCH-style partial update that
        # never touched achievements/responsibilities/projects shouldn't
        # pay for a no-op reconciliation pass.
        if "achievements" in fields or "responsibilities" in fields or "projects" in fields:
            removed_ids: list[str] = []
            with session_scope(self._engine) as session:
                if "achievements" in fields or "responsibilities" in fields:
                    removed_ids += self._sync_evidence_for_scope(
                        session, experience_id, None,
                        [*updated.responsibilities, *updated.achievements],
                    )
                if "projects" in fields:
                    # A project dropped from this Experience (deleted, or
                    # blanked-out — see ExperienceForm.tsx's
                    # toExperienceRequestBody, which already reassigns its
                    # bullets to role-level before this call ever sees
                    # them) no longer owns any bullets; wipe its Evidence
                    # outright rather than leave it orphaned under a
                    # project id nothing points to anymore.
                    new_project_ids = {project.id for project in updated.projects}
                    for stale_id in {project.id for project in entry.projects} - new_project_ids:
                        removed_ids += self._sync_evidence_for_scope(session, experience_id, stale_id, [])
                    for project in updated.projects:
                        removed_ids += self._sync_evidence_for_scope(
                            session, experience_id, project.id,
                            [*project.responsibilities, *project.achievements],
                        )
            self._strip_evidence_ids(removed_ids)
        return updated

    def remove_experience(self, experience_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.experience, experience_id, "Experience")  # raises if missing
        candidate.experience = [
            e for e in candidate.experience if e.id != experience_id
        ]
        self._save(candidate)

    # ----- Experience Project CRUD (nested inside one Experience entry) --
    # For roles structured company -> project -> dates -> bullets rather
    # than a flat bullet list — see domain.models.ExperienceProject.

    def add_experience_project(
        self,
        experience_id: str,
        name: str,
        period: str | None = None,
        achievements: list[str] | None = None,
        url: str | None = None,
    ) -> ExperienceProject:
        candidate = self._require_existing()
        index, entry = self._find(candidate.experience, experience_id, "Experience")
        if not name or not name.strip():
            raise ValidationError("Experience project name must not be empty.")

        project = ExperienceProject(
            id=_new_id(), name=name, period=period, achievements=list(achievements or []), url=url
        )
        candidate.experience[index] = entry.model_copy(
            update={"projects": [*entry.projects, project]}
        )
        self._save(candidate)
        if project.responsibilities or project.achievements:
            with session_scope(self._engine) as session:
                self._sync_evidence_for_scope(
                    session, experience_id, project.id,
                    [*project.responsibilities, *project.achievements],
                )
        return project

    def update_experience_project(
        self, experience_id: str, project_id: str, **fields: Any
    ) -> ExperienceProject:
        candidate = self._require_existing()
        index, entry = self._find(candidate.experience, experience_id, "Experience")
        project_index, project = self._find(entry.projects, project_id, "Experience project")

        updated_project = ExperienceProject.model_validate({**project.model_dump(), **fields})
        new_projects = list(entry.projects)
        new_projects[project_index] = updated_project
        candidate.experience[index] = entry.model_copy(update={"projects": new_projects})
        self._save(candidate)

        if "achievements" in fields or "responsibilities" in fields:
            with session_scope(self._engine) as session:
                removed_ids = self._sync_evidence_for_scope(
                    session, experience_id, project_id,
                    [*updated_project.responsibilities, *updated_project.achievements],
                )
            self._strip_evidence_ids(removed_ids)
        return updated_project

    def remove_experience_project(self, experience_id: str, project_id: str) -> None:
        candidate = self._require_existing()
        index, entry = self._find(candidate.experience, experience_id, "Experience")
        self._find(entry.projects, project_id, "Experience project")  # raises if missing

        new_projects = [p for p in entry.projects if p.id != project_id]
        candidate.experience[index] = entry.model_copy(update={"projects": new_projects})
        self._save(candidate)

    # ----- Volunteer Experience CRUD --------------------------------------

    def add_volunteer_experience(
        self,
        organization: str,
        role: str,
        period: str | None = None,
        description: str | None = None,
    ) -> VolunteerExperience:
        candidate = self._require_existing()
        if not organization or not organization.strip():
            raise ValidationError("Volunteer experience organization must not be empty.")
        if not role or not role.strip():
            raise ValidationError("Volunteer experience role must not be empty.")

        entry = VolunteerExperience(
            id=_new_id(), organization=organization, role=role, period=period, description=description
        )
        candidate.volunteer_experience.append(entry)
        self._save(candidate)
        return entry

    def update_volunteer_experience(self, volunteer_experience_id: str, **fields: Any) -> VolunteerExperience:
        candidate = self._require_existing()
        index, entry = self._find(
            candidate.volunteer_experience, volunteer_experience_id, "Volunteer experience"
        )
        updated = VolunteerExperience.model_validate({**entry.model_dump(), **fields})
        candidate.volunteer_experience[index] = updated
        self._save(candidate)
        return updated

    def remove_volunteer_experience(self, volunteer_experience_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.volunteer_experience, volunteer_experience_id, "Volunteer experience")
        candidate.volunteer_experience = [
            v for v in candidate.volunteer_experience if v.id != volunteer_experience_id
        ]
        self._save(candidate)

    # ----- Education CRUD -------------------------------------------------

    def add_education(
        self,
        institution: str,
        degree: str | None = None,
        field: str | None = None,
        period: str | None = None,
    ) -> Education:
        candidate = self._require_existing()
        if not institution or not institution.strip():
            raise ValidationError("Education institution must not be empty.")

        entry = Education(
            id=_new_id(), institution=institution, degree=degree, field=field, period=period
        )
        candidate.education.append(entry)
        self._save(candidate)
        return entry

    def update_education(self, education_id: str, **fields: Any) -> Education:
        candidate = self._require_existing()
        index, entry = self._find(candidate.education, education_id, "Education")
        updated = Education.model_validate({**entry.model_dump(), **fields})
        candidate.education[index] = updated
        self._save(candidate)
        return updated

    def remove_education(self, education_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.education, education_id, "Education")
        candidate.education = [e for e in candidate.education if e.id != education_id]
        self._save(candidate)

    # ----- Skill CRUD -------------------------------------------------

    def add_skill(
        self,
        name: str,
        category: str | None = None,
        proficiency: str | None = None,
        is_category_header: bool = False,
    ) -> Skill:
        candidate = self._require_existing()
        if not name or not name.strip():
            raise ValidationError("Skill name must not be empty.")

        entry = Skill(
            id=_new_id(),
            name=name,
            category=category,
            proficiency=proficiency,
            is_category_header=is_category_header,
        )
        candidate.skills.append(entry)
        self._save(candidate)
        return entry

    def update_skill(self, skill_id: str, **fields: Any) -> Skill:
        """Setting `evidence_ids` here is the "manual linking" path Phase
        15 adds (ingestion sets it automatically instead, via replace()) —
        unlike Evidence.experience_id, which is never cross-validated at
        write time (see add_evidence()'s docstring), this DOES validate:
        it's the one explicit "link this skill to that evidence" action a
        person takes, so rejecting a typo'd/stale id here beats silently
        accepting a dangling reference nothing else will ever catch."""
        candidate = self._require_existing()
        index, entry = self._find(candidate.skills, skill_id, "Skill")
        if "evidence_ids" in fields:
            self._validate_evidence_ids(fields["evidence_ids"])
        updated = Skill.model_validate({**entry.model_dump(), **fields})
        candidate.skills[index] = updated
        self._save(candidate)
        return updated

    def remove_skill(self, skill_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.skills, skill_id, "Skill")
        candidate.skills = [s for s in candidate.skills if s.id != skill_id]
        self._save(candidate)

    # ----- Technology CRUD -----------------------------------------------

    def add_technology(
        self,
        name: str,
        category: str | None = None,
        proficiency: str | None = None,
        is_category_header: bool = False,
    ) -> Technology:
        candidate = self._require_existing()
        if not name or not name.strip():
            raise ValidationError("Technology name must not be empty.")

        entry = Technology(
            id=_new_id(),
            name=name,
            category=category,
            proficiency=proficiency,
            is_category_header=is_category_header,
        )
        candidate.technologies.append(entry)
        self._save(candidate)
        return entry

    def update_technology(self, technology_id: str, **fields: Any) -> Technology:
        """See update_skill()'s docstring — same evidence_ids validation,
        same reasoning."""
        candidate = self._require_existing()
        index, entry = self._find(candidate.technologies, technology_id, "Technology")
        if "evidence_ids" in fields:
            self._validate_evidence_ids(fields["evidence_ids"])
        updated = Technology.model_validate({**entry.model_dump(), **fields})
        candidate.technologies[index] = updated
        self._save(candidate)
        return updated

    def remove_technology(self, technology_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.technologies, technology_id, "Technology")
        candidate.technologies = [t for t in candidate.technologies if t.id != technology_id]
        self._save(candidate)

    # ----- Language CRUD -------------------------------------------------

    def add_language(self, name: str, proficiency: str | None = None) -> Language:
        candidate = self._require_existing()
        if not name or not name.strip():
            raise ValidationError("Language name must not be empty.")

        entry = Language(id=_new_id(), name=name, proficiency=proficiency)
        candidate.languages.append(entry)
        self._save(candidate)
        return entry

    def update_language(self, language_id: str, **fields: Any) -> Language:
        candidate = self._require_existing()
        index, entry = self._find(candidate.languages, language_id, "Language")
        updated = Language.model_validate({**entry.model_dump(), **fields})
        candidate.languages[index] = updated
        self._save(candidate)
        return updated

    def remove_language(self, language_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.languages, language_id, "Language")
        candidate.languages = [lang for lang in candidate.languages if lang.id != language_id]
        self._save(candidate)

    # ----- Certification CRUD ---------------------------------------------

    def add_certification(
        self, name: str, issuer: str | None = None, date: str | None = None
    ) -> Certification:
        candidate = self._require_existing()
        if not name or not name.strip():
            raise ValidationError("Certification name must not be empty.")

        entry = Certification(id=_new_id(), name=name, issuer=issuer, date=date)
        candidate.certifications.append(entry)
        self._save(candidate)
        return entry

    def update_certification(self, certification_id: str, **fields: Any) -> Certification:
        candidate = self._require_existing()
        index, entry = self._find(candidate.certifications, certification_id, "Certification")
        updated = Certification.model_validate({**entry.model_dump(), **fields})
        candidate.certifications[index] = updated
        self._save(candidate)
        return updated

    def remove_certification(self, certification_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.certifications, certification_id, "Certification")
        candidate.certifications = [
            c for c in candidate.certifications if c.id != certification_id
        ]
        self._save(candidate)

    # ----- Award CRUD -------------------------------------------------

    def add_award(self, name: str, issuer: str | None = None, date: str | None = None) -> Award:
        candidate = self._require_existing()
        if not name or not name.strip():
            raise ValidationError("Award name must not be empty.")

        entry = Award(id=_new_id(), name=name, issuer=issuer, date=date)
        candidate.awards.append(entry)
        self._save(candidate)
        return entry

    def update_award(self, award_id: str, **fields: Any) -> Award:
        candidate = self._require_existing()
        index, entry = self._find(candidate.awards, award_id, "Award")
        updated = Award.model_validate({**entry.model_dump(), **fields})
        candidate.awards[index] = updated
        self._save(candidate)
        return updated

    def remove_award(self, award_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.awards, award_id, "Award")
        candidate.awards = [a for a in candidate.awards if a.id != award_id]
        self._save(candidate)

    # ----- Contact CRUD -----------------------------------------------

    def add_contact(self, label: str, value: str) -> ContactItem:
        """Add one labeled contact/identity item (Email, Phone, LinkedIn,
        Location, Work Authorization, Portfolio, GitHub, ...). See
        domain.models.ContactItem's docstring for why this is a flexible
        label+value pair rather than named fields."""
        candidate = self._require_existing()
        if not label or not label.strip():
            raise ValidationError("Contact label must not be empty.")
        if not value or not value.strip():
            raise ValidationError("Contact value must not be empty.")

        entry = ContactItem(id=_new_id(), label=label, value=value)
        candidate.contacts.append(entry)
        self._save(candidate)
        return entry

    def update_contact(self, contact_id: str, **fields: Any) -> ContactItem:
        candidate = self._require_existing()
        index, entry = self._find(candidate.contacts, contact_id, "Contact")
        updated = ContactItem.model_validate({**entry.model_dump(), **fields})
        candidate.contacts[index] = updated
        self._save(candidate)
        return updated

    def remove_contact(self, contact_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.contacts, contact_id, "Contact")
        candidate.contacts = [c for c in candidate.contacts if c.id != contact_id]
        self._save(candidate)

    # ----- Project CRUD -------------------------------------------------

    def add_project(
        self, name: str, description: str | None = None, url: str | None = None
    ) -> Project:
        candidate = self._require_existing()
        if not name or not name.strip():
            raise ValidationError("Project name must not be empty.")

        entry = Project(id=_new_id(), name=name, description=description, url=url)
        candidate.projects.append(entry)
        self._save(candidate)
        return entry

    def update_project(self, project_id: str, **fields: Any) -> Project:
        candidate = self._require_existing()
        index, entry = self._find(candidate.projects, project_id, "Project")
        updated = Project.model_validate({**entry.model_dump(), **fields})
        candidate.projects[index] = updated
        self._save(candidate)
        return updated

    def remove_project(self, project_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.projects, project_id, "Project")
        candidate.projects = [p for p in candidate.projects if p.id != project_id]
        self._save(candidate)

    # ----- Publication CRUD -----------------------------------------------

    def add_publication(
        self,
        title: str,
        venue: str | None = None,
        date: str | None = None,
        url: str | None = None,
    ) -> Publication:
        candidate = self._require_existing()
        if not title or not title.strip():
            raise ValidationError("Publication title must not be empty.")

        entry = Publication(id=_new_id(), title=title, venue=venue, date=date, url=url)
        candidate.publications.append(entry)
        self._save(candidate)
        return entry

    def update_publication(self, publication_id: str, **fields: Any) -> Publication:
        candidate = self._require_existing()
        index, entry = self._find(candidate.publications, publication_id, "Publication")
        updated = Publication.model_validate({**entry.model_dump(), **fields})
        candidate.publications[index] = updated
        self._save(candidate)
        return updated

    def remove_publication(self, publication_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.publications, publication_id, "Publication")
        candidate.publications = [p for p in candidate.publications if p.id != publication_id]
        self._save(candidate)

    # ----- Portfolio Link CRUD -------------------------------------------

    def add_portfolio_link(self, url: str, description: str | None = None) -> PortfolioLink:
        candidate = self._require_existing()
        if not url or not url.strip():
            raise ValidationError("Portfolio link URL must not be empty.")

        entry = PortfolioLink(id=_new_id(), url=url, description=description)
        candidate.portfolio_links.append(entry)
        self._save(candidate)
        return entry

    def update_portfolio_link(self, portfolio_link_id: str, **fields: Any) -> PortfolioLink:
        candidate = self._require_existing()
        index, entry = self._find(candidate.portfolio_links, portfolio_link_id, "Portfolio link")
        updated = PortfolioLink.model_validate({**entry.model_dump(), **fields})
        candidate.portfolio_links[index] = updated
        self._save(candidate)
        return updated

    def remove_portfolio_link(self, portfolio_link_id: str) -> None:
        candidate = self._require_existing()
        self._find(candidate.portfolio_links, portfolio_link_id, "Portfolio link")
        candidate.portfolio_links = [
            p for p in candidate.portfolio_links if p.id != portfolio_link_id
        ]
        self._save(candidate)

    # ----- storage helpers ------------------------------------------------

    def _validate_evidence_ids(self, evidence_ids: list[str]) -> None:
        if not evidence_ids:
            return
        with session_scope(self._engine) as session:
            existing_ids = set(
                session.exec(
                    select(EvidenceRow.id).where(EvidenceRow.candidate_id == self._candidate_id)
                ).all()
            )
        missing = [eid for eid in evidence_ids if eid not in existing_ids]
        if missing:
            raise ValidationError(f"Evidence id(s) not found: {', '.join(missing)}")

    def _upsert_candidate_row(self, session: Session, candidate: Candidate) -> None:
        row = session.get(CandidateRow, self._candidate_id)
        now = datetime.now(timezone.utc)
        if row is None:
            row = CandidateRow(
                id=self._candidate_id,
                data=candidate.model_dump(mode="json"),
                created_at=now,
                updated_at=now,
            )
        else:
            row.data = candidate.model_dump(mode="json")
            row.updated_at = now
        session.add(row)

    def _save(self, candidate: Candidate) -> None:
        with session_scope(self._engine) as session:
            self._upsert_candidate_row(session, candidate)

    def _replace_evidence_rows(self, session: Session, evidence: list[Evidence]) -> None:
        session.execute(delete(EvidenceRow).where(EvidenceRow.candidate_id == self._candidate_id))
        for position, item in enumerate(evidence):
            session.add(
                EvidenceRow(
                    id=item.id,
                    candidate_id=self._candidate_id,
                    position=position,
                    text=item.text,
                    source_context=item.source_context,
                    experience_id=item.experience_id,
                    experience_project_id=item.experience_project_id,
                    locked=item.locked,
                    locked_text=item.locked_text,
                )
            )

    def _strip_evidence_ids(self, evidence_ids: list[str]) -> None:
        """Removes the given ids from every Skill/Technology.evidence_ids
        that references one — shared by remove_evidence() and
        _sync_evidence_for_scope()'s callers, both of which can delete
        EvidenceRow(s) that something else still points at."""
        if not evidence_ids:
            return
        ids = set(evidence_ids)
        candidate = self._require_existing()
        changed = False
        for skill in candidate.skills:
            if any(eid in ids for eid in skill.evidence_ids):
                skill.evidence_ids = [eid for eid in skill.evidence_ids if eid not in ids]
                changed = True
        for technology in candidate.technologies:
            if any(eid in ids for eid in technology.evidence_ids):
                technology.evidence_ids = [eid for eid in technology.evidence_ids if eid not in ids]
                changed = True
        if changed:
            self._save(candidate)

    def _sync_evidence_for_scope(
        self,
        session: Session,
        experience_id: str,
        experience_project_id: str | None,
        new_texts: list[str],
    ) -> list[str]:
        """Reconciles the EvidenceRow(s) for one (experience_id,
        experience_project_id) scope to match `new_texts` — the
        role's/project's freshly-saved achievements + responsibilities —
        so a manual profile edit is reflected immediately in the read-only
        Evidence panel (ExperienceEvidencePanel.tsx) and in every future CV
        generate, instead of only the Edit form itself seeing it (see
        docs/domain-model.md's note, above, that these two layers
        otherwise don't sync).

        Matches by exact text so an unchanged bullet keeps its existing
        row's id — and therefore its locked/locked_text and any
        Skill/Technology.evidence_ids link — untouched. A bullet whose text
        actually changed is *not* treated as "the same bullet reworded": it
        surfaces as one delete + one add, same as removing an old bullet
        and typing a new one, which is the correct behavior since a
        locked_text or evidence_ids link made for the old wording has no
        reason to carry over to unrelated new wording. Returns the ids of
        any rows deleted, for the caller to also strip from
        Skill/Technology.evidence_ids (this method only touches
        EvidenceRow; it does not touch the Candidate JSON blob).
        """
        existing = session.exec(
            select(EvidenceRow)
            .where(EvidenceRow.candidate_id == self._candidate_id)
            .where(EvidenceRow.experience_id == experience_id)
            .where(EvidenceRow.experience_project_id == experience_project_id)
            .order_by(EvidenceRow.position)
        ).all()
        unmatched = list(existing)
        for text in new_texts:
            match = next((row for row in unmatched if row.text == text), None)
            if match is not None:
                unmatched.remove(match)
                continue
            existing_positions = session.exec(
                select(EvidenceRow.position).where(EvidenceRow.candidate_id == self._candidate_id)
            ).all()
            position = (max(existing_positions) + 1) if existing_positions else 0
            session.add(
                EvidenceRow(
                    id=_new_id(),
                    candidate_id=self._candidate_id,
                    position=position,
                    text=text,
                    experience_id=experience_id,
                    experience_project_id=experience_project_id,
                )
            )
        removed_ids = [row.id for row in unmatched]
        for row in unmatched:
            session.delete(row)
        return removed_ids

    @staticmethod
    def _evidence_from_row(row: EvidenceRow) -> Evidence:
        return Evidence(
            id=row.id,
            text=row.text,
            source_context=row.source_context,
            experience_id=row.experience_id,
            experience_project_id=row.experience_project_id,
            locked=row.locked,
            locked_text=row.locked_text,
        )

    # ----- helpers -----------------------------------------------------

    def _require_existing(self) -> Candidate:
        candidate = self.get()
        if candidate is None:
            raise ValidationError("No candidate profile exists yet; call create() first.")
        return candidate

    @staticmethod
    def _find(items: list[Any], item_id: str, label: str) -> tuple[int, Any]:
        for index, item in enumerate(items):
            if item.id == item_id:
                return index, item
        raise ValidationError(f"{label} with id {item_id!r} not found.")
