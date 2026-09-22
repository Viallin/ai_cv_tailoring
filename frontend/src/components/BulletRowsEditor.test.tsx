import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { BulletRowsEditor, reorderBulletRows, type BulletRow } from "./BulletRowsEditor";

const PROJECTS = [
  { id: "proj-1", name: "Internal tool" },
  { id: "proj-2", name: "" },
];

describe("BulletRowsEditor", () => {
  it("renders one row per bullet, showing its assigned project or (none)", () => {
    const rows: BulletRow[] = [
      { id: "b1", text: "Shipped v1", projectId: "proj-1" },
      { id: "b2", text: "Led standups", projectId: null },
    ];

    render(<BulletRowsEditor label="Achievements" rows={rows} projects={PROJECTS} onChange={vi.fn()} />);

    expect(screen.getByDisplayValue("Shipped v1")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Led standups")).toBeInTheDocument();
    expect(screen.getByLabelText("Achievements 1 project")).toHaveTextContent("Internal tool");
    expect(screen.getByLabelText("Achievements 2 project")).toHaveTextContent("(none)");
  });

  it("an untitled project falls back to a placeholder label in the dropdown", () => {
    const rows: BulletRow[] = [{ id: "b1", text: "Something", projectId: "proj-2" }];

    render(<BulletRowsEditor label="Achievements" rows={rows} projects={PROJECTS} onChange={vi.fn()} />);

    expect(screen.getByLabelText("Achievements 1 project")).toHaveTextContent("Untitled project");
  });

  it("editing a row's text calls onChange with only that row updated", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const rows: BulletRow[] = [{ id: "b1", text: "Shipped v1", projectId: null }];

    render(<BulletRowsEditor label="Achievements" rows={rows} projects={PROJECTS} onChange={onChange} />);

    await user.type(screen.getByLabelText("Achievements 1"), "!");

    expect(onChange).toHaveBeenLastCalledWith([{ id: "b1", text: "Shipped v1!", projectId: null }]);
  });

  it("removing a row drops only that row", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const rows: BulletRow[] = [
      { id: "b1", text: "First", projectId: null },
      { id: "b2", text: "Second", projectId: null },
    ];

    render(<BulletRowsEditor label="Achievements" rows={rows} projects={PROJECTS} onChange={onChange} />);

    await user.click(screen.getAllByRole("button", { name: "Remove" })[0]);

    expect(onChange).toHaveBeenCalledWith([{ id: "b2", text: "Second", projectId: null }]);
  });

  it("+ Add appends a blank role-level row with a freshly generated id", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(<BulletRowsEditor label="Achievements" rows={[]} projects={PROJECTS} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "+ Add Achievement" }));

    const [added] = onChange.mock.calls[0][0] as BulletRow[];
    expect(added).toMatchObject({ text: "", projectId: null });
    expect(added.id).toBeTruthy();
  });

  // ----- drag-reorder ---------------------------------------------------

  it("renders a drag handle for every row", () => {
    const rows: BulletRow[] = [
      { id: "b1", text: "First", projectId: null },
      { id: "b2", text: "Second", projectId: null },
    ];

    render(<BulletRowsEditor label="Achievements" rows={rows} projects={PROJECTS} onChange={vi.fn()} />);

    expect(screen.getByLabelText("Drag to reorder achievements 1")).toBeInTheDocument();
    expect(screen.getByLabelText("Drag to reorder achievements 2")).toBeInTheDocument();
  });

  it("reorderBulletRows moves a row to the target position without mutating the input", () => {
    // jsdom has no real pointer/drag geometry to simulate an actual drag
    // gesture through, so the reorder logic itself (extracted as a plain
    // function of ids) is tested directly here rather than through a
    // simulated DndContext drag — same limitation the A4 CV editor's own
    // (now native-ProseMirror-drag-based) reorder hits, see
    // lib/tiptap/plugins.test.ts.
    const rows: BulletRow[] = [
      { id: "b1", text: "First", projectId: null },
      { id: "b2", text: "Second", projectId: null },
      { id: "b3", text: "Third", projectId: null },
    ];

    const result = reorderBulletRows(rows, "b1", "b3");

    expect(result.map((r) => r.id)).toEqual(["b2", "b3", "b1"]);
    expect(rows.map((r) => r.id)).toEqual(["b1", "b2", "b3"]); // input untouched
  });

  it("reorderBulletRows returns the rows unchanged if either id can't be found", () => {
    const rows: BulletRow[] = [
      { id: "b1", text: "First", projectId: null },
      { id: "b2", text: "Second", projectId: null },
    ];

    expect(reorderBulletRows(rows, "missing", "b2")).toBe(rows);
    expect(reorderBulletRows(rows, "b1", "missing")).toBe(rows);
  });
});
