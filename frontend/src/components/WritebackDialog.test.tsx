import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AssembledCV } from "@/api/models";
import type { DocumentModel } from "@/lib/structuredDocument";
import { WritebackDialog } from "./WritebackDialog";

const CV: AssembledCV = { name: "Ada Lovelace", language: "en", summary: "A tailored summary." };
const DOCUMENT: DocumentModel = {
  sections: [
    {
      key: "summary",
      title: "Summary",
      included: true,
      entries: [{ id: "summary", text: "A tailored summary.", included: true }],
    },
  ],
};

function renderWithQueryClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown) {
  return { ok: true, json: async () => body };
}

describe("WritebackDialog", () => {
  it("is disabled until candidateId/assembledCv/cvDocument all exist", () => {
    renderWithQueryClient(
      <WritebackDialog candidateId={null} assembledCv={null} cvDocument={null} />,
    );
    expect(screen.getByRole("button", { name: "Save to Profile" })).toBeDisabled();
  });

  it("previews proposals on open, pre-checking enabled ones and disabling the rest", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([
        { key: "0", label: "Update candidate summary", enabled: true },
        { key: "1", label: "Could not map the Experience section...", enabled: false },
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(
      <WritebackDialog candidateId="cand-1" assembledCv={CV} cvDocument={DOCUMENT} />,
    );
    await user.click(screen.getByRole("button", { name: "Save to Profile" }));

    await waitFor(() => expect(screen.getByText("Update candidate summary")).toBeInTheDocument());

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/writeback/preview");
    expect(JSON.parse(init.body as string)).toEqual({ assembled_cv: CV, document: DOCUMENT });

    const enabledCheckbox = screen.getByLabelText("Update candidate summary");
    expect(enabledCheckbox).toBeChecked();
    expect(enabledCheckbox).not.toBeDisabled();

    const disabledCheckbox = screen.getByLabelText("Could not map the Experience section...");
    expect(disabledCheckbox).not.toBeChecked();
    expect(disabledCheckbox).toBeDisabled();
  });

  it("saves only the checked proposals' keys", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse([
          { key: "0", label: "Update candidate summary", enabled: true },
          { key: "1", label: "Add skill: Go", enabled: true },
        ]),
      )
      .mockResolvedValueOnce(jsonResponse({ applied_keys: ["0"] }));
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(
      <WritebackDialog candidateId="cand-1" assembledCv={CV} cvDocument={DOCUMENT} />,
    );
    await user.click(screen.getByRole("button", { name: "Save to Profile" }));
    await waitFor(() => expect(screen.getByText("Add skill: Go")).toBeInTheDocument());

    // Uncheck the second proposal before saving.
    await user.click(screen.getByLabelText("Add skill: Go"));
    await user.click(screen.getByRole("button", { name: "Save selected" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/writeback/apply");
    const body = JSON.parse(init.body as string);
    expect(body.selected_keys).toEqual(["0"]);
  });
});
