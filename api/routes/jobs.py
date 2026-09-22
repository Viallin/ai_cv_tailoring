"""POST /jobs + GET /jobs/{id} — in-process async job execution.

Replaces ui/main_window.py's _CallableWorker(QThread) pattern for the web
API: run_resume_ingestion()/run_cv_generation() are fully synchronous
(blocking LLM SDK calls), so asyncio's run_in_executor (default
ThreadPoolExecutor) is the async-native equivalent of _CallableWorker's
QThread — get blocking work off the thread handling the HTTP request,
same two-tier `except AppError / except Exception` catch shape as
_CallableWorker.run().

Job state lives in an in-memory dict guarded by a threading.Lock — no
Celery/Redis, per docs/technology_stack.md's single-user/local scope for
this phase. Lost on process restart: job records are ephemeral
orchestration metadata, not user data (Candidate/Evidence, which do need to
survive a restart, live in SQLite instead — see db/models.py).
"""

from __future__ import annotations

import asyncio
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, Union

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field

import app.errors as app_errors
from api.deps import get_services
from app.pipeline import (
    run_cv_generation,
    run_gap_recheck,
    run_resume_ingestion,
    run_skill_evidence_relink,
)
from app.resume_reader import read_resume_text
from app.services import Services
from domain.models import (
    AssembledCV,
    BulletProvenanceReport,
    Candidate,
    GenerationTiming,
    MatchResult,
    Requirement,
    Vacancy,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


class IngestJobRequest(BaseModel):
    type: Literal["ingest"] = "ingest"
    resume_text: str


class GenerateJobRequest(BaseModel):
    type: Literal["generate"] = "generate"
    candidate_id: str
    vacancy_text: str
    # A Regenerate/Regenerate as New on an existing CVDraft already has this
    # draft's own previously-parsed Vacancy on hand — passing it lets
    # run_cv_generation skip re-running the JD Parser stage entirely when
    # `vacancy_text` is unchanged from `existing_vacancy.raw_text` (the
    # common case: re-tailoring against the same job description, not a
    # new/edited one). `None` for a first-time generate (ExportScreen.tsx's
    # "Tailor CV to Job Description" — no prior parse exists yet).
    existing_vacancy: Vacancy | None = None


class RecheckJobRequest(BaseModel):
    type: Literal["recheck"] = "recheck"
    candidate_id: str
    requirements: list[Requirement]
    # Ids of Evidence items whose bullet the user has since toggled off in
    # the A4 editor.
    excluded_evidence_ids: list[str] = Field(default_factory=list)
    # The four fields below carry the document's own current content into
    # the recheck — see run_gap_recheck's docstring for the full reasoning
    # and frontend/src/lib/documentEvidence.ts /
    # frontend/src/lib/structuredDocument.ts for how the frontend builds
    # them from the live `DocumentModel` right before calling this route.
    edited_bullet_text: dict[str, str] = Field(default_factory=dict)
    manual_bullet_text: list[str] = Field(default_factory=list)
    document_skills: list[str] | None = None
    document_technologies: list[str] | None = None


class RelinkSkillEvidenceJobRequest(BaseModel):
    type: Literal["relink_skill_evidence"] = "relink_skill_evidence"
    candidate_id: str


JobRequest = Annotated[
    Union[IngestJobRequest, GenerateJobRequest, RecheckJobRequest, RelinkSkillEvidenceJobRequest],
    Field(discriminator="type"),
]


class IngestJobResult(BaseModel):
    candidate_id: str
    candidate: Candidate


class GenerateJobResult(BaseModel):
    vacancy: Vacancy
    match_result: MatchResult
    assembled_cv: AssembledCV
    provenance: BulletProvenanceReport
    timing: GenerationTiming


class RecheckJobResult(BaseModel):
    match_result: MatchResult


class RelinkSkillEvidenceJobResult(BaseModel):
    updated_skill_count: int
    updated_technology_count: int


class JobErrorBody(BaseModel):
    category: str
    message: str


class JobStatus(BaseModel):
    id: str
    type: Literal["ingest", "generate", "recheck", "relink_skill_evidence"]
    status: Literal["pending", "running", "succeeded", "failed"] = "pending"
    # Progress within a "generate" job's six-stage chain (app/pipeline.py's
    # GENERATION_STAGES) — `None` for every other job type, and for
    # "generate" itself until the first stage actually starts (there's a
    # real, if usually brief, gap between this record's creation and
    # _execute_generate picking it up from the executor). Frontend polling
    # is already 1s (useJobPolling), same cadence a stage takes at minimum,
    # so this is cheap to add and doesn't need its own faster poll.
    stage: str | None = None
    stage_number: int | None = None
    stage_count: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    result: IngestJobResult | GenerateJobResult | RecheckJobResult | RelinkSkillEvidenceJobResult | None = None
    error: JobErrorBody | None = None


_jobs: dict[str, JobStatus] = {}
_jobs_lock = threading.Lock()


def _execute_ingest(job_id: str, request: IngestJobRequest, services: Services) -> None:
    with _jobs_lock:
        _jobs[job_id].status = "running"
    try:
        candidate_id, candidate = run_resume_ingestion(request.resume_text, services)
    except app_errors.AppError as exc:
        _set_failed(job_id, exc)
        return
    except Exception as exc:  # noqa: BLE001 — mirrors _CallableWorker's last-resort catch
        _set_failed(job_id, exc)
        return
    _set_succeeded(job_id, IngestJobResult(candidate_id=candidate_id, candidate=candidate))


def _report_stage(job_id: str, label: str, number: int, count: int) -> None:
    with _jobs_lock:
        record = _jobs.get(job_id)
        if record is not None:
            record.stage = label
            record.stage_number = number
            record.stage_count = count


def _execute_generate(job_id: str, request: GenerateJobRequest, services: Services) -> None:
    with _jobs_lock:
        _jobs[job_id].status = "running"
    try:
        service = services.candidate_registry.service_for(request.candidate_id)
        candidate = service.get()
        if candidate is None:
            raise app_errors.ValidationError(f"Candidate {request.candidate_id!r} not found.")
        evidence = service.get_evidence()
        result = run_cv_generation(
            candidate,
            evidence,
            request.vacancy_text,
            services,
            existing_vacancy=request.existing_vacancy,
            on_stage=lambda label, number, count: _report_stage(job_id, label, number, count),
        )
    except app_errors.AppError as exc:
        _set_failed(job_id, exc)
        return
    except Exception as exc:  # noqa: BLE001
        _set_failed(job_id, exc)
        return
    _set_succeeded(
        job_id,
        GenerateJobResult(
            vacancy=result.vacancy,
            match_result=result.match_result,
            assembled_cv=result.assembled_cv,
            provenance=result.provenance,
            timing=result.timing,
        ),
    )


def _execute_recheck(job_id: str, request: RecheckJobRequest, services: Services) -> None:
    with _jobs_lock:
        _jobs[job_id].status = "running"
    try:
        service = services.candidate_registry.service_for(request.candidate_id)
        candidate = service.get()
        if candidate is None:
            raise app_errors.ValidationError(f"Candidate {request.candidate_id!r} not found.")
        evidence = service.get_evidence()
        match_result = run_gap_recheck(
            candidate,
            evidence,
            request.requirements,
            set(request.excluded_evidence_ids),
            services,
            edited_bullet_text=request.edited_bullet_text,
            manual_bullet_text=request.manual_bullet_text,
            document_skills=request.document_skills,
            document_technologies=request.document_technologies,
        )
    except app_errors.AppError as exc:
        _set_failed(job_id, exc)
        return
    except Exception as exc:  # noqa: BLE001
        _set_failed(job_id, exc)
        return
    _set_succeeded(job_id, RecheckJobResult(match_result=match_result))


def _execute_relink_skill_evidence(
    job_id: str, request: RelinkSkillEvidenceJobRequest, services: Services
) -> None:
    with _jobs_lock:
        _jobs[job_id].status = "running"
    try:
        service = services.candidate_registry.service_for(request.candidate_id)
        candidate = service.get()
        if candidate is None:
            raise app_errors.ValidationError(f"Candidate {request.candidate_id!r} not found.")
        evidence = service.get_evidence()
        skill_count, technology_count = run_skill_evidence_relink(service, candidate, evidence, services)
    except app_errors.AppError as exc:
        _set_failed(job_id, exc)
        return
    except Exception as exc:  # noqa: BLE001
        _set_failed(job_id, exc)
        return
    _set_succeeded(
        job_id,
        RelinkSkillEvidenceJobResult(updated_skill_count=skill_count, updated_technology_count=technology_count),
    )


def _set_succeeded(
    job_id: str,
    result: IngestJobResult | GenerateJobResult | RecheckJobResult | RelinkSkillEvidenceJobResult,
) -> None:
    with _jobs_lock:
        record = _jobs[job_id]
        record.status = "succeeded"
        record.result = result
        record.finished_at = datetime.now(timezone.utc)


def _set_failed(job_id: str, exc: Exception) -> None:
    with _jobs_lock:
        record = _jobs[job_id]
        record.status = "failed"
        record.error = JobErrorBody(category=type(exc).__name__, message=str(exc))
        record.finished_at = datetime.now(timezone.utc)


@router.post("", status_code=202)
async def create_job(request: JobRequest, services: Services = Depends(get_services)) -> JobStatus:
    job_id = uuid.uuid4().hex[:8]
    with _jobs_lock:
        _jobs[job_id] = JobStatus(id=job_id, type=request.type)

    loop = asyncio.get_event_loop()
    if isinstance(request, IngestJobRequest):
        loop.run_in_executor(None, _execute_ingest, job_id, request, services)
    elif isinstance(request, GenerateJobRequest):
        loop.run_in_executor(None, _execute_generate, job_id, request, services)
    elif isinstance(request, RecheckJobRequest):
        loop.run_in_executor(None, _execute_recheck, job_id, request, services)
    else:
        loop.run_in_executor(None, _execute_relink_skill_evidence, job_id, request, services)

    with _jobs_lock:
        return _jobs[job_id]


@router.post("/ingest-upload", status_code=202)
async def create_ingest_upload_job(
    file: UploadFile, services: Services = Depends(get_services)
) -> JobStatus:
    """Multipart-upload counterpart to `POST /jobs {"type": "ingest", ...}`
    (Version 4, Phase 4.5) — the frontend's paste-a-resume box gets a
    file-upload alternative, not a parallel ingestion pipeline. Extraction
    (app/resume_reader.py's PDF/DOCX/RTF/TXT/MD dispatch) runs against a
    temp copy of the upload, off the event loop via `run_in_executor` —
    same reasoning as every other blocking call in this file (see the
    module docstring), not just the LLM-calling ones: `pypdf.extract_text()`
    is normally milliseconds, but a pathological file (a huge embedded
    image, a deeply nested object graph) could take a while, and running it
    in-request on the event loop directly (as this used to) would block
    every other request the whole server is handling for that long, not
    just this one — worse than a slow upload, indistinguishable from the
    app itself going unresponsive. An unsupported type, unreadable file, or
    empty extraction raises ParsingError, which propagates out of
    run_in_executor's awaited future same as a synchronous raise would;
    api/errors.py's handler turns it into an immediate error response —
    that's a request-validation problem, not something that fails mid-
    LLM-call the way a genuine ingestion failure does, so it's surfaced
    before a job record even exists rather than as a "failed" job. Once
    extraction succeeds, this hands off to create_job() unchanged — same
    job id/polling/result shape a pasted-text ingest gets.
    """
    suffix = Path(file.filename or "").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = Path(tmp.name)
    try:
        loop = asyncio.get_event_loop()
        resume_text = await loop.run_in_executor(None, read_resume_text, tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return await create_job(IngestJobRequest(resume_text=resume_text), services)


@router.get("/{job_id}")
async def get_job(job_id: str) -> JobStatus:
    with _jobs_lock:
        record = _jobs.get(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found.")
    return record
