import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { CVDraft, CVDraftSummary } from "./models";

// Phase 20 — create/update/remove reuse useEntityMutations<CVDraft>
// (api/entities.ts) directly against pathSegment "drafts" — CVDraft is
// registered in api/routes/entity_crud.py's generic factory like every
// other entity, so there's nothing new to wrap for those three. Only
// list/get-one need their own hooks: they're hand-written on the backend
// (api/routes/cv_drafts.py, mirroring api/evidence.ts's own precedent —
// the factory has never had a GET verb for any entity).

export function useCvDrafts(candidateId: string | null) {
  return useQuery({
    queryKey: ["candidates", candidateId, "drafts"],
    queryFn: () => apiFetch<CVDraftSummary[]>(`/candidates/${candidateId}/drafts`),
    enabled: candidateId != null,
  });
}

// `enabled` (default true) lets a caller stop observing this query
// without unmounting — DraftScreen.tsx passes `false` once its own
// delete-draft mutation starts, so this actively-mounted query can't
// still be invalidated-and-refetched (a real, reproducible race: the
// remove mutation's own cache invalidation was refetching this exact
// draft — already gone server-side — for the split second before
// `navigate()` away could unmount the component and stop it, and that
// concurrent refetch was intermittently aborting the DELETE request
// itself, net::ERR_ABORTED, leaving the UI stuck on "Deleting…" even
// though the delete had already succeeded).
export function useCvDraft(candidateId: string | null, draftId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["candidates", candidateId, "drafts", draftId],
    queryFn: () => apiFetch<CVDraft>(`/candidates/${candidateId}/drafts/${draftId}`),
    enabled: enabled && candidateId != null && draftId != null,
  });
}
