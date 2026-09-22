import { useMutation } from "@tanstack/react-query";

import { apiFetch, apiFetchBlob } from "./client";
import type { AssembledCV, PageBreakPosition } from "./models";
import type { DocumentModel } from "@/lib/structuredDocument";

export type ExportFormat = "md" | "docx" | "pdf";

export interface ExportPayload {
  assembledCv: AssembledCV;
  // Phase 16c: the structured document (A4 Preview tab state) is now the
  // single source of truth for every export format, plain and templated
  // alike — the old flat `sections: Record<string,string>` field is gone.
  document: DocumentModel;
  format: ExportFormat;
  // Absent = plain/ATS-safe rendering; set = the Classic/Modern templated
  // path. Never applicable to format "md" (rejected server-side).
  templateId?: string;
}

// Hidden <a download> + synthetic click relies on the browser's own
// download manager to prompt for a save location.
async function triggerDownload(blob: Blob, filename: string): Promise<void> {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

// On-screen page-break-prediction fix (follow-up to Version 4, Phase
// 4.9) — PageBreakGuide.tsx calls this (debounced, not on every
// keystroke) instead of approximating breaks from the live browser DOM,
// which stopped corresponding to what PDF export actually produces once
// templated PDF became a browser-free reportlab renderer. A plain async
// function, not a hook — PageBreakGuide.tsx already owns its own
// debounce/effect timing (see that component's own docstring); a
// TanStack Query hook here would just be a second, redundant scheduling
// layer on top of that.
export async function fetchPageBreaks(
  assembledCv: AssembledCV,
  document: DocumentModel,
  templateId: string | null,
): Promise<PageBreakPosition[]> {
  return apiFetch<PageBreakPosition[]>("/export/page-breaks", {
    method: "POST",
    body: JSON.stringify({
      assembled_cv: assembledCv,
      document,
      template_id: templateId ?? undefined,
    }),
  });
}

export function useExportCv() {
  return useMutation({
    mutationFn: async (payload: ExportPayload) => {
      const { blob, filename } = await apiFetchBlob("/export", {
        method: "POST",
        body: JSON.stringify({
          assembled_cv: payload.assembledCv,
          document: payload.document,
          format: payload.format,
          // Undefined is dropped by JSON.stringify — omitted entirely for
          // plain/ATS-safe exports and for format "md".
          template_id: payload.templateId,
        }),
      });
      await triggerDownload(blob, filename);
    },
  });
}
