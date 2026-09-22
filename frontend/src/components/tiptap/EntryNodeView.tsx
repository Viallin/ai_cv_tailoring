import { NodeViewContent, NodeViewWrapper, type NodeViewProps } from "@tiptap/react";
import { Sparkles, X } from "lucide-react";
import { useRef, useState } from "react";

import { DragHandle } from "@/components/tiptap/DragHandle";
import { Button } from "@/components/ui/button";
import { Popover, PopoverAnchor, PopoverClose, PopoverContent } from "@/components/ui/popover";
import { useDocumentEditorNodeViewContext } from "@/lib/tiptap/context";
import { HANDLE_LEFT_PX } from "@/lib/tiptap/gutterLayout";
import { useGutterItem } from "@/lib/tiptap/useGutterItem";
import { useNodeAncestry } from "@/lib/tiptap/useNodeAncestry";
import { cn } from "@/lib/utils";

// Phase 26 — the `<div class="cv-print-entry">` wrapper around an
// entry's own entryHeading + bullets, matching PrintExperienceSection.tsx's
// per-entry `<div className="cv-print-entry">` shape exactly (so
// on-screen typography/spacing lines up with the export target — see
// the dev-plan's "closes the not pixel-real gap" goal). Rendered for
// every section, not just Experience — a Skills/Contacts/etc. entry (no
// bullets) just ends up with one child instead of several; the extra
// wrapping div vs. PrintSectionBlock.tsx's bare `<p className="cv-print-entry">`
// there is a deliberate, harmless simplification — no rule in index.css
// targets one over the other beyond the shared class, which still lands
// on a real ancestor either way.
//
// Phase 27 — NodeViewWrapper is a real, box-generating `<div>` here, NOT
// `display:contents` (the first version of this file used
// `className="contents"` to avoid an extra visual wrapper layer around
// NodeViewContent). Found from a real reported bug ("drop shows the
// dropcursor line, but releasing the mouse does nothing"): ProseMirror's
// `view.posAtCoords()` — which the native drop handler depends on to
// figure out where to insert the dragged node — returned the *entry's
// own start position* for every coordinate anywhere inside "Oversaw
// product direction..." bullet's own text, never resolving deeper.
// Traced directly to `getBoundingClientRect()` on this wrapper returning
// an all-zero rect (confirmed by inspecting the live DOM) — a
// `display:contents` element generates no box at all, and ProseMirror's
// coordinate-to-position resolution relies on rect comparisons to
// decide which child NodeView a given point falls inside; with a
// zero-rect ancestor in the way, it can't descend past this level, so
// every drop silently computed the same (wrong, and for a same-entry
// bullet move, always exactly where it already was) position and
// inserted nothing new. The extra `<div>` this reintroduces was already
// an accepted, harmless-for-rendering tradeoff (see two paragraphs up)
// — it turns out not harmless for native drag/drop hit-testing, which
// is worth the one extra DOM level.
//
// Phase 27 (revised) — the drag-handle chrome for the whole entry lives
// *here* now, not inside EntryHeadingNodeView, even though it visually
// sits inline with the heading row. See schema.ts's TiptapEntryHeading
// comment for the two concrete bugs (stopEvent() swallowing the drag,
// then onDragStart corrupting the selection — the second one
// destructive, confirmed against a real draft) that came from putting it
// in the child NodeView instead.
//
// Phase 28 — the checkbox itself moved to DocumentGutter
// (components/tiptap/DocumentGutter.tsx). `anchorRef` here is what
// DocumentGutter measures for this entry's checkbox position; visibility
// gates on this entry's own `included` only (an ancestor section being
// excluded is checked separately, fresh against the live doc, by
// DocumentGutter itself — see useGutterItem.ts's own docstring for why).
//
// Phase 28 (follow-up) — the handle's own `left: 0` (flush with
// EntryHeadingNodeView's own `pl-6`-reserved space) became `left:
// gutterLayout.HANDLE_LEFT_PX` (negative, into the page's own blank
// margin) once that reserved space was removed entirely — reported
// directly: pushing the heading text right to make room for the handle
// was exactly the kind of layout shift that needed to go away, not just
// move to a different column. `anchorRef` still measures this row's own
// top correctly; the chrome div's own left offset doesn't affect that.
//
// `group` here spans the *whole* entry (all its bullets too), not just
// the heading row — hovering any bullet reveals the entry's own handle
// floating at the top, not just hovering the heading itself. A
// deliberate simplification, not a bug: scoping the hover strictly to
// the heading row would need a `:has()`-based cross-branch hover query
// (the handle and the heading text are siblings in different DOM
// subtrees now, not parent/child, so plain `group-hover` can't reach
// across on its own), which isn't worth the added complexity for what
// is, worst case, "the handle reveals a little more eagerly than
// before."
//
// An excluded entry (`included: false`) is hidden entirely, not shown
// struck-through — same Phase 24 invariant as before, just enforced by
// a NodeView instead of a `.filter()` before `.map()`. The underlying
// ProseMirror node stays in the document either way (see
// lib/tiptap/plugins.ts's own docstring) — ExcludedContentPanel's
// "Restore" flips `included` back via DocumentEditor.tsx's dual-write
// path, not by re-inserting anything.
//
// "+ Add Bullet" (a blank, untailored bullet — for hand-addressing a Gap
// the AI didn't cover, see structuredDocument.ts::addBullet's docstring)
// only ever applied to Experience in the old DocumentExperienceSection.tsx
// too — every other section's entries have no bullets to add to — so
// it's gated on the owning section's key (from useNodeAncestry — this
// node has no sectionKey of its own), the same check EntryHeadingNodeView
// uses for its own default bold/italic styling. Rendered as a
// NodeViewWrapper sibling to <NodeViewContent>, not inside it — chrome,
// not document content, exactly like the checkbox/handle above.
export function EntryNodeView({ node, editor, getPos }: NodeViewProps) {
  const ctx = useDocumentEditorNodeViewContext();
  const { sectionKey } = useNodeAncestry({ editor, getPos });
  const included = node.attrs.included !== false;
  const locked = Boolean(node.attrs.locked);
  const entryId = node.attrs.id as string;
  const pageBreakBefore = node.attrs.page_break_before === true;
  const showAddBullet = included && !locked && sectionKey === "experience";
  const anchorRef = useRef<HTMLDivElement>(null);
  // entryHeading is always this node's first child (schema.ts) — folded
  // into the aria-label so multiple entries' checkboxes (all sharing the
  // same generic "Include this entry" wording otherwise) are actually
  // distinguishable, now that they're siblings in one shared gutter
  // rather than each sitting next to its own row's text.
  const headingText = node.firstChild?.textContent ?? "";

  // The summary is structurally just one more plain entry (structuredDocument.ts's
  // buildSummarySection — a single `{id: "summary", text: cv.summary}`
  // entry, same "entry" node type every other section's own entries use),
  // so its own Sparkles/"revert to original" affordance lives here rather
  // than as a one-off special case elsewhere. Reported directly: bullets
  // show whether they were AI-edited and let you compare/revert, but the
  // summary — also freshly written by the same tailoring pass — gave no
  // sign it wasn't just copied from the profile. Gated on this exact
  // entry (not just `sectionKey === "summary"`, though today's summary
  // section only ever has the one entry) so a future summary-section
  // shape with more than one entry doesn't pick this up by accident.
  const isSummaryEntry = sectionKey === "summary" && entryId === "summary";
  const summaryProvenance = isSummaryEntry ? ctx.summaryProvenance : undefined;
  // Mirrors BulletNodeView's own isSubstantiveEdit — compares the *live*
  // text (possibly hand-edited further since generation) against the
  // original, not summaryProvenance.rewritten_text, so a user's own edit
  // back to the original text makes the affordance disappear correctly.
  const summaryEdited = summaryProvenance != null && headingText.trim() !== summaryProvenance.original_text.trim();
  // Accepted tradeoff, not an oversight: this is the one entry that can
  // pass both `sparkles` and `pageBreak` to useGutterItem below, and
  // DocumentGutter.tsx's shared visual slot renders `sparkles` first when
  // both are present (see gutterRegistry.ts's GutterItem.pageBreak
  // docstring) — so while this badge is showing, the summary entry's own
  // "start on a new page" toggle is reachable only by first reverting or
  // otherwise clearing the edit. Forcing a page break directly before the
  // CV's very first content section is a rare enough need that trading it
  // away here, rather than adding a second visual slot, was the smaller
  // change for what these two features actually get used for.
  const [summaryPopoverOpen, setSummaryPopoverOpen] = useState(false);
  // Virtual Popover anchor pointing at the real `.cv-print-entry` element
  // (this entry's own NodeViewContent, the very next sibling of the chrome
  // div `anchorRef` below) rather than the small Sparkles icon itself —
  // same fix, and same reasoning, as BulletNodeView's own bulletAnchor.
  const summaryAnchor = useRef<{ getBoundingClientRect: () => DOMRect }>({
    getBoundingClientRect: () => anchorRef.current?.nextElementSibling?.getBoundingClientRect() ?? new DOMRect(),
  });

  // Only this entry's *own* `included` gates registration here — whether
  // its ancestor section is also excluded is DocumentGutter's own concern
  // (computeNodeAncestry, checked fresh on every remeasure — see
  // useGutterItem.ts's docstring for why that can't safely be decided at
  // this component's own render time).
  useGutterItem(
    `entry:${entryId}`,
    anchorRef,
    getPos,
    included
      ? {
          checkbox: {
            checked: true, // visible in the gutter at all implies included, by construction — same invariant BulletNodeView's own checkbox keeps
            onToggle: () => ctx.onToggleEntry(sectionKey, entryId),
            // Phase 28 (follow-up) — a locked (career-gap) entry's
            // checkbox used to be disabled outright ("Career gaps can't
            // be excluded"). Reported directly: the system not *auto*-
            // dropping a gap during generation was never meant to mean
            // the user can't exclude one by hand afterward — that's
            // their call, same as any other entry. `locked` still means
            // something (EntryHeadingNodeView's italic styling,
            // commands.ts's backspace-merge guard, "+ Add Bullet" staying
            // hidden for a gap) — only the checkbox's own disabled state
            // and grey "can't be excluded" wording are gone.
            ariaLabel: headingText ? `Include this entry: ${headingText}` : "Include this entry",
          },
          // Phase 30 — manual pagination control (GutterPageBreakProps's
          // own docstring).
          pageBreak: {
            active: pageBreakBefore,
            onToggle: () => ctx.onToggleEntryPageBreak(sectionKey, entryId),
            ariaLabel: pageBreakBefore
              ? `Remove the forced page break before this entry${headingText ? `: ${headingText}` : ""}`
              : `Start this entry on a new page${headingText ? `: ${headingText}` : ""}`,
          },
          sparkles: summaryEdited ? (
            <Popover open={summaryPopoverOpen} onOpenChange={setSummaryPopoverOpen}>
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label="AI-edited summary — view original text and revert"
                aria-haspopup="dialog"
                aria-expanded={summaryPopoverOpen}
                onClick={() => setSummaryPopoverOpen((current) => !current)}
              >
                <Sparkles />
              </Button>
              <PopoverAnchor virtualRef={summaryAnchor} />
              <PopoverContent
                side="bottom"
                align="center"
                collisionPadding={16}
                className="space-y-3 p-4"
                style={{ width: "var(--radix-popper-anchor-width)" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-medium text-muted-foreground uppercase">Rewritten</p>
                  <PopoverClose asChild>
                    <Button type="button" variant="ghost" size="icon-xs" aria-label="Close">
                      <X />
                    </Button>
                  </PopoverClose>
                </div>
                <div className="rounded bg-muted p-2 text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">Original: </span>
                  {summaryProvenance?.original_text}
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={() => summaryProvenance && ctx.onRevertSummary(summaryProvenance.original_text)}
                >
                  Revert to original
                </Button>
              </PopoverContent>
            </Popover>
          ) : undefined,
        }
      : null,
  );

  return (
    <NodeViewWrapper as="div" className="relative">
      {/* Phase 28 (follow-up) — `position: absolute` moved from this div
          onto DragHandle itself, matching Bullet/SectionNodeView's own
          pattern exactly. Reported directly, found by measurement: this
          div carrying `absolute top-0` while DragHandle stayed a plain
          (default `display: inline`) `<span>` meant DragHandle's own
          `mt-1.5` had no visual effect at all — CSS vertical margins are
          ignored on inline-level boxes — so the handle rendered flush
          with this row's own top instead of 6px down, 6px out of sync
          with Checkbox next to it. `position: absolute` forces block-
          level box generation regardless of the element's own `display`,
          which is incidentally why Bullet/Section's handles were never
          affected — passing that positioning to DragHandle there (not a
          separate wrapper) was already the correct pattern; this file
          was the one NodeView that didn't follow it. This div now only
          needs `group` (DragHandle's own hover scope) and `anchorRef`
          (DocumentGutter's checkbox measurement point) — no positioning
          of its own, so it collapses to zero height, which is fine: only
          its own `top` (still correct, still exactly where it sits in
          normal flow) is ever read. */}
      <div ref={anchorRef} className="group" contentEditable={false}>
        <DragHandle
          ariaLabel="Drag to reorder this entry"
          className="absolute top-0"
          style={{ left: HANDLE_LEFT_PX }}
          onDragSelect={() => {
            const pos = getPos();
            if (typeof pos === "number") editor.commands.setNodeSelection(pos);
          }}
        />
      </div>
      {/* Phase 30 — data-page-break-before is a plain DOM signal
          PageBreakGuide.tsx's measureUnits reads directly (same "measure
          reality" call SectionNodeView.tsx's own h2 makes), not a second,
          independently-maintained copy of this entry's model state. */}
      <NodeViewContent
        as="div"
        className={cn("cv-print-entry", !included && "hidden")}
        contentEditable={included}
        data-page-break-before={pageBreakBefore || undefined}
        // On-screen page-break-prediction fix (follow-up to Version 4,
        // Phase 4.9) — see BulletNodeView.tsx's identical data-bullet-id
        // for the full rationale; this is the entry-level counterpart.
        data-entry-id={entryId}
      />
      {showAddBullet && (
        <Button
          type="button"
          variant="outline"
          size="xs"
          className="ml-8"
          contentEditable={false}
          onClick={() => ctx.onAddBullet(sectionKey, entryId)}
          // Phase 31 (follow-up), reported directly: the on-screen page
          // guide predicted 4 pages for a document that really exports to
          // 3 — confirmed against a real templated PDF (pypdf page count),
          // and traced to this exact button. Real, normal-flow content on
          // screen (unlike every other piece of editor chrome — the drag
          // handle, checkbox/Sparkles, DocumentGutter's whole overlay —
          // which were all deliberately made `position: absolute`
          // precisely to avoid shifting real content, see EntryNodeView's
          // own Phase 28 history above), but PrintExperienceSection.tsx
          // (what the real export actually screenshots) never renders an
          // "Add Bullet" affordance at all — every one of these visible on
          // screen (this document had 9) adds height PageBreakGuide.tsx's
          // measureUnits sees but the real export never produces,
          // compounding into a phantom extra page. `data-page-break-exclude`
          // is PageBreakGuide.tsx's own signal to subtract this element's
          // height from every measurement below it — the same "measure
          // reality, but discount what reality itself excludes" pattern
          // `data-page-break-before` above already uses for the opposite
          // direction (adding a break, not removing height).
          data-page-break-exclude="true"
        >
          + Add Bullet
        </Button>
      )}
    </NodeViewWrapper>
  );
}
