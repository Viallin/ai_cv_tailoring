import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CandidateWorkflowLayout } from "./CandidateWorkflowLayout";

function renderLayout(initialPath: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/" element={<div>Start screen</div>} />
          <Route path="/candidates/:candidateId" element={<CandidateWorkflowLayout />}>
            <Route path="profile" element={<div>Profile content</div>} />
            <Route path="drafts/:draftId" element={<div>Draft content</div>} />
          </Route>
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

// Both list ("Switch profile" picker) and single-candidate ("Home" crumb
// no longer reads this, but useCandidate isn't called here at all post-
// nav-redesign) shapes a real backend would return for candidate cand-1.
const CANDIDATE_LIST = [{ id: "cand-1", name: "Ada Lovelace", experience_count: 3, headline: "Engineer", language: "en" }];

describe("CandidateWorkflowLayout", () => {
  it("renders the matched nested route, with the breadcrumb showing just Home and the profile picker on the Profile screen", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(CANDIDATE_LIST)));

    renderLayout("/candidates/cand-1/profile");

    expect(await screen.findByText("Profile content")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /home/i })).toHaveAttribute("href", "/");
    expect(await screen.findByRole("combobox", { name: "Switch profile" })).toBeInTheDocument();
  });

  // Post-4.10 nav redesign, round 3 — there's no "CV export" screen/crumb
  // any more (ProfileExportPanel.tsx folds it into the profile itself), so
  // a draft's breadcrumb goes straight from the profile crumb to the
  // draft's own title.
  it("on a draft screen, adds the draft's own crumb right after the profile picker", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/candidates") {
        return jsonResponse(CANDIDATE_LIST);
      }
      if (url === "/api/candidates/cand-1/drafts") {
        return jsonResponse([{ id: "draft-1", vacancy_title: "Product Manager", vacancy_company: "Plummy Games" }]);
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderLayout("/candidates/cand-1/drafts/draft-1");

    expect(await screen.findByText("Draft content")).toBeInTheDocument();
    expect(await screen.findByText("Product Manager — Plummy Games")).toBeInTheDocument();
    expect(screen.queryByText("CV export")).not.toBeInTheDocument();
  });
});
