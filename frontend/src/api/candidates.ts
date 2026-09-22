import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { AssembledCV, Candidate, CandidateProfileSummary, EmploymentType } from "./models";

export interface CandidateCreateResult {
  id: string;
  candidate: Candidate;
}

export function useCandidates() {
  return useQuery({
    queryKey: ["candidates"],
    queryFn: () => apiFetch<CandidateProfileSummary[]>("/candidates"),
  });
}

// Added in Phase 15b-i for the new profile view — Phase 14 deliberately
// didn't need this (generate only ever sends a candidate_id string, never
// fetches the full Candidate client-side).
export function useCandidate(candidateId: string | null) {
  return useQuery({
    queryKey: ["candidates", candidateId],
    queryFn: () => apiFetch<Candidate>(`/candidates/${candidateId}`),
    enabled: candidateId != null,
  });
}

export interface CandidateProfileUpdate {
  name?: string;
  headline?: string | null;
  summary?: string | null;
  employment_types_sought?: EmploymentType[];
}

// PATCH — partial update, matches CandidateService.update()'s semantics
// (only the fields present in the body are touched). Invalidates both the
// single-candidate query (profile view re-renders) and the list query
// (the picker's "{name} — N entries" label can change too, e.g. on a name edit).
export function useUpdateCandidateProfile(candidateId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (update: CandidateProfileUpdate) =>
      apiFetch<Candidate>(`/candidates/${candidateId}`, {
        method: "PATCH",
        body: JSON.stringify(update),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["candidates", candidateId] });
      void queryClient.invalidateQueries({ queryKey: ["candidates"] });
    },
  });
}

// Version 4, Phase 4.6 (3.2.2) — the empty-profile creation path (name +
// language, no resume text to ingest). Same POST /candidates route
// api/routes/candidates.py's create_candidate already serves; this is a
// separate hook from the ingest jobs (useIngestJob/useIngestUploadJob in
// ./jobs.ts) because there's no LLM call and thus no job to poll — a plain
// mutation, same shape as useExportUntailored below.
export function useCreateCandidate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; language: string }) =>
      apiFetch<CandidateCreateResult>("/candidates", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["candidates"] });
    },
  });
}

// Version 4, Phase 4.6 (3.1/4.2) — backs both the start screen's candidate
// table (Delete column) and the loaded-profile Delete button
// (ProfileHeader.tsx). DELETE /candidates/{id} already exists end-to-end
// server-side (api/routes/candidates.py, cascades evidence via FK) — no
// backend change needed for this hook.
export function useDeleteCandidate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (candidateId: string) => apiFetch<void>(`/candidates/${candidateId}`, { method: "DELETE" }),
    onSuccess: (_data, candidateId) => {
      void queryClient.invalidateQueries({ queryKey: ["candidates"] });
      queryClient.removeQueries({ queryKey: ["candidates", candidateId] });
    },
  });
}

// CV export screen's "export without tailoring" path
// (app.cv_assembler.build_untailored_projection) — deliberately a plain
// mutation, not a job-polling hook like useGenerateJob: there's no LLM
// call on the backend, so the whole round trip is effectively
// synchronous. The caller turns the returned AssembledCV into a CVDraft
// itself via the existing generic drafts POST route, the same way a real
// generate job's result does.
export function useExportUntailored(candidateId: string) {
  return useMutation({
    mutationFn: () =>
      apiFetch<AssembledCV>(`/candidates/${candidateId}/export-untailored`, { method: "POST" }),
  });
}
