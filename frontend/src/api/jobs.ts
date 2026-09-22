// Ingest and generate are both POST /jobs { type, ... } -> poll GET
// /jobs/{id} until a terminal status — the async-native equivalent of
// ui/main_window.py's _CallableWorker(QThread) pattern. useJobPolling is
// the one genuinely nontrivial piece, shared by both purpose-built hooks
// below so IngestPanel/VacancyPanel+GenerateButton don't each have to
// discriminate the JobStatus.result union by hand.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ApiError, apiFetch, apiFetchUpload } from "./client";
import type {
  GenerateJobResult,
  IngestJobResult,
  JobErrorBody,
  JobStatus,
  RecheckJobResult,
  RelinkSkillEvidenceJobResult,
  Requirement,
  Vacancy,
} from "./models";

function isTerminal(status: JobStatus["status"] | undefined): boolean {
  return status === "succeeded" || status === "failed";
}

function useJobPolling(jobId: string | null) {
  return useQuery({
    queryKey: ["jobs", jobId],
    queryFn: () => apiFetch<JobStatus>(`/jobs/${jobId}`),
    enabled: jobId != null,
    // Poll every 1s while pending/running (matches the multi-second LLM
    // call latency api/routes/jobs.py's docstring describes); stop once a
    // terminal status is reached — TanStack Query v5's function-form
    // refetchInterval is exactly built for "poll until terminal state".
    refetchInterval: (query) => (isTerminal(query.state.data?.status) ? false : 1000),
  });
}

export function useIngestJob() {
  const [jobId, setJobId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (resumeText: string) =>
      apiFetch<JobStatus>("/jobs", {
        method: "POST",
        body: JSON.stringify({ type: "ingest", resume_text: resumeText }),
      }),
    onSuccess: (job) => setJobId(job.id),
  });

  const poll = useJobPolling(jobId);
  const status = poll.data?.status;

  useEffect(() => {
    if (status === "succeeded") {
      // Mirrors _on_ingest_succeeded's _reload_profiles(select_id=...) —
      // the picker's candidate list must include the just-created profile.
      void queryClient.invalidateQueries({ queryKey: ["candidates"] });
    }
  }, [status, queryClient]);

  return {
    ingest: (resumeText: string) => {
      setJobId(null);
      mutation.mutate(resumeText);
    },
    isSubmitting: mutation.isPending,
    isRunning: jobId != null && !isTerminal(status),
    result: status === "succeeded" ? (poll.data?.result as IngestJobResult) : undefined,
    error: status === "failed" ? (poll.data?.error as JobErrorBody | undefined) : undefined,
  };
}

// Version 4, Phase 4.5 — the file-upload counterpart to useIngestJob, for
// api/routes/jobs.py's POST /jobs/ingest-upload. Mirrors useIngestJob's
// shape exactly (same result/error types — both routes return the same
// IngestJobResult-shaped job); the only difference is the POST itself uses
// apiFetchUpload with a FormData body instead of apiFetch with a JSON one.
export function useIngestUploadJob() {
  const [jobId, setJobId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiFetchUpload<JobStatus>("/jobs/ingest-upload", formData);
    },
    onSuccess: (job) => setJobId(job.id),
  });

  const poll = useJobPolling(jobId);
  const status = poll.data?.status;

  useEffect(() => {
    if (status === "succeeded") {
      void queryClient.invalidateQueries({ queryKey: ["candidates"] });
    }
  }, [status, queryClient]);

  // Unlike a pasted-text ingest, extraction (app/resume_reader.py) runs
  // synchronously in api/routes/jobs.py's POST /jobs/ingest-upload itself
  // — an unsupported type or unreadable file fails that POST directly
  // (mutation.error), no job record ever gets created to later transition
  // to "failed" the way poll.data?.error below assumes. Both are surfaced
  // through the same `error` shape so IngestPanel's caller doesn't need to
  // know which of the two failure paths actually happened.
  const uploadError =
    mutation.error instanceof ApiError
      ? { category: mutation.error.category, message: mutation.error.message }
      : undefined;

  return {
    ingest: (file: File) => {
      setJobId(null);
      mutation.mutate(file);
    },
    isSubmitting: mutation.isPending,
    isRunning: jobId != null && !isTerminal(status),
    result: status === "succeeded" ? (poll.data?.result as IngestJobResult) : undefined,
    error: status === "failed" ? (poll.data?.error as JobErrorBody | undefined) : uploadError,
  };
}

export function useGenerateJob() {
  const [jobId, setJobId] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: { candidateId: string; vacancyText: string; existingVacancy?: Vacancy }) =>
      apiFetch<JobStatus>("/jobs", {
        method: "POST",
        body: JSON.stringify({
          type: "generate",
          candidate_id: payload.candidateId,
          vacancy_text: payload.vacancyText,
          existing_vacancy: payload.existingVacancy ?? null,
        }),
      }),
    onSuccess: (job) => setJobId(job.id),
  });

  const poll = useJobPolling(jobId);
  const status = poll.data?.status;

  return {
    // `existingVacancy` — a Regenerate/Regenerate as New on an existing
    // draft passes that draft's own already-parsed Vacancy, so the backend
    // can skip re-running the JD Parser stage when `vacancyText` matches
    // its `raw_text` unchanged (app/pipeline.py::run_cv_generation's own
    // `existing_vacancy` docstring). Omitted for a first-time generate
    // (ExportScreen.tsx) — there's no prior parse to reuse.
    generate: (candidateId: string, vacancyText: string, existingVacancy?: Vacancy) => {
      setJobId(null);
      mutation.mutate({ candidateId, vacancyText, existingVacancy });
    },
    isSubmitting: mutation.isPending,
    isRunning: jobId != null && !isTerminal(status),
    // Which of app/pipeline.py's six GENERATION_STAGES is currently
    // running — undefined before the first stage starts (a real, if
    // usually brief, gap right after the job record is created) and,
    // deliberately, still populated once the job finishes (the caller
    // only reads this while `isRunning`, and holding the last value
    // avoids a "Step 6/6" flash to blank right before `result` appears).
    progress:
      poll.data?.stage != null && poll.data.stage_number != null && poll.data.stage_count != null
        ? { stage: poll.data.stage, stageNumber: poll.data.stage_number, stageCount: poll.data.stage_count }
        : undefined,
    result: status === "succeeded" ? (poll.data?.result as GenerateJobResult) : undefined,
    error: status === "failed" ? (poll.data?.error as JobErrorBody | undefined) : undefined,
  };
}

// Phase 18 — re-runs just the Matching stage (app/pipeline.py::
// run_gap_recheck) against the CV as currently edited, not the full
// ingest/generate chain. Mirrors useGenerateJob's shape exactly; the only
// difference is the request payload and result type.
// Post-4.10 fixes round 3 — the recheck payload's `RecheckDocumentContext`
// carries the document's own current content into the recheck (see
// api/routes/jobs.py's RecheckJobRequest and app/pipeline.py's
// run_gap_recheck docstring for the full reasoning): edited/hand-typed
// bullet text and the document's own Skills/Technologies lists, none of
// which the stored Candidate profile alone can reflect once the person
// starts editing the draft directly.
export interface RecheckDocumentContext {
  editedBulletText: Record<string, string>;
  manualBulletText: string[];
  documentSkills: string[];
  documentTechnologies: string[];
}

export function useRecheckGapsJob() {
  const [jobId, setJobId] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (payload: {
      candidateId: string;
      requirements: Requirement[];
      excludedEvidenceIds: string[];
      documentContext: RecheckDocumentContext;
    }) =>
      apiFetch<JobStatus>("/jobs", {
        method: "POST",
        body: JSON.stringify({
          type: "recheck",
          candidate_id: payload.candidateId,
          requirements: payload.requirements,
          excluded_evidence_ids: payload.excludedEvidenceIds,
          edited_bullet_text: payload.documentContext.editedBulletText,
          manual_bullet_text: payload.documentContext.manualBulletText,
          document_skills: payload.documentContext.documentSkills,
          document_technologies: payload.documentContext.documentTechnologies,
        }),
      }),
    onSuccess: (job) => setJobId(job.id),
  });

  const poll = useJobPolling(jobId);
  const status = poll.data?.status;

  return {
    recheck: (
      candidateId: string,
      requirements: Requirement[],
      excludedEvidenceIds: string[],
      documentContext: RecheckDocumentContext,
    ) => {
      setJobId(null);
      mutation.mutate({ candidateId, requirements, excludedEvidenceIds, documentContext });
    },
    isSubmitting: mutation.isPending,
    isRunning: jobId != null && !isTerminal(status),
    result: status === "succeeded" ? (poll.data?.result as RecheckJobResult) : undefined,
    error: status === "failed" ? (poll.data?.error as JobErrorBody | undefined) : undefined,
  };
}

// The on-demand "Re-evaluate Skill Dependencies" action
// (app/pipeline.py::run_skill_evidence_relink) — a standalone linking-only
// pass over the profile's current Skills/Technologies/Evidence, run
// whenever a person wants links refreshed rather than automatically on
// every edit. Mirrors useRecheckGapsJob's shape, plus an
// invalidate-on-success (mirroring useIngestJob's own) so the refreshed
// evidence_ids show up in the Skills/Technologies sections without a
// manual reload.
export function useRelinkSkillEvidenceJob() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [candidateId, setCandidateId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (targetCandidateId: string) =>
      apiFetch<JobStatus>("/jobs", {
        method: "POST",
        body: JSON.stringify({ type: "relink_skill_evidence", candidate_id: targetCandidateId }),
      }),
    onSuccess: (job) => setJobId(job.id),
  });

  const poll = useJobPolling(jobId);
  const status = poll.data?.status;

  useEffect(() => {
    if (status === "succeeded" && candidateId != null) {
      void queryClient.invalidateQueries({ queryKey: ["candidates", candidateId] });
    }
  }, [status, candidateId, queryClient]);

  return {
    relink: (targetCandidateId: string) => {
      setJobId(null);
      setCandidateId(targetCandidateId);
      mutation.mutate(targetCandidateId);
    },
    isSubmitting: mutation.isPending,
    isRunning: jobId != null && !isTerminal(status),
    result: status === "succeeded" ? (poll.data?.result as RelinkSkillEvidenceJobResult) : undefined,
    error: status === "failed" ? (poll.data?.error as JobErrorBody | undefined) : undefined,
  };
}
