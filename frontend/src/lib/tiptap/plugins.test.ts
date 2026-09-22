import { Editor } from "@tiptap/core";
import { Text } from "@tiptap/extension-text";
import type { Node as PMNode } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import { afterEach, describe, expect, it } from "vitest";

import type { DocumentModel } from "@/lib/structuredDocument";
import { documentModelToTiptapJSON, tiptapJSONToDocumentModel } from "./converter";
import { computeAutoScrollDelta, computeDragScope, DocumentGuards, invalidDropMessage, isPositionInScope } from "./plugins";
import { DOCUMENT_NODE_EXTENSIONS } from "./schema";

// Phase 27 — dragScopeGuardPlugin, exercised against a real, headless
// Editor (no native DragEvent/DataTransfer simulation — jsdom doesn't
// support that, the same gap Phase 26 hit for click-to-position-cursor).
// The plugin only ever inspects the *resulting* document, not how a
// transaction was produced, so a hand-built delete+insert "move" stands
// in for what a real native ProseMirror node drag would actually
// dispatch — this is exactly the level Phase 26's own commands.test.ts
// already tests at.

// Undestroyed Editors leave a ProseMirror DOMObserver poll scheduled via
// setTimeout; if it fires after jsdom tears down between test files, it
// throws "document is not defined" as an unhandled error and fails the
// run despite every assertion passing. Track and destroy them below.
const editors: Editor[] = [];

afterEach(() => {
  editors.splice(0).forEach((editor) => editor.destroy());
});

function makeEditor(model: DocumentModel): Editor {
  const editor = new Editor({
    extensions: [...DOCUMENT_NODE_EXTENSIONS, Text, DocumentGuards],
    content: documentModelToTiptapJSON(model),
  });
  editors.push(editor);
  return editor;
}

function findNode(doc: PMNode, predicate: (node: PMNode) => boolean): { node: PMNode; pos: number } {
  let result: { node: PMNode; pos: number } | null = null;
  doc.descendants((node, pos) => {
    if (result) return false;
    if (predicate(node)) {
      result = { node, pos };
      return false;
    }
    return true;
  });
  if (!result) throw new Error("node not found");
  return result;
}

function byId(id: string) {
  return (node: PMNode) => node.attrs.id === id;
}

// Simulates the net effect of a native ProseMirror node drag: remove
// the node at `nodeId` from wherever it is, insert it right before the
// node at `beforeId` (or at the document's end, if omitted).
function moveNode(editor: Editor, nodeId: string, beforeId?: string) {
  const { state } = editor.view;
  const { node, pos } = findNode(state.doc, byId(nodeId));
  const tr = state.tr.delete(pos, pos + node.nodeSize);
  const targetPos =
    beforeId != null ? tr.mapping.map(findNode(state.doc, byId(beforeId)).pos) : tr.doc.content.size;
  tr.insert(targetPos, node);
  editor.view.dispatch(tr);
}

const TWO_SECTIONS: DocumentModel = {
  sections: [
    {
      key: "education",
      title: "Education",
      included: true,
      entries: [
        { id: "edu-1", text: "State University", included: true },
        { id: "edu-2", text: "Community College", included: true },
      ],
    },
    {
      key: "experience",
      title: "Experience",
      included: true,
      entries: [
        {
          id: "exp-1",
          text: "Engineer — Acme",
          included: true,
          bullets: [
            { id: "bullet-a", text: "Shipped a thing.", included: true },
            { id: "bullet-b", text: "Shipped another thing.", included: true },
          ],
        },
        { id: "exp-2", text: "Junior Engineer — Acme", included: true },
      ],
    },
  ],
};

describe("dragScopeGuardPlugin", () => {
  it("allows moving an entry within its own section", () => {
    const editor = makeEditor(TWO_SECTIONS);
    moveNode(editor, "edu-2", "edu-1"); // edu-2 before edu-1, still within "education"

    const education = tiptapJSONToDocumentModel(editor.getJSON()).sections[0];
    expect(education.entries.map((e) => e.id)).toEqual(["edu-2", "edu-1"]);
  });

  it("reverts moving an entry into a different section", () => {
    const editor = makeEditor(TWO_SECTIONS);
    moveNode(editor, "edu-1", "exp-1"); // edu-1 dropped into "experience"

    const model = tiptapJSONToDocumentModel(editor.getJSON());
    expect(model).toEqual(TWO_SECTIONS); // wholesale-reverted, unchanged
  });

  it("allows moving a bullet within its own entry", () => {
    const editor = makeEditor(TWO_SECTIONS);
    moveNode(editor, "bullet-b", "bullet-a"); // bullet-b before bullet-a, still within exp-1

    const exp1 = tiptapJSONToDocumentModel(editor.getJSON()).sections[1].entries[0];
    expect(exp1.bullets!.map((b) => b.id)).toEqual(["bullet-b", "bullet-a"]);
  });

  it("reverts moving a bullet into a different entry", () => {
    const editor = makeEditor(TWO_SECTIONS);
    const { state } = editor.view;
    const { node: bulletA, pos: bulletAPos } = findNode(state.doc, byId("bullet-a"));
    const { node: exp2, pos: exp2Pos } = findNode(state.doc, byId("exp-2"));
    const tr = state.tr.delete(bulletAPos, bulletAPos + bulletA.nodeSize);
    // Right after exp-2's own entryHeading -- a real position inside a
    // *different* entry, not the document's own top level (which would
    // otherwise get auto-wrapped into a whole new bogus section, not
    // what a real cross-entry drop looks like).
    const insertPos = tr.mapping.map(exp2Pos) + 1 + exp2.firstChild!.nodeSize;
    tr.insert(insertPos, bulletA);
    editor.view.dispatch(tr);

    const model = tiptapJSONToDocumentModel(editor.getJSON());
    expect(model).toEqual(TWO_SECTIONS); // wholesale-reverted, unchanged
  });

  it("allows reordering sections themselves — the new capability this phase adds, no guard applies", () => {
    const editor = makeEditor(TWO_SECTIONS);
    const { state } = editor.view;
    const { node, pos } = findNode(state.doc, (n) => n.type.name === "section" && n.attrs.key === "experience");
    const tr = state.tr.delete(pos, pos + node.nodeSize).insert(0, node);
    editor.view.dispatch(tr);

    const model = tiptapJSONToDocumentModel(editor.getJSON());
    expect(model.sections.map((s) => s.key)).toEqual(["experience", "education"]);
  });
});

// Phase 28 (follow-up) — emptyBulletExclusionPlugin. Same headless-Editor
// technique as dragScopeGuardPlugin's own tests above: a hand-built
// delete transaction stands in for what a real "select all, Backspace"
// gesture produces, since the plugin only ever inspects the resulting
// document, not how the transaction was made.
describe("emptyBulletExclusionPlugin", () => {
  it("excludes a bullet whose text was fully deleted", () => {
    const editor = makeEditor(TWO_SECTIONS);
    const { node, pos } = findNode(editor.state.doc, byId("bullet-a"));
    editor.view.dispatch(editor.state.tr.delete(pos + 1, pos + 1 + node.content.size));

    expect(findNode(editor.state.doc, byId("bullet-a")).node.attrs.included).toBe(false);
  });

  it("leaves a bullet that still has some text left alone", () => {
    const editor = makeEditor(TWO_SECTIONS);
    const { node, pos } = findNode(editor.state.doc, byId("bullet-a")); // "Shipped a thing."
    editor.view.dispatch(editor.state.tr.delete(pos + 2, pos + 1 + node.content.size)); // leaves "S"

    expect(findNode(editor.state.doc, byId("bullet-a")).node.attrs.included).toBe(true);
  });

  it("never excludes a freshly-inserted blank bullet — it didn't exist (let alone have text) before this transaction", () => {
    const editor = makeEditor(TWO_SECTIONS);
    const { node: entry, pos: entryPos } = findNode(editor.state.doc, byId("exp-1"));
    const freshBullet = editor.schema.nodes.bullet.create({ id: "fresh-bullet" });
    const insertPos = entryPos + entry.nodeSize - 1; // end of exp-1, after its existing bullets
    editor.view.dispatch(editor.state.tr.insert(insertPos, freshBullet));

    expect(findNode(editor.state.doc, byId("fresh-bullet")).node.attrs.included).toBe(true);
  });

  it("is a harmless no-op for a bullet that was already excluded", () => {
    const editor = makeEditor(TWO_SECTIONS);
    const { pos: bulletPos } = findNode(editor.state.doc, byId("bullet-a"));
    editor.view.dispatch(editor.state.tr.setNodeMarkup(bulletPos, undefined, { id: "bullet-a", included: false }));
    const { node, pos } = findNode(editor.state.doc, byId("bullet-a"));
    editor.view.dispatch(editor.state.tr.delete(pos + 1, pos + 1 + node.content.size));

    expect(findNode(editor.state.doc, byId("bullet-a")).node.attrs.included).toBe(false);
  });

  it("relocates the selection out of a bullet auto-excluded this way, in the same pass as excludedSelectionGuardPlugin", () => {
    const editor = makeEditor(TWO_SECTIONS);
    const { node, pos } = findNode(editor.state.doc, byId("bullet-a"));
    const tr = editor.state.tr.delete(pos + 1, pos + 1 + node.content.size);
    tr.setSelection(TextSelection.create(tr.doc, pos + 1));
    editor.view.dispatch(tr);

    const after = findNode(editor.state.doc, byId("bullet-a"));
    const selFrom = editor.state.selection.from;
    expect(selFrom < after.pos || selFrom > after.pos + after.node.nodeSize).toBe(true);
  });
});

// Phase 27 (follow-up) — computeAutoScrollDelta is the one part of
// dragAutoScroll's behavior that's a pure function and worth testing
// directly; the requestAnimationFrame loop and real DragEvent timing
// around it aren't something jsdom can meaningfully exercise (same gap
// as dragScopeGuardPlugin's own tests above).
describe("computeAutoScrollDelta", () => {
  const VIEWPORT = 800;

  it("returns 0 in the middle of the viewport, away from either edge", () => {
    expect(computeAutoScrollDelta(400, VIEWPORT)).toBe(0);
  });

  it("scrolls up (negative) near the top edge, faster the closer to it", () => {
    const nearEdge = computeAutoScrollDelta(60, VIEWPORT);
    const atEdge = computeAutoScrollDelta(0, VIEWPORT);
    expect(nearEdge).toBeLessThan(0);
    expect(atEdge).toBeLessThan(0);
    expect(Math.abs(atEdge)).toBeGreaterThan(Math.abs(nearEdge));
  });

  it("scrolls down (positive) near the bottom edge, faster the closer to it", () => {
    const nearEdge = computeAutoScrollDelta(VIEWPORT - 60, VIEWPORT);
    const atEdge = computeAutoScrollDelta(VIEWPORT, VIEWPORT);
    expect(nearEdge).toBeGreaterThan(0);
    expect(atEdge).toBeGreaterThan(0);
    expect(atEdge).toBeGreaterThan(nearEdge);
  });

  it("is 0 exactly at the edge threshold, non-zero just inside it", () => {
    expect(computeAutoScrollDelta(140, VIEWPORT)).toBe(0);
    expect(computeAutoScrollDelta(139, VIEWPORT)).toBeLessThan(0);
  });
});

// Phase 27 (follow-up #3) — DragScopeFeedback's own pure logic:
// `computeDragScope`/`isPositionInScope`/`invalidDropMessage`. Its live
// DOM/dragover-driven side (the actual cursor line, dimming, tooltip
// positioning) isn't something jsdom can meaningfully exercise — same
// gap as the rest of this file's own native-drag-timing concerns — but
// the "what's the scope, is this position inside it, what does the
// tooltip say" decisions it's built on are ordinary pure functions of
// editor state, worth testing directly.
describe("DragScopeFeedback", () => {
  function selectNode(editor: Editor, nodeId: string) {
    const { pos } = findNode(editor.state.doc, byId(nodeId));
    editor.commands.setNodeSelection(pos);
  }

  describe("computeDragScope", () => {
    it("scopes an entry drag to its own section, by key, with a human label", () => {
      const editor = makeEditor(TWO_SECTIONS);
      selectNode(editor, "edu-1");

      expect(computeDragScope(editor.state)).toEqual({
        nodeType: "entry",
        scopeId: "education",
        scopeLabel: "Education",
      });
    });

    it("scopes a bullet drag to its own entry, by id, with no label", () => {
      const editor = makeEditor(TWO_SECTIONS);
      selectNode(editor, "bullet-a");

      expect(computeDragScope(editor.state)).toEqual({
        nodeType: "bullet",
        scopeId: "exp-1",
        scopeLabel: null,
      });
    });

    it("puts no restriction on a section drag", () => {
      const editor = makeEditor(TWO_SECTIONS);
      const { pos } = findNode(editor.state.doc, (n) => n.type.name === "section" && n.attrs.key === "education");
      editor.commands.setNodeSelection(pos);

      expect(computeDragScope(editor.state)).toEqual({ nodeType: "section", scopeId: null, scopeLabel: null });
    });

    it("returns null when the selection isn't a NodeSelection at all (nothing being dragged)", () => {
      const editor = makeEditor(TWO_SECTIONS);
      editor.commands.setTextSelection(1);

      expect(computeDragScope(editor.state)).toBeNull();
    });
  });

  describe("isPositionInScope", () => {
    it("allows a position inside a different entry of the same section", () => {
      const editor = makeEditor(TWO_SECTIONS);
      const scope = { nodeType: "entry" as const, scopeId: "education", scopeLabel: "Education" };
      const { pos } = findNode(editor.state.doc, byId("edu-2"));

      expect(isPositionInScope(editor.state, pos + 1, scope)).toBe(true);
    });

    it("rejects a position inside a different section", () => {
      const editor = makeEditor(TWO_SECTIONS);
      const scope = { nodeType: "entry" as const, scopeId: "education", scopeLabel: "Education" };
      const { pos } = findNode(editor.state.doc, byId("exp-1"));

      expect(isPositionInScope(editor.state, pos + 1, scope)).toBe(false);
    });

    it("allows a position inside a different bullet of the same entry", () => {
      const editor = makeEditor(TWO_SECTIONS);
      const scope = { nodeType: "bullet" as const, scopeId: "exp-1", scopeLabel: null };
      const { pos } = findNode(editor.state.doc, byId("bullet-b"));

      expect(isPositionInScope(editor.state, pos + 1, scope)).toBe(true);
    });

    it("rejects a position inside a different entry", () => {
      const editor = makeEditor(TWO_SECTIONS);
      const scope = { nodeType: "bullet" as const, scopeId: "exp-1", scopeLabel: null };
      const { pos } = findNode(editor.state.doc, byId("exp-2"));

      expect(isPositionInScope(editor.state, pos + 1, scope)).toBe(false);
    });

    it("allows any position for a section-level (unrestricted) scope", () => {
      const editor = makeEditor(TWO_SECTIONS);
      const scope = { nodeType: "section" as const, scopeId: null, scopeLabel: null };
      const { pos } = findNode(editor.state.doc, byId("exp-1"));

      expect(isPositionInScope(editor.state, pos + 1, scope)).toBe(true);
    });
  });

  describe("invalidDropMessage", () => {
    it("names the section for an entry drag", () => {
      expect(invalidDropMessage({ nodeType: "entry", scopeId: "education", scopeLabel: "Education" })).toBe(
        "Can only be reordered within the “Education” section.",
      );
    });

    it("falls back to generic wording for an entry drag with no label", () => {
      expect(invalidDropMessage({ nodeType: "entry", scopeId: "education", scopeLabel: null })).toBe(
        "Can only be reordered within its own section.",
      );
    });

    it("names no specific entry for a bullet drag", () => {
      expect(invalidDropMessage({ nodeType: "bullet", scopeId: "exp-1", scopeLabel: null })).toBe(
        "Can only be reordered within its own entry.",
      );
    });
  });
});
