import { describe, expect, it, vi } from "vitest";

import { GutterRegistry } from "@/lib/tiptap/gutterRegistry";

function makeAnchor(): HTMLElement {
  const el = document.createElement("div");
  document.body.appendChild(el);
  return el;
}

function makeCheckbox() {
  return { checked: true, onToggle: vi.fn(), ariaLabel: "Include this row" };
}

const noopGetPos = () => 0;

describe("GutterRegistry", () => {
  it("starts with an empty snapshot", () => {
    const registry = new GutterRegistry();
    expect(registry.getSnapshot()).toEqual([]);
  });

  it("register adds an item to the snapshot and notifies subscribers", () => {
    const registry = new GutterRegistry();
    const listener = vi.fn();
    registry.subscribe(listener);

    const anchorEl = makeAnchor();
    registry.register({ id: "bullet:b1", anchorEl, getPos: noopGetPos, checkbox: makeCheckbox() });

    expect(registry.getSnapshot()).toHaveLength(1);
    expect(registry.getSnapshot()[0].id).toBe("bullet:b1");
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("register is an upsert — re-registering the same id updates it in place rather than duplicating", () => {
    const registry = new GutterRegistry();
    const anchorEl = makeAnchor();
    registry.register({ id: "entry:e1", anchorEl, getPos: noopGetPos, checkbox: { ...makeCheckbox(), checked: true } });
    registry.register({ id: "entry:e1", anchorEl, getPos: noopGetPos, checkbox: { ...makeCheckbox(), checked: false } });

    const snapshot = registry.getSnapshot();
    expect(snapshot).toHaveLength(1);
    expect(snapshot[0].checkbox.checked).toBe(false);
  });

  it("unregister removes the item and notifies subscribers", () => {
    const registry = new GutterRegistry();
    const listener = vi.fn();
    registry.register({ id: "section:summary", anchorEl: makeAnchor(), getPos: noopGetPos, checkbox: makeCheckbox() });
    registry.subscribe(listener);

    registry.unregister("section:summary");

    expect(registry.getSnapshot()).toEqual([]);
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("unregistering an id that was never registered is a harmless no-op — no notification", () => {
    const registry = new GutterRegistry();
    const listener = vi.fn();
    registry.subscribe(listener);

    registry.unregister("bullet:does-not-exist");

    expect(listener).not.toHaveBeenCalled();
  });

  it("publishes a fresh array identity every change — required for useSyncExternalStore's reference-equality check", () => {
    const registry = new GutterRegistry();
    const before = registry.getSnapshot();
    registry.register({ id: "bullet:b1", anchorEl: makeAnchor(), getPos: noopGetPos, checkbox: makeCheckbox() });
    const after = registry.getSnapshot();

    expect(after).not.toBe(before);
  });

  it("subscribe's own cleanup stops further notifications", () => {
    const registry = new GutterRegistry();
    const listener = vi.fn();
    const unsubscribe = registry.subscribe(listener);
    unsubscribe();

    registry.register({ id: "bullet:b1", anchorEl: makeAnchor(), getPos: noopGetPos, checkbox: makeCheckbox() });

    expect(listener).not.toHaveBeenCalled();
  });
});
