import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useCandidate, useCreateCandidate, useDeleteCandidate, useExportUntailored, useUpdateCandidateProfile } from "./candidates";

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

describe("useCandidate", () => {
  it("fetches GET /api/candidates/{id} when an id is given", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ name: "Ada Lovelace" }) });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useCandidate("cand-1"), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.data?.name).toBe("Ada Lovelace"));
    expect(fetchMock).toHaveBeenCalledWith("/api/candidates/cand-1", expect.anything());
  });

  it("does not fetch when the id is null", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderHook(() => useCandidate(null), { wrapper: makeWrapper() });

    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("useUpdateCandidateProfile", () => {
  it("PATCHes /api/candidates/{id} with only the given fields", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ name: "Ada Lovelace" }) });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useUpdateCandidateProfile("cand-1"), { wrapper: makeWrapper() });
    result.current.mutate({ summary: "Updated summary." });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({ summary: "Updated summary." });
  });
});

describe("useCreateCandidate", () => {
  it("POSTs /api/candidates with the given name/language and resolves with the new id", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: "new-cand", candidate: { name: "Grace Hopper", language: "en" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useCreateCandidate(), { wrapper: makeWrapper() });
    result.current.mutate({ name: "Grace Hopper", language: "en" });

    await waitFor(() => expect(result.current.data?.id).toBe("new-cand"));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ name: "Grace Hopper", language: "en" });
  });

  it("invalidates the candidates list query on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: "new-cand", candidate: { name: "Grace Hopper" } }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    function Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useCreateCandidate(), { wrapper: Wrapper });
    result.current.mutate({ name: "Grace Hopper", language: "en" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["candidates"] });
  });
});

describe("useDeleteCandidate", () => {
  it("DELETEs /api/candidates/{id}", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => null });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useDeleteCandidate(), { wrapper: makeWrapper() });
    result.current.mutate("cand-1");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1");
    expect(init.method).toBe("DELETE");
  });

  it("invalidates the list query and drops the single-candidate query on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => null });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const removeSpy = vi.spyOn(queryClient, "removeQueries");
    function Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useDeleteCandidate(), { wrapper: Wrapper });
    result.current.mutate("cand-1");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["candidates"] });
    expect(removeSpy).toHaveBeenCalledWith({ queryKey: ["candidates", "cand-1"] });
  });
});

describe("useExportUntailored", () => {
  it("POSTs /api/candidates/{id}/export-untailored and resolves with the assembled CV", async () => {
    const assembledCv = { name: "Ada Lovelace", summary: "" };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => assembledCv });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useExportUntailored("cand-1"), { wrapper: makeWrapper() });
    result.current.mutate();

    await waitFor(() => expect(result.current.data).toEqual(assembledCv));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/export-untailored");
    expect(init.method).toBe("POST");
  });

  it("surfaces an error if the candidate is missing", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: { category: "NotFoundError", message: "Candidate not found." } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useExportUntailored("does-not-exist"), { wrapper: makeWrapper() });
    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("Candidate not found.");
  });
});
