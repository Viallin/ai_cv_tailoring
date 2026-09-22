import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchPageBreaks, useExportCv } from "./export";
import type { AssembledCV } from "./models";
import type { DocumentModel } from "@/lib/structuredDocument";

const CV: AssembledCV = { name: "Ada Lovelace", language: "en", summary: "Engineer." };
const DOCUMENT: DocumentModel = {
  sections: [
    { key: "summary", title: "Summary", included: true, entries: [{ id: "summary", text: "Engineer.", included: true }] },
  ],
};

function makeWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function mockFetchBlobResponse() {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    headers: new Headers({ "Content-Disposition": 'attachment; filename="cv.pdf"' }),
    blob: async () => new Blob(["%PDF"]),
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("URL", { createObjectURL: vi.fn(() => "blob:mock"), revokeObjectURL: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  return fetchMock;
}

describe("useExportCv", () => {
  it("always sends document, and omits template_id when not provided (plain export)", async () => {
    const fetchMock = mockFetchBlobResponse();
    const { result } = renderHook(() => useExportCv(), { wrapper: makeWrapper() });

    result.current.mutate({ assembledCv: CV, document: DOCUMENT, format: "pdf" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.document).toEqual(DOCUMENT);
    expect(body.template_id).toBeUndefined();
  });

  it("includes template_id in the request body when provided (templated export)", async () => {
    const fetchMock = mockFetchBlobResponse();
    const { result } = renderHook(() => useExportCv(), { wrapper: makeWrapper() });

    result.current.mutate({
      assembledCv: CV,
      document: DOCUMENT,
      format: "pdf",
      templateId: "classic",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.template_id).toBe("classic");
    expect(body.document).toEqual(DOCUMENT);
  });
});

describe("fetchPageBreaks", () => {
  it("POSTs assembled_cv/document/template_id and resolves with the parsed breaks", async () => {
    const breaks = [{ kind: "line", element_id: "exp-1", page: 2 }];
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => breaks });
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchPageBreaks(CV, DOCUMENT, "classic");

    expect(result).toEqual(breaks);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/export/page-breaks");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body.assembled_cv).toEqual(CV);
    expect(body.document).toEqual(DOCUMENT);
    expect(body.template_id).toBe("classic");
  });

  it("omits template_id when null (plain/ATS-safe)", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);

    await fetchPageBreaks(CV, DOCUMENT, null);

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.template_id).toBeUndefined();
  });

  it("rejects with an ApiError on a failed response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ error: { category: "RequestValidationError", message: "Invalid document." } }),
    }));

    await expect(fetchPageBreaks(CV, DOCUMENT, null)).rejects.toMatchObject({
      category: "RequestValidationError",
      message: "Invalid document.",
    });
  });
});
