import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CandidatePicker, NEW_CANDIDATE_OPTION } from "./CandidatePicker";

function renderPicker(selectedId: string | null = null, disabled = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onSelect = vi.fn();
  render(
    <QueryClientProvider client={queryClient}>
      <CandidatePicker selectedId={selectedId} onSelect={onSelect} disabled={disabled} />
    </QueryClientProvider>,
  );
  return { onSelect };
}

function jsonResponse(body: unknown) {
  return { ok: true, json: async () => body };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CandidatePicker", () => {
  // Doesn't drive the Radix Select's actual open/select interaction —
  // jsdom doesn't implement hasPointerCapture, the same limitation
  // ExportButton.test.tsx/DocumentEditor.test.tsx already work around by
  // not exercising a Select interactively either.
  it("renders once profiles load, without error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse([{ id: "cand-1", name: "Ada Lovelace", experience_count: 3 }])),
    );

    renderPicker();

    expect(await screen.findByRole("combobox", { name: "Switch profile" })).toBeInTheDocument();
  });

  // Version 4, Phase 4.6 (4.1) — NEW_CANDIDATE_OPTION is the sentinel a
  // caller (CandidateWorkflowLayout.tsx) branches on to navigate("/")
  // instead of to a candidate profile; just confirms the constant is a
  // real, non-empty value distinct from any real candidate id shape.
  it("exports a New Candidate sentinel value distinct from a real candidate id", () => {
    expect(NEW_CANDIDATE_OPTION).toBeTruthy();
    expect(NEW_CANDIDATE_OPTION).not.toMatch(/^[0-9a-f]{8}$/);
  });
});
