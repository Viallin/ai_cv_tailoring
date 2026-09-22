import type { Editor } from "@tiptap/react";
import { SeparatorHorizontal } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { PAGE_EDGE_CHECKBOX_ROW_LEFT_PX } from "@/lib/tiptap/gutterLayout";
import type { GutterCheckboxProps, GutterPageBreakProps, GutterRegistry } from "@/lib/tiptap/gutterRegistry";
import { computeActiveGutterItemId, computeNodeAncestry } from "@/lib/tiptap/useNodeAncestry";
import { cn } from "@/lib/utils";

interface DocumentGutterProps {
  registry: GutterRegistry;
  editor: Editor;
}

interface MeasuredItem {
  id: string;
  top: number;
  checkbox: GutterCheckboxProps;
  sparkles?: ReactNode;
  // Phase 30 — see GutterItem.pageBreak's own docstring.
  pageBreak?: GutterPageBreakProps;
}

// Phase 28 (follow-up) — the one place that actually renders a checkbox/
// Sparkles element for any section/entry/bullet row; the NodeViews
// themselves (components/tiptap/{Section,Entry,Bullet}NodeView.tsx) only
// register data via useGutterItem. Rendered as a child *inside*
// `<A4Page>` now (DocumentEditor.tsx), not as a separate column outside
// it — see gutterLayout.ts's own docstring for why: pulling this out to
// its own layout column was the actual mistake reported, not the idea of
// hoisting the chrome out of the text flow itself. `position: absolute;
// inset: 0` here, `pointer-events: none` on this root (each item's own
// row opts back in with `pointer-events-auto`) so the overlay never
// blocks clicking/selecting the real CV text it sits on top of —
// everything renders at `gutterLayout.ts`'s
// PAGE_EDGE_CHECKBOX_ROW_LEFT_PX, landing inside the page's own blank
// left padding without ever overlapping the text area. That constant
// (not the more obvious-looking CHECKBOX_ROW_LEFT_PX) matters: this
// container's own `inset: 0` resolves against `.cv-a4-page`'s own
// padding *box* — its outer edge, not the text's — so a first pass that
// used the text-relative offset directly here rendered the checkbox 62px
// to the *left of the page itself*, not merely deep in its padding; see
// gutterLayout.ts's own docstring for the full story (a real, reported
// bug: unreachable behind the surrounding `overflow-x-auto`, since a
// scrollable container's default range doesn't extend to *negative*
// overflow the way it does for positive).
//
// Position is the one thing here that can't be verified under jsdom
// (getBoundingClientRect() is always a zero rect there, same limitation
// every Tiptap-era phase has hit — see Phase 26/27's own notes) — the
// *visibility* rule (which rows get a checkbox at all) is deliberately
// kept independent of measurement (see useGutterItem.ts), specifically so
// that part stays unit-testable; only the on-screen `top` position is a
// live-verification-only concern.

// Phase 28 (follow-up) — reported directly: a checkbox on every single
// row, all the time, made it hard to tell which bullets were even there
// — the checkboxes themselves became the dominant visual signal, not the
// CV text. The expected use case is "leave what the AI chose alone,"
// exclude is the rare action — so the checkbox now only shows for the row
// currently being hovered or edited, the same "reveal near the content
// it belongs to" idea DragHandle.tsx already established for the drag
// handle (Phase 27), just driven by JS hover/selection tracking instead
// of CSS `group-hover` — a gutter item and its own row live in two
// different DOM subtrees (that's the whole point of this file), so plain
// CSS can't reach across on its own. Sparkles stays always-visible,
// deliberately not folded into this — it's a passive, useful-while-
// scanning signal ("this bullet was AI-edited"), not a rarely-used
// action like the checkbox.
const HOVER_HIDE_DELAY_MS = 150;

export function DocumentGutter({ registry, editor }: DocumentGutterProps) {
  const items = useSyncExternalStore(registry.subscribe, registry.getSnapshot);
  const containerRef = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState<MeasuredItem[]>([]);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [activeSelectionId, setActiveSelectionId] = useState<string | null>(null);
  const hideTimeoutRef = useRef<number | null>(null);

  // A short grace period before hiding, not an immediate clear on
  // mouseleave — the row (in the page) and its checkbox (in this
  // overlay, rendered separately) are two independent hover targets with
  // a real gap between them; without this, moving the mouse from one
  // toward the other reads as "left," hiding the checkbox before the
  // pointer ever arrives at it.
  const showHover = useCallback((id: string) => {
    if (hideTimeoutRef.current != null) {
      window.clearTimeout(hideTimeoutRef.current);
      hideTimeoutRef.current = null;
    }
    setHoveredId(id);
  }, []);

  const scheduleHideHover = useCallback((id: string) => {
    if (hideTimeoutRef.current != null) {
      window.clearTimeout(hideTimeoutRef.current);
    }
    hideTimeoutRef.current = window.setTimeout(() => {
      setHoveredId((current) => (current === id ? null : current));
      hideTimeoutRef.current = null;
    }, HOVER_HIDE_DELAY_MS);
  }, []);

  useEffect(() => {
    return () => {
      if (hideTimeoutRef.current != null) {
        window.clearTimeout(hideTimeoutRef.current);
      }
    };
  }, []);

  // Hover on the row itself (in the page) is a native DOM listener, not a
  // React prop — anchorEl belongs to a NodeView, entirely outside this
  // component's own JSX.
  useEffect(() => {
    const cleanups: Array<() => void> = [];
    for (const item of items) {
      const el = item.anchorEl;
      const onEnter = () => showHover(item.id);
      const onLeave = () => scheduleHideHover(item.id);
      el.addEventListener("mouseenter", onEnter);
      el.addEventListener("mouseleave", onLeave);
      cleanups.push(() => {
        el.removeEventListener("mouseenter", onEnter);
        el.removeEventListener("mouseleave", onLeave);
      });
    }
    return () => cleanups.forEach((cleanup) => cleanup());
  }, [items, showHover, scheduleHideHover]);

  const remeasure = useCallback(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const containerRect = container.getBoundingClientRect();
    const next: MeasuredItem[] = [];
    for (const item of registry.getSnapshot()) {
      if (!item.anchorEl.isConnected) {
        continue; // a stale registration mid-unmount — the cleanup effect will unregister it shortly
      }
      // Cascading exclusion (an excluded ancestor entry/section) is
      // checked here, against the *live* document, rather than trusted
      // from whatever the registering NodeView's own included/sparkles
      // props were at its last render — see gutterRegistry.ts's own
      // docstring on GutterItem.getPos for the staleness bug this avoids.
      const ancestry = computeNodeAncestry(editor.state.doc, item.getPos());
      if (!ancestry.sectionIncluded || !ancestry.entryIncluded) {
        continue;
      }
      const rect = item.anchorEl.getBoundingClientRect();
      next.push({
        id: item.id,
        top: rect.top - containerRect.top,
        checkbox: item.checkbox,
        sparkles: item.sparkles,
        pageBreak: item.pageBreak,
      });
    }
    // Sorted by measured position, not registration order (Map iteration
    // order doesn't move an existing key on re-registration, so it can't
    // be trusted to reflect document order after a drag reorder) — this
    // also gives keyboard Tab order a sensible top-to-bottom sequence.
    next.sort((a, b) => a.top - b.top);
    setMeasured(next);
  }, [registry, editor]);

  useLayoutEffect(() => {
    remeasure();
  }, [items, remeasure]);

  useEffect(() => {
    const onUpdate = () => {
      remeasure();
      setActiveSelectionId(computeActiveGutterItemId(editor.state.doc, editor.state.selection.from));
    };
    editor.on("update", onUpdate);
    editor.on("selectionUpdate", onUpdate);
    return () => {
      editor.off("update", onUpdate);
      editor.off("selectionUpdate", onUpdate);
    };
  }, [editor, remeasure]);

  // Self-observed rather than an outer wrapper passed in from
  // DocumentEditor.tsx — this container is now `inset: 0` inside
  // `.cv-a4-page` itself (not a separate flex sibling with its own
  // independent size), so its own border-box already tracks the page's
  // height for free; watching it directly catches the same reflow
  // (font load, template swap) an outer-wrapper observer would have.
  useEffect(() => {
    const target = containerRef.current;
    if (!target || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(() => remeasure());
    observer.observe(target);
    return () => observer.disconnect();
  }, [remeasure]);

  return (
    // `.cv-a4-page > * + *` (index.css) gives every direct child but the
    // first a top margin — harmless for this element's own coordinate
    // math (every item's `top` is computed relative to *this* container's
    // own rendered position, so it self-corrects for any offset the
    // container itself has), but `marginTop: 0` here removes the need to
    // reason about that at all.
    <div ref={containerRef} className="pointer-events-none absolute inset-0" style={{ marginTop: 0 }}>
      {measured.map((item) => {
        const checkboxVisible = item.id === hoveredId || item.id === activeSelectionId;
        return (
          // Reported directly: Checkbox (size-4, 16px) and the Sparkles
          // trigger (icon-xs, 24px) are two different sizes, and
          // `items-start` (both prior fixes in this file used it) aligns
          // their *top* edges, not their icons' visual centers — Sparkles
          // reading as always-lower is that 8px size difference, not a
          // positioning bug. `items-center` cross-aligns them properly
          // instead; `mt-0.5` (was `mt-1.5`) is the compensating base
          // offset — Checkbox, centered within Sparkles' taller 24px box,
          // lands 4px lower than the row's own top either way, so
          // dropping the row's own margin by that same 4px keeps
          // Checkbox's final position exactly where the earlier `mt-1.5`
          // fix already put it (this file's own git history has the
          // math), while lifting Sparkles up to match it instead of the
          // other way around. Each NodeView's own drag handle (rendered
          // separately, not in this row at all — see gutterLayout.ts's
          // own docstring for why) needed the *same* target: it's
          // `size-4` like Checkbox, so it only needs the plain `mt-1.5`
          // DragHandle.tsx already defaults to — SectionNodeView's own
          // `mt-0` override (a leftover from the old flex-centered header
          // row, no longer applicable now that this is `position:
          // absolute`) was the one real mismatch, removed separately.
          //
          // `min-h-6` (24px, matching Sparkles' own icon-xs size) is load-
          // bearing, not decorative — reported directly: the fix above
          // only held for a bullet that actually *has* Sparkles. Most
          // rows don't (every section/entry, and any bullet the AI didn't
          // rewrite) — without a sparkles sibling, this row's own height
          // collapses to Checkbox's bare 16px, `items-center` has nothing
          // taller to center it against, and Checkbox loses the 4px
          // offset that keeps it level with the handle. `min-h-6` keeps
          // the row's cross-axis size at 24px unconditionally, whether or
          // not `item.sparkles` is actually present this render.
          <div
            key={item.id}
            className="pointer-events-auto absolute mt-0.5 flex min-h-6 items-center gap-0.5"
            style={{ top: item.top, left: PAGE_EDGE_CHECKBOX_ROW_LEFT_PX }}
            onMouseEnter={() => showHover(item.id)}
            onMouseLeave={() => scheduleHideHover(item.id)}
          >
            <Checkbox
              checked={item.checkbox.checked}
              onCheckedChange={item.checkbox.onToggle}
              disabled={item.checkbox.disabled}
              aria-label={item.checkbox.ariaLabel}
              className={cn("transition-opacity", checkboxVisible ? "opacity-100" : "opacity-0 pointer-events-none")}
            />
            {/* Phase 30 — same visual slot as sparkles, `sparkles` winning
                when a row has both (only the summary entry ever can — see
                gutterRegistry.ts's own GutterItem.pageBreak docstring for
                that one accepted tradeoff). Unlike the checkbox (hover-
                only regardless of state) or Sparkles (always visible,
                passive), this splits the difference: hover-only while
                *off* (a rare action, same reveal-on-hover reasoning as
                the checkbox), but stays visible once *on* — a person
                needs to be able to tell at a glance which rows are
                forcing a break without hovering every one of them. */}
            {item.sparkles ??
              (item.pageBreak && (
                <Button
                  type="button"
                  variant={item.pageBreak.active ? "secondary" : "ghost"}
                  size="icon-xs"
                  aria-label={item.pageBreak.ariaLabel}
                  aria-pressed={item.pageBreak.active}
                  onClick={item.pageBreak.onToggle}
                  className={cn(
                    "transition-opacity",
                    item.pageBreak.active || checkboxVisible ? "opacity-100" : "opacity-0 pointer-events-none",
                  )}
                >
                  <SeparatorHorizontal />
                </Button>
              ))}
          </div>
        );
      })}
    </div>
  );
}
