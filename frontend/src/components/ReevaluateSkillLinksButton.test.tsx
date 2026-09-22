import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReevaluateSkillLinksButton } from "./ReevaluateSkillLinksButton";

function renderWithQueryClient(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReevaluateSkillLinksButton", () => {
  it("posts a relink job for the given candidate id, disabling itself while running", async () => {
    const user = userEvent.setup();
    let resolvePost: (() => void) | undefined;
    const pending = new Promise<void>((resolve) => {
      resolvePost = resolve;
    });
    const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        await pending;
        return { ok: true, json: async () => ({ id: "job-1", type: "relink_skill_evidence", status: "pending" }) };
      }
      return {
        ok: true,
        json: async () => ({
          id: "job-1",
          type: "relink_skill_evidence",
          status: "succeeded",
          result: { updated_skill_count: 2, updated_technology_count: 1 },
        }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(<ReevaluateSkillLinksButton candidateId="cand-1" />);

    await user.click(screen.getByRole("button", { name: "Re-evaluate Skill Dependencies" }));

    expect(screen.getByRole("button", { name: "Re-evaluating…" })).toBeDisabled();

    resolvePost?.();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Re-evaluate Skill Dependencies" })).not.toBeDisabled(),
    );

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/jobs");
    expect(JSON.parse(init.body as string)).toEqual({
      type: "relink_skill_evidence",
      candidate_id: "cand-1",
    });
  });
});
