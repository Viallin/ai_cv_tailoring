import { useEffect, type ReactNode, type RefObject } from "react";

import { useDocumentEditorNodeViewContext } from "@/lib/tiptap/context";
import type { GutterCheckboxProps, GutterPageBreakProps } from "@/lib/tiptap/gutterRegistry";

interface GutterItemContent {
  checkbox: GutterCheckboxProps;
  sparkles?: ReactNode;
  // Phase 30 — see GutterItem.pageBreak's own docstring.
  pageBreak?: GutterPageBreakProps;
}

// Phase 28 — the one hook every gutter-eligible NodeView (Section/Entry/
// Bullet) calls instead of rendering its own checkbox/Sparkles inline.
// `content === null` means "this row itself isn't included right now"
// (its own `included`/`hasEntries`, whichever applies — see each
// caller). Cascading exclusion from an *ancestor* being excluded is
// deliberately NOT decided here — DocumentGutter.tsx re-checks that
// itself, directly against the live document, via `getPos` on every
// remeasure (see gutterRegistry.ts's own docstring on why: a value
// derived from an ancestor's state at *this* NodeView's own render time
// can go stale without this component ever re-rendering).
//
// Runs on every render, deliberately with no dependency array —
// `content` is a fresh object/ReactNode most renders (checked/disabled
// state, provenance-derived popover content), and registry.register is a
// cheap Map upsert (see gutterRegistry.ts), so there's no correctness
// reason to hand-memoize every caller's props just to skip it. Only the
// unmount cleanup is a real one-time effect.
export function useGutterItem(
  id: string,
  anchorRef: RefObject<HTMLElement | null>,
  getPos: () => number | undefined,
  content: GutterItemContent | null,
): void {
  const ctx = useDocumentEditorNodeViewContext();

  useEffect(() => {
    if (content != null && anchorRef.current != null) {
      ctx.registerGutterItem({
        id,
        anchorEl: anchorRef.current,
        getPos,
        checkbox: content.checkbox,
        sparkles: content.sparkles,
        pageBreak: content.pageBreak,
      });
    } else {
      ctx.unregisterGutterItem(id);
    }
  });

  useEffect(() => {
    return () => ctx.unregisterGutterItem(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- unregister only on real unmount/id change, not every render (the effect above already re-registers with fresh content every render)
  }, [id, ctx]);
}
