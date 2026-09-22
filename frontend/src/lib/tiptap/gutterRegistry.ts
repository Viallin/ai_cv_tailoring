import type { ReactNode } from "react";

export interface GutterCheckboxProps {
  checked: boolean;
  onToggle: () => void;
  ariaLabel: string;
  disabled?: boolean;
}

// Phase 30 — manual pagination control. Same shape as GutterCheckboxProps
// deliberately (a plain on/off with a click handler), kept as its own
// type rather than reusing that one: `checked` there means "included in
// the export," semantically unrelated to "forces a page break," even
// though the props happen to line up.
export interface GutterPageBreakProps {
  active: boolean;
  onToggle: () => void;
  ariaLabel: string;
}

export interface GutterItem {
  // Stable per-row key: `section:${key}` | `entry:${id}` | `bullet:${id}` —
  // see the three NodeViews for exactly what they pass.
  id: string;
  // The row's own DOM element, used only to *measure* where to position
  // this item's chrome (DocumentGutter.tsx reads its
  // getBoundingClientRect() on every remeasure) — never rendered directly.
  anchorEl: HTMLElement;
  // Tiptap's own live-bound `getPos` (NodeViewProps.getPos, re-exposed as
  // `() => this.getPos()` — see @tiptap/react's ReactNodeView.mount()),
  // not a value captured once. DocumentGutter calls this — never a value
  // read from the registering NodeView's own last render — to check
  // whether every ancestor (section/entry) is still included, precisely
  // because that fact can change *without* this row's own NodeView
  // re-rendering (see useNodeAncestry.ts's own docstring on
  // computeNodeAncestry for the real bug this fixes: a child NodeView
  // whose own node is unchanged isn't guaranteed to re-render just
  // because an ancestor's attrs changed).
  getPos: () => number | undefined;
  checkbox: GutterCheckboxProps;
  // Bullets have one from BulletNodeView's own isSubstantiveEdit check;
  // EntryNodeView's summary entry is the one other case, from its own
  // summaryEdited check — the fully-built Popover element, not just its
  // content, since DocumentGutter has no reason to know *how* to render
  // it.
  sparkles?: ReactNode;
  // Phase 30 — only sections/entries ever have one (never bullets, see
  // structuredDocument.ts's DocumentEntry.page_break_before docstring on
  // why that's entry-only). Shares one visual slot with `sparkles` below
  // (DocumentGutter.tsx renders whichever is present, `sparkles` winning
  // when both are) — true mutual exclusivity for every *other* entry (at
  // most one of the two is ever set), except the one entry that can
  // legitimately have both: a summary that's both AI-edited (`sparkles`)
  // and a candidate for a forced page break (`pageBreak`). There, the
  // page-break toggle is simply unreachable via this gutter row for as
  // long as the edit badge is showing — accepted directly as a minor,
  // narrowly-scoped tradeoff (see EntryNodeView.tsx's own comment) rather
  // than adding a second visual slot for a combination nothing else in
  // the document ever produces.
  pageBreak?: GutterPageBreakProps;
}

type Listener = () => void;

// Phase 28 — registration is bottom-up (every NodeView -> the one
// DocumentGutter overlay), which plain React Context can't do on its own:
// context.tsx's own docstring already established that a *nested*
// Context.Provider re-provided inside one NodeView is invisible to
// NodeViews mounted under it (Tiptap's ReactNodeViewRenderer mounts every
// NodeView as its own portal into one editor-wide React tree, not nested
// React subtrees) — but that finding was about *providing new values*
// top-down, not about calling a stable function handed down from the one
// real top-level Provider, which already works fine (onToggleBullet etc.
// prove it). So registration itself reuses that existing top-level
// Context (registerGutterItem/unregisterGutterItem added to
// DocumentEditorNodeViewContextValue); this class is the actual mutable
// store those two functions write into on every NodeView render.
//
// A plain external store, not React state — DocumentGutter is a
// completely different component subtree than the NodeViews registering
// into it, so there's no ordinary parent-render-drives-child-render path
// for "a NodeView registered/updated" to reach it. useSyncExternalStore
// is the correct primitive for exactly this (subscribe/getSnapshot must be
// stable identities, which is why they're bound instance methods here,
// not fresh closures per call).
export class GutterRegistry {
  private items = new Map<string, GutterItem>();
  private listeners = new Set<Listener>();
  private snapshot: GutterItem[] = [];

  // Upsert — every NodeView calls this on every render (checked/disabled/
  // sparkles content can all change without the anchor element itself
  // changing), not just once at mount.
  register = (item: GutterItem): void => {
    this.items.set(item.id, item);
    this.publish();
  };

  unregister = (id: string): void => {
    if (this.items.delete(id)) {
      this.publish();
    }
  };

  private publish(): void {
    // A fresh array identity every publish — useSyncExternalStore compares
    // getSnapshot()'s return by reference to decide whether to re-render.
    this.snapshot = Array.from(this.items.values());
    this.listeners.forEach((listener) => listener());
  }

  subscribe = (listener: Listener): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = (): GutterItem[] => this.snapshot;
}
