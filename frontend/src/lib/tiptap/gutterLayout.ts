// Phase 28 (follow-up) — reported directly: pulling the checkbox/Sparkles
// out to a floating column outside `.cv-a4-page` was a mistake — the
// actual ask was "don't let them push the exported text around," not
// "move them off the page entirely." Losing that proximity made it hard
// to tell which bullets were even there. This is the shared coordinate
// system for the corrected design: checkbox, Sparkles, and the drag
// handle all live *inside* `.cv-a4-page`'s own left padding (currently
// blank, unused space — the 18mm print margin), positioned via `left`
// offsets relative to 0 = the text's own left edge (flush with the real
// print margin — see Phase 28's own "fidelity win" note on why text
// starts there at all). Negative offsets extend left from there, into
// that blank padding, so none of these ever reserve inline flow space or
// shift the text — the actual TipTap contentEditable content's own
// position is untouched by any of this.
//
// Checkbox and Sparkles are rendered together by DocumentGutter.tsx (one
// shared overlay — the reason for that hasn't changed: cascading-
// exclusion visibility needs to be computed against the live doc,
// independent of any one NodeView's own render, see that file's own
// docstring). The drag handle stays rendered by each NodeView's own
// chrome, in its own DOM — deliberately NOT folded into DocumentGutter:
// Tiptap's drag mechanics (`stopEvent()`, `nearestDesc()`) require a
// `[data-drag-handle]` element to live inside the *dragged node's own*
// view DOM (see schema.ts's TiptapEntryHeading comment for the two real
// bugs — one of them destructive — that came from getting this wrong
// even while the handle stayed inside the page); moving it to a
// separately-rendered overlay would risk reopening exactly that class of
// bug for a purely cosmetic gain. These constants are what keep the two
// independently-rendered pieces visually aligned as one cluster despite
// that split.
// GAP_PX=2 (not the more natural-looking 4) is deliberate, confirmed
// necessary by live measurement: the page's own left padding is 18mm
// (≈68.03px) and the *total* chrome width has to fit inside it — 4px
// gaps summed to exactly 68px, leaving zero breathing room at the page's
// own outer edge (a checkbox rendered flush against it, one rounding
// error from visibly clipping). 2px gaps leave a real ~6px margin.
const GAP_PX = 2;
export const CHECKBOX_WIDTH_PX = 16; // Checkbox's own size-4
export const SPARKLES_WIDTH_PX = 24; // Sparkles trigger's own icon-xs button (size-6)
export const HANDLE_WIDTH_PX = 16; // DragHandle's own GripVertical icon (size-4)

// Left-to-right order, matching the reported mockup: checkbox, Sparkles,
// handle, text. DocumentGutter renders checkbox+Sparkles as one flex row
// (DOM order checkbox-then-Sparkles, `gap-0.5` = GAP_PX between them) at
// this single left offset; the handle is positioned independently, by
// each NodeView, at HANDLE_LEFT_PX.
//
// Both of the exports below describe the same physical position (text
// start = 0, negative = left into the page's own padding) — but they get
// applied against two *different* positioning containers, which turned
// out to matter and produced a real, reported bug: HANDLE_LEFT_PX is
// consumed by each NodeView's own chrome, whose `position: relative`
// ancestor sits in normal document flow — its own `left: 0` already
// coincides with the text's own start, so the raw negative offset is
// correct there as-is. CHECKBOX_ROW_LEFT_PX is consumed by
// DocumentGutter.tsx, whose own container is `position: absolute; inset:
// 0` on `.cv-a4-page` *itself* — CSS resolves that `inset: 0` against the
// page's own padding *box*, i.e. the page's outer edge, not the text's
// (68.03px further right). Using CHECKBOX_ROW_LEFT_PX directly there, as
// a first pass did, put the checkbox 62px to the *left of the page's own
// edge* — genuinely outside `.cv-a4-page` entirely, not merely deep in
// its padding, and (reported directly) unreachable/clipped by the
// `overflow-x-auto` ancestor around it, since a scrollable container's
// default scroll range doesn't extend to content overflowing in the
// *negative* direction the way it does for positive overflow.
// PAGE_EDGE_CHECKBOX_ROW_LEFT_PX is the same offset re-expressed in the
// *other* container's coordinate frame (page-edge = 0) by adding the
// page's own known, fixed padding-left (18mm — never templated, see
// index.css's `.cv-a4-page` rule) — DocumentGutter.tsx uses this one
// specifically, HANDLE_LEFT_PX stays as the NodeViews already use it.
const CHECKBOX_ROW_LEFT_PX = -(CHECKBOX_WIDTH_PX + GAP_PX + SPARKLES_WIDTH_PX + GAP_PX + HANDLE_WIDTH_PX + GAP_PX);
export const HANDLE_LEFT_PX = -(HANDLE_WIDTH_PX + GAP_PX);

const MM_TO_PX = 96 / 25.4;
const PAGE_PADDING_LEFT_PX = 18 * MM_TO_PX; // .cv-a4-page's own `padding: 20mm 18mm` (index.css) — fixed, not templated
export const PAGE_EDGE_CHECKBOX_ROW_LEFT_PX = PAGE_PADDING_LEFT_PX + CHECKBOX_ROW_LEFT_PX;
