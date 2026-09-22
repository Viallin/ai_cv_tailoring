import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Evidence, Experience } from "@/api/models";
import { ExperienceEvidencePanel } from "./ExperienceEvidencePanel";

const EXPERIENCE: Experience = {
  id: "exp-1",
  position: "Engineer",
  company: "Acme",
  is_gap: false,
  projects: [{ id: "proj-1", name: "Internal tool", achievements: [], responsibilities: [] }],
};

function renderWithQueryClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ExperienceEvidencePanel", () => {
  it("renders nothing when no evidence matches this experience", () => {
    const { container } = renderWithQueryClient(
      <ExperienceEvidencePanel
        candidateId="cand-1"
        experience={EXPERIENCE}
        evidence={[{ id: "ev-1", text: "Unrelated", experience_id: "exp-other", locked: false }]}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("groups role-level and per-project evidence under the Responsibilities & Achievements heading", () => {
    const evidence: Evidence[] = [
      { id: "ev-1", text: "Led the team", source_context: "Acme", experience_id: "exp-1", locked: false },
      {
        id: "ev-2",
        text: "Built the API",
        experience_id: "exp-1",
        experience_project_id: "proj-1",
        locked: false,
      },
    ];

    renderWithQueryClient(
      <ExperienceEvidencePanel candidateId="cand-1" experience={EXPERIENCE} evidence={evidence} />,
    );

    expect(screen.getByText("Responsibilities & Achievements")).toBeInTheDocument();
    expect(screen.getByText("Led the team")).toBeInTheDocument();
    expect(screen.getByText("Internal tool")).toBeInTheDocument();
    expect(screen.getByText("Built the API")).toBeInTheDocument();
  });

  it("renders the project heading as a real link when the project has a url — the read-only counterpart of ExperienceForm.tsx's ProjectSummaryLine", () => {
    // Found live: a project's url added via the edit form showed as a
    // link there but as plain text in this read-only panel — the two
    // never shared the same rendering.
    const withLinkedProject: Experience = {
      ...EXPERIENCE,
      projects: [
        { id: "proj-1", name: "Internal tool", url: "https://internal.example/", achievements: [], responsibilities: [] },
      ],
    };
    const evidence: Evidence[] = [
      {
        id: "ev-2",
        text: "Built the API",
        experience_id: "exp-1",
        experience_project_id: "proj-1",
        locked: false,
      },
    ];

    renderWithQueryClient(
      <ExperienceEvidencePanel candidateId="cand-1" experience={withLinkedProject} evidence={evidence} />,
    );

    const link = screen.getByRole("link", { name: "Internal tool" });
    expect(link).toHaveAttribute("href", "https://internal.example/");
  });

  it("renders the project heading as plain text when it has no url", () => {
    const evidence: Evidence[] = [
      {
        id: "ev-2",
        text: "Built the API",
        experience_id: "exp-1",
        experience_project_id: "proj-1",
        locked: false,
      },
    ];

    renderWithQueryClient(
      <ExperienceEvidencePanel candidateId="cand-1" experience={EXPERIENCE} evidence={evidence} />,
    );

    expect(screen.getByText("Internal tool")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Internal tool" })).not.toBeInTheDocument();
  });

  it("never shows source_context — the project/company grouping already shown by the panel's heading made it pure duplication", () => {
    // Regression guard: ingestion commonly sets source_context to a
    // "Company, Project: <bullet text again>" restatement, which used to
    // render right after the identical bullet text.
    const evidence: Evidence[] = [
      {
        id: "ev-1",
        text: "Led the team",
        source_context: "Acme, Internal tool: Led the team",
        experience_id: "exp-1",
        locked: false,
      },
    ];

    renderWithQueryClient(
      <ExperienceEvidencePanel candidateId="cand-1" experience={EXPERIENCE} evidence={evidence} />,
    );

    expect(screen.getByText("Led the team")).toBeInTheDocument();
    expect(screen.queryByText(/Acme, Internal tool/)).not.toBeInTheDocument();
  });
});

// ----- Phase 19: lock/unlock (moved here from the A4 CV editor) -----------

describe("ExperienceEvidencePanel — Phase 19 bullet locking", () => {
  function mockFetchOk() {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("shows the Unlock icon for an already-locked item and the Lock icon otherwise", () => {
    const evidence: Evidence[] = [
      { id: "ev-1", text: "Locked wording", experience_id: "exp-1", locked: true, locked_text: "Locked wording" },
      { id: "ev-2", text: "Unlocked wording", experience_id: "exp-1", locked: false },
    ];

    renderWithQueryClient(
      <ExperienceEvidencePanel candidateId="cand-1" experience={EXPERIENCE} evidence={evidence} />,
    );

    expect(screen.getByLabelText("Locked — reused verbatim for every future vacancy")).toBeInTheDocument();
    expect(screen.getByLabelText("Lock this wording for every future vacancy")).toBeInTheDocument();
  });

  it("clicking Lock sends locked:true and the item's current text as locked_text", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchOk();
    const evidence: Evidence[] = [
      { id: "ev-1", text: "Led the team", experience_id: "exp-1", locked: false },
    ];

    renderWithQueryClient(
      <ExperienceEvidencePanel candidateId="cand-1" experience={EXPERIENCE} evidence={evidence} />,
    );

    await user.click(screen.getByLabelText("Lock this wording for every future vacancy"));
    await user.click(screen.getByRole("button", { name: "Lock this wording" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/candidates/cand-1/evidence/ev-1",
      expect.objectContaining({ method: "PUT" }),
    );
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body).toEqual({ locked: true, locked_text: "Led the team" });
  });

  it("clicking Unlock sends locked:false", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchOk();
    const evidence: Evidence[] = [
      { id: "ev-1", text: "Led the team", experience_id: "exp-1", locked: true, locked_text: "Led the team" },
    ];

    renderWithQueryClient(
      <ExperienceEvidencePanel candidateId="cand-1" experience={EXPERIENCE} evidence={evidence} />,
    );

    await user.click(screen.getByLabelText("Locked — reused verbatim for every future vacancy"));
    await user.click(screen.getByRole("button", { name: "Unlock" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/candidates/cand-1/evidence/ev-1",
      expect.objectContaining({ method: "PUT" }),
    );
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body).toEqual({ locked: false });
  });
});
