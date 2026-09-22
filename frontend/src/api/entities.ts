import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "./client";

// One generic hook factory for every entity nested under a candidate
// (education, skills, technologies, ... — see lib/entityConfigs.ts),
// mirroring api/routes/entity_crud.py's generic route factory on the
// backend: same three operations, same URL shape
// (/candidates/{id}/{pathSegment}[/{itemId}]), for every entity — one
// hook instead of ~11 hand-written near-duplicates.
//
// `T` defaults to `unknown` (its type before this generic was added) so
// every existing call site that doesn't need the created/updated entity's
// shape is unaffected; ExperienceSection.tsx is the first caller that does
// (it needs a just-created Experience's `id` for its own follow-up
// projects-only PUT — see its handleSave).
export function useEntityMutations<T = unknown>(candidateId: string, pathSegment: string) {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["candidates", candidateId] });

  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiFetch<T>(`/candidates/${candidateId}/${pathSegment}`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });

  const update = useMutation({
    mutationFn: ({ itemId, body }: { itemId: string; body: Record<string, unknown> }) =>
      apiFetch(`/candidates/${candidateId}/${pathSegment}/${itemId}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (itemId: string) =>
      apiFetch(`/candidates/${candidateId}/${pathSegment}/${itemId}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  // Only meaningful for the 11 entities registered with a `list_field` on
  // the backend (api/routes/entity_crud.py) — calling this against one
  // that isn't (currently just "experience", which reorders through a
  // different mechanism) 405s, same as any other unregistered route.
  const reorder = useMutation({
    mutationFn: (orderedIds: string[]) =>
      apiFetch<T[]>(`/candidates/${candidateId}/${pathSegment}/reorder`, {
        method: "POST",
        body: JSON.stringify({ ordered_ids: orderedIds }),
      }),
    onSuccess: invalidate,
  });

  return { create, update, remove, reorder };
}
