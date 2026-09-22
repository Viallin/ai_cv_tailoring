import { useMutation } from "@tanstack/react-query";

import { apiFetch } from "./client";
import type { AssembledCV, WritebackApplyResult, WritebackProposalOut } from "./models";
import type { DocumentModel } from "@/lib/structuredDocument";

// Phase 19 — mirrors api/export.ts's shape: stateless, the client resends
// its own assembledCv/document (exactly what CvWorkflowView already holds
// after a generate) rather than anything being looked up server-side.

export interface WritebackPreviewPayload {
  candidateId: string;
  assembledCv: AssembledCV;
  document: DocumentModel;
}

export interface WritebackApplyPayload extends WritebackPreviewPayload {
  selectedKeys: string[];
}

export function useWritebackPreview() {
  return useMutation({
    mutationFn: (payload: WritebackPreviewPayload) =>
      apiFetch<WritebackProposalOut[]>(`/candidates/${payload.candidateId}/writeback/preview`, {
        method: "POST",
        body: JSON.stringify({
          assembled_cv: payload.assembledCv,
          document: payload.document,
        }),
      }),
  });
}

export function useWritebackApply() {
  return useMutation({
    mutationFn: (payload: WritebackApplyPayload) =>
      apiFetch<WritebackApplyResult>(`/candidates/${payload.candidateId}/writeback/apply`, {
        method: "POST",
        body: JSON.stringify({
          assembled_cv: payload.assembledCv,
          document: payload.document,
          selected_keys: payload.selectedKeys,
        }),
      }),
  });
}
