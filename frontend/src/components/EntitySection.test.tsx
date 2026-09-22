import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Evidence } from "@/api/models";
import { ENTITY_CONFIGS } from "@/lib/entityConfigs";
import {
  deriveCategories,
  EntitySection,
  groupItemsByHeader,
  reorderEntityItems,
  type EntityItem,
} from "./EntitySection";

const skillsConfig = ENTITY_CONFIGS.find((config) => config.pathSegment === "skills")!;
const educationConfig = ENTITY_CONFIGS.find((config) => config.pathSegment === "education")!;
const contactsConfig = ENTITY_CONFIGS.find((config) => config.pathSegment === "contacts")!;

function renderWithQueryClient(ui: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("EntitySection", () => {
  it("renders a summarized row per item", () => {
    // educationConfig, not skillsConfig: skills/technologies now render
    // read-only rows via the grouped category-header view (see the
    // "category headers" describe block below), not config.summarize.
    const items: EntityItem[] = [{ id: "edu-1", institution: "MIT", degree: "BSc", field: "Math" }];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={educationConfig} title="Education" items={items} />);

    expect(screen.getByText("MIT — BSc, Math")).toBeInTheDocument();
  });

  it("turns a Contact's email/URL value into a clickable link, read-only row", () => {
    const items: EntityItem[] = [
      { id: "c1", label: "Email", value: "ada@example.com" },
      { id: "c2", label: "Phone", value: "+1 555 0100" },
      // Bare domain, no http(s)/www prefix — a real resume's own format.
      { id: "c3", label: "LinkedIn", value: "linkedin.com/in/ada" },
    ];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={contactsConfig} title="Contacts" items={items} />);

    expect(screen.getByRole("link", { name: "ada@example.com" })).toHaveAttribute(
      "href",
      "mailto:ada@example.com",
    );
    expect(screen.getByRole("link", { name: "linkedin.com/in/ada" })).toHaveAttribute(
      "href",
      "https://linkedin.com/in/ada",
    );
    // A value with no link-shaped content (a phone number) stays plain text.
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("adds a new item via the inline form, sending blank optional fields as null", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => ({ id: "skill-2", name: "SQL" }) });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={[]} />);

    await user.click(screen.getByRole("button", { name: /Add Skill/ }));
    await user.type(screen.getByLabelText("Name"), "SQL");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/skills");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ name: "SQL", proficiency: null });

    // Form closes back to the Add button after a successful save.
    await waitFor(() => expect(screen.getByRole("button", { name: /Add Skill/ })).toBeInTheDocument());
  });

  it("edits an existing item, submitting all fields from the form", async () => {
    // educationConfig, not skillsConfig: this is testing that an untouched
    // field (here, "degree") still gets submitted with the touched one
    // ("field") — skills/technologies no longer have an untouched
    // directly-editable field of that shape now that Category is derived.
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    const items: EntityItem[] = [{ id: "edu-1", institution: "MIT", degree: "BSc" }];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={educationConfig} title="Education" items={items} />);

    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.type(screen.getByLabelText("Field"), "Mathematics");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/education/edu-1");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({
      institution: "MIT",
      degree: "BSc",
      field: "Mathematics",
      period: null,
    });
  });

  it("removes an item after confirming", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 });
    vi.stubGlobal("fetch", fetchMock);
    const items: EntityItem[] = [{ id: "skill-1", name: "Python" }];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
    await user.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/skills/skill-1");
    expect(init.method).toBe("DELETE");
  });

  it("shows a 'Deleting…' state and disables that row's own Delete button while its request is in flight", async () => {
    // Regression: previously the button gave no feedback at all while the
    // request was in flight — a real, reported delete (confirmed to have
    // actually succeeded server-side moments later) looked like it
    // "didn't work" because nothing on screen changed right away.
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    let resolveFetch!: (value: unknown) => void;
    const fetchMock = vi.fn().mockReturnValue(new Promise((resolve) => (resolveFetch = resolve)));
    vi.stubGlobal("fetch", fetchMock);
    const items: EntityItem[] = [{ id: "skill-1", name: "Python" }];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByRole("button", { name: "Deleting…" })).toBeDisabled();

    resolveFetch({ ok: true, status: 204 });
    await waitFor(() => expect(screen.queryByRole("button", { name: "Deleting…" })).not.toBeInTheDocument());
  });

  it("leaves a different row's Delete button untouched while another row's delete is in flight", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn().mockReturnValue(new Promise(() => {})); // never resolves within this test
    vi.stubGlobal("fetch", fetchMock);
    const items: EntityItem[] = [
      { id: "skill-1", name: "Python" },
      { id: "skill-2", name: "Rust" },
    ];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
    const deleteButtons = screen.getAllByRole("button", { name: "Delete" });
    await user.click(deleteButtons[0]);

    expect(await screen.findByRole("button", { name: "Deleting…" })).toBeInTheDocument();
    // The other row's own button is a plain, still-enabled "Delete" —
    // `remove.isPending` is shared across the section, but which item it's
    // *for* is tracked per row via `remove.variables`.
    expect(screen.getByRole("button", { name: "Delete" })).toBeEnabled();
  });

  it("does not remove an item when the confirm dialog is cancelled", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const items: EntityItem[] = [{ id: "skill-1", name: "Python" }];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
    await user.click(screen.getByRole("button", { name: "Delete" }));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows a count summary under a skill row with linked evidence, revealing the list on click", async () => {
    const user = userEvent.setup();
    const items: EntityItem[] = [{ id: "skill-1", name: "Python", evidence_ids: ["ev-1"] }];
    const evidenceById = new Map<string, Evidence>([
      ["ev-1", { id: "ev-1", text: "Led a team of five engineers", source_context: "Acme", locked: false }],
    ]);

    renderWithQueryClient(
      <EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} evidenceById={evidenceById} />,
    );

    expect(screen.getByText("Supported by achievements: 1")).toBeInTheDocument();
    expect(screen.queryByText(/Led a team of five engineers/)).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("Show supporting achievements"));

    // No experience/project to resolve a heading from, and source_context
    // is never rendered directly (it's usually just a restatement of the
    // bullet text) — a bare bullet.
    expect(screen.getByText("Led a team of five engineers")).toBeInTheDocument();
    expect(screen.queryByText(/Acme/)).not.toBeInTheDocument();
  });

  it("groups the popover by company/position/project instead of repeating source_context", async () => {
    const user = userEvent.setup();
    const items: EntityItem[] = [{ id: "skill-1", name: "Python", evidence_ids: ["ev-1", "ev-2", "ev-3"] }];
    const evidenceById = new Map<string, Evidence>([
      [
        "ev-1",
        {
          id: "ev-1",
          text: "Led the backend team",
          source_context: "Acme, Backend: Led the backend team",
          experience_id: "exp-1",
          locked: false,
        },
      ],
      [
        "ev-2",
        {
          id: "ev-2",
          text: "Shipped the payments API",
          source_context: "Acme, Backend: Shipped the payments API",
          experience_id: "exp-1",
          locked: false,
        },
      ],
      ["ev-3", { id: "ev-3", text: "Mentored two juniors", source_context: "General", locked: false }],
    ]);
    const experience = [
      { id: "exp-1", company: "Acme", position: "Engineer", is_gap: false as const },
    ];

    renderWithQueryClient(
      <EntitySection
        candidateId="cand-1"
        config={skillsConfig} title="Skills"
        items={items}
        evidenceById={evidenceById}
        experience={experience}
      />,
    );
    await user.click(screen.getByLabelText("Show supporting achievements"));

    // One heading for both exp-1 items, not repeated per bullet.
    expect(screen.getAllByText("Acme, Engineer")).toHaveLength(1);
    expect(screen.getByText("Led the backend team")).toBeInTheDocument();
    expect(screen.getByText("Shipped the payments API")).toBeInTheDocument();
    // The ungrouped item (no experience_id) still shows, with no heading
    // and no source_context restatement.
    expect(screen.getByText("Mentored two juniors")).toBeInTheDocument();
    expect(screen.queryByText(/General/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Backend: /)).not.toBeInTheDocument();
  });

  it("shows nothing extra in bulk-edit mode for a skill row with linked evidence", async () => {
    const user = userEvent.setup();
    const items: EntityItem[] = [{ id: "skill-1", name: "Python", evidence_ids: ["ev-1"] }];
    const evidenceById = new Map<string, Evidence>([
      ["ev-1", { id: "ev-1", text: "Led a team of five engineers", source_context: "Acme", locked: false }],
    ]);

    renderWithQueryClient(
      <EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} evidenceById={evidenceById} />,
    );
    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.queryByText(/Supported by achievements/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Show supporting achievements")).not.toBeInTheDocument();
  });

  it("renders nothing extra for a config with no evidenceIds accessor, even with evidenceById passed", () => {
    const items: EntityItem[] = [{ id: "edu-1", institution: "State University" }];
    const evidenceById = new Map<string, Evidence>([
      ["ev-1", { id: "ev-1", text: "Should not appear", locked: false }],
    ]);

    renderWithQueryClient(
      <EntitySection candidateId="cand-1" config={educationConfig} title="Education" items={items} evidenceById={evidenceById} />,
    );

    expect(screen.queryByText("Should not appear")).not.toBeInTheDocument();
  });

  // ----- bulk edit-all mode -------------------------------------------------

  it("hides the section-wide Edit button when there are no items to edit", () => {
    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={[]} />);

    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("clicking Edit turns every row into editable fields at once", async () => {
    const user = userEvent.setup();
    const items: EntityItem[] = [
      { id: "skill-1", name: "Python" },
      { id: "skill-2", name: "SQL" },
    ];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getAllByLabelText("Name")).toHaveLength(2);
    expect(screen.getAllByLabelText("Name")[0]).toHaveValue("Python");
    expect(screen.getAllByLabelText("Name")[1]).toHaveValue("SQL");
  });

  it("saving in bulk mode only sends a PUT for rows that actually changed", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    const items: EntityItem[] = [
      { id: "skill-1", name: "Python" },
      { id: "skill-2", name: "SQL" },
    ];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.type(screen.getAllByLabelText(/Proficiency/)[0], "Advanced");
    // Header now shows the bulk Save/Cancel pair, not per-row buttons.
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/skills/skill-1");
    expect(init.method).toBe("PUT");

    // Back to read-only for both rows.
    await waitFor(() => expect(screen.queryByLabelText("Name")).not.toBeInTheDocument());
  });

  it("saves multiple changed rows sequentially, not concurrently, to avoid clobbering the shared candidate blob", async () => {
    // Regression test: every entity lives inside the same whole-Candidate
    // JSON blob row, and each PUT is its own independent read-mutate-write
    // round trip with no locking — firing them concurrently (the original
    // Promise.all) let a later request's stale read overwrite an earlier
    // request's already-persisted write. Asserting the second PUT only
    // fires after the first one's response has resolved is what would have
    // caught that regression.
    const user = userEvent.setup();
    let resolveFirst: (() => void) | undefined;
    const firstResponse = new Promise<void>((resolve) => {
      resolveFirst = resolve;
    });
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (url === "/api/candidates/cand-1/skills/skill-1") {
        await firstResponse;
      }
      return { ok: true, json: async () => ({}) };
    });
    vi.stubGlobal("fetch", fetchMock);
    const items: EntityItem[] = [
      { id: "skill-1", name: "Python" },
      { id: "skill-2", name: "SQL" },
    ];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.type(screen.getAllByLabelText(/Proficiency/)[0], "Advanced");
    await user.type(screen.getAllByLabelText(/Proficiency/)[1], "Beginner");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    // The second row's PUT must not have fired yet — the first is still pending.
    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolveFirst?.();

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [secondUrl] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(secondUrl).toBe("/api/candidates/cand-1/skills/skill-2");
  });

  it("Cancel discards edits on every row without saving anything", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const items: EntityItem[] = [{ id: "skill-1", name: "Python" }];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.type(screen.getByLabelText(/Proficiency/), "Advanced");
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
  });

  it("Delete stays available and works immediately while the section is in bulk-edit mode", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204 });
    vi.stubGlobal("fetch", fetchMock);
    const items: EntityItem[] = [{ id: "skill-1", name: "Python" }];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/candidates/cand-1/skills/skill-1");
    expect(init.method).toBe("DELETE");
  });

  it("+ Add stays available and independent while the section is in bulk-edit mode", async () => {
    const user = userEvent.setup();
    const items: EntityItem[] = [{ id: "skill-1", name: "Python" }];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    await user.click(screen.getByRole("button", { name: /Add Skill/ }));

    // The existing row's bulk-edit field and the new-item form's own field
    // both render "Name" labels — one for the existing row, one for the
    // add form — without clashing ids.
    expect(screen.getAllByLabelText("Name")).toHaveLength(2);
  });

  // ----- drag-reorder ----------------------------------------------------

  it("reorderEntityItems moves an item to the target position without mutating the input", () => {
    const items: EntityItem[] = [
      { id: "skill-1", name: "Python" },
      { id: "skill-2", name: "SQL" },
      { id: "skill-3", name: "Go" },
    ];

    const result = reorderEntityItems(items, "skill-1", "skill-3");

    expect(result.map((i) => i.id)).toEqual(["skill-2", "skill-3", "skill-1"]);
    expect(items.map((i) => i.id)).toEqual(["skill-1", "skill-2", "skill-3"]); // input untouched
  });

  it("reorderEntityItems returns the items unchanged if either id can't be found", () => {
    const items: EntityItem[] = [
      { id: "skill-1", name: "Python" },
      { id: "skill-2", name: "SQL" },
    ];

    expect(reorderEntityItems(items, "missing", "skill-2")).toBe(items);
    expect(reorderEntityItems(items, "skill-1", "missing")).toBe(items);
  });

  it("shows no drag handle outside bulk-edit mode", () => {
    const items: EntityItem[] = [{ id: "skill-1", name: "Python" }];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);

    expect(screen.queryByLabelText(/Drag to reorder/)).not.toBeInTheDocument();
  });

  it("shows a drag handle per row once in bulk-edit mode", async () => {
    const user = userEvent.setup();
    const items: EntityItem[] = [
      { id: "skill-1", name: "Python" },
      { id: "skill-2", name: "SQL" },
    ];

    renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getAllByLabelText("Drag to reorder skills")).toHaveLength(2);
  });

  // ----- category headers (skills/technologies only) ----------------------

  describe("groupItemsByHeader / deriveCategories", () => {
    it("groups members under the nearest preceding header, in contiguous runs", () => {
      const items: EntityItem[] = [
        { id: "s0", name: "Photoshop" },
        { id: "h1", name: "Backend", is_category_header: true },
        { id: "s1", name: "Python" },
        { id: "s2", name: "SQL" },
        { id: "h2", name: "Design", is_category_header: true },
        { id: "s3", name: "Figma" },
      ];

      expect(groupItemsByHeader(items)).toEqual([
        { header: null, members: [items[0]] },
        { header: items[1], members: [items[2], items[3]] },
        { header: items[4], members: [items[5]] },
      ]);
    });

    it("omits the leading uncategorized group when it's empty", () => {
      const items: EntityItem[] = [
        { id: "h1", name: "Backend", is_category_header: true },
        { id: "s1", name: "Python" },
      ];

      expect(groupItemsByHeader(items)).toEqual([{ header: items[0], members: [items[1]] }]);
    });

    it("keeps a header with no members", () => {
      const items: EntityItem[] = [{ id: "h1", name: "Backend", is_category_header: true }];

      expect(groupItemsByHeader(items)).toEqual([{ header: items[0], members: [] }]);
    });

    it("maps every member id to its group header's name, or null if none precedes it", () => {
      const items: EntityItem[] = [
        { id: "s0", name: "Photoshop" },
        { id: "h1", name: "Backend", is_category_header: true },
        { id: "s1", name: "Python" },
      ];

      const derived = deriveCategories(items);

      expect(derived.get("s0")).toBeNull();
      expect(derived.get("s1")).toBe("Backend");
      expect(derived.has("h1")).toBe(false); // a header is never its own member
    });
  });

  describe("category header bootstrap migration", () => {
    it("synthesizes one header per distinct existing category, first-appearance order, then reorders into contiguous runs", async () => {
      // A candidateId unique to this test: bootstrap's one-shot guard is
      // module-level (survives a StrictMode remount in production — see
      // EntitySection.tsx's bootstrappedSections comment), which also means
      // it persists across tests in this file; a shared "cand-1" key could
      // let an earlier or later test's render silently consume the guard.
      const candidateId = "cand-bootstrap-1";
      let nextHeaderId = 100;
      const fetchMock = vi.fn().mockImplementation(async (url: string, init?: RequestInit) => {
        if (url === `/api/candidates/${candidateId}/skills` && init?.method === "POST") {
          const body = JSON.parse(init.body as string) as Record<string, unknown>;
          return { ok: true, status: 201, json: async () => ({ id: `hdr-${nextHeaderId++}`, ...body }) };
        }
        return { ok: true, json: async () => [] };
      });
      vi.stubGlobal("fetch", fetchMock);
      const items: EntityItem[] = [
        { id: "skill-1", name: "Python", category: "Backend" },
        { id: "skill-2", name: "SQL", category: "Backend" },
        { id: "skill-3", name: "Photoshop", category: "Design" },
        { id: "skill-4", name: "Excel" },
      ];

      renderWithQueryClient(<EntitySection candidateId={candidateId} config={skillsConfig} title="Skills" items={items} />);

      await waitFor(() =>
        expect(
          fetchMock.mock.calls.some(([url]) => url === `/api/candidates/${candidateId}/skills/reorder`),
        ).toBe(true),
      );

      const createCalls = (fetchMock.mock.calls as [string, RequestInit][]).filter(
        ([url, init]) => url === `/api/candidates/${candidateId}/skills` && init.method === "POST",
      );
      expect(createCalls.map(([, init]) => JSON.parse(init.body as string))).toEqual([
        { name: "Backend", is_category_header: true },
        { name: "Design", is_category_header: true },
      ]);

      const [, reorderInit] = fetchMock.mock.calls.find(
        ([url]) => url === `/api/candidates/${candidateId}/skills/reorder`,
      ) as [string, RequestInit];
      expect(JSON.parse(reorderInit.body as string)).toEqual({
        ordered_ids: ["hdr-100", "skill-1", "skill-2", "hdr-101", "skill-3", "skill-4"],
      });
    });

    it("does not run when a header row already exists", () => {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);
      const items: EntityItem[] = [
        { id: "hdr-1", name: "Backend", is_category_header: true },
        { id: "skill-1", name: "Python", category: "Backend" },
      ];

      renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);

      expect(fetchMock).not.toHaveBeenCalled();
    });

    it("does not run when no item has a category", () => {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);
      const items: EntityItem[] = [{ id: "skill-1", name: "Python" }];

      renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);

      expect(fetchMock).not.toHaveBeenCalled();
    });
  });

  describe("category header recompute", () => {
    it("PUTs a skill's derived category when it no longer matches its position relative to headers", async () => {
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
      vi.stubGlobal("fetch", fetchMock);
      const items: EntityItem[] = [
        { id: "hdr-1", name: "Backend", is_category_header: true },
        { id: "skill-1", name: "Python", category: "Frontend" },
      ];

      renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);

      await waitFor(() => expect(fetchMock).toHaveBeenCalled());
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("/api/candidates/cand-1/skills/skill-1");
      expect(init.method).toBe("PUT");
      expect(JSON.parse(init.body as string)).toEqual({ category: "Backend" });
    });

    it("does not fire when every item's category already matches its derived value", () => {
      const fetchMock = vi.fn();
      vi.stubGlobal("fetch", fetchMock);
      const items: EntityItem[] = [
        { id: "hdr-1", name: "Backend", is_category_header: true },
        { id: "skill-1", name: "Python", category: "Backend" },
      ];

      renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);

      expect(fetchMock).not.toHaveBeenCalled();
    });

    it("does not start a second recompute pass while one is still in flight", async () => {
      // Regression test for a real runaway-loop bug found live: each PUT's
      // onSuccess: invalidate refetches the candidate, re-firing this
      // effect with a fresh `items` reference — with no guard, a second
      // pass could start before the first PUT resolved, and the two
      // overlapping passes raced each other indefinitely against a real
      // profile (hundreds of PUTs to the same two skills). This asserts
      // that a rerender arriving while a PUT is still pending does not
      // start a second one.
      let resolvePut: (() => void) | undefined;
      const pending = new Promise<void>((resolve) => {
        resolvePut = resolve;
      });
      const fetchMock = vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
        if (init?.method === "PUT") {
          await pending;
        }
        return { ok: true, json: async () => ({}) };
      });
      vi.stubGlobal("fetch", fetchMock);

      const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
      const itemsV1: EntityItem[] = [
        { id: "hdr-1", name: "Backend", is_category_header: true },
        { id: "skill-1", name: "Python", category: "Frontend" },
      ];
      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={itemsV1} />
        </QueryClientProvider>,
      );

      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

      // Simulate an in-between refetch landing with a still-stale category
      // (the real sequence: the pending PUT above hasn't resolved/persisted
      // yet, so a refetch racing ahead of it would still show "Frontend").
      const itemsV2: EntityItem[] = [
        { id: "hdr-1", name: "Backend", is_category_header: true },
        { id: "skill-1", name: "Python", category: "Frontend" },
      ];
      rerender(
        <QueryClientProvider client={queryClient}>
          <EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={itemsV2} />
        </QueryClientProvider>,
      );

      expect(fetchMock).toHaveBeenCalledTimes(1);

      resolvePut?.();
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
      // Give a wrongly-started follow-up call a chance to appear, then
      // confirm it didn't.
      await new Promise((resolve) => setTimeout(resolve, 20));
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });

  describe("+ Add Category", () => {
    it("only appears in bulk-edit mode, and creates a placeholder header row on click", async () => {
      const user = userEvent.setup();
      const fetchMock = vi
        .fn()
        .mockResolvedValue({ ok: true, json: async () => ({ id: "hdr-new", name: "New Category", is_category_header: true }) });
      vi.stubGlobal("fetch", fetchMock);
      const items: EntityItem[] = [{ id: "skill-1", name: "Python" }];

      renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
      expect(screen.queryByRole("button", { name: "+ Add Category" })).not.toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Edit" }));
      expect(screen.getByRole("button", { name: "+ Add Category" })).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "+ Add Category" }));

      await waitFor(() => expect(fetchMock).toHaveBeenCalled());
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(url).toBe("/api/candidates/cand-1/skills");
      expect(JSON.parse(init.body as string)).toEqual({ name: "New Category", is_category_header: true });
    });

    it("does not appear for entities without categoryHeaders", async () => {
      const user = userEvent.setup();
      const items: EntityItem[] = [{ id: "edu-1", institution: "MIT" }];

      renderWithQueryClient(<EntitySection candidateId="cand-1" config={educationConfig} title="Education" items={items} />);
      await user.click(screen.getByRole("button", { name: "Edit" }));

      expect(screen.queryByRole("button", { name: "+ Add Category" })).not.toBeInTheDocument();
    });
  });

  describe("grouped read-only view", () => {
    it("renders skills nested under bold category headers, and ungrouped items with no header at all", () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
      const items: EntityItem[] = [
        { id: "skill-0", name: "Photoshop" },
        { id: "hdr-1", name: "Backend", is_category_header: true },
        { id: "skill-1", name: "Python", proficiency: "Advanced" },
        { id: "skill-2", name: "SQL" },
      ];

      renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);

      expect(screen.getByText("Backend")).toBeInTheDocument();
      expect(screen.getByText("Python (Advanced)")).toBeInTheDocument();
      expect(screen.getByText("SQL")).toBeInTheDocument();
      expect(screen.getByText("Photoshop")).toBeInTheDocument();
    });

    it("shows a header row with no members, with no crash", () => {
      const items: EntityItem[] = [{ id: "hdr-1", name: "Backend", is_category_header: true }];

      renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);

      expect(screen.getByText("Backend")).toBeInTheDocument();
    });

    it("does not use the grouped view for entities without categoryHeaders", () => {
      const items: EntityItem[] = [{ id: "edu-1", institution: "MIT", degree: "BSc" }];

      renderWithQueryClient(<EntitySection candidateId="cand-1" config={educationConfig} title="Education" items={items} />);

      expect(screen.getByText("MIT — BSc")).toBeInTheDocument();
    });
  });

  describe("header row editing", () => {
    it("renders just a label input for a header row in bulk-edit mode, not the skill fields", async () => {
      const user = userEvent.setup();
      const items: EntityItem[] = [{ id: "hdr-1", name: "Backend", is_category_header: true }];

      renderWithQueryClient(<EntitySection candidateId="cand-1" config={skillsConfig} title="Skills" items={items} />);
      await user.click(screen.getByRole("button", { name: "Edit" }));

      expect(screen.getByLabelText("Category label")).toHaveValue("Backend");
      expect(screen.queryByLabelText(/Proficiency/)).not.toBeInTheDocument();
    });
  });
});
