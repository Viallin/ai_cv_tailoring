import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CandidateTable } from "./CandidateTable";

function renderTable(disabled = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<CandidateTable disabled={disabled} />} />
          <Route path="/candidates/:candidateId/profile" element={<div>Profile screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CandidateTable", () => {
  it("renders nothing when there are no candidates", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));

    const { container } = renderTable();

    await waitFor(() => expect(screen.queryByText("Loading…")).not.toBeInTheDocument());
    expect(container.querySelector("table")).not.toBeInTheDocument();
  });

  it("falls back to an em dash for a candidate with no headline", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse([{ id: "cand-1", name: "Ada Lovelace", experience_count: 0, headline: null, language: "en" }]),
      ),
    );

    renderTable();

    expect(await screen.findByText("—")).toBeInTheDocument();
  });

  it("clicking Open navigates to that candidate's profile", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse([
          { id: "cand-1", name: "Ada Lovelace", experience_count: 3, headline: "Engineer", language: "en" },
        ]),
      ),
    );
    const user = userEvent.setup();

    renderTable();
    await user.click(await screen.findByRole("button", { name: "Open" }));

    expect(await screen.findByText("Profile screen")).toBeInTheDocument();
  });

  it("disables Open/Delete when disabled is true", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse([
          { id: "cand-1", name: "Ada Lovelace", experience_count: 3, headline: "Engineer", language: "en" },
        ]),
      ),
    );

    renderTable(true);

    expect(await screen.findByRole("button", { name: "Open" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete" })).toBeDisabled();
  });
});
