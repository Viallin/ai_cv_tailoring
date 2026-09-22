import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Candidate } from "@/api/models";
import { ProfileHeader } from "./ProfileHeader";

const CANDIDATE = {
  name: "Ada Lovelace",
  language: "en",
  headline: "Engineer",
  summary: null,
  employment_types_sought: ["Full-time"],
} as Candidate;

// ProfileHeader now calls useNavigate() (Version 4, Phase 4.6's Delete
// button) — every render needs a Router ancestor, not just the ones
// exercising Delete itself.
function renderWithQueryClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/candidates/cand-1/profile"]}>
        <Routes>
          <Route path="/candidates/:candidateId/profile" element={ui} />
          <Route path="/" element={<div>Start screen</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ProfileHeader", () => {
  it("renders read-only by default, same convention as every other Profile Explorer section", () => {
    renderWithQueryClient(<ProfileHeader candidateId="cand-1" candidate={CANDIDATE} />);

    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Engineer")).toBeInTheDocument();
    expect(screen.getByText("Seeking: Full-time")).toBeInTheDocument();
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
  });

  it("shows the profile's language as a human-readable label", () => {
    renderWithQueryClient(
      <ProfileHeader candidateId="cand-1" candidate={{ ...CANDIDATE, language: "ru" }} />,
    );

    expect(screen.getByText("Language: Russian")).toBeInTheDocument();
  });

  it("omits the Seeking line entirely when nothing is selected", () => {
    renderWithQueryClient(
      <ProfileHeader candidateId="cand-1" candidate={{ ...CANDIDATE, employment_types_sought: [] }} />,
    );

    expect(screen.queryByText(/Seeking:/)).not.toBeInTheDocument();
  });

  it("clicking Edit pre-fills the form from the given candidate", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<ProfileHeader candidateId="cand-1" candidate={CANDIDATE} />);

    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByLabelText("Name")).toHaveValue("Ada Lovelace");
    expect(screen.getByLabelText("Headline")).toHaveValue("Engineer");
    expect(screen.getByRole("checkbox", { name: "Full-time" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Part-time" })).not.toBeChecked();
  });

  it("toggling an employment-type checkbox and saving submits the updated list, then returns to read-only", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => CANDIDATE });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(<ProfileHeader candidateId="cand-1" candidate={CANDIDATE} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("checkbox", { name: "Contract" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1");
    expect(init.method).toBe("PATCH");
    const body = JSON.parse(init.body as string);
    expect(body.employment_types_sought).toEqual(["Full-time", "Contract"]);

    await waitFor(() => expect(screen.queryByLabelText("Name")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
  });

  it("Cancel discards in-progress edits and returns to the read-only view unchanged", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(<ProfileHeader candidateId="cand-1" candidate={CANDIDATE} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Name"));
    await user.type(screen.getByLabelText("Name"), "Someone Else");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();

    // Re-opening the form shows the original value, not the discarded edit.
    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.getByLabelText("Name")).toHaveValue("Ada Lovelace");
  });

  describe("Delete", () => {
    it("clicking Delete asks for confirmation, then DELETEs and navigates to the start screen", async () => {
      const user = userEvent.setup();
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => null });
      vi.stubGlobal("fetch", fetchMock);
      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

      renderWithQueryClient(<ProfileHeader candidateId="cand-1" candidate={CANDIDATE} />);
      await user.click(screen.getByRole("button", { name: "Delete" }));

      expect(confirmSpy).toHaveBeenCalledWith('Delete "Ada Lovelace"? This can\'t be undone.');
      await waitFor(() => expect(screen.getByText("Start screen")).toBeInTheDocument());
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("/api/candidates/cand-1");
      expect(init.method).toBe("DELETE");
    });

    it("does not delete when the confirm dialog is cancelled", async () => {
      const user = userEvent.setup();
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);
      vi.spyOn(window, "confirm").mockReturnValue(false);

      renderWithQueryClient(<ProfileHeader candidateId="cand-1" candidate={CANDIDATE} />);
      await user.click(screen.getByRole("button", { name: "Delete" }));

      expect(fetchMock).not.toHaveBeenCalled();
      expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    });
  });
});
