import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch, apiFetchBlob, apiFetchUpload } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ hello: "world" }) }),
    );

    const result = await apiFetch<{ hello: string }>("/candidates");

    expect(result).toEqual({ hello: "world" });
  });

  it("throws an ApiError with category/message from the {error:...} envelope on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          error: { category: "ValidationError", message: "Name must not be empty." },
        }),
      }),
    );

    await expect(apiFetch("/candidates")).rejects.toMatchObject({
      name: "ApiError",
      category: "ValidationError",
      message: "Name must not be empty.",
      status: 422,
    });
  });

  it("returns undefined for a 204 No Content response, without calling .json()", async () => {
    const json = vi.fn().mockRejectedValue(new Error("no body to parse"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 204, json }));

    const result = await apiFetch("/candidates/cand-1/skills/skill-1");

    expect(result).toBeUndefined();
    expect(json).not.toHaveBeenCalled();
  });

  it("falls back to a generic error when the response body isn't the expected envelope", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: async () => {
          throw new Error("not json");
        },
      }),
    );

    await expect(apiFetch("/candidates")).rejects.toMatchObject({
      category: "UnknownError",
      status: 500,
    });
  });
});

describe("apiFetchUpload", () => {
  it("POSTs the given FormData without setting a Content-Type header itself", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ id: "job-1", status: "pending" }) });
    vi.stubGlobal("fetch", fetchMock);
    const formData = new FormData();
    formData.append("file", new File(["resume text"], "resume.txt"));

    const result = await apiFetchUpload<{ id: string }>("/jobs/ingest-upload", formData);

    expect(result).toEqual({ id: "job-1", status: "pending" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/jobs/ingest-upload");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(formData);
    // No headers object at all — letting fetch compute Content-Type
    // (including the multipart boundary) from the FormData body itself is
    // the whole point; passing any explicit header here would break that.
    expect(init.headers).toBeUndefined();
  });

  it("throws an ApiError with category/message from the {error:...} envelope on failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => ({ error: { category: "ParsingError", message: "Unsupported file type." } }),
      }),
    );

    await expect(apiFetchUpload("/jobs/ingest-upload", new FormData())).rejects.toMatchObject({
      name: "ApiError",
      category: "ParsingError",
      message: "Unsupported file type.",
      status: 502,
    });
  });
});

describe("apiFetchBlob", () => {
  it("returns the blob and the filename parsed from Content-Disposition", async () => {
    const blob = new Blob(["hello"]);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "Content-Disposition": 'attachment; filename="cv.pdf"' }),
        blob: async () => blob,
      }),
    );

    const result = await apiFetchBlob("/export");

    expect(result.blob).toBe(blob);
    expect(result.filename).toBe("cv.pdf");
  });

  it("still parses the JSON error envelope on failure, not a blob", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ error: { category: "ExportError", message: "PDF too large." } }),
      }),
    );

    await expect(apiFetchBlob("/export")).rejects.toMatchObject({
      category: "ExportError",
      message: "PDF too large.",
    });
  });
});
