import type { NodeViewProps } from "@tiptap/react";
import type { Node as PMNode } from "@tiptap/pm/model";

// Phase 26 — a NodeView's own `getPos()`/`editor.state.doc` are the only
// reliable way to learn which section/entry a nested NodeView belongs
// to. Nesting a *React* Context provider inside SectionNodeView/
// EntryNodeView (the first approach tried here) does not work: Tiptap's
// ReactNodeViewRenderer mounts every NodeView in the document as its own
// portal into the single editor-wide React tree — a node view nested
// inside another node view's contentDOM at the *DOM* level is not a
// descendant of that other node view's own *React component* subtree,
// so a Context.Provider re-provided inside one NodeView is invisible to
// NodeViews nested under it. Found from a real failing test (the
// "+ Add Bullet" button never rendering, and toggling an entry's
// checkbox silently doing nothing — both traced back to `ctx.sectionKey`/
// `ctx.entryId` always reading the top-level DocumentEditor.tsx
// provider's placeholder values, never SectionNodeView's/EntryNodeView's
// own overrides), not anticipated in the original design.
//
// Walking the real ProseMirror document from `getPos()` sidesteps the
// whole React-tree-vs-DOM-tree mismatch — it's a query against the
// document model itself, unaffected by how NodeViews happen to be
// mounted.
export interface NodeAncestry {
  sectionKey: string;
  // Phase 28 — whether every ancestor *above* the node this was resolved
  // from is included. sectionIncluded/entryIncluded default to `true` when
  // no such ancestor exists at all (e.g. calling this from a section's own
  // getPos() finds no entry/section ancestor above it) — a deliberately
  // harmless default, since "no ancestor to exclude me" and "ancestor
  // includes me" both mean the same thing here: nothing above is hiding
  // this row.
  sectionIncluded: boolean;
  entryId: string | null;
  entryLocked: boolean;
  entryIncluded: boolean;
  // Phase 31 (follow-up) — the enclosing entry's own `alignment` attr.
  // `entryHeading` (schema.ts) has no attrs of its own at all — `id`/
  // `included`/`locked`/`kind`/`evidence_id`/`alignment` all live on the
  // *parent* `entry` node (see converter.ts's entryToJSON: the
  // `entryHeading` JSON node carries only `type`/`content`, no `attrs`
  // key) — so a NodeView rendering entryHeading text can't read
  // `node.attrs.alignment` off its own node; it has to walk up to its
  // parent entry the same way it already does for `sectionKey`/
  // `entryLocked`. This is exactly the bug reported directly: alignment
  // worked for bullets (which do carry their own `alignment` via
  // `blockAttributes()`) but silently did nothing for every entry's own
  // heading text — Summary, Contacts, Key Projects, Education, Skills,
  // Tools & Technologies, Languages, and an Experience role's own title
  // line alike.
  entryAlignment: "left" | "center" | "right" | null;
}

const EMPTY_ANCESTRY: NodeAncestry = {
  sectionKey: "",
  sectionIncluded: true,
  entryId: null,
  entryLocked: false,
  entryIncluded: true,
  entryAlignment: null,
};

// Phase 28 — split out from the hook below so DocumentGutter.tsx can call
// it directly against the *live* `editor.state.doc` at remeasure time
// (driven by its own `editor.on("update")` listener, which reliably fires
// on every real document change) instead of through a NodeView's own
// render. That distinction turned out to matter, not just be tidier: a
// NodeView whose *own* node didn't change (e.g. an entry when its
// ancestor *section*'s `included` toggles) isn't guaranteed to re-render
// at all — ProseMirror/Tiptap's own reconciliation can reuse an unchanged
// child NodeView wholesale across a `setContent` call, so a value derived
// from `useNodeAncestry` inside that child can silently go stale. Every
// NodeView still uses this for the ancestor facts that *are* safe to read
// at its own render time (sectionKey/entryLocked, never reused across a
// change to the thing they actually describe) — only the gutter's
// cascading-exclusion check needed the doc-driven, always-fresh version.
export function computeNodeAncestry(doc: PMNode, pos: number | undefined): NodeAncestry {
  if (typeof pos !== "number") {
    return EMPTY_ANCESTRY;
  }
  const $pos = doc.resolve(pos);
  let sectionKey = "";
  let sectionIncluded = true;
  let entryId: string | null = null;
  let entryLocked = false;
  let entryIncluded = true;
  let entryAlignment: "left" | "center" | "right" | null = null;
  for (let depth = $pos.depth; depth >= 0; depth--) {
    const ancestor = $pos.node(depth);
    if (ancestor.type.name === "entry" && entryId == null) {
      entryId = ancestor.attrs.id as string;
      entryLocked = Boolean(ancestor.attrs.locked);
      entryIncluded = ancestor.attrs.included !== false;
      entryAlignment = (ancestor.attrs.alignment as "left" | "center" | "right" | null) ?? null;
    }
    if (ancestor.type.name === "section") {
      sectionKey = ancestor.attrs.key as string;
      sectionIncluded = ancestor.attrs.included !== false;
      break;
    }
  }
  return { sectionKey, sectionIncluded, entryId, entryLocked, entryIncluded, entryAlignment };
}

export function useNodeAncestry({ editor, getPos }: Pick<NodeViewProps, "editor" | "getPos">): NodeAncestry {
  return computeNodeAncestry(editor.state.doc, getPos());
}

// Phase 28 (follow-up) — which gutter item (`section:${key}` |
// `entry:${id}` | `bullet:${id}`) the given position sits inside, if any.
// Walks from the innermost ancestor outward so a position inside a
// bullet's own text resolves to that bullet specifically, not its parent
// entry — and a position inside an entryHeading (which has no gutter item
// of its own) falls through to its parent entry, same as
// computeNodeAncestry's own entryId lookup does. Used to keep a row's
// checkbox visible while the text cursor is actually inside it, alongside
// (not instead of) hover — see DocumentGutter.tsx.
export function computeActiveGutterItemId(doc: PMNode, pos: number | undefined): string | null {
  if (typeof pos !== "number") {
    return null;
  }
  const $pos = doc.resolve(pos);
  for (let depth = $pos.depth; depth >= 0; depth--) {
    const ancestor = $pos.node(depth);
    if (ancestor.type.name === "bullet") {
      return `bullet:${ancestor.attrs.id as string}`;
    }
    if (ancestor.type.name === "entry") {
      return `entry:${ancestor.attrs.id as string}`;
    }
    if (ancestor.type.name === "section") {
      return `section:${ancestor.attrs.key as string}`;
    }
  }
  return null;
}
