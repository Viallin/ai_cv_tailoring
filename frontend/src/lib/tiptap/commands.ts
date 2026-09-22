import type { Editor } from "@tiptap/core";
import { joinBackward, splitBlockAs } from "@tiptap/pm/commands";
import type { ResolvedPos } from "@tiptap/pm/model";
import { splitListItem } from "@tiptap/pm/schema-list";
import type { EditorState, Transaction } from "@tiptap/pm/state";

// Phase 26 — the Enter/Backspace commands wired from schema.ts's
// `bullet`/`entryHeading` addKeyboardShortcuts. Everywhere else (typing,
// arrow/Home/End/Ctrl+Arrow/PageUp-PageDown navigation, plain
// single-character Backspace/Delete) is native contentEditable/
// ProseMirror behavior, untouched — these two functions only exist to
// guard the structural boundaries the dev-plan calls out.

// Attrs a freshly-split entry/bullet always resets to — a
// Tiptap-created sibling is never a continuation of the original (never
// AI-tailored, never a Gap, never a category/project subheading, never
// linked to Evidence) — mirrors structuredDocument.ts::addBullet's own
// "always untailored, verbatim text" contract. `id: null` is deliberate:
// idIntegrityPlugin (plugins.ts) assigns the real fresh id in a
// follow-up transaction, so neither split command needs to mint a UUID
// itself.
const RESET_ATTRS = {
  id: null,
  included: true,
  locked: null,
  kind: null,
  evidence_id: null,
  alignment: null,
};

// Enter inside a bullet — dev-plan's explicit rule: "creates a sibling
// bullet, not a new section." `splitBlockAs`'s callback lets us fix both
// the new node's type *and* attrs in one step, so there's nothing to
// patch after the fact (contrast splitEntryHeadingSibling below).
export function splitBulletSibling(editor: Editor): boolean {
  const { state, dispatch } = editor.view;
  const { $from } = state.selection;
  if ($from.parent.type.name !== "bullet") {
    return false;
  }
  const bulletType = state.schema.nodes.bullet;
  const command = splitBlockAs(() => ({ type: bulletType, attrs: RESET_ATTRS }));
  return command(state, dispatch);
}

// Enter inside an entryHeading — modeled on `splitListItem`, the same
// mechanism `prosemirror-schema-list`'s own `list_item` uses for
// splitting a "text-then-block-children" node in two (exactly our
// `entry: "entryHeading bullet*"` shape). We don't depend on
// splitListItem's own `itemAttrs` param — which of the two split
// boundaries it applies to is an internal implementation detail not
// worth relying on — and instead intercept the transaction it would
// dispatch to fix up the result ourselves.
//
// splitListItem's own default is a plain, positional split: content
// *after* the cursor — which includes every bullet, not just trailing
// text — moves to the new entry. That's the wrong default for this app:
// pressing Enter at the end of a role's title means "start a new role
// below," and the bullets typed so far still belong to the role *above*
// the cursor, not the new, still-untitled one. So after the library's
// split, we move any bullets it left on the new entry back onto the
// original — the new entry keeps only whatever heading text followed
// the cursor (normally none, since Enter is pressed at the end).
export function splitEntryHeadingSibling(editor: Editor): boolean {
  const { state, dispatch } = editor.view;
  const { $from } = state.selection;
  if ($from.parent.type.name !== "entryHeading") {
    return false;
  }
  const entryType = state.schema.nodes.entry;
  const command = splitListItem(entryType);
  return command(state, (tr: Transaction) => {
    const $sel = tr.selection.$from;
    const entryDepth = $sel.depth - 1;
    if (entryDepth >= 0 && $sel.node(entryDepth).type === entryType) {
      const newEntryPos = $sel.before(entryDepth);
      // Attrs first — setNodeMarkup doesn't change doc structure/
      // positions, so it's safe to do before the position-shifting
      // delete+insert below (and `newEntryPos` stays valid for both).
      tr.setNodeMarkup(newEntryPos, undefined, RESET_ATTRS);
      const newEntry = tr.doc.nodeAt(newEntryPos)!;
      const headingSize = newEntry.firstChild!.nodeSize;
      const strandedBullets = newEntry.content.cut(headingSize);
      if (strandedBullets.size > 0) {
        const removeFrom = newEntryPos + 1 + headingSize;
        tr.delete(removeFrom, removeFrom + strandedBullets.size);
        // `newEntryPos - 1` is *inside* the previous (original) entry,
        // just before its own closing token — not the ambiguous
        // sibling boundary at `newEntryPos` itself, which ProseMirror
        // resolves at the *section* level (entry/entry are siblings
        // there) and would reject/mis-place a bare bullet Fragment.
        // Safe to still use `newEntryPos` here (unshifted by the delete
        // above, since that range is entirely after it).
        tr.insert(newEntryPos - 1, strandedBullets);
      }
    }
    dispatch?.(tr);
  });
}

// Backspace at the start of a bullet/entryHeading's text — dev-plan's
// explicit rule ("Backspace at a section's first character doesn't
// merge into the previous section") generalized one structural level:
// never silently merge across a section boundary, an entry boundary, or
// into/out of a locked (career-gap) entry. Every other case reuses
// ProseMirror's own `joinBackward` unmodified.
export function handleBackspace(editor: Editor): boolean {
  const { state, dispatch } = editor.view;
  if (!state.selection.empty) {
    return false; // a real selection — let the default deleteSelection handle it
  }
  const { $from } = state.selection;
  if ($from.parentOffset !== 0) {
    return false; // not at the start of the block — native char-delete applies
  }
  const parentType = $from.parent.type.name;
  if (parentType === "bullet") {
    return handleBulletBackspace($from, state, dispatch);
  }
  if (parentType === "entryHeading") {
    return handleEntryHeadingBackspace($from, state, dispatch);
  }
  return false;
}

function handleBulletBackspace(
  $from: ResolvedPos,
  state: EditorState,
  dispatch: ((tr: Transaction) => void) | undefined,
): boolean {
  const entryDepth = $from.depth - 1;
  // entry.content = "entryHeading bullet*" — child index 0 is always the
  // entryHeading, so index 1 is the *first* bullet.
  const indexInEntry = $from.index(entryDepth);
  if (indexInEntry <= 1) {
    return true; // first bullet — merging would splice bullet text onto the entry's own heading line
  }
  const entry = $from.node(entryDepth);
  if (entry.attrs.locked) {
    return true; // a Gap entry's bullets never silently rearrange via merge either
  }
  return joinBackward(state, dispatch);
}

function handleEntryHeadingBackspace(
  $from: ResolvedPos,
  state: EditorState,
  dispatch: ((tr: Transaction) => void) | undefined,
): boolean {
  const sectionDepth = $from.depth - 2;
  const indexInSection = $from.index(sectionDepth);
  if (indexInSection === 0) {
    return true; // first entry in its section — never merges into the previous section
  }
  const section = $from.node(sectionDepth);
  const entry = $from.node(sectionDepth + 1);
  const prevEntry = section.child(indexInSection - 1);
  if (entry.attrs.locked || prevEntry.attrs.locked) {
    return true; // a Gap entry never silently disappears via merge, on either side
  }
  return joinBackward(state, dispatch);
}
