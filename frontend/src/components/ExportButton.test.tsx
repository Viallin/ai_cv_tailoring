import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AssembledCV } from "@/api/models";
import { NO_TEMPLATE_ID } from "@/lib/cvTemplates";
import type { DocumentModel } from "@/lib/structuredDocument";
import { ExportButton } from "./ExportButton";

const CV: AssembledCV = { name: "Ada Lovelace", language: "en", summary: "Original summary." };
const EDITED_DOCUMENT: DocumentModel = {
  sections: [
    {
      key: "summary",
      title: "Summary",
      included: true,
      entries: [{ id: "summary", text: "An edited summary the user just typed.", included: true }],
    },
  ],
};

function renderWithQueryClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
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
  // jsdom doesn't implement real navigation — silence the resulting
  // "Not implemented" console noise from the download anchor's .click().
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  return fetchMock;
}

// The invariant this pins: export always sends whatever is CURRENTLY in
// the structured document, never a value re-derived from `assembledCv` —
// the same "edited text is never re-parsed" rule ui/main_window.py's
// export dispatch follows.
describe("ExportButton", () => {
  it("sends the current (edited) document, not the original assembledCv content, and 'none' as no template_id", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchBlobResponse();

    renderWithQueryClient(
      <ExportButton
        assembledCv={CV}
        cvDocument={EDITED_DOCUMENT}
        templateId={NO_TEMPLATE_ID}
        onTemplateIdChange={vi.fn()}
        format="pdf"
        onFormatChange={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Export CV/ }));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.document).toEqual(EDITED_DOCUMENT);
    expect(body.assembled_cv.summary).toBe("Original summary.");
    expect(body.format).toBe("pdf");
    // The lifted-up Template selection (now owned by DraftScreen, not
    // this component — see its own docstring) converts NO_TEMPLATE_ID to
    // `undefined` before hitting the export API.
    expect(body.template_id).toBeUndefined();
  });

  it("sends the selected template's id when one other than 'none' is chosen", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchBlobResponse();

    renderWithQueryClient(
      <ExportButton
        assembledCv={CV}
        cvDocument={EDITED_DOCUMENT}
        templateId="classic"
        onTemplateIdChange={vi.fn()}
        format="pdf"
        onFormatChange={vi.fn()}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Export CV/ }));

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.template_id).toBe("classic");
  });

  it("is disabled until both an AssembledCV and a document exist", () => {
    const { rerender } = renderWithQueryClient(
      <ExportButton
        assembledCv={null}
        cvDocument={null}
        templateId={NO_TEMPLATE_ID}
        onTemplateIdChange={vi.fn()}
        format="pdf"
        onFormatChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /Export CV/ })).toBeDisabled();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ExportButton
          assembledCv={CV}
          cvDocument={null}
          templateId={NO_TEMPLATE_ID}
          onTemplateIdChange={vi.fn()}
          format="pdf"
          onFormatChange={vi.fn()}
        />
      </QueryClientProvider>,
    );
    expect(screen.getByRole("button", { name: /Export CV/ })).toBeDisabled();
  });

  it("is enabled once both an AssembledCV and a document exist", () => {
    renderWithQueryClient(
      <ExportButton
        assembledCv={CV}
        cvDocument={EDITED_DOCUMENT}
        templateId={NO_TEMPLATE_ID}
        onTemplateIdChange={vi.fn()}
        format="pdf"
        onFormatChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /Export CV/ })).not.toBeDisabled();
  });
});
