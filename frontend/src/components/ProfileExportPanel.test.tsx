import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProfileExportPanel } from "./ProfileExportPanel";

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/candidates/cand-1/profile"]}>
        <Routes>
          <Route
            path="/candidates/:candidateId/profile"
            element={<ProfileExportPanel candidateId="cand-1" language="en" />}
          />
          <Route path="/candidates/:candidateId/drafts/:draftId" element={<div>Draft screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown) {
  return { ok: true, json: async () => body };
}

describe("ProfileExportPanel", () => {
  it("shows the language disclaimer, and no drafts card when there are none yet", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse([])));

    renderPanel();

    expect(await screen.findByText(/CVs are generated in this profile's language \(English\)/)).toBeInTheDocument();
    expect(screen.queryByText("Your drafts")).not.toBeInTheDocument();
  });

  it("lists existing drafts by title and opens one on click", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([{ id: "draft-1", vacancy_title: "Senior Engineer", vacancy_company: "Acme", updated_at: "2026-01-01T00:00:00Z" }]),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderPanel();

    const draftButton = await screen.findByRole("button", { name: /^Senior Engineer/ });
    await user.click(draftButton);

    expect(await screen.findByText("Draft screen")).toBeInTheDocument();
  });

  it("deletes a draft after confirmation", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/candidates/cand-1/drafts" && method === "GET") {
        return jsonResponse([{ id: "draft-1", vacancy_title: "Senior Engineer", vacancy_company: null, updated_at: "2026-01-01T00:00:00Z" }]);
      }
      if (url === "/api/candidates/cand-1/drafts/draft-1" && method === "DELETE") {
        return jsonResponse(null);
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();

    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Delete draft: Senior Engineer" }));

    expect(window.confirm).toHaveBeenCalledWith('Delete the draft "Senior Engineer"? This can\'t be undone.');
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) => url === "/api/candidates/cand-1/drafts/draft-1" && (init as RequestInit)?.method === "DELETE",
        ),
      ).toBe(true),
    );
  });

  it("exports without tailoring, creates a draft, and navigates to it", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/candidates/cand-1/drafts" && method === "GET") {
        return jsonResponse([]);
      }
      if (url === "/api/candidates/cand-1/export-untailored" && method === "POST") {
        return jsonResponse({ name: "Ada Lovelace", language: "en" });
      }
      if (url === "/api/candidates/cand-1/drafts" && method === "POST") {
        return jsonResponse({ id: "draft-9" });
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderPanel();
    await user.click(await screen.findByRole("button", { name: "Export without tailoring" }));

    expect(await screen.findByText("Draft screen")).toBeInTheDocument();
  });
});
