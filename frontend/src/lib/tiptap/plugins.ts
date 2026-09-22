import { Extension } from "@tiptap/core";
import type { Node as PMNode } from "@tiptap/pm/model";
import type { EditorState } from "@tiptap/pm/state";
import { NodeSelection, Plugin, PluginKey, Selection } from "@tiptap/pm/state";
import { dropPoint } from "@tiptap/pm/transform";
import type { EditorView } from "@tiptap/pm/view";

// Phase 26 — every entry/bullet must carry a unique, non-null `id`
// (structuredDocument.ts's own DocumentBlock.id contract). commands.ts's
// two split commands deliberately leave `id: null` on a freshly-split
// node rather than minting a UUID themselves — this plugin is the one
// place id-hygiene actually happens, so it's independently testable and
// the split commands stay thin wrappers around ProseMirror's own
// split/join.
export const idIntegrityPlugin = new Plugin({
  key: new PluginKey("documentIdIntegrity"),
  appendTransaction(transactions, _oldState, newState) {
    if (!transactions.some((tr) => tr.docChanged)) {
      return null;
    }
    const seen = new Set<string>();
    let tr: ReturnType<typeof newState.tr.setNodeMarkup> | null = null;
    newState.doc.descendants((node, pos) => {
      if (node.type.name !== "entry" && node.type.name !== "bullet") {
        return true;
      }
      const id = node.attrs.id as string | null;
      if (id != null && !seen.has(id)) {
        seen.add(id);
        return true;
      }
      const freshId = crypto.randomUUID();
      seen.add(freshId);
      tr = (tr ?? newState.tr).setNodeMarkup(pos, undefined, { ...node.attrs, id: freshId });
      return true;
    });
    return tr;
  },
});

// Excluded content (`included: false`) stays a real, persisted part of
// the document — ExcludedContentPanel/collectExcludedContent
// (lib/excludedContent.ts) walk the *full* DocumentModel, not a filtered
// one, so the ProseMirror doc must keep excluded nodes too rather than
// deleting them on toggle-off. The NodeViews hide excluded content
// visually (display:none + contentEditable=false — see
// components/tiptap/*NodeView.tsx), which is best-effort: browsers won't
// place a native caret inside a display:none subtree, but that's a DOM
// convention, not something ProseMirror's own selection model enforces.
// This plugin is the authoritative backstop — if a selection still
// resolves inside an excluded node (or an excluded ancestor entry/
// section, matching today's "hide all entries, keep the header" rule for
// a fully-excluded section), relocate it just outside that node's range.
export const excludedSelectionGuardPlugin = new Plugin({
  key: new PluginKey("documentExcludedSelectionGuard"),
  appendTransaction(transactions, oldState, newState) {
    if (!transactions.some((tr) => tr.selectionSet || tr.docChanged)) {
      return null;
    }
    const $from = newState.selection.$from;
    let excludedRange: { from: number; to: number } | null = null;
    for (let depth = $from.depth; depth >= 0; depth--) {
      const node = $from.node(depth);
      const isScopedNode = node.type.name === "entry" || node.type.name === "bullet" || node.type.name === "section";
      if (isScopedNode && node.attrs.included === false) {
        excludedRange = { from: $from.before(depth), to: $from.after(depth) };
        break;
      }
    }
    if (excludedRange == null) {
      return null;
    }
    const movingForward = newState.selection.from >= oldState.selection.from;
    const target = movingForward ? excludedRange.to : excludedRange.from;
    const clamped = Math.min(Math.max(target, 0), newState.doc.content.size);
    const nextSelection = Selection.near(newState.doc.resolve(clamped), movingForward ? 1 : -1);
    return newState.tr.setSelection(nextSelection);
  },
});

// Phase 28 (follow-up) — a bullet whose text is fully deleted (not a
// freshly-created blank one — see below) auto-excludes itself instead of
// sitting on the page as a blank line. Reported directly, alongside the
// gutter's checkboxes going hover-only (DocumentGutter.tsx): with the
// checkbox no longer visible by default, "select all, delete" is now the
// natural way a user removes a bullet they don't want, and leaving it
// included-but-empty would be a silent, confusing dead end — a blank
// line on the exported CV with no obvious way back to a checkbox to
// exclude it properly.
//
// Only a bullet that *had* real text in oldState and is now empty in
// newState triggers this — comparing against a set of ids that were
// non-empty *before* this transaction (not just "is newState's bullet
// empty") is what keeps a freshly-added blank bullet ("+ Add Bullet", or
// a fresh sibling from pressing Enter) from being excluded the instant
// it's created, before the user types anything: neither case's id exists
// in oldState at all (both mint a fresh id — addBullet via
// crypto.randomUUID(), a split via idIntegrityPlugin above), so neither
// is ever in oldNonEmptyIds and neither is ever touched here.
export const emptyBulletExclusionPlugin = new Plugin({
  key: new PluginKey("documentEmptyBulletExclusion"),
  appendTransaction(transactions, oldState, newState) {
    if (!transactions.some((tr) => tr.docChanged)) {
      return null;
    }
    const oldNonEmptyIds = new Set<string>();
    oldState.doc.descendants((node) => {
      if (node.type.name === "bullet" && node.attrs.included !== false && node.textContent.trim() !== "") {
        oldNonEmptyIds.add(node.attrs.id as string);
      }
      return true;
    });
    if (oldNonEmptyIds.size === 0) {
      return null;
    }
    let tr: ReturnType<typeof newState.tr.setNodeMarkup> | null = null;
    newState.doc.descendants((node, pos) => {
      if (node.type.name !== "bullet") {
        return true;
      }
      if (node.attrs.included === false || node.textContent.trim() !== "") {
        return true;
      }
      if (!oldNonEmptyIds.has(node.attrs.id as string)) {
        return true;
      }
      tr = (tr ?? newState.tr).setNodeMarkup(pos, undefined, { ...node.attrs, included: false });
      return true;
    });
    return tr;
  },
});

// Phase 27 — id -> immediate-parent-identity maps, used by
// dragScopeGuardPlugin below to detect a node that changed *which*
// section/entry owns it (only possible via a drag-drop; every
// split/join path in commands.ts already stays within-section/
// within-entry by construction, via its own Backspace guards).
function collectParentMap(doc: PMNode): { entryParent: Map<string, string>; bulletParent: Map<string, string> } {
  const entryParent = new Map<string, string>();
  const bulletParent = new Map<string, string>();
  doc.descendants((node, _pos, parent) => {
    if (node.type.name === "entry" && parent?.type.name === "section") {
      entryParent.set(node.attrs.id, parent.attrs.key);
    } else if (node.type.name === "bullet" && parent?.type.name === "entry") {
      bulletParent.set(node.attrs.id, parent.attrs.id);
    }
    return true;
  });
  return { entryParent, bulletParent };
}

// Entries stay within their own section, bullets within their own
// entry — the same restriction the pre-Phase-26 dnd-kit editor enforced
// ("cross-section drags unsupported"): a section's entries and another
// section's entries hold structurally different kinds of content, so
// there's no legitimate reason to drag one across that boundary.
// Native ProseMirror node dragging (schema.ts's `draggable: true`)
// doesn't know about this on its own — the schema alone would happily
// accept an `entry` dropped into any `section` — so this plugin is the
// enforcement: compare each existing entry's/bullet's parent identity
// before and after a transaction, and revert wholesale (the whole
// transaction, not a per-node patch) if any pre-existing one changed.
// A newly-created node (a fresh split, see commands.ts) only ever
// appears in the *new* map, never the old one, so it's never flagged.
// Section-level moves have no such check at all — reordering sections
// relative to each other is exactly Phase 27's new capability.
export const dragScopeGuardPlugin = new Plugin({
  key: new PluginKey("documentDragScopeGuard"),
  appendTransaction(transactions, oldState, newState) {
    if (!transactions.some((tr) => tr.docChanged)) {
      return null;
    }
    const before = collectParentMap(oldState.doc);
    const after = collectParentMap(newState.doc);
    const crossedBoundary = (oldMap: Map<string, string>, newMap: Map<string, string>) => {
      for (const [id, oldParent] of oldMap) {
        const newParent = newMap.get(id);
        if (newParent != null && newParent !== oldParent) {
          return true;
        }
      }
      return false;
    };
    if (crossedBoundary(before.entryParent, after.entryParent) || crossedBoundary(before.bulletParent, after.bulletParent)) {
      return newState.tr.replaceWith(0, newState.doc.content.size, oldState.doc.content);
    }
    return null;
  },
});

// Wraps all four plugins above as one Extension so DocumentEditor.tsx's
// extensions array only needs one entry — none of them are scoped to a
// specific node type (all four walk the whole doc/selection), so there's
// no natural single node to attach addProseMirrorPlugins() to instead.
// Order matters for two of these: emptyBulletExclusionPlugin has to run
// *before* excludedSelectionGuardPlugin — ProseMirror's own
// appendTransaction chaining applies each plugin's returned transaction
// before calling the next plugin, so putting the exclusion first is what
// lets the selection-guard plugin see (and relocate the cursor out of)
// a bullet that was just excluded by deleting all its text, in the same
// pass rather than a visibly separate one.
export const DocumentGuards = Extension.create({
  name: "documentGuards",
  addProseMirrorPlugins() {
    return [idIntegrityPlugin, emptyBulletExclusionPlugin, excludedSelectionGuardPlugin, dragScopeGuardPlugin];
  },
});

// Phase 27 (follow-up) — native HTML5 drag-and-drop does not auto-scroll
// once the drop target's own `dragover` handler calls
// `event.preventDefault()`, which is required for a drop to be accepted
// at all (`prosemirror-view`'s own core `editHandlers.dragover` does
// exactly this, unconditionally) — most browsers tie their built-in
// "scroll when the drag nears a viewport edge" behavior to the
// *default* dragover action, so that mandatory preventDefault silently
// disables it. Reported directly: with a long section (Experience) open,
// there was no way to drop anything before/after it — the target
// position was off-screen, and nothing scrolled it into view while the
// drag was held, since the browser's own edge-autoscroll never ran.
//
// This app has no inner scrollable container for the editor itself —
// DraftScreen.tsx's only `overflow-y-auto` is the *sidebar*
// (Gaps/Excluded/Unused-Evidence panel); the page itself scrolls via
// the window, so this drives `window.scrollBy` directly rather than
// hunting for a scroll-ancestor.
//
// Widened from an original 72px/18px-per-frame after mouse-wheel
// scrolling during a drag turned out to be unfixable from here: a
// diagnostic the user ran directly in DevTools (listeners on `window`
// and `document`, both capture and bubble, plus a running count) showed
// *zero* `wheel` events reaching the page for the drag's entire
// duration, despite spinning the wheel repeatedly mid-drag — confirming
// the browser's own native drag session (on Windows, Chrome's
// `DoDragDrop` modal loop) never dispatches `wheel` to the page while a
// drag is held at all, not just to whatever's under the cursor. Nothing
// lands on the page's own event queue to intercept, so no listener
// placement fixes it (see `createDragAutoScrollPlugin`'s own comment
// for the full history of that investigation, kept as-is since it's
// harmless and might still work on a browser/OS combination that
// doesn't suppress it the same way). This edge-hover mechanism is the
// one actually confirmed working, so it gets to be the primary way to
// scroll during a drag — a bigger hot zone and faster top speed mean
// less precise hovering and less time spent waiting for it.
const AUTO_SCROLL_EDGE_PX = 140;
const AUTO_SCROLL_MAX_SPEED_PX = 26;

// Exported on its own — the "how close to which edge, how fast" math is
// a pure function worth testing directly, independent of the
// `requestAnimationFrame` loop that drives it (real native `DragEvent`
// timing isn't something jsdom can exercise meaningfully — the same gap
// `dragScopeGuardPlugin`'s own tests, above, work around by asserting on
// the resulting document rather than simulating the gesture itself).
export function computeAutoScrollDelta(clientY: number, viewportHeight: number): number {
  const distanceFromTop = clientY;
  const distanceFromBottom = viewportHeight - clientY;
  if (distanceFromTop < AUTO_SCROLL_EDGE_PX) {
    const intensity = 1 - Math.max(distanceFromTop, 0) / AUTO_SCROLL_EDGE_PX;
    return -Math.ceil(intensity * AUTO_SCROLL_MAX_SPEED_PX);
  }
  if (distanceFromBottom < AUTO_SCROLL_EDGE_PX) {
    const intensity = 1 - Math.max(distanceFromBottom, 0) / AUTO_SCROLL_EDGE_PX;
    return Math.ceil(intensity * AUTO_SCROLL_MAX_SPEED_PX);
  }
  return 0;
}

// A factory, not a module-level singleton like the three guard plugins
// above — those are stateless (pure functions of whatever `tr`/`state`
// they're handed each call), but this one holds real mutable state (the
// in-flight rAF handle, the last known drag position) across calls,
// which must not be shared between separate `Editor` instances (e.g.
// two tests in the same run, or a remount) or leak past one editor's
// own lifetime. `view()`'s `destroy` (called when the EditorView itself
// is torn down) is what guarantees the loop actually stops rather than
// scrolling a window that no longer has this editor in it.
export function createDragAutoScrollPlugin(): Plugin {
  let lastClientY: number | null = null;
  let frame: number | null = null;
  // Phase 27 (follow-up #2) — separate from `lastClientY`/`frame` above:
  // this just tracks "is a drag currently held," for the `wheel`
  // handling below. Reported directly: edge-hover autoscroll (above)
  // worked, but spinning the mouse wheel while dragging still didn't
  // scroll at all.
  //
  // The obvious cause — ProseMirror's own core `dragover` handler
  // calling `preventDefault()`, which is what silently disabled the
  // browser's built-in *edge*-autoscroll above — turned out not to be
  // the whole story here. `wheel` isn't part of the drag-and-drop event
  // family at all, and a synthetic (untrusted) `wheel` event dispatched
  // mid-drag against the live editor *did* reach a `handleDOMEvents.wheel`
  // hook correctly. But that only proves the *handler* is correct, not
  // that a real trusted wheel gesture ever reaches it — an untrusted
  // `dispatchEvent` always reaches an `addEventListener`-registered
  // handler regardless of what the browser's own native input routing
  // would actually do mid-drag, the same gap that made every earlier
  // "confirmed via dispatchEvent" check in this phase not equivalent to
  // an actual mouse gesture. Retested for real: still nothing.
  //
  // **Confirmed, not just suspected**, by a diagnostic the user ran
  // directly in DevTools — plain listeners on `window` and `document`
  // (both capture and bubble phase) plus a running count, active for
  // one full drag: spinning the mouse wheel repeatedly mid-drag produced
  // *zero* `wheel` events anywhere on the page for the drag's entire
  // duration. On Windows, Chrome's native drag-and-drop runs through the
  // OS's own modal drag loop (`DoDragDrop`), which only pumps a limited
  // set of input messages back to the page while a drag is held (mouse
  // move, Escape-to-cancel) — `WM_MOUSEWHEEL` isn't one of them. The
  // event never reaches the page's own event queue at all, for any
  // element, so there is nothing here — or anywhere else in this
  // codebase — for a JS listener to intercept. This is a real platform
  // ceiling, not a bug in this plugin.
  //
  // The handling below (and the extra `window`-level, capture-phase
  // listener past the end of this function) stays anyway: harmless when
  // inactive, and untested whether every browser/OS combination
  // suppresses `wheel`-during-drag the same way Windows Chrome does —
  // if some don't, this still helps there. But the edge-hover
  // auto-scroll above is the one mechanism actually confirmed working,
  // which is why *it* got widened (bigger hot zone, faster top speed)
  // once this dead end was confirmed, rather than sinking more effort
  // into wheel specifically.
  let dragActive = false;

  const step = () => {
    if (lastClientY == null) {
      frame = null;
      return;
    }
    const delta = computeAutoScrollDelta(lastClientY, window.innerHeight);
    if (delta !== 0) {
      window.scrollBy(0, delta);
    }
    frame = requestAnimationFrame(step);
  };

  const stop = () => {
    lastClientY = null;
    dragActive = false;
    if (frame != null) {
      cancelAnimationFrame(frame);
      frame = null;
    }
  };

  // Shared by both the ProseMirror-level `handleDOMEvents.wheel` and
  // the raw `window` capture-phase listener below — manually replays
  // the scroll a `wheel` event would normally produce on its own
  // (`deltaY`/`deltaMode` straight from the event, not the edge-hover
  // speed curve above — this is a deliberate, user-driven scroll
  // amount, not a proximity-based one). `preventDefault()` so nothing
  // else double-applies it if some browser/OS combination *does* still
  // run its own default handling here too.
  const applyWheelScroll = (event: WheelEvent): boolean => {
    if (!dragActive) {
      return false;
    }
    const pixelDelta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
    window.scrollBy(0, pixelDelta);
    event.preventDefault();
    return true;
  };

  const onWindowWheelCapture = (event: WheelEvent) => {
    if (applyWheelScroll(event)) {
      event.stopPropagation();
    }
  };

  return new Plugin({
    key: new PluginKey("documentDragAutoScroll"),
    props: {
      handleDOMEvents: {
        dragover: (_view, event) => {
          dragActive = true;
          lastClientY = event.clientY;
          if (frame == null) {
            frame = requestAnimationFrame(step);
          }
          // Never swallow — ProseMirror's own core dragover handler
          // (preventDefault, so a drop is accepted at all; Dropcursor's
          // own positioning) still needs to run after this.
          return false;
        },
        dragend: () => {
          stop();
          return false;
        },
        drop: () => {
          stop();
          return false;
        },
        wheel: (_view, event) => applyWheelScroll(event),
      },
    },
    view() {
      window.addEventListener("wheel", onWindowWheelCapture, { capture: true, passive: false });
      return {
        destroy: () => {
          window.removeEventListener("wheel", onWindowWheelCapture, { capture: true });
          stop();
        },
      };
    },
  });
}

export const DragAutoScroll = Extension.create({
  name: "documentDragAutoScroll",
  addProseMirrorPlugins() {
    return [createDragAutoScrollPlugin()];
  },
});

// Phase 27 (follow-up #3) — visual scope feedback during a drag: every
// entry/bullet that *isn't* a legal drop target for whatever's being
// dragged dims out (matching dragScopeGuardPlugin's own restriction —
// entries stay within their section, bullets within their entry), and
// the drop-position cursor itself turns red, with a short tooltip, over
// an illegal spot. Purely visual — dragScopeGuardPlugin above is still
// what actually *enforces* the restriction (reverting a bad drop after
// the fact); this only helps the user avoid attempting one, or
// understand why one didn't stick.
//
// A `DragScope` is computed once, at `dragstart`, from `state.selection`
// (already a NodeSelection over the correct dragged node — see
// DragHandle.tsx's own `onDragSelect`) — not recomputed per `dragover`,
// since what's being dragged can't change mid-drag. `scopeId` is the
// id/key of the ancestor (section for an entry, entry for a bullet) the
// drop has to land back inside; `null` means "no restriction" (a
// section can be dropped anywhere).
export interface DragScope {
  nodeType: "section" | "entry" | "bullet";
  scopeId: string | null;
  // Human-readable label for the tooltip — only meaningful (and only
  // ever set) for an `entry` drag, where "the Experience section" reads
  // far better than a bare section key. A bullet's own scope is "its
  // entry," which doesn't need a name to be clear.
  scopeLabel: string | null;
}

export function computeDragScope(state: EditorState): DragScope | null {
  const { selection } = state;
  if (!(selection instanceof NodeSelection)) {
    return null;
  }
  const nodeType = selection.node.type.name;
  if (nodeType !== "section" && nodeType !== "entry" && nodeType !== "bullet") {
    return null;
  }
  if (nodeType === "section") {
    return { nodeType, scopeId: null, scopeLabel: null };
  }
  const ancestorType = nodeType === "entry" ? "section" : "entry";
  const $pos = state.doc.resolve(selection.from);
  for (let depth = $pos.depth; depth >= 0; depth--) {
    const ancestor = $pos.node(depth);
    if (ancestor.type.name === ancestorType) {
      return {
        nodeType,
        scopeId: (nodeType === "entry" ? ancestor.attrs.key : ancestor.attrs.id) as string,
        scopeLabel: nodeType === "entry" ? (ancestor.attrs.title as string) : null,
      };
    }
  }
  return null;
}

// Is the given document position still inside the dragged node's
// required ancestor? Walks up from `pos` the same way `computeDragScope`
// walked up from the drag's own origin, so a mismatch here is exactly
// what `dragScopeGuardPlugin` would revert if the drop actually
// happened.
export function isPositionInScope(state: EditorState, pos: number, scope: DragScope): boolean {
  if (scope.scopeId == null) {
    return true;
  }
  const ancestorType = scope.nodeType === "entry" ? "section" : "entry";
  const $pos = state.doc.resolve(pos);
  for (let depth = $pos.depth; depth >= 0; depth--) {
    const ancestor = $pos.node(depth);
    if (ancestor.type.name === ancestorType) {
      const key = scope.nodeType === "entry" ? ancestor.attrs.key : ancestor.attrs.id;
      return key === scope.scopeId;
    }
  }
  return false;
}

export function invalidDropMessage(scope: DragScope): string {
  if (scope.nodeType === "entry") {
    return scope.scopeLabel
      ? `Can only be reordered within the “${scope.scopeLabel}” section.`
      : "Can only be reordered within its own section.";
  }
  return "Can only be reordered within its own entry.";
}

const DIMMED_OPACITY = "0.28";

// Phase 27 (follow-up #4) — the drop-position line itself, widened
// ~25% after it proved too thin/narrow a target to comfortably aim
// for — reported directly. `CURSOR_HORIZONTAL_OVERHANG_RATIO` extends
// the line past the underlying row's own left/right edges (split
// evenly on both sides) rather than just matching its width exactly,
// giving a visibly bigger target without the line reading as
// disconnected from the row it corresponds to; `CURSOR_HEIGHT_PX` (was
// a bare `2` inlined in the cursor element's own `cssText`) makes the
// line itself thicker, easier to spot and easier to land the cursor
// precisely on.
const CURSOR_HEIGHT_PX = 3;
const CURSOR_HORIZONTAL_OVERHANG_RATIO = 0.25;

// A raw `view()` plugin (no decorations, no meta-transaction dance to
// force a redraw) — the same architecture `prosemirror-dropcursor`
// itself uses: native `dragover`/`dragend`/`drop`/`dragleave` listeners
// added directly to `editorView.dom`, driving a couple of plain,
// manually-positioned DOM elements. Decorations would need a dispatched
// (if meta-only) transaction on every `dragover` just to trigger a
// redraw — pure overhead here, since nothing about the *document* ever
// changes while hovering.
//
// Replaces `@tiptap/extensions`' stock `Dropcursor` outright rather than
// running both side by side — two independently-computed cursor lines
// would fight each other, and this plugin already needs everything
// Dropcursor computes (the actual drop position, via the same
// `dropPoint` helper) to decide the color.
class DragScopeFeedbackView {
  private readonly editorView: EditorView;
  private cursorPos: number | null = null;
  private cursorEl: HTMLElement | null = null;
  private tooltipEl: HTMLElement | null = null;
  private dimmedEls: HTMLElement[] = [];
  private dragScope: DragScope | null = null;
  private lastDragEvent: DragEvent | null = null;
  private readonly onDragStart = () => this.handleDragStart();
  private readonly onDragOver = (event: Event) => this.handleDragOver(event as DragEvent);
  private readonly onDragEnd = () => this.reset();
  private readonly onDrop = () => this.reset();
  private readonly onDragLeave = (event: Event) => this.handleDragLeave(event as DragEvent);

  constructor(editorView: EditorView) {
    this.editorView = editorView;
    editorView.dom.addEventListener("dragstart", this.onDragStart);
    editorView.dom.addEventListener("dragover", this.onDragOver);
    editorView.dom.addEventListener("dragend", this.onDragEnd);
    editorView.dom.addEventListener("drop", this.onDrop);
    editorView.dom.addEventListener("dragleave", this.onDragLeave);
  }

  destroy() {
    this.editorView.dom.removeEventListener("dragstart", this.onDragStart);
    this.editorView.dom.removeEventListener("dragover", this.onDragOver);
    this.editorView.dom.removeEventListener("dragend", this.onDragEnd);
    this.editorView.dom.removeEventListener("drop", this.onDrop);
    this.editorView.dom.removeEventListener("dragleave", this.onDragLeave);
    this.reset();
  }

  // Mirrors DropCursorView's own `update()`: if the document changed
  // while a cursor is showing (e.g. an in-progress collaborative edit,
  // or — the actually-relevant case here — DragAutoScroll's own window
  // scroll shifting where the drop target visually is), recompute the
  // cursor's position from the last known drag coordinates.
  update(editorView: EditorView, prevState: EditorState) {
    if (this.cursorPos != null && prevState.doc !== editorView.state.doc && this.lastDragEvent) {
      this.setCursor(this.computeTarget(this.lastDragEvent));
    }
  }

  private handleDragStart() {
    this.dragScope = computeDragScope(this.editorView.state);
    this.applyDim();
  }

  private handleDragOver(event: DragEvent) {
    if (!this.editorView.editable) {
      return;
    }
    this.lastDragEvent = event;
    this.setCursor(this.computeTarget(event));
  }

  private handleDragLeave(event: DragEvent) {
    if (!this.editorView.dom.contains(event.relatedTarget as Node | null)) {
      this.removeCursor();
      this.removeTooltip();
    }
  }

  private reset() {
    this.lastDragEvent = null;
    this.dragScope = null;
    this.clearDim();
    this.removeCursor();
    this.removeTooltip();
  }

  private computeTarget(event: DragEvent): number | null {
    const pos = this.editorView.posAtCoords({ left: event.clientX, top: event.clientY });
    if (!pos) {
      return null;
    }
    let target = pos.pos;
    const { dragging } = this.editorView;
    if (dragging?.slice) {
      const point = dropPoint(this.editorView.state.doc, target, dragging.slice);
      if (point != null) {
        target = point;
      }
    }
    return target;
  }

  private setCursor(pos: number | null) {
    this.cursorPos = pos;
    if (pos == null) {
      this.removeCursor();
      this.removeTooltip();
      return;
    }
    const valid = this.dragScope == null || isPositionInScope(this.editorView.state, pos, this.dragScope);
    this.updateCursorOverlay(pos, valid);
    if (valid || this.dragScope == null) {
      this.removeTooltip();
    } else {
      this.updateTooltip(invalidDropMessage(this.dragScope));
    }
  }

  // Adapted from prosemirror-dropcursor's own `updateOverlay` (MIT
  // licensed, prosemirror-dropcursor package) — this project only ever
  // drags block nodes (section/entry/bullet), never inline content, so
  // this keeps just the block-level rect math and drops the inline
  // (thin vertical line) branch entirely.
  private updateCursorOverlay(pos: number, valid: boolean) {
    const $pos = this.editorView.state.doc.resolve(pos);
    const before = $pos.nodeBefore;
    const after = $pos.nodeAfter;
    const refPos = pos - (before ? before.nodeSize : 0);
    const dom = before || after ? this.editorView.nodeDOM(refPos) : null;
    if (!(dom instanceof HTMLElement)) {
      return;
    }
    const nodeRect = dom.getBoundingClientRect();
    const top = before ? nodeRect.bottom : nodeRect.top;
    const editorRect = this.editorView.dom.getBoundingClientRect();
    const overhang = (nodeRect.right - nodeRect.left) * (CURSOR_HORIZONTAL_OVERHANG_RATIO / 2);

    if (!this.cursorEl) {
      this.cursorEl = document.createElement("div");
      this.cursorEl.style.cssText = `position: fixed; z-index: 50; pointer-events: none; height: ${CURSOR_HEIGHT_PX}px; border-radius: 1px;`;
      document.body.appendChild(this.cursorEl);
    }
    this.cursorEl.style.left = `${nodeRect.left - overhang}px`;
    this.cursorEl.style.top = `${top - CURSOR_HEIGHT_PX / 2}px`;
    this.cursorEl.style.width = `${nodeRect.right - nodeRect.left + overhang * 2}px`;
    this.cursorEl.style.backgroundColor = valid ? "var(--primary)" : "var(--destructive)";
    // Clamp to the editor's own bounds -- the line shouldn't render
    // past whatever's actually visible of the document.
    this.cursorEl.style.display = top >= editorRect.top - 4 && top <= editorRect.bottom + 4 ? "block" : "none";
  }

  private removeCursor() {
    this.cursorPos = null;
    if (this.cursorEl) {
      this.cursorEl.remove();
      this.cursorEl = null;
    }
  }

  private updateTooltip(message: string) {
    const event = this.lastDragEvent;
    if (!event) {
      return;
    }
    if (!this.tooltipEl) {
      this.tooltipEl = document.createElement("div");
      this.tooltipEl.style.cssText = [
        "position: fixed",
        "z-index: 51",
        "pointer-events: none",
        "max-width: 220px",
        "padding: 6px 10px",
        "border-radius: 8px",
        "font-size: 12px",
        "line-height: 1.4",
        "font-family: inherit",
        "background: var(--popover)",
        "color: var(--popover-foreground)",
        "box-shadow: 0 4px 12px rgb(0 0 0 / 0.15)",
        "box-sizing: border-box",
      ].join(";");
      document.body.appendChild(this.tooltipEl);
    }
    this.tooltipEl.textContent = message;
    const offset = 14;
    const maxLeft = window.innerWidth - 232; // tooltip's own max-width + a small margin
    const left = Math.min(event.clientX + offset, Math.max(offset, maxLeft));
    const maxTop = window.innerHeight - 48;
    const top = Math.min(event.clientY + offset, maxTop);
    this.tooltipEl.style.left = `${left}px`;
    this.tooltipEl.style.top = `${top}px`;
  }

  private removeTooltip() {
    if (this.tooltipEl) {
      this.tooltipEl.remove();
      this.tooltipEl = null;
    }
  }

  // Dims whole out-of-scope *subtrees*, not just nodes of the same type
  // as whatever's being dragged. An earlier version only walked nodes
  // matching `scope.nodeType` (only other bullets, for a bullet drag;
  // only other entries, for an entry drag) — which left every *other*
  // section's own header, and every entry a dragged bullet could never
  // land in, reading as available when they weren't. Reported directly:
  // dragging a bullet dimmed other roles' bullets, but not the Contacts/
  // Key Projects/Skills sections themselves, even though the bullet
  // can't land in any of them either.
  //
  // Dimming one ancestor's own DOM root is enough to visually dim its
  // entire subtree — CSS `opacity` composites across all descendants at
  // once, confirmed the same way EntryNodeView's own indirection through
  // `nodeDOM()` was (see this file's earlier comment on that gotcha) —
  // so this only ever needs to reach as high as the first out-of-scope
  // ancestor, never recursing further into something already dimmed.
  private applyDim() {
    this.clearDim();
    const scope = this.dragScope;
    if (scope == null || scope.scopeId == null) {
      return;
    }
    this.editorView.state.doc.forEach((sectionNode, sectionOffset) => {
      if (sectionNode.type.name !== "section") {
        return;
      }
      const sectionPos = sectionOffset;
      if (scope.nodeType === "entry") {
        // A dragged entry can only land back in its own section — every
        // other section, header included, is entirely out of bounds.
        if (sectionNode.attrs.key !== scope.scopeId) {
          this.dimNodeAt(sectionPos);
        }
        return;
      }
      // scope.nodeType === "bullet": scopeId is the bullet's own entry's
      // id. A section that doesn't contain that entry at all is
      // entirely out of bounds; one that does needs its *other* entries
      // (not the bullet's own) dimmed instead, leaving the matching
      // entry's own bullets — the only legal drop targets — untouched.
      let ownEntryPos: number | null = null;
      sectionNode.forEach((entryNode, entryOffset) => {
        if (entryNode.attrs.id === scope.scopeId) {
          ownEntryPos = sectionPos + 1 + entryOffset;
        }
      });
      if (ownEntryPos == null) {
        this.dimNodeAt(sectionPos);
        return;
      }
      sectionNode.forEach((_entryNode, entryOffset) => {
        const entryPos = sectionPos + 1 + entryOffset;
        if (entryPos !== ownEntryPos) {
          this.dimNodeAt(entryPos);
        }
      });
    });
  }

  private dimNodeAt(pos: number) {
    const dom = this.editorView.nodeDOM(pos);
    if (dom instanceof HTMLElement) {
      dom.style.opacity = DIMMED_OPACITY;
      dom.style.pointerEvents = "none";
      this.dimmedEls.push(dom);
    }
  }

  private clearDim() {
    for (const dom of this.dimmedEls) {
      dom.style.opacity = "";
      dom.style.pointerEvents = "";
    }
    this.dimmedEls = [];
  }
}

export function createDragScopeFeedbackPlugin(): Plugin {
  return new Plugin({
    key: new PluginKey("documentDragScopeFeedback"),
    view(editorView) {
      return new DragScopeFeedbackView(editorView);
    },
  });
}

export const DragScopeFeedback = Extension.create({
  name: "documentDragScopeFeedback",
  addProseMirrorPlugins() {
    return [createDragScopeFeedbackPlugin()];
  },
});
