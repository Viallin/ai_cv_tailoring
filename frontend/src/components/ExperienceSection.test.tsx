import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Experience } from "@/api/models";
import { ExperienceSection } from "./ExperienceSection";

function renderWithQueryClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const EXPERIENCE: Experience = {
  id: "exp-1",
  position: "Engineer",
  company: "Acme",
  period: "2020-2022",
  location: "Remote",
  is_gap: false,
  responsibilities: ["Did X"],
  achievements: [],
  projects: [],
};

describe("ExperienceSection", () => {
  it("renders a summarized row per entry, including a [GAP] suffix", () => {
    const gap: Experience = {
      id: "exp-2",
      position: "Career break",
      is_gap: true,
      company: null,
      period: null,
      location: null,
    };

    renderWithQueryClient(
      <ExperienceSection
        candidateId="cand-1"
        experience={[EXPERIENCE, gap]}
        evidence={[]}
        language="en"
      />,
    );

    expect(screen.getByText("Engineer — Acme (2020-2022, Remote)")).toBeInTheDocument();
    expect(screen.getByText("Career break [GAP]")).toBeInTheDocument();
  });

  it("renders the company name as a real, visibly-styled link when company_url is set", () => {
    const withLink: Experience = { ...EXPERIENCE, company_url: "https://acme.example/" };

    renderWithQueryClient(
      <ExperienceSection candidateId="cand-1" experience={[withLink]} evidence={[]} language="en" />,
    );

    const link = screen.getByRole("link", { name: "Acme" });
    expect(link).toHaveAttribute("href", "https://acme.example/");
    expect(link).toHaveClass("underline");
  });

  it("renders the company name as plain text when there's no company_url", () => {
    renderWithQueryClient(
      <ExperienceSection candidateId="cand-1" experience={[EXPERIENCE]} evidence={[]} language="en" />,
    );

    expect(screen.queryByRole("link", { name: "Acme" })).not.toBeInTheDocument();
  });

  it("adds a new experience via the inline form, sending blank optional fields as null", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: "exp-3" }) });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(
      <ExperienceSection candidateId="cand-1" experience={[]} evidence={[]} language="en" />,
    );

    await user.click(screen.getByRole("button", { name: /Add Experience/ }));
    await user.type(screen.getByLabelText("Position"), "Engineer");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/experience");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      position: "Engineer",
      company: null,
      company_url: null,
      period: null,
      location: null,
      is_gap: false,
      responsibilities: [],
      achievements: [],
    });
  });

  it("new-experience mode has a Projects manager available immediately (no save-first gate)", async () => {
    // Phase 17c: the old per-project-atomic-save architecture required an
    // existing Experience id before a Project could be attached at all.
    // The unified editor removes that restriction — Projects are in-memory
    // state until the whole form saves, same as ui/graph_explorer.py's
    // dialog, so Add Project works in new-experience mode too.
    const user = userEvent.setup();

    renderWithQueryClient(
      <ExperienceSection candidateId="cand-1" experience={[]} evidence={[]} language="en" />,
    );

    await user.click(screen.getByRole("button", { name: /Add Experience/ }));

    expect(screen.getByRole("button", { name: "+ Add Project" })).toBeInTheDocument();
  });

  it("adding a project opens its inline name/period editor immediately", async () => {
    const user = userEvent.setup();

    renderWithQueryClient(
      <ExperienceSection candidateId="cand-1" experience={[]} evidence={[]} language="en" />,
    );

    await user.click(screen.getByRole("button", { name: /Add Experience/ }));
    await user.click(screen.getByRole("button", { name: "+ Add Project" }));

    expect(screen.getByLabelText("Name")).toBeInTheDocument();
  });

  it("creating a new experience with a project does a create-then-projects-only-PUT two-write sequence", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ id: "exp-new" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(
      <ExperienceSection candidateId="cand-1" experience={[]} evidence={[]} language="en" />,
    );

    await user.click(screen.getByRole("button", { name: /Add Experience/ }));
    await user.type(screen.getByLabelText("Position"), "Engineer");
    await user.click(screen.getByRole("button", { name: "+ Add Project" }));
    await user.type(screen.getByLabelText("Name"), "Internal tool");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

    const [createUrl, createInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(createUrl).toBe("/api/candidates/cand-1/experience");
    expect(createInit.method).toBe("POST");
    expect(JSON.parse(createInit.body as string)).not.toHaveProperty("projects");

    const [updateUrl, updateInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(updateUrl).toBe("/api/candidates/cand-1/experience/exp-new");
    expect(updateInit.method).toBe("PUT");
    const updateBody = JSON.parse(updateInit.body as string);
    expect(updateBody.projects).toEqual([
      {
        id: expect.any(String),
        name: "Internal tool",
        period: null,
        achievements: [],
        responsibilities: [],
        url: null,
      },
    ]);
  });

  it("creating a new experience with no project only does the one create write", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: "exp-new" }) });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(
      <ExperienceSection candidateId="cand-1" experience={[]} evidence={[]} language="en" />,
    );

    await user.click(screen.getByRole("button", { name: /Add Experience/ }));
    await user.type(screen.getByLabelText("Position"), "Engineer");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("edits an existing entry, submitting the full overwritten body", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(
      <ExperienceSection
        candidateId="cand-1"
        experience={[EXPERIENCE]}
        evidence={[]}
      language="en"
      />,
    );

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.type(screen.getByLabelText("Company"), "Corp");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/experience/exp-1");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({
      position: "Engineer",
      company: "AcmeCorp",
      company_url: null,
      period: "2020-2022",
      location: "Remote",
      is_gap: false,
      responsibilities: ["Did X"],
      achievements: [],
      projects: [],
    });
  });

  it("editing an existing entry with an existing project sends the project's achievements nested under it", async () => {
    const withProject: Experience = {
      ...EXPERIENCE,
      achievements: [],
      projects: [{ id: "proj-1", name: "Internal tool", period: "2021", achievements: ["Shipped v1"], responsibilities: [] }],
    };
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(
      <ExperienceSection
        candidateId="cand-1"
        experience={[withProject]}
        evidence={[]}
      language="en"
      />,
    );

    await user.click(screen.getByRole("button", { name: "Edit" }));
    // The project's achievement is visible directly in the unified list —
    // no separate "Edit" click on the project row needed to see it.
    expect(screen.getByDisplayValue("Shipped v1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.achievements).toEqual([]);
    expect(body.projects).toEqual([
      {
        id: "proj-1",
        name: "Internal tool",
        period: "2021",
        achievements: ["Shipped v1"],
        responsibilities: [],
        url: null,
      },
    ]);
  });

  it("the Projects list shows a project's name as a real, visibly-styled link when it has a url", async () => {
    const withLinkedProject: Experience = {
      ...EXPERIENCE,
      projects: [
        { id: "proj-1", name: "Internal tool", url: "https://internal.example/", achievements: [], responsibilities: [] },
      ],
    };
    const user = userEvent.setup();

    renderWithQueryClient(
      <ExperienceSection candidateId="cand-1" experience={[withLinkedProject]} evidence={[]} language="en" />,
    );

    await user.click(screen.getByRole("button", { name: "Edit" }));

    const link = screen.getByRole("link", { name: "Internal tool" });
    expect(link).toHaveAttribute("href", "https://internal.example/");
    expect(link).toHaveClass("underline");
  });

  it("deleting a project unlinks its achievement (falls back to role-level) rather than dropping it", async () => {
    const withProject: Experience = {
      ...EXPERIENCE,
      achievements: [],
      projects: [{ id: "proj-1", name: "Internal tool", period: "2021", achievements: ["Shipped v1"], responsibilities: [] }],
    };
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(
      <ExperienceSection
        candidateId="cand-1"
        experience={[withProject]}
        evidence={[]}
      language="en"
      />,
    );

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.projects).toEqual([]);
    expect(body.achievements).toEqual(["Shipped v1"]);
  });

  it("removes an entry after confirming", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(
      <ExperienceSection
        candidateId="cand-1"
        experience={[EXPERIENCE]}
        evidence={[]}
      language="en"
      />,
    );
    await user.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/experience/exp-1");
    expect(init.method).toBe("DELETE");
  });
});
