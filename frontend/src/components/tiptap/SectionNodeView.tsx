import { NodeViewContent, NodeViewWrapper, type NodeViewProps } from "@tiptap/react";
import { useRef } from "react";

import { DragHandle } from "@/components/tiptap/DragHandle";
import { useDocumentEditorNodeViewContext } from "@/lib/tiptap/context";
import { HANDLE_LEFT_PX } from "@/lib/tiptap/gutterLayout";
import { useGutterItem } from "@/lib/tiptap/useGutterItem";
import { cn } from "@/lib/utils";

// Phase 26 — a section's own always-visible heading+checkbox
// (unaffected by `included`, exactly like DocumentSectionBlock.tsx/
// DocumentExperienceSection.tsx before it — a fully-excluded section
// still shows its header so it stays toggleable) plus its `entry*`
// children, hidden as a whole (not walked into) when `included` is
// false — matching the old `{section.included && (...)}` gate. Hidden
// via CSS only when there are zero entries, never by skipping
// <NodeViewContent> itself — ProseMirror needs a stable contentDOM for
// the node's whole lifetime, so "nothing to show" has to stay a style
// concern, not a conditional-render one (matches DocumentSectionBlock.tsx's
// old "section.entries.length === 0 -> render nothing" rule, just
// enforced with `hidden` instead of an early return).
//
// No nested context Provider here — see lib/tiptap/context.tsx's own
// docstring for why re-providing context per-NodeView doesn't work with
// Tiptap's ReactNodeViewRenderer; EntryNodeView/EntryHeadingNodeView/
// BulletNodeView derive their own section/entry identity from the live
// ProseMirror doc instead (lib/tiptap/useNodeAncestry.ts).
//
// Phase 27 — the header row is the one drag handle *not* inside
// DocumentRow.tsx (this is the only draggable node with no bullet/entry
// text of its own to share that layout with), so it gets its own
// `group` wrapper directly. Reordering a whole section is new — the old
// dnd-kit editor never supported it at all, only entry/bullet reorder
// within a fixed section list (see structuredDocument.ts's history).
// `onDragSelect` explicitly selects this section before the native drag
// starts — see DragHandle.tsx's own docstring for why that's required,
// not just belt-and-suspenders, for entries; applied uniformly here too.
//
// Phase 28 — the checkbox itself moved out to DocumentGutter
// (components/tiptap/DocumentGutter.tsx); `anchorRef` on this row (not on
// `<NodeViewWrapper>` itself) is what DocumentGutter measures to position
// the section's checkbox — visible whenever this row is (gated on
// `hasEntries` below, same as before), independent of `included` (a
// fully-excluded section still needs its own checkbox reachable to
// toggle it back).
//
// Phase 28 (follow-up) — the drag handle moved from a normal-flow flex
// sibling of `<h2>` to `position: absolute` at gutterLayout.ts's
// HANDLE_LEFT_PX (a negative offset into the page's own blank left
// padding) — reported directly: the old flex layout pushed the heading
// text right by the handle's own width, and the fix needed was "stop
// shifting the text," not "move the handle somewhere else entirely."
// `anchorRef` still measures this row's own top correctly — the handle
// no longer contributes to its height (being absolute), but the div's
// height still tracks `<h2>`, its one remaining normal-flow child.
export function SectionNodeView({ node, editor, getPos }: NodeViewProps) {
  const ctx = useDocumentEditorNodeViewContext();
  const included = node.attrs.included !== false;
  const key = node.attrs.key as string;
  const title = node.attrs.title as string;
  const hasEntries = node.childCount > 0;
  const pageBreakBefore = node.attrs.page_break_before === true;
  const anchorRef = useRef<HTMLDivElement>(null);

  useGutterItem(
    `section:${key}`,
    anchorRef,
    getPos,
    hasEntries
      ? {
          checkbox: {
            checked: included,
            onToggle: () => ctx.onToggleSection(key),
            ariaLabel: `Include ${title} section`,
          },
          // Phase 30 — manual pagination control (GutterPageBreakProps's
          // own docstring). Independent of `included`/`hasEntries` beyond
          // the outer gate above — an excluded section can still force a
          // break before wherever it would otherwise render.
          pageBreak: {
            active: pageBreakBefore,
            onToggle: () => ctx.onToggleSectionPageBreak(key),
            ariaLabel: pageBreakBefore
              ? `Remove the forced page break before ${title}`
              : `Start ${title} on a new page`,
          },
        }
      : null, // no entries at all (not merely all-excluded) — the whole <section> renders nothing, gutter included
  );

  return (
    <NodeViewWrapper as="section" className={cn("space-y-1", !hasEntries && "hidden")}>
      <div ref={anchorRef} className="group relative" contentEditable={false}>
        <DragHandle
          ariaLabel={`Drag to reorder the ${title} section`}
          className="absolute top-0"
          style={{ left: HANDLE_LEFT_PX }}
          onDragSelect={() => {
            const pos = getPos();
            if (typeof pos === "number") editor.commands.setNodeSelection(pos);
          }}
        />
        {/* Phase 30 — a plain DOM signal PageBreakGuide.tsx's measureUnits
            reads directly (`h2[data-page-break-before="true"]`), same
            "measure reality, don't recompute a parallel layout" call
            gutterLayout.ts's own hidden-class checks already make —
            rather than duplicating this section's own model state via a
            second, independently-maintained lookup. data-section-key is
            the on-screen page-break-prediction fix's own equivalent
            (follow-up to Version 4, Phase 4.9) — see
            BulletNodeView.tsx's data-bullet-id for the full rationale;
            this is the section-level counterpart. */}
        <h2
          className="text-base font-semibold"
          data-page-break-before={pageBreakBefore || undefined}
          data-section-key={key}
        >
          {title}
        </h2>
      </div>
      <NodeViewContent<"ul"> as="ul" className={cn("space-y-1", !included && "hidden")} contentEditable={included} />
    </NodeViewWrapper>
  );
}
