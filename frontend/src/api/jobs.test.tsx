import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useIngestJob, useIngestUploadJob, useRecheckGapsJob, useRelinkSkillEvidenceJob } from "./jobs";

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

describe("useIngestJob", () => {
  it("polls pending -> running -> succeeded and then stops", async () => {
    const responses = [
      { ok: true, json: async () => ({ id: "job-1", type: "ingest", status: "pending" }) }, // POST /jobs
      { ok: true, json: async () => ({ id: "job-1", type: "ingest", status: "running" }) }, // first poll
      {
        ok: true,
        json: async () => ({
          id: "job-1",
          type: "ingest",
          status: "succeeded",
          result: { candidate_id: "cand-1", candidate: { name: "Ada Lovelace" } },
        }),
      }, // second poll — terminal
    ];
    const fetchMock = vi.fn();
    for (const response of responses) {
      fetchMock.mockResolvedValueOnce(response);
    }
    fetchMock.mockResolvedValue(responses[responses.length - 1]); // any further poll repeats the terminal state
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useIngestJob(), { wrapper: makeWrapper() });

    result.current.ingest("some resume text");

    await waitFor(() => expect(result.current.result?.candidate_id).toBe("cand-1"), { timeout: 3000 });
    expect(result.current.isRunning).toBe(false);
    expect(result.current.error).toBeUndefined();
  });

  it("surfaces category/message and stops polling when the job fails", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "job-2", type: "ingest", status: "pending" }),
    });
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "job-2",
        type: "ingest",
        status: "failed",
        error: { category: "ProviderError", message: "Gemini is unavailable." },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useIngestJob(), { wrapper: makeWrapper() });

    result.current.ingest("some resume text");

    await waitFor(() => expect(result.current.error?.category).toBe("ProviderError"), { timeout: 3000 });
    expect(result.current.error?.message).toBe("Gemini is unavailable.");
    expect(result.current.isRunning).toBe(false);
    expect(result.current.result).toBeUndefined();
  });
});

describe("useIngestUploadJob", () => {
  it("posts the file as multipart FormData and polls to a succeeded result", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "job-6", type: "ingest", status: "pending" }),
    });
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "job-6",
        type: "ingest",
        status: "succeeded",
        result: { candidate_id: "cand-2", candidate: { name: "Bea" } },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useIngestUploadJob(), { wrapper: makeWrapper() });
    const file = new File(["resume text"], "resume.pdf");

    result.current.ingest(file);

    await waitFor(() => expect(result.current.result?.candidate_id).toBe("cand-2"), { timeout: 3000 });
    expect(result.current.isRunning).toBe(false);
    expect(result.current.error).toBeUndefined();

    const [url, postInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/jobs/ingest-upload");
    const formData = postInit.body as FormData;
    expect(formData.get("file")).toBe(file);
  });

  it("surfaces category/message and stops polling when extraction fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({ error: { category: "ParsingError", message: "Unsupported file type." } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useIngestUploadJob(), { wrapper: makeWrapper() });

    result.current.ingest(new File(["x"], "resume.odt"));

    await waitFor(() => expect(result.current.error?.category).toBe("ParsingError"), { timeout: 3000 });
    expect(result.current.error?.message).toBe("Unsupported file type.");
    expect(result.current.isRunning).toBe(false);
  });
});

describe("useRecheckGapsJob", () => {
  it("posts a recheck job with the given requirements/excluded ids and resolves with its match_result", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "job-3", type: "recheck", status: "pending" }),
    });
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "job-3",
        type: "recheck",
        status: "succeeded",
        result: { match_result: { matches: [], gaps: [], missing_keywords: ["AWS"] } },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRecheckGapsJob(), { wrapper: makeWrapper() });

    result.current.recheck("cand-1", [{ text: "AWS certification", priority: "required" }], ["ev-2"], {
      editedBulletText: { "ev-1": "Did a thing, using AI tools daily" },
      manualBulletText: ["Hand-typed bullet"],
      documentSkills: ["Python", "AI Tools"],
      documentTechnologies: [],
    });

    await waitFor(() => expect(result.current.result?.match_result.missing_keywords).toEqual(["AWS"]), {
      timeout: 3000,
    });
    expect(result.current.isRunning).toBe(false);

    const [, postInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(postInit.body as string)).toEqual({
      type: "recheck",
      candidate_id: "cand-1",
      requirements: [{ text: "AWS certification", priority: "required" }],
      excluded_evidence_ids: ["ev-2"],
      edited_bullet_text: { "ev-1": "Did a thing, using AI tools daily" },
      manual_bullet_text: ["Hand-typed bullet"],
      document_skills: ["Python", "AI Tools"],
      document_technologies: [],
    });
  });
});

describe("useRelinkSkillEvidenceJob", () => {
  it("posts a relink_skill_evidence job with the given candidate id and resolves with its counts", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "job-4", type: "relink_skill_evidence", status: "pending" }),
    });
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "job-4",
        type: "relink_skill_evidence",
        status: "succeeded",
        result: { updated_skill_count: 3, updated_technology_count: 1 },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useRelinkSkillEvidenceJob(), { wrapper: makeWrapper() });

    result.current.relink("cand-1");

    await waitFor(() => expect(result.current.result?.updated_skill_count).toBe(3), { timeout: 3000 });
    expect(result.current.result?.updated_technology_count).toBe(1);
    expect(result.current.isRunning).toBe(false);

    const [, postInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(postInit.body as string)).toEqual({
      type: "relink_skill_evidence",
      candidate_id: "cand-1",
    });
  });

  it("invalidates the candidate's own query on success, so refreshed evidence_ids show up without a reload", async () => {
    const fetchMock = vi.fn();
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "job-5", type: "relink_skill_evidence", status: "pending" }),
    });
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "job-5",
        type: "relink_skill_evidence",
        status: "succeeded",
        result: { updated_skill_count: 1, updated_technology_count: 0 },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    function Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useRelinkSkillEvidenceJob(), { wrapper: Wrapper });

    result.current.relink("cand-1");

    await waitFor(() => expect(result.current.result?.updated_skill_count).toBe(1), { timeout: 3000 });

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["candidates", "cand-1"] });
  });
});
