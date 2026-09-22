import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DraftScreen } from "./DraftScreen";

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/candidates/cand-1/drafts/draft-1"]}>
        <Routes>
          <Route path="/candidates/:candidateId/drafts/:draftId" element={<DraftScreen />} />
          <Route path="/candidates/:candidateId/profile" element={<div>Profile screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

// Comfortably past the 1500ms autosave debounce (matches the 500+1200
// split the existing document-autosave test already uses below).
const AUTOSAVE_WAIT_MS = 1700;

const DRAFT = {
  id: "draft-1",
  candidate_id: "cand-1",
  vacancy: { title: "Engineer", company: "Acme", raw_text: "jd", requirements: [] },
  assembled_cv: { name: "Ada Lovelace", summary: "A tailored summary." },
  document: {
    sections: [
      {
        key: "summary",
        title: "Summary",
        included: true,
        entries: [{ id: "summary", text: "A tailored summary.", included: true }],
      },
    ],
  },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body };
}

function mockFetch(overrides: Record<string, unknown> = {}) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const key = `${method} ${url}`;
    if (key in overrides) {
      return jsonResponse(overrides[key]);
    }
    if (url === "/api/candidates/cand-1/drafts/draft-1" && method === "GET") {
      return jsonResponse(DRAFT);
    }
    if (url === "/api/candidates/cand-1/drafts/draft-1" && method === "PUT") {
      return jsonResponse({ ...DRAFT, updated_at: "2026-01-01T00:05:00Z" });
    }
    throw new Error(`Unexpected fetch: ${method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("DraftScreen", () => {
  it("hydrates the editor from the fetched draft's document, not a fresh rebuild from assembled_cv", async () => {
    mockFetch();
    renderScreen();

    expect(await screen.findByText("A tailored summary.")).toBeInTheDocument();
  });

  it("autosaves the edited document ~1.5s after the last change, not on every keystroke", async () => {
    // Phase 26: triggers the edit via a checkbox toggle rather than a
    // raw keystroke into the Tiptap contentEditable — jsdom has no real
    // Selection/Range/layout (notably no `elementFromPoint`, which
    // ProseMirror's own click-to-position-cursor handling depends on),
    // so a simulated click-then-type can't reliably land text at a
    // specific position. The debounced-autosave hook under test here
    // reacts to *any* DocumentModel change, keystroke or not, so a
    // checkbox click exercises the identical debounce timing without
    // depending on jsdom's contentEditable/layout support at all — see
    // lib/tiptap's own test files for where actual keystroke/split/join
    // behavior is exercised instead, via a headless Editor instance.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const fetchMock = mockFetch();

    renderScreen();
    await screen.findByText("A tailored summary.");
    const checkbox = screen.getByRole("checkbox", { name: /Include Summary section/ });

    await user.click(checkbox);
    // Not yet -- still inside the debounce window.
    vi.advanceTimersByTime(500);
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "PUT")).toBe(false);

    vi.advanceTimersByTime(1200);
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "PUT")).toBe(true),
    );

    const putCall = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === "PUT")!;
    const body = JSON.parse((putCall[1] as RequestInit).body as string);
    expect(body.document.sections[0].included).toBe(false);
  });

  it("shows the draft's vacancy title, editable", async () => {
    mockFetch();
    renderScreen();

    await screen.findByText("A tailored summary.");
    expect(screen.getByLabelText("Vacancy title")).toHaveValue("Engineer");
  });

  it("shows a blank, placeholder-labeled field for an untailored draft with no vacancy title", async () => {
    mockFetch({
      "GET /api/candidates/cand-1/drafts/draft-1": {
        ...DRAFT,
        vacancy: { title: null, company: null, raw_text: "", requirements: [] },
      },
    });
    renderScreen();

    await screen.findByText("A tailored summary.");
    const field = screen.getByLabelText("Vacancy title");
    expect(field).toHaveValue("");
    expect(field).toHaveAttribute("placeholder", "Untitled vacancy");
  });

  it("does not PUT anything on load, before the title is actually touched", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = mockFetch();

    renderScreen();
    await screen.findByText("A tailored summary.");

    vi.advanceTimersByTime(AUTOSAVE_WAIT_MS);
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "PUT")).toBe(false);
  });

  it("autosaves the vacancy title ~1.5s after the last change, PUTting only vacancy", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const fetchMock = mockFetch();

    renderScreen();
    const field = await screen.findByLabelText("Vacancy title");

    await user.clear(field);
    await user.type(field, "Senior Engineer");
    vi.advanceTimersByTime(500);
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "PUT")).toBe(false);

    vi.advanceTimersByTime(1200);
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "PUT")).toBe(true),
    );

    // A separate, unrelated PUT for `document` can also fire here (a
    // harmless quirk of the debounced-autosave hook settling once
    // DocumentEditor hands DraftScreen its freshly-built model — nothing
    // to do with the title). Find the vacancy-carrying PUT specifically,
    // not just whichever PUT happened first.
    const vacancyPutCall = fetchMock.mock.calls.find(
      ([, init]) =>
        (init as RequestInit)?.method === "PUT" &&
        JSON.parse((init as RequestInit).body as string).vacancy != null,
    )!;
    const body = JSON.parse((vacancyPutCall[1] as RequestInit).body as string);
    expect(body.vacancy).toEqual({ title: "Senior Engineer", company: "Acme", raw_text: "jd", requirements: [] });
    expect(body.document).toBeUndefined();
  });

  it("autosaves a cleared title back as null, not an empty string", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const fetchMock = mockFetch();

    renderScreen();
    const field = await screen.findByLabelText("Vacancy title");

    await user.clear(field);
    vi.advanceTimersByTime(AUTOSAVE_WAIT_MS);
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "PUT")).toBe(true),
    );

    const vacancyPutCall = fetchMock.mock.calls.find(
      ([, init]) =>
        (init as RequestInit)?.method === "PUT" &&
        JSON.parse((init as RequestInit).body as string).vacancy != null,
    )!;
    const body = JSON.parse((vacancyPutCall[1] as RequestInit).body as string);
    expect(body.vacancy.title).toBeNull();
  });

  it("shows the draft's role title (assembled_cv.headline), editable, separately from vacancy title", async () => {
    mockFetch({
      "GET /api/candidates/cand-1/drafts/draft-1": {
        ...DRAFT,
        assembled_cv: { ...DRAFT.assembled_cv, headline: "Senior/Lead Game Designer, Product Manager" },
      },
    });
    renderScreen();

    await screen.findByText("A tailored summary.");
    expect(screen.getByLabelText("Role title")).toHaveValue(
      "Senior/Lead Game Designer, Product Manager",
    );
  });

  it("autosaves the role title ~1.5s after the last change, PUTting only assembled_cv", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const fetchMock = mockFetch({
      "GET /api/candidates/cand-1/drafts/draft-1": {
        ...DRAFT,
        assembled_cv: { ...DRAFT.assembled_cv, headline: "Senior/Lead Game Designer, Product Manager" },
      },
    });

    renderScreen();
    const field = await screen.findByLabelText("Role title");

    await user.clear(field);
    await user.type(field, "Senior Game Designer");
    vi.advanceTimersByTime(500);
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "PUT")).toBe(false);

    vi.advanceTimersByTime(1200);
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "PUT")).toBe(true),
    );

    const headlinePutCall = fetchMock.mock.calls.find(
      ([, init]) =>
        (init as RequestInit)?.method === "PUT" &&
        JSON.parse((init as RequestInit).body as string).assembled_cv != null,
    )!;
    const body = JSON.parse((headlinePutCall[1] as RequestInit).body as string);
    expect(body.assembled_cv.headline).toBe("Senior Game Designer");
    // The rest of assembled_cv rides along unchanged, same shallow-merge
    // shape update_cv_draft expects (no `document` in this PUT at all).
    expect(body.assembled_cv.name).toBe("Ada Lovelace");
    expect(body.document).toBeUndefined();
  });

  it("autosaves a cleared role title back as null, not an empty string, and never touches the candidate's profile headline", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const fetchMock = mockFetch({
      "GET /api/candidates/cand-1/drafts/draft-1": {
        ...DRAFT,
        assembled_cv: { ...DRAFT.assembled_cv, headline: "Senior/Lead Game Designer, Product Manager" },
      },
    });

    renderScreen();
    const field = await screen.findByLabelText("Role title");

    await user.clear(field);
    vi.advanceTimersByTime(AUTOSAVE_WAIT_MS);
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "PUT")).toBe(true),
    );

    const headlinePutCall = fetchMock.mock.calls.find(
      ([, init]) =>
        (init as RequestInit)?.method === "PUT" &&
        JSON.parse((init as RequestInit).body as string).assembled_cv != null,
    )!;
    const body = JSON.parse((headlinePutCall[1] as RequestInit).body as string);
    expect(body.assembled_cv.headline).toBeNull();
    // Only ever a draft-scoped PUT (assembled_cv on this one CVDraft row) —
    // no request touches a candidate-profile endpoint at all.
    expect(fetchMock.mock.calls.every(([url]) => !String(url).includes("/candidates/cand-1/profile"))).toBe(true);
  });

  it("shows no Unused Evidence panel and no Gaps content after a plain reopen of an untailored/pre-migration draft (no location.state, no persisted match_result/provenance)", async () => {
    mockFetch();
    renderScreen();

    await screen.findByText("A tailored summary.");
    // Neither location.state nor the fetched draft itself has provenance
    // -- the panel doesn't render at all.
    expect(screen.queryByText("Unused Evidence")).not.toBeInTheDocument();
    // No matchResult either -- GapsPanel itself renders nothing when null
    // (not even a "no gaps" message, which only appears once a real,
    // empty MatchResult exists).
    expect(screen.queryByText("No notable gaps found for this vacancy.")).not.toBeInTheDocument();
  });

  it("shows Unused Evidence and Gaps on a plain reopen when the draft itself has persisted match_result/provenance (Phase 20b)", async () => {
    // Regression guard for the actual reported bug: match_result/
    // provenance used to only ever arrive via location.state on the
    // *very first* navigation right after a generate -- reopening the
    // exact same draft (no state) showed no Gaps and no Sparkles, even
    // though the bullets had genuinely been AI-edited. Now persisted on
    // the draft itself, so a reopen looks the same as the first landing.
    mockFetch({
      "GET /api/candidates/cand-1/drafts/draft-1": {
        ...DRAFT,
        match_result: { matches: [], gaps: [], missing_keywords: [] },
        provenance: {
          bullets: [],
          unused_evidence: [
            {
              id: "ev-1",
              text: "Led a hackathon team.",
              source_context: null,
              experience_id: null,
              experience_project_id: null,
            },
          ],
        },
      },
    });
    renderScreen();

    await screen.findByText("A tailored summary.");
    expect(await screen.findByText("Unused Evidence")).toBeInTheDocument();
    expect(screen.getByText("No notable gaps found for this vacancy.")).toBeInTheDocument();
  });

  it("clicking Add to Role removes that item from Unused Evidence, so it can't be added twice", async () => {
    // Regression: the button stayed clickable after adding, so repeated
    // clicks kept inserting duplicate bullets for the same Evidence.
    const user = userEvent.setup();
    const draftWithExperience = {
      ...DRAFT,
      assembled_cv: {
        ...DRAFT.assembled_cv,
        experience: [
          { experience_id: "exp-1", position: "Engineer", company: "Acme", is_gap: false, bullets: [] },
        ],
      },
      document: {
        sections: [
          ...DRAFT.document.sections,
          {
            key: "experience",
            title: "Experience",
            included: true,
            entries: [{ id: "exp-1", text: "Engineer — Acme", included: true, bullets: [] }],
          },
        ],
      },
      match_result: { matches: [], gaps: [], missing_keywords: [] },
      provenance: {
        bullets: [],
        unused_evidence: [
          {
            id: "ev-1",
            text: "Led a hackathon team.",
            source_context: null,
            experience_id: "exp-1",
            experience_project_id: null,
          },
        ],
      },
    };
    mockFetch({ "GET /api/candidates/cand-1/drafts/draft-1": draftWithExperience });
    renderScreen();

    await screen.findByText("A tailored summary.");
    expect(screen.getByText("Led a hackathon team.")).toBeInTheDocument();
    const addButton = screen.getByRole("button", { name: "Add to Engineer — Acme" });

    await user.click(addButton);

    // The bullet was inserted into the document (a real Tiptap bullet
    // node now, not a <textarea> -- Phase 26)...
    expect(await screen.findByText("Led a hackathon team.")).toBeInTheDocument();
    // ...and the Unused Evidence item (and its Add button) is gone, not
    // just still sitting there ready for a second, duplicate click --
    // the panel's own empty state is proof its copy is gone (the panel
    // and the document both render plain <p> text now, so a bare
    // `queryByText` can no longer disambiguate the two the way it did
    // when the document's copy lived in a <textarea>).
    expect(screen.queryByRole("button", { name: "Add to Engineer — Acme" })).not.toBeInTheDocument();
    expect(screen.getByText("Every Evidence item made it into this CV.")).toBeInTheDocument();
  });

  // ----- Phase 24: Excluded from CV panel -----------------------------------

  it("unchecking an entry in the document moves it to the Excluded from CV panel, not just strikes it through in place", async () => {
    const user = userEvent.setup();
    const draftWithEducation = {
      ...DRAFT,
      document: {
        sections: [
          ...DRAFT.document.sections,
          {
            key: "education",
            title: "Education",
            included: true,
            entries: [{ id: "edu-1", text: "State University", included: true }],
          },
        ],
      },
    };
    mockFetch({ "GET /api/candidates/cand-1/drafts/draft-1": draftWithEducation });
    renderScreen();

    const heading = (await screen.findByText("State University")).closest("p")!;
    const entryContainer = heading.closest(".cv-print-entry")!;
    // Phase 28 — the checkbox now lives in the floating DocumentGutter, so
    // it's found by its own (heading-text-bearing) aria-label instead of
    // DOM containment — see DocumentEditor.test.tsx's own note.
    await user.click(await screen.findByRole("checkbox", { name: /Include this entry: State University/ }));

    // Gone from the page -- hidden, not struck through in place (Phase
    // 26: the underlying ProseMirror node stays in the doc, so this
    // checks the `hidden` class rather than DOM absence -- see
    // DocumentEditor.test.tsx's own note on why).
    expect(entryContainer).toHaveClass("hidden");
    // Surfaced in the new panel instead, with a way back.
    expect(screen.getByText("Excluded from CV")).toBeInTheDocument();
    const restoreButton = screen.getByRole("button", { name: "Restore" });
    expect(within(restoreButton.closest("li")!).getByText("State University")).toBeInTheDocument();
  });

  it("clicking Restore in the Excluded from CV panel brings the item back into the document", async () => {
    const user = userEvent.setup();
    const draftWithExcludedEducation = {
      ...DRAFT,
      document: {
        sections: [
          ...DRAFT.document.sections,
          {
            key: "education",
            title: "Education",
            included: true,
            entries: [{ id: "edu-1", text: "State University", included: false }],
          },
        ],
      },
    };
    mockFetch({ "GET /api/candidates/cand-1/drafts/draft-1": draftWithExcludedEducation });
    renderScreen();

    await screen.findByText("A tailored summary.");
    // Only in the Excluded panel at this point -- confirm via its own
    // Restore button rather than a bare `getByText("State University")`,
    // which would also match the document's own (hidden, but still
    // DOM-present -- Phase 26) copy.
    const restoreButton = await screen.findByRole("button", { name: "Restore" });
    expect(within(restoreButton.closest("li")!).getByText("State University")).toBeInTheDocument();

    await user.click(restoreButton);

    expect(await screen.findByText("Nothing excluded from this CV.")).toBeInTheDocument();
    // Restored: the document's own copy is no longer hidden, and (the
    // panel copy now gone) this is unambiguous again.
    expect(screen.getByText("State University").closest(".cv-print-entry")).not.toHaveClass("hidden");
  });

  it("clicking Delete Draft asks for confirmation naming the current title, then DELETEs and navigates back to the profile", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetch({ "DELETE /api/candidates/cand-1/drafts/draft-1": null });
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    renderScreen();
    await screen.findByText("A tailored summary.");
    await user.click(screen.getByRole("button", { name: "Delete Draft" }));

    expect(confirmSpy).toHaveBeenCalledWith('Delete the draft "Engineer"? This can\'t be undone.');
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) => url === "/api/candidates/cand-1/drafts/draft-1" && (init as RequestInit)?.method === "DELETE",
        ),
      ).toBe(true),
    );
    expect(await screen.findByText("Profile screen")).toBeInTheDocument();
  });

  it("does not delete the draft when the confirm dialog is cancelled", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetch();
    vi.spyOn(window, "confirm").mockReturnValue(false);

    renderScreen();
    await screen.findByText("A tailored summary.");
    await user.click(screen.getByRole("button", { name: "Delete Draft" }));

    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "DELETE")).toBe(false);
    // Still on the draft, not navigated away.
    expect(screen.getByText("A tailored summary.")).toBeInTheDocument();
  });

  // ----- Regenerate / Regenerate as New --------------------------------------

  const REGENERATED_RESULT = {
    vacancy: { title: "Engineer II", company: "Acme", raw_text: "jd", requirements: [] },
    match_result: { matches: [], gaps: [], missing_keywords: [] },
    assembled_cv: { name: "Ada Lovelace", summary: "A regenerated summary." },
    provenance: { bullets: [], unused_evidence: [] },
  };

  function mockFetchWithGenerate(overrides: Record<string, unknown> = {}) {
    return mockFetch({
      "POST /api/jobs": { id: "job-1", type: "generate", status: "pending" },
      "GET /api/jobs/job-1": { id: "job-1", type: "generate", status: "succeeded", result: REGENERATED_RESULT },
      ...overrides,
    });
  }

  it("disables both Regenerate buttons for an untailored draft (no job description to regenerate from)", async () => {
    mockFetch({
      "GET /api/candidates/cand-1/drafts/draft-1": {
        ...DRAFT,
        vacancy: { title: null, company: null, raw_text: "", requirements: [] },
      },
    });
    renderScreen();

    await screen.findByText("A tailored summary.");
    expect(screen.getByRole("button", { name: "Regenerate as New" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Regenerate" })).toBeDisabled();
  });

  it("clicking Regenerate asks for confirmation naming the current title, then re-tailors against the same JD and PUTs the result onto this same draft", async () => {
    const user = userEvent.setup();
    // Stateful, unlike the plain mockFetch/mockFetchWithGenerate above:
    // this test needs the PUT to actually persist, so the GET refetch it
    // triggers (updateDraft's onSuccess invalidate) returns the *new*
    // document — otherwise DocumentEditor's forced remount (regenVersion)
    // would just re-seed the same old content it started with, and this
    // test couldn't tell a working remount from a no-op one.
    let currentDraft: unknown = DRAFT;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      if (url === "/api/candidates/cand-1/drafts/draft-1" && method === "GET") {
        return jsonResponse(currentDraft);
      }
      if (url === "/api/candidates/cand-1/drafts/draft-1" && method === "PUT") {
        currentDraft = { ...(currentDraft as object), ...JSON.parse(init!.body as string) };
        return jsonResponse(currentDraft);
      }
      if (url === "/api/jobs" && method === "POST") {
        return jsonResponse({ id: "job-1", type: "generate", status: "pending" });
      }
      if (url === "/api/jobs/job-1" && method === "GET") {
        return jsonResponse({ id: "job-1", type: "generate", status: "succeeded", result: REGENERATED_RESULT });
      }
      throw new Error(`Unexpected fetch: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

    renderScreen();
    await screen.findByText("A tailored summary.");
    await user.click(screen.getByRole("button", { name: "Regenerate" }));

    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('Regenerate "Engineer"?'));

    const jobCall = await waitFor(() =>
      fetchMock.mock.calls.find(([url, init]) => url === "/api/jobs" && (init as RequestInit)?.method === "POST")!,
    );
    // Re-tailors against the draft's own already-stored JD text — never
    // asks the person to paste it again. Also sends the draft's own
    // already-parsed Vacancy as `existing_vacancy`, so the backend can
    // skip re-running the JD Parser when the text is unchanged (see
    // app/pipeline.py::run_cv_generation's own docstring).
    expect(JSON.parse((jobCall[1] as RequestInit).body as string)).toMatchObject({
      candidate_id: "cand-1",
      vacancy_text: "jd",
      existing_vacancy: DRAFT.vacancy,
    });

    // Result lands on *this* draft (a PUT to draft-1), not a new one.
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url, init]) => {
          if (url !== "/api/candidates/cand-1/drafts/draft-1" || (init as RequestInit)?.method !== "PUT") {
            return false;
          }
          const body = JSON.parse((init as RequestInit).body as string);
          return body.assembled_cv?.summary === "A regenerated summary.";
        }),
      ).toBe(true),
    );
    // The fresh content shows up without a manual reload -- the whole
    // point of forcing DocumentEditor to remount (regenVersion).
    expect(await screen.findByText("A regenerated summary.")).toBeInTheDocument();
    expect(screen.getByLabelText("Vacancy title")).toHaveValue("Engineer II");
  });

  it("does not call the generate job when the Regenerate confirm dialog is cancelled", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchWithGenerate();
    vi.spyOn(window, "confirm").mockReturnValue(false);

    renderScreen();
    await screen.findByText("A tailored summary.");
    await user.click(screen.getByRole("button", { name: "Regenerate" }));

    expect(fetchMock.mock.calls.some(([url]) => url === "/api/jobs")).toBe(false);
    expect(screen.getByText("A tailored summary.")).toBeInTheDocument();
  });

  it("clicking Regenerate as New re-tailors against the same JD without confirmation, saves it as a new draft, and navigates there", async () => {
    const user = userEvent.setup();
    // Not mocked to return a value -- this flow must never call it at all,
    // so a stray real invocation (which would hang/throw in jsdom) is
    // itself proof of a bug. Cleared first since the spy itself isn't
    // restored between tests in this file (see the Delete Draft tests
    // above) -- this test only cares about calls made during its own run.
    const confirmSpy = vi.spyOn(window, "confirm");
    confirmSpy.mockClear();
    const fetchMock = mockFetchWithGenerate({
      "POST /api/candidates/cand-1/drafts": {
        id: "draft-2",
        candidate_id: "cand-1",
        ...REGENERATED_RESULT,
        document: { sections: [] },
      },
      "GET /api/candidates/cand-1/drafts/draft-2": {
        ...DRAFT,
        id: "draft-2",
        vacancy: REGENERATED_RESULT.vacancy,
        assembled_cv: REGENERATED_RESULT.assembled_cv,
        document: {
          sections: [
            {
              key: "summary",
              title: "Summary",
              included: true,
              entries: [{ id: "summary", text: "A regenerated summary.", included: true }],
            },
          ],
        },
      },
    });

    renderScreen();
    await screen.findByText("A tailored summary.");
    await user.click(screen.getByRole("button", { name: "Regenerate as New" }));

    // Nothing to confirm -- this draft is never touched.
    expect(confirmSpy).not.toHaveBeenCalled();

    const jobCall = await waitFor(() =>
      fetchMock.mock.calls.find(([url, init]) => url === "/api/jobs" && (init as RequestInit)?.method === "POST")!,
    );
    expect(JSON.parse((jobCall[1] as RequestInit).body as string)).toMatchObject({
      candidate_id: "cand-1",
      vacancy_text: "jd",
      existing_vacancy: DRAFT.vacancy,
    });

    const createCall = await waitFor(() =>
      fetchMock.mock.calls.find(
        ([url, init]) => url === "/api/candidates/cand-1/drafts" && (init as RequestInit)?.method === "POST",
      )!,
    );
    const body = JSON.parse((createCall[1] as RequestInit).body as string);
    expect(body.vacancy).toEqual(REGENERATED_RESULT.vacancy);
    expect(body.assembled_cv).toEqual(REGENERATED_RESULT.assembled_cv);

    // Navigated to the newly-created draft, this one untouched.
    expect(await screen.findByText("A regenerated summary.")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url, init]) => url === "/api/candidates/cand-1/drafts/draft-1" && (init as RequestInit)?.method === "PUT"),
    ).toBe(false);
  });
});
