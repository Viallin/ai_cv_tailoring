import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { Evidence } from "./models";

// Evidence isn't embedded in the Candidate object (GET /candidates/{id}
// has no `evidence` field) — it's its own table, fetched separately.
// Query key is a strict extension of ["candidates", candidateId], so
// every existing mutation (useEntityMutations, useUpdateCandidateProfile)
// already invalidates it for free via TanStack Query v5's default
// prefix-match invalidateQueries.
export function useEvidence(candidateId: string | null) {
  return useQuery({
    queryKey: ["candidates", candidateId, "evidence"],
    queryFn: () => apiFetch<Evidence[]>(`/candidates/${candidateId}/evidence`),
    enabled: candidateId != null,
  });
}
