import { mergeAttributes, Node } from "@tiptap/core";
import { ReactNodeViewRenderer } from "@tiptap/react";

import { BulletNodeView } from "@/components/tiptap/BulletNodeView";
import { EntryHeadingNodeView } from "@/components/tiptap/EntryHeadingNodeView";
import { EntryNodeView } from "@/components/tiptap/EntryNodeView";
import { SectionNodeView } from "@/components/tiptap/SectionNodeView";

import { handleBackspace, splitBulletSibling, splitEntryHeadingSibling } from "./commands";

// Phase 26 — the custom node schema (development_plan.md's Phase 26).
// Four semantic concepts (`section`/`entry`/`bullet`/`kind:"subheading"`)
// map to five ProseMirror node types: `entryHeading` is forced by a real
// schema constraint, not preference — a node's `content` expression
// can't mix inline text and block children directly, so `entry`'s own
// heading/role-name text needs a dedicated textblock child, exactly the
// problem `prosemirror-schema-list`'s `list_item` solves with
// `content: "paragraph block*"` (see commands.ts's splitEntryHeadingSibling,
// modeled on that same library's `splitListItem`).
//
// `kind: "subheading"` (a Skills/Technologies category header, or an
// Experience project heading) stays an *attr* on `entry`/`bullet`, not a
// 5th node type — it's already an attr on today's DocumentBlock, and
// structurally a subheading is identical to a plain entry/bullet: same
// content shape, only styling (components/tiptap/*NodeView.tsx) and the
// exclude-cascade rule (structuredDocument.ts::toggleEntryIncluded)
// differ.
//
// Every attr here is a same-named mirror of structuredDocument.ts's
// DocumentBlock fields — see lib/tiptap/converter.ts for the JSON⇄
// DocumentModel mapping this exists to support; keep the two in lockstep
// by hand, same "field names must match exactly" rule
// domain.models.PrintDocumentBlock's own docstring already documents for
// the JS/Python boundary.
function blockAttributes() {
  return {
    id: { default: null },
    included: { default: true },
    locked: { default: null },
    kind: { default: null },
    evidence_id: { default: null },
    alignment: { default: null },
  };
}

export const TiptapDoc = Node.create({
  name: "doc",
  topNode: true,
  // "section*", not "section+" — DocumentEditor.tsx creates the editor
  // once and pushes real content in only once assembledCv/initialDocument
  // resolves (can be async — see its own effect), so the doc needs a
  // valid empty state to start from.
  content: "section*",
  renderHTML() {
    return ["div", 0];
  },
});

export const TiptapSection = Node.create({
  name: "section",
  content: "entry*", // not entry+ — buildListSection can legitimately produce zero entries (e.g. an empty Portfolio Links list)
  // Phase 27 — native ProseMirror node dragging (not a redraggable-row
  // library): the browser only *starts* a drag from an element carrying
  // the real HTML `draggable` attribute — that's the small hover-only
  // handle icon in SectionNodeView.tsx/EntryHeadingNodeView.tsx/
  // BulletNodeView.tsx, never this node's own root — but ProseMirror
  // still needs `draggable: true` here so its own dragstart handler
  // (which walks up from the drag position to the nearest ancestor node
  // whose *type* has this flag) recognizes "section" as a draggable
  // unit at all. `entryHeading` deliberately never gets this — its own
  // NodeSpec comment below explains why the entry-level handle can't
  // even physically live inside entryHeading's own DOM in the first
  // place, which sidesteps the whole question.
  draggable: true,
  addAttributes() {
    return {
      key: { default: null },
      title: { default: null },
      included: { default: true },
      // Phase 30 — manual pagination control, mirrors
      // structuredDocument.ts's DocumentSection.page_break_before
      // exactly; see that field's own docstring.
      page_break_before: { default: false },
    };
  },
  renderHTML({ HTMLAttributes }) {
    return ["section", mergeAttributes(HTMLAttributes), 0];
  },
  addNodeView() {
    return ReactNodeViewRenderer(SectionNodeView);
  },
});

export const TiptapEntry = Node.create({
  name: "entry",
  content: "entryHeading bullet*",
  draggable: true, // Phase 27 — see TiptapSection's own comment
  // Not the shared `blockAttributes()` — `page_break_before` is
  // deliberately entry-only (see structuredDocument.ts's
  // DocumentEntry.page_break_before docstring for why bullets don't get
  // it), so `TiptapBullet` below stays on the plain shared shape.
  addAttributes() {
    return { ...blockAttributes(), page_break_before: { default: false } };
  },
  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes), 0];
  },
  addNodeView() {
    return ReactNodeViewRenderer(EntryNodeView);
  },
});

export const TiptapEntryHeading = Node.create({
  name: "entryHeading",
  content: "text*",
  // Phase 27 — deliberately no `draggable` here, and (unlike bullet/
  // section) no drag handle rendered inside this NodeView's own DOM
  // either — see EntryNodeView.tsx's own comment for why. Two real,
  // separately-confirmed bugs came from an earlier version that *did*
  // put the entry-level handle here:
  //
  // 1. Tiptap's `NodeView.stopEvent()` (@tiptap/core) only recognizes a
  //    `[data-drag-handle]` element as legitimate — and only tracks the
  //    mousedown→dragstart `isDragging` handoff that keeps `stopEvent()`
  //    from swallowing the dragstart event — for a NodeView whose *own*
  //    node type is draggable. A handle living inside entryHeading's own
  //    chrome, while the type that's actually meant to move is its
  //    *parent* `entry`, fails that check: entryHeading isn't draggable,
  //    so its stopEvent() falls through to its default `return true` for
  //    the dragstart event, and ProseMirror's own `handlers.dragstart`
  //    never even runs. Confirmed directly: `view.dragging` stayed
  //    `undefined` after a real dragstart despite the preceding mousedown
  //    already having set the correct NodeSelection over `entry`.
  // 2. Worse, and separate: `@tiptap/react`'s `NodeViewWrapper`
  //    unconditionally wires every NodeView's own `onDragStart` (used to
  //    build the native drag *image*, @tiptap/core's `NodeView.ts`) to
  //    the DOM element's `onDragStart` prop, with no way to opt out.
  //    That method bails out only if the drag target is inside *this*
  //    NodeView's own `contentDOM` — true for `entry`'s onDragStart
  //    (the handle nested inside entryHeading is inside entry's
  //    contentDOM) but *false* for entryHeading's own onDragStart (the
  //    handle sits in entryHeading's chrome, outside its own, much
  //    smaller contentDOM). So entryHeading's onDragStart doesn't bail —
  //    it runs `NodeSelection.create(doc, this.getPos())`, overwriting
  //    the correct whole-`entry` selection with one scoped to just
  //    entryHeading, moments before the real drop handler reads it. This
  //    is what actually corrupted a real draft during testing: the drop
  //    intended as a move ended up deleting entryHeading's own text
  //    (`tr.deleteSelection()` on the wrong, narrow selection) while
  //    inserting a copy of the *original* dragged slice — captured
  //    before the corruption — at the target position, i.e. a duplicate
  //    with a blanked-out original.
  //
  // Both failure modes trace to the same structural cause: a NodeView's
  // own drag machinery only behaves correctly for chrome living directly
  // inside *that* NodeView, never a descendant's. entryHeading has no
  // chrome of its own at all now — see EntryNodeView.tsx.
  renderHTML({ HTMLAttributes }) {
    return ["p", mergeAttributes(HTMLAttributes), 0];
  },
  addKeyboardShortcuts() {
    return {
      Enter: () => splitEntryHeadingSibling(this.editor),
      Backspace: () => handleBackspace(this.editor),
    };
  },
  addNodeView() {
    return ReactNodeViewRenderer(EntryHeadingNodeView);
  },
});

export const TiptapBullet = Node.create({
  name: "bullet",
  content: "text*",
  draggable: true, // Phase 27 — see TiptapSection's own comment
  addAttributes: blockAttributes,
  renderHTML({ HTMLAttributes }) {
    return ["p", mergeAttributes(HTMLAttributes), 0];
  },
  addKeyboardShortcuts() {
    return {
      Enter: () => splitBulletSibling(this.editor),
      Backspace: () => handleBackspace(this.editor),
    };
  },
  addNodeView() {
    return ReactNodeViewRenderer(BulletNodeView);
  },
});

export const DOCUMENT_NODE_EXTENSIONS = [TiptapDoc, TiptapSection, TiptapEntry, TiptapEntryHeading, TiptapBullet];
