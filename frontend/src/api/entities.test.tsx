import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useEntityMutations } from "./entities";

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useEntityMutations", () => {
  it("create POSTs to /api/candidates/{id}/{segment} with the given body", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ id: "skill-1", name: "Python" }) });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useEntityMutations("cand-1", "skills"), { wrapper: makeWrapper() });
    result.current.create.mutate({ name: "Python" });

    await waitFor(() => expect(result.current.create.isSuccess).toBe(true));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/skills");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ name: "Python" });
  });

  it("update PUTs to /api/candidates/{id}/{segment}/{itemId}", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ id: "skill-1", proficiency: "Advanced" }) });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useEntityMutations("cand-1", "skills"), { wrapper: makeWrapper() });
    result.current.update.mutate({ itemId: "skill-1", body: { proficiency: "Advanced" } });

    await waitFor(() => expect(result.current.update.isSuccess).toBe(true));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/skills/skill-1");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ proficiency: "Advanced" });
  });

  it("remove DELETEs to /api/candidates/{id}/{segment}/{itemId} (204, no body)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useEntityMutations("cand-1", "skills"), { wrapper: makeWrapper() });
    result.current.remove.mutate("skill-1");

    await waitFor(() => expect(result.current.remove.isSuccess).toBe(true));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/skills/skill-1");
    expect(init.method).toBe("DELETE");
  });
});
