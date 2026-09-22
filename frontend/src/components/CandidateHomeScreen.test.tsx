import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CandidateHomeScreen } from "./CandidateHomeScreen";

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<CandidateHomeScreen />} />
          <Route path="/candidates/:candidateId/profile" element={<div>Profile screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body };
}

describe("CandidateHomeScreen", () => {
  // Version 4, Phase 4.6 (3.1): CandidateTable replaced the CandidatePicker
  // dropdown here — confirms the fetched candidate list reaches the table
  // as a row with Name/Role/Language and Open/Delete buttons.
  it("renders a table row per candidate once profiles load", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/candidates") {
        return jsonResponse([
          { id: "cand-1", name: "Ada Lovelace", experience_count: 3, headline: "Engineer", language: "en" },
        ]);
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderScreen();

    expect(await screen.findByText("Ada Lovelace")).toBeInTheDocument();
    // Scoped to the table: the empty-profile-creation form's language
    // Select also defaults to "English" text elsewhere on this screen.
    const table = within(screen.getByRole("table"));
    expect(table.getByText("Engineer")).toBeInTheDocument();
    expect(table.getByText("English")).toBeInTheDocument();
    expect(table.getByRole("button", { name: "Open" })).toBeInTheDocument();
    expect(table.getByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(screen.queryByText(/No profiles yet/)).not.toBeInTheDocument();
  });

  it("clicking Open navigates to that candidate's profile", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/candidates") {
        return jsonResponse([
          { id: "cand-1", name: "Ada Lovelace", experience_count: 3, headline: null, language: "en" },
        ]);
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderScreen();
    await user.click(await screen.findByRole("button", { name: "Open" }));

    expect(await screen.findByText("Profile screen")).toBeInTheDocument();
  });

  it("clicking Delete asks for confirmation, then DELETEs and removes the row", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/candidates" && method === "GET") {
        return jsonResponse([
          { id: "cand-1", name: "Ada Lovelace", experience_count: 3, headline: null, language: "en" },
        ]);
      }
      if (url === "/api/candidates/cand-1" && method === "DELETE") {
        return jsonResponse(null, 204);
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();

    renderScreen();
    await user.click(await screen.findByRole("button", { name: "Delete" }));

    expect(confirmSpy).toHaveBeenCalledWith('Delete "Ada Lovelace"? This can\'t be undone.');
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) => url === "/api/candidates/cand-1" && (init as RequestInit)?.method === "DELETE",
        ),
      ).toBe(true),
    );
  });

  it("does not delete when the confirm dialog is cancelled", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/candidates" && method === "GET") {
        return jsonResponse([
          { id: "cand-1", name: "Ada Lovelace", experience_count: 3, headline: null, language: "en" },
        ]);
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();

    renderScreen();
    await user.click(await screen.findByRole("button", { name: "Delete" }));

    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "DELETE")).toBe(false);
  });

  it("hints that ingesting or creating a profile gets you started when none exist yet", async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === "/api/candidates") {
        return jsonResponse([]);
      }
      throw new Error(`Unexpected fetch: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderScreen();

    expect(
      await screen.findByText("No profiles yet — ingest a resume or create a blank one below to get started."),
    ).toBeInTheDocument();
  });

  it("a successful ingest navigates to the new candidate's profile", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/candidates" && method === "GET") {
        return jsonResponse([]);
      }
      if (url === "/api/jobs" && method === "POST") {
        return jsonResponse({ id: "job-1", type: "ingest", status: "pending" });
      }
      if (url === "/api/jobs/job-1" && method === "GET") {
        return jsonResponse({
          id: "job-1",
          type: "ingest",
          status: "succeeded",
          result: { candidate_id: "new-cand", candidate: { name: "Bea" } },
        });
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderScreen();
    await user.type(screen.getByPlaceholderText("Paste your resume text here..."), "Resume text.");
    await user.click(screen.getByRole("button", { name: "Ingest Resume" }));

    await waitFor(() => expect(screen.getByText("Profile screen")).toBeInTheDocument());
  });

  // Version 4, Phase 4.5: the file-upload path — its own job
  // (useIngestUploadJob), its own POST /jobs/ingest-upload route, but the
  // same navigate-on-success behavior as the paste path above.
  it("a successful file upload navigates to the new candidate's profile", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/candidates" && method === "GET") {
        return jsonResponse([]);
      }
      if (url === "/api/jobs/ingest-upload" && method === "POST") {
        return jsonResponse({ id: "job-7", type: "ingest", status: "pending" });
      }
      if (url === "/api/jobs/job-7" && method === "GET") {
        return jsonResponse({
          id: "job-7",
          type: "ingest",
          status: "succeeded",
          result: { candidate_id: "new-cand", candidate: { name: "Bea" } },
        });
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderScreen();
    const file = new File(["resume text"], "resume.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Upload resume file"), file);

    await waitFor(() => expect(screen.getByText("Profile screen")).toBeInTheDocument());
  });

  it("a failed file upload shows the ingestion-failed status message", async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/candidates" && method === "GET") {
        return jsonResponse([]);
      }
      if (url === "/api/jobs/ingest-upload" && method === "POST") {
        // A .pdf extension passes the file input's own `accept` filter
        // (unlike an actually-unsupported extension, which userEvent.upload
        // itself refuses to attach — see IngestPanel.test.tsx) but the
        // upload can still fail server-side, e.g. an unreadable/scanned
        // PDF — app/resume_reader.py's ParsingError path.
        return jsonResponse({ error: { category: "ParsingError", message: "No extractable text found." } }, 502);
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderScreen();
    const file = new File(["x"], "resume.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Upload resume file"), file);

    expect(await screen.findByText("Ingestion failed: No extractable text found.")).toBeInTheDocument();
  });

  // Version 4, Phase 4.6 (3.2.2): the empty-profile creation path — a
  // plain POST /candidates, not a job, since there's no LLM call.
  describe("create an empty profile", () => {
    it("creating with a name navigates to the new candidate's profile", async () => {
      const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (url === "/api/candidates" && method === "GET") {
          return jsonResponse([]);
        }
        if (url === "/api/candidates" && method === "POST") {
          const body = JSON.parse(init!.body as string);
          expect(body).toEqual({ name: "Grace Hopper", language: "en" });
          return jsonResponse({ id: "new-cand", candidate: { name: "Grace Hopper" } }, 201);
        }
        throw new Error(`Unexpected fetch: ${method} ${url}`);
      });
      vi.stubGlobal("fetch", fetchMock);
      const user = userEvent.setup();

      renderScreen();
      await user.type(screen.getByLabelText("Name"), "Grace Hopper");
      await user.click(screen.getByRole("button", { name: "Create Profile" }));

      await waitFor(() => expect(screen.getByText("Profile screen")).toBeInTheDocument());
    });

    it("shows a status message instead of calling the API when the name is blank", async () => {
      const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (url === "/api/candidates" && method === "GET") {
          return jsonResponse([]);
        }
        throw new Error(`Unexpected fetch: ${method} ${url}`);
      });
      vi.stubGlobal("fetch", fetchMock);
      const user = userEvent.setup();

      renderScreen();
      await user.click(screen.getByRole("button", { name: "Create Profile" }));

      expect(await screen.findByText("Enter a name first.")).toBeInTheDocument();
      expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "POST")).toBe(
        false,
      );
    });

    it("shows a status message when creation fails", async () => {
      const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (url === "/api/candidates" && method === "GET") {
          return jsonResponse([]);
        }
        if (url === "/api/candidates" && method === "POST") {
          return jsonResponse({ error: { category: "ValidationError", message: "Name must not be empty." } }, 422);
        }
        throw new Error(`Unexpected fetch: ${method} ${url}`);
      });
      vi.stubGlobal("fetch", fetchMock);
      const user = userEvent.setup();

      renderScreen();
      await user.type(screen.getByLabelText("Name"), "  ");
      await user.type(screen.getByLabelText("Name"), "X");
      await user.click(screen.getByRole("button", { name: "Create Profile" }));

      expect(
        await screen.findByText("Couldn't create the profile: Name must not be empty."),
      ).toBeInTheDocument();
    });
  });
});
