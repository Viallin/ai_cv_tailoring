import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AssembledCV, BulletProvenanceReport } from "@/api/models";
import { NO_TEMPLATE_ID } from "@/lib/cvTemplates";
import type { DocumentModel } from "@/lib/structuredDocument";
import { DocumentEditor, type DocumentEditorHandle } from "./DocumentEditor";

// Phase 26 — Tiptap's ReactNodeViewRenderer mounts each node's actual
// React content (checkbox, text span, Sparkles, …) via a queued portal,
// not synchronously during the triggering render/rerender/act() (see its
// own "ProseMirror maps the selection before the queued portal render"
// comment) — a raw contentDOM placeholder briefly exists in the DOM
// first. Every query below that follows a render, rerender, or a
// content-replacing mutation therefore uses `findBy*` (which polls) for
// its *first* touch of freshly-(re)mounted content, not a synchronous
// `getBy*` — this is a real async-mount gap, not a flakiness workaround.

const CV: AssembledCV = {
  name: "Ada Lovelace",
  summary: "Engineer with a track record of shipping things.",
  contacts: [{ id: "c1", label: "Email", value: "ada@example.com" }],
  experience: [
    { experience_id: "exp-1", position: "Engineer", company: "Acme", is_gap: false, bullets: [] },
  ],
  education: [{ id: "edu-1", institution: "State University" }],
} as unknown as AssembledCV;

function jsonResponse(body: unknown) {
  return { ok: true, json: async () => body };
}

function renderWithQueryClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("DocumentEditor", () => {
  it("shows a placeholder when there's no assembled CV yet", () => {
    renderWithQueryClient(<DocumentEditor assembledCv={null} />);
    expect(screen.getByText("Generate a CV to preview it here.")).toBeInTheDocument();
  });

  it("renders the document once an assembledCv is given", async () => {
    renderWithQueryClient(<DocumentEditor assembledCv={CV} />);

    expect(await screen.findByText(/Engineer — Acme/)).toBeInTheDocument();
    expect(screen.getByText("State University")).toBeInTheDocument();
  });

  it("renders the header (name), not just the sections", () => {
    // Regression guard: the on-screen A4 Preview previously had no header
    // at all (only the exported PDF/DOCX did) — CvPrintHeader must be
    // rendered here too. Plain React (not a Tiptap NodeView), so no
    // async-portal wait needed.
    renderWithQueryClient(<DocumentEditor assembledCv={CV} />);

    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("renders Contacts as its own editable section, each contact individually includable", async () => {
    // Contacts moved out of the read-only header into a real section
    // (like every other CV fact) so a contact can be excluded per
    // application — same editable-row shape every other section gets
    // (EntryHeadingNodeView, Phase 26). A real contentEditable paragraph,
    // not a clickable link — see linkify.test.tsx for the plain-text
    // linkify coverage.
    renderWithQueryClient(<DocumentEditor assembledCv={CV} />);

    expect(await screen.findByText("Contacts")).toBeInTheDocument();
    expect(screen.getByText("Email: ada@example.com")).toBeInTheDocument();
  });

  it("re-derives the document when a different assembledCv arrives", async () => {
    const { rerender } = renderWithQueryClient(<DocumentEditor assembledCv={CV} />);
    expect(await screen.findByText("State University")).toBeInTheDocument();

    const otherCv: AssembledCV = {
      ...CV,
      education: [{ id: "edu-2", institution: "Other University" }],
    };
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <DocumentEditor assembledCv={otherCv} />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Other University")).toBeInTheDocument();
    expect(screen.queryByText("State University")).not.toBeInTheDocument();
  });

  it("defaults to the first template when templateId is omitted, applied via the page's data-template attribute", () => {
    // The Template picker itself now lives outside this component (in
    // ExportButton, controlled from DraftScreen — see this component's
    // `templateId` prop docstring) so there's no Select here to exercise
    // interactively any more. This just pins the standalone/no-prop
    // fallback; explicit-templateId behavior is covered below.
    const { container } = renderWithQueryClient(<DocumentEditor assembledCv={CV} />);

    expect(container.querySelector(".cv-a4-page")).toHaveAttribute("data-template", "classic");
  });

  it("renders with the given templateId, applied via the page's data-template attribute", () => {
    const { container } = renderWithQueryClient(<DocumentEditor assembledCv={CV} templateId="modern" />);

    expect(container.querySelector(".cv-a4-page")).toHaveAttribute("data-template", "modern");
  });

  it("renders the plain/ATS-safe style (no CSS vars applied) when templateId is 'none'", () => {
    const { container } = renderWithQueryClient(<DocumentEditor assembledCv={CV} templateId="none" />);

    expect(container.querySelector(".cv-a4-page")).toHaveAttribute("data-template", "none");
  });

  it("calls onModelChange with the built document once an assembledCv is given", () => {
    const onModelChange = vi.fn();
    renderWithQueryClient(<DocumentEditor assembledCv={CV} onModelChange={onModelChange} />);

    expect(onModelChange).toHaveBeenCalled();
    const lastModel = onModelChange.mock.calls.at(-1)?.[0] as DocumentModel;
    expect(lastModel.sections.some((s) => s.key === "education")).toBe(true);
  });

  it("calls onModelChange with null when there's no assembledCv", () => {
    const onModelChange = vi.fn();
    renderWithQueryClient(<DocumentEditor assembledCv={null} onModelChange={onModelChange} />);

    expect(onModelChange).toHaveBeenCalledWith(null);
  });

  it("calls onModelChange again after an edit (toggling a section off)", async () => {
    const user = userEvent.setup();
    const onModelChange = vi.fn();
    renderWithQueryClient(<DocumentEditor assembledCv={CV} onModelChange={onModelChange} />);

    const checkbox = await screen.findByRole("checkbox", { name: /Include Summary section/ });
    const callsBeforeEdit = onModelChange.mock.calls.length;
    await user.click(checkbox);

    expect(onModelChange.mock.calls.length).toBeGreaterThan(callsBeforeEdit);
    const lastModel = onModelChange.mock.calls.at(-1)?.[0] as DocumentModel;
    const summary = lastModel.sections.find((s) => s.key === "summary");
    expect(summary?.included).toBe(false);
  });

  it("clicking + Add Bullet on a role adds a blank, editable bullet", async () => {
    const user = userEvent.setup();
    const onModelChange = vi.fn();
    renderWithQueryClient(<DocumentEditor assembledCv={CV} onModelChange={onModelChange} />);

    const addBulletButton = await screen.findByRole("button", { name: "+ Add Bullet" });
    await user.click(addBulletButton);

    const lastModel = onModelChange.mock.calls.at(-1)?.[0] as DocumentModel;
    const experience = lastModel.sections.find((s) => s.key === "experience")!;
    expect(experience.entries[0].bullets).toHaveLength(1);
    expect(experience.entries[0].bullets![0].text).toBe("");
  });

  it("exposes addBulletFromEvidence via ref, for Unused Evidence's Add to Role action", async () => {
    const onModelChange = vi.fn();
    const ref = createRef<DocumentEditorHandle>();
    renderWithQueryClient(<DocumentEditor ref={ref} assembledCv={CV} onModelChange={onModelChange} />);
    await screen.findByText(/Engineer — Acme/); // wait for the initial mount to settle first

    act(() => {
      ref.current!.addBulletFromEvidence("exp-1", "Led a cross-functional initiative.", "ev-9");
    });

    const lastModel = onModelChange.mock.calls.at(-1)?.[0] as DocumentModel;
    const experience = lastModel.sections.find((s) => s.key === "experience")!;
    expect(experience.entries[0].bullets).toHaveLength(1);
    expect(experience.entries[0].bullets![0]).toMatchObject({
      text: "Led a cross-functional initiative.",
      evidence_id: "ev-9",
      included: true,
    });
    expect(await screen.findByText("Led a cross-functional initiative.")).toBeInTheDocument();
  });

  // ----- Phase 24: ExcludedContentPanel's "Restore" action ------------------
  //
  // Phase 26: excluded content stays a real (if hidden) part of the
  // ProseMirror doc rather than being removed from the DOM (see
  // lib/tiptap/plugins.ts's own docstring), so these assert the `hidden`
  // class toggling on the excluded node's own wrapper instead of the old
  // "the field is gone from the document entirely" — the DocumentModel
  // (via onModelChange) stays the authoritative "is it actually excluded"
  // check either way.

  it("exposes restoreContent via ref — round-trips exclude (via checkbox) then restore (via ref)", async () => {
    const user = userEvent.setup();
    const onModelChange = vi.fn();
    const ref = createRef<DocumentEditorHandle>();
    renderWithQueryClient(<DocumentEditor ref={ref} assembledCv={CV} onModelChange={onModelChange} />);

    const heading = (await screen.findByText("State University")).closest("p")!;
    const entryContainer = heading.closest(".cv-print-entry")!;
    // Phase 28 — the checkbox now lives in the floating DocumentGutter, a
    // completely separate part of the tree from `.cv-print-entry`, so it
    // can no longer be found via DOM containment — its aria-label folds
    // in the entry's own heading text specifically to stay findable (and
    // distinguishable from every other entry's checkbox) this way.
    await user.click(await screen.findByRole("checkbox", { name: /Include this entry: State University/ }));

    expect(entryContainer).toHaveClass("hidden");
    let lastModel = onModelChange.mock.calls.at(-1)?.[0] as DocumentModel;
    expect(lastModel.sections.find((s) => s.key === "education")!.entries[0].included).toBe(false);

    act(() => {
      ref.current!.restoreContent("education", "edu-1");
    });

    expect((await screen.findByText("State University")).closest(".cv-print-entry")).not.toHaveClass("hidden");
    lastModel = onModelChange.mock.calls.at(-1)?.[0] as DocumentModel;
    expect(lastModel.sections.find((s) => s.key === "education")!.entries[0].included).toBe(true);
  });

  it("exposes restoreContent via ref — round-trips an excluded bullet the same way", async () => {
    const user = userEvent.setup();
    const onModelChange = vi.fn();
    const ref = createRef<DocumentEditorHandle>();
    renderWithQueryClient(<DocumentEditor ref={ref} assembledCv={CV} onModelChange={onModelChange} />);
    await screen.findByText(/Engineer — Acme/); // wait for the initial mount to settle first

    act(() => {
      ref.current!.addBulletFromEvidence("exp-1", "Led a cross-functional initiative.", "ev-9");
    });
    // The bullet's id isn't derivable from the DOM alone (it's a
    // crypto.randomUUID() minted inside addBullet) — read it back from
    // the model onModelChange just handed us instead of guessing it.
    const modelAfterAdd = onModelChange.mock.calls.at(-1)?.[0] as DocumentModel;
    const bulletId = modelAfterAdd.sections.find((s) => s.key === "experience")!.entries[0].bullets![0].id;

    const bulletRow = (await screen.findByText("Led a cross-functional initiative.")).closest("p")!;
    // Phase 28 — same DocumentGutter relocation as the entry checkbox
    // above; found by its own (now text-bearing) aria-label instead of
    // DOM containment.
    await user.click(await screen.findByRole("checkbox", { name: /Include this bullet: Led a cross-functional initiative/ }));
    expect(bulletRow).toHaveClass("hidden");

    act(() => {
      ref.current!.restoreContent("experience", "exp-1", bulletId);
    });
    expect((await screen.findByText("Led a cross-functional initiative.")).closest("p")).not.toHaveClass("hidden");
  });
});

// ----- Phase 28: floating gutter -------------------------------------------

describe("DocumentEditor — Phase 28 floating gutter", () => {
  it("renders a section's, an entry's, and a bullet's checkbox outside the printed content tree, not nested inside it", async () => {
    renderWithQueryClient(<DocumentEditor assembledCv={CV} />);

    const entryContainer = (await screen.findByText("State University")).closest(".cv-print-entry")!;
    // The regression this guards against: a checkbox left behind inside
    // .cv-print-entry/.cv-print-bullet would mean the relocation to
    // DocumentGutter didn't actually happen, even if clicking "a"
    // checkbox elsewhere still passed every other test here.
    expect(entryContainer.querySelector('[role="checkbox"]')).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Include this entry: State University/ })).toBeInTheDocument();

    const summarySection = (await screen.findByText("Summary")).closest("section")!;
    expect(summarySection.querySelector('[role="checkbox"]')).not.toBeInTheDocument();
  });

  it("excluding a whole section hides its entries' gutter checkboxes too, not just their content", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(<DocumentEditor assembledCv={CV} />);

    await screen.findByRole("checkbox", { name: /Include this entry: State University/ }); // present while Education is included
    await user.click(screen.getByRole("checkbox", { name: "Include Education section" }));

    expect(screen.queryByRole("checkbox", { name: /Include this entry: State University/ })).not.toBeInTheDocument();
    // The section's own checkbox stays — a fully-excluded section is
    // still toggleable back on (Phase 24/26's own established rule).
    expect(screen.getByRole("checkbox", { name: "Include Education section" })).toBeInTheDocument();
  });
});

// ----- Phase 28 (follow-up): hover-only checkboxes -------------------------
//
// Reported directly: a checkbox on every row, all the time, made it hard
// to tell which bullets were even there — exclude is the rare action, so
// the checkbox itself shouldn't be the dominant visual signal. Sparkles
// deliberately stays untouched (see DocumentGutter.tsx's own comment) —
// these tests only cover the checkbox's own visibility.

describe("DocumentEditor — Phase 28 (follow-up) hover-only checkboxes", () => {
  it("a checkbox starts hidden and becomes visible when its own row is hovered", async () => {
    renderWithQueryClient(<DocumentEditor assembledCv={CV} />);

    const heading = await screen.findByText("State University");
    const row = heading.closest(".cv-print-entry")!.previousElementSibling!; // EntryNodeView's own chrome div, see its own comment
    const checkbox = await screen.findByRole("checkbox", { name: /Include this entry: State University/ });

    expect(checkbox).toHaveClass("opacity-0");

    fireEvent.mouseEnter(row);
    expect(checkbox).toHaveClass("opacity-100");
  });

  it("hides again once the mouse leaves, after a short grace period rather than immediately", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderWithQueryClient(<DocumentEditor assembledCv={CV} />);

    const heading = await screen.findByText("State University");
    const row = heading.closest(".cv-print-entry")!.previousElementSibling!;
    const checkbox = await screen.findByRole("checkbox", { name: /Include this entry: State University/ });

    fireEvent.mouseEnter(row);
    expect(checkbox).toHaveClass("opacity-100");

    fireEvent.mouseLeave(row);
    expect(checkbox).toHaveClass("opacity-100"); // still visible immediately after leaving — the grace period exists precisely to bridge the gap to the gutter's own checkbox
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(checkbox).toHaveClass("opacity-0");
  });

  it("hovering the checkbox's own row inside the gutter (not just the row in the page) also keeps it visible", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderWithQueryClient(<DocumentEditor assembledCv={CV} />);

    await screen.findByText("State University");
    const checkbox = await screen.findByRole("checkbox", { name: /Include this entry: State University/ });
    const gutterRow = checkbox.parentElement!; // DocumentGutter's own per-item row wrapper

    fireEvent.mouseEnter(gutterRow);
    expect(checkbox).toHaveClass("opacity-100");
    fireEvent.mouseLeave(gutterRow);
    act(() => {
      vi.advanceTimersByTime(200);
    });
    expect(checkbox).toHaveClass("opacity-0");
  });

  // The "stays visible while the text cursor is inside it" half (driven
  // by editor.on("selectionUpdate") -> computeActiveGutterItemId) isn't
  // covered at this level — real caret placement isn't reliable under
  // jsdom (no document.elementFromPoint; a raw click into contentEditable
  // is documented elsewhere in this file as unsafe here), and this
  // component doesn't expose its editor instance externally the way
  // lib/tiptap's own headless-Editor tests do. computeActiveGutterItemId
  // itself (the pure "which row is this position inside" query) has its
  // own direct coverage in useNodeAncestry.test.ts; the wiring from a
  // real selection change to the checkbox's opacity is a live-
  // verification-only concern, same precedent as every position-related
  // fact in this phase.
});

// ----- Phase 20: initialDocument (reopening a saved CVDraft) --------------

const EDITED_DOCUMENT: DocumentModel = {
  sections: [
    {
      key: "education",
      title: "Education",
      included: true,
      entries: [{ id: "edu-1", text: "A hand-edited education line.", included: true }],
    },
  ],
};

describe("DocumentEditor — Phase 20 initialDocument", () => {
  it("seeds from initialDocument instead of rebuilding from assembledCv, when given", async () => {
    renderWithQueryClient(<DocumentEditor assembledCv={CV} initialDocument={EDITED_DOCUMENT} />);

    expect(await screen.findByText("A hand-edited education line.")).toBeInTheDocument();
    expect(screen.queryByText("State University")).not.toBeInTheDocument();
  });

  it("still rebuilds from assembledCv as before when initialDocument is omitted", async () => {
    renderWithQueryClient(<DocumentEditor assembledCv={CV} />);
    expect(await screen.findByText("State University")).toBeInTheDocument();
  });

  it("only seeds from initialDocument once — a later identity change (e.g. a background refetch) never resets in-progress edits", async () => {
    const user = userEvent.setup();
    const onModelChange = vi.fn();
    const { rerender } = renderWithQueryClient(
      <DocumentEditor assembledCv={CV} initialDocument={EDITED_DOCUMENT} onModelChange={onModelChange} />,
    );

    // A real edit via a real interaction (not a raw keystroke — jsdom has
    // no real Selection/Range tied to layout; see lib/tiptap's own test
    // files for where actual typing/split/join behavior is exercised,
    // via a headless Editor instance instead): exclude the seeded entry.
    const heading = (await screen.findByText("A hand-edited education line.")).closest("p")!;
    const entryContainer = heading.closest(".cv-print-entry")!;
    await user.click(await screen.findByRole("checkbox", { name: /Include this entry: A hand-edited education line\./ }));
    expect(entryContainer).toHaveClass("hidden");

    // A new object reference, same content — the shape of what a
    // background query refetch would hand back.
    const sameContentNewReference: DocumentModel = JSON.parse(JSON.stringify(EDITED_DOCUMENT));
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <DocumentEditor assembledCv={CV} initialDocument={sameContentNewReference} onModelChange={onModelChange} />
      </QueryClientProvider>,
    );

    // Still excluded — the rerender's initialDocument (a fresh reference
    // of the *original*, still-included seed) never overwrote the edit.
    expect((await screen.findByText("A hand-edited education line.")).closest(".cv-print-entry")).toHaveClass(
      "hidden",
    );
  });
});

// ----- Phase 31 (follow-up): AI-edit provenance popover redesign ---------

const REWRITTEN_DOCUMENT: DocumentModel = {
  sections: [
    {
      key: "experience",
      title: "Experience",
      included: true,
      entries: [
        {
          id: "exp-1",
          text: "Engineer — Acme",
          included: true,
          bullets: [{ id: "b1", text: "Rewritten bullet text.", included: true, evidence_id: "ev-1" }],
        },
      ],
    },
  ],
};

const REWRITE_PROVENANCE: BulletProvenanceReport = {
  bullets: [
    {
      evidence_id: "ev-1",
      original_text: "Original bullet text.",
      rewritten_text: "Rewritten bullet text.",
      action: "rewrite",
      rationale: "Made it punchier.",
      locked: false,
    },
  ],
};

describe("DocumentEditor — Phase 31 (follow-up) AI-edit provenance popover", () => {
  it("opens on the Sparkles trigger, shows Original before the rationale, and Revert to original restores the bullet's text", async () => {
    const user = userEvent.setup();
    const onModelChange = vi.fn();
    renderWithQueryClient(
      <DocumentEditor
        assembledCv={CV}
        initialDocument={REWRITTEN_DOCUMENT}
        provenance={REWRITE_PROVENANCE}
        onModelChange={onModelChange}
      />,
    );

    await user.click(await screen.findByRole("button", { name: "AI-edited bullet — view original text and rationale" }));

    expect(await screen.findByText("Rewritten")).toBeInTheDocument();
    const original = screen.getByText("Original bullet text.");
    const rationale = screen.getByText("Made it punchier.");
    // DOCUMENT_POSITION_FOLLOWING means the first node comes *before* the
    // second — confirms Original renders above the rationale, the order
    // this follow-up swapped (was rationale-then-Original before).
    expect(original.compareDocumentPosition(rationale) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Revert to original" }));

    const lastModel = onModelChange.mock.calls.at(-1)?.[0] as DocumentModel;
    const bullet = lastModel.sections[0].entries[0].bullets?.[0];
    expect(bullet?.text).toBe("Original bullet text.");
  });

  it("closes via the explicit close button", async () => {
    const user = userEvent.setup();
    renderWithQueryClient(
      <DocumentEditor assembledCv={CV} initialDocument={REWRITTEN_DOCUMENT} provenance={REWRITE_PROVENANCE} />,
    );

    await user.click(await screen.findByRole("button", { name: "AI-edited bullet — view original text and rationale" }));
    expect(await screen.findByText("Original bullet text.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByText("Original bullet text.")).not.toBeInTheDocument();
  });
});

// ----- Summary's own AI-edit provenance popover --------------------------

const SUMMARY_DOCUMENT: DocumentModel = {
  sections: [
    {
      key: "summary",
      title: "Summary",
      included: true,
      entries: [{ id: "summary", text: "Rewritten summary text.", included: true }],
    },
  ],
};

const SUMMARY_PROVENANCE: BulletProvenanceReport = {
  bullets: [],
  summary: { original_text: "Original summary text.", rewritten_text: "Rewritten summary text." },
};

describe("DocumentEditor — summary AI-edit provenance popover", () => {
  it("opens on the Sparkles trigger, shows Original, and Revert to original restores the summary's text", async () => {
    const user = userEvent.setup();
    const onModelChange = vi.fn();
    renderWithQueryClient(
      <DocumentEditor
        assembledCv={CV}
        initialDocument={SUMMARY_DOCUMENT}
        provenance={SUMMARY_PROVENANCE}
        onModelChange={onModelChange}
      />,
    );

    await user.click(
      await screen.findByRole("button", { name: "AI-edited summary — view original text and revert" }),
    );

    expect(await screen.findByText("Rewritten")).toBeInTheDocument();
    expect(screen.getByText("Original summary text.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Revert to original" }));

    const lastModel = onModelChange.mock.calls.at(-1)?.[0] as DocumentModel;
    expect(lastModel.sections[0].entries[0].text).toBe("Original summary text.");
  });

  it("shows no Sparkles trigger when the summary has no provenance to compare against", async () => {
    renderWithQueryClient(<DocumentEditor assembledCv={CV} initialDocument={SUMMARY_DOCUMENT} />);

    await screen.findByText("Rewritten summary text.");
    expect(
      screen.queryByRole("button", { name: "AI-edited summary — view original text and revert" }),
    ).not.toBeInTheDocument();
  });

  it("shows no Sparkles trigger once the live text is hand-edited back to the original", async () => {
    renderWithQueryClient(
      <DocumentEditor
        assembledCv={CV}
        initialDocument={{
          sections: [
            {
              key: "summary",
              title: "Summary",
              included: true,
              entries: [{ id: "summary", text: "Original summary text.", included: true }],
            },
          ],
        }}
        provenance={SUMMARY_PROVENANCE}
      />,
    );

    await screen.findByText("Original summary text.");
    expect(
      screen.queryByRole("button", { name: "AI-edited summary — view original text and revert" }),
    ).not.toBeInTheDocument();
  });
});

// On-screen page-break-prediction fix (follow-up to Version 4, Phase
// 4.9) — PageBreakGuide.tsx now asks the real backend renderer where
// pages break instead of approximating from the DOM, debounced. Tested
// through the full DocumentEditor (not PageBreakGuide in isolation) —
// it needs a real Tiptap Editor instance and a page element with the
// real data-entry-id/data-section-key attributes DocumentEditor's own
// NodeViews render, which this file's existing harness already provides.
describe("PageBreakGuide (on-screen page-break prediction)", () => {
  it("fetches real page breaks (debounced) and draws a line at the matching element", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([{ kind: "line", element_id: "exp-1", page: 2 }]));
    vi.stubGlobal("fetch", fetchMock);

    // NO_TEMPLATE_ID ("none") — DocumentEditor otherwise defaults
    // templateId to DEFAULT_TEMPLATE_ID ("classic"), which would send a
    // real template_id and muddy this test's own "the request body is
    // shaped correctly" purpose; the plain/ATS-safe-vs-template
    // distinction has its own dedicated test below.
    renderWithQueryClient(<DocumentEditor assembledCv={CV} templateId={NO_TEMPLATE_ID} />);
    await screen.findByText(/Engineer — Acme/);

    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(await screen.findByText("↓ Page 2")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/export/page-breaks");
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body.assembled_cv.name).toBe("Ada Lovelace");
    expect(body.document.sections).toBeInstanceOf(Array);
    expect(body.template_id).toBeUndefined(); // "none" maps to the plain/ATS-safe path (no template_id sent)
  });

  it("skips a returned break whose element isn't found in the DOM, without throwing", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse([{ kind: "line", element_id: "does-not-exist", page: 2 }])),
    );

    renderWithQueryClient(<DocumentEditor assembledCv={CV} />);
    await screen.findByText(/Engineer — Acme/);

    act(() => {
      vi.advanceTimersByTime(500);
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByText(/↓ Page/)).not.toBeInTheDocument();
  });

  it("does not fetch, and shows a disclaimer instead of a guide, for docx", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(<DocumentEditor assembledCv={CV} exportFormat="docx" />);
    await screen.findByText(/Engineer — Acme/);
    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText(/Page breaks are approximate for Word/)).toBeInTheDocument();
  });

  it("does not fetch and renders nothing for md", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(<DocumentEditor assembledCv={CV} exportFormat="md" />);
    await screen.findByText(/Engineer — Acme/);
    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByText(/Page breaks are approximate/)).not.toBeInTheDocument();
  });

  it("sends the selected template id", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(<DocumentEditor assembledCv={CV} templateId="classic" />);
    await screen.findByText(/Engineer — Acme/);
    act(() => {
      vi.advanceTimersByTime(500);
    });
    await act(async () => {
      await Promise.resolve();
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.template_id).toBe("classic");
  });
});
