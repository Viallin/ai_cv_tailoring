import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TailorToJobDialog } from "./TailorToJobDialog";

function renderDialog() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/candidates/cand-1/profile"]}>
        <Routes>
          <Route path="/candidates/:candidateId/profile" element={<TailorToJobDialog candidateId="cand-1" language="en" />} />
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

describe("TailorToJobDialog", () => {
  it("opens on trigger click, showing the language disclaimer and the JD textarea", async () => {
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole("button", { name: "Tailor CV to a Job Description" }));

    expect(screen.getByText(/CVs are generated in this profile's language \(English\)/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Paste the job description here...")).toBeInTheDocument();
  });

  it("shows an inline error and starts no job when submitted empty", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole("button", { name: "Tailor CV to a Job Description" }));
    await user.click(screen.getByRole("button", { name: "Tailor CV to Job Description" }));

    expect(await screen.findByText("Paste a job description first.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  // A never-resolving POST keeps generateJob.isSubmitting true indefinitely
  // — enough to assert the "can't close mid-run" behavior deterministically,
  // without racing a full mocked job-then-draft chain that can resolve
  // faster than an intermediate state is observable (tried first; flaked).
  it("disables Cancel (and blocks the close button) once a job submission starts", async () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole("button", { name: "Tailor CV to a Job Description" }));
    await user.type(screen.getByPlaceholderText("Paste the job description here..."), "Senior Engineer role.");
    await user.click(screen.getByRole("button", { name: "Tailor CV to Job Description" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled());
    expect(screen.getByText(/please don't close this window/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Close" })).not.toBeInTheDocument();
  });

  it("creates a draft from the generated result and navigates to it on success", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/jobs" && method === "POST") {
        return jsonResponse({ id: "job-1", type: "generate", status: "pending" });
      }
      if (url === "/api/jobs/job-1" && method === "GET") {
        return jsonResponse({
          id: "job-1",
          type: "generate",
          status: "succeeded",
          result: {
            vacancy: { raw_text: "Senior Engineer", title: "Senior Engineer", company: null },
            assembled_cv: { name: "Ada Lovelace", language: "en" },
            match_result: null,
            provenance: null,
            timing: null,
          },
        });
      }
      if (url === "/api/candidates/cand-1/drafts" && method === "POST") {
        return jsonResponse({ id: "draft-9" });
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    renderDialog();

    await user.click(screen.getByRole("button", { name: "Tailor CV to a Job Description" }));
    await user.type(screen.getByPlaceholderText("Paste the job description here..."), "Senior Engineer role.");
    await user.click(screen.getByRole("button", { name: "Tailor CV to Job Description" }));

    await waitFor(() => expect(screen.getByText("Draft screen")).toBeInTheDocument());

    const draftPost = fetchMock.mock.calls.find(
      ([url, init]) => url === "/api/candidates/cand-1/drafts" && (init as RequestInit)?.method === "POST",
    )!;
    const body = JSON.parse((draftPost[1] as RequestInit).body as string);
    expect(body.vacancy.title).toBe("Senior Engineer");
  });
});
