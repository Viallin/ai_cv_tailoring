import { GripVertical } from "lucide-react";
import type { CSSProperties } from "react";

import { cn } from "@/lib/utils";

interface DragHandleProps {
  ariaLabel: string;
  className?: string;
  // Phase 28 (follow-up) — every caller now positions this via
  // gutterLayout.ts's HANDLE_LEFT_PX (a negative offset into the page's
  // own blank left padding, keeping it visually aligned with the
  // checkbox/Sparkles cluster DocumentGutter renders independently — see
  // that file's own docstring), so `style` needs to reach the real DOM
  // node here rather than each caller re-deriving `className`.
  style?: CSSProperties;
  // Phase 27 — see this file's own docstring below for why every caller
  // passes one.
  onDragSelect: () => void;
}

// Phase 27 — the one thing that actually makes a section/entry/bullet
// draggable: the browser only *starts* a native drag from an element
// that itself carries the real HTML `draggable` attribute (set here,
// deliberately not on the NodeView's own root — see schema.ts's own
// comment on why dragging has to be handle-only, not whole-row, or it'd
// break click-drag text selection).
//
// Hover-only via Tailwind's `group`/`group-hover:opacity-100` — the
// nearest ancestor with `className="group"` (SectionNodeView.tsx's
// header row, EntryNodeView.tsx's chrome overlay, or BulletNodeView.tsx's
// own row — Phase 28 folded the row-wrapping DocumentRow.tsx used to
// provide into BulletNodeView directly, once it had nothing left to
// share but that one row) controls when it's revealed. Space is always
// reserved (`opacity-0`, never conditionally unmounted) so hovering
// never shifts layout, per the dev-plan's explicit requirement.
//
// `contentEditable={false}`, `data-drag-handle`, `pointer-events-none`
// on the icon, and `select-none` are all real, individually-confirmed
// fixes from earlier reports in this same investigation (a caret-
// placement gesture competing with the drag inside the editable region;
// Tiptap core's own `NodeView.stopEvent()` needing this exact attribute
// to recognize a custom handle at all; a stray SVG primitive absorbing
// the mousedown; `cursor: grab` never actually rendering, showing the
// text/I-beam caret instead — Chrome falls back to that default inside
// a `contentEditable` ancestor for anything it still considers
// text-selectable, and `contentEditable={false}` alone doesn't turn
// that off, only `user-select: none` does) — each real, each necessary,
// none by itself sufficient.
//
// `onDragSelect` (called from `onMouseDown`, wired by every caller to
// `editor.commands.setNodeSelection(pos)` for *their own* draggable
// ancestor) is what actually made dragging work end to end. Root cause,
// found only after all of the above still reproduced identically on a
// completely fresh draft, incognito, cross-browser, with console
// instrumentation confirming ProseMirror's own dragstart handler still
// never ran: `view.posAtCoords()`/`nearestDesc()` — what ProseMirror
// uses by default to figure out *what* is being dragged — resolve to
// the *nearest* NodeView ancestor of the mousedown position and stop
// there, never continuing further up if that nearest one isn't
// `draggable`. That's exactly entryHeading's situation: it sits
// *inside* the actual draggable `entry` node, but has no `draggable` of
// its own (only `entry`/`bullet`/`section` do — see schema.ts), so a
// handle physically positioned inside EntryHeadingNodeView's own DOM
// (to sit inline with the role's own heading row) always resolved to
// "entryHeading, not draggable" and ProseMirror silently gave up —
// confirmed directly via console: `view.input.mouseDown.mightDrag` was
// never populated, for that exact reason, on every real attempt.
// Explicitly setting a NodeSelection around the *correct* ancestor on
// mousedown sidesteps this entirely — ProseMirror's dragstart handler
// checks the *current selection* first, before ever falling back to its
// own (fragile, nearest-ancestor-only) position-based guessing.
export function DragHandle({ ariaLabel, className, style, onDragSelect }: DragHandleProps) {
  return (
    <span
      draggable
      data-drag-handle
      contentEditable={false}
      role="img"
      aria-label={ariaLabel}
      onMouseDown={onDragSelect}
      style={style}
      className={cn(
        "mt-1.5 cursor-grab text-muted-foreground opacity-0 transition-opacity select-none group-hover:opacity-100",
        className,
      )}
    >
      <GripVertical className="pointer-events-none size-4" />
    </span>
  );
}
