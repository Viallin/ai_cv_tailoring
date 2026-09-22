import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useEvidence } from "./evidence";

function makeWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useEvidence", () => {
  it("fetches GET /api/candidates/{id}/evidence when an id is given", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [{ id: "ev-1", text: "Did a thing" }] });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useEvidence("cand-1"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.data).toEqual([{ id: "ev-1", text: "Did a thing" }]));
    expect(fetchMock).toHaveBeenCalledWith("/api/candidates/cand-1/evidence", expect.anything());
  });

  it("does not fetch when the id is null", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderHook(() => useEvidence(null), { wrapper: makeWrapper() });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
