import { Editor } from "@tiptap/core";
import { Text } from "@tiptap/extension-text";
import type { Node as PMNode } from "@tiptap/pm/model";
import { afterEach, describe, expect, it } from "vitest";

import type { DocumentModel } from "@/lib/structuredDocument";
import { documentModelToTiptapJSON } from "./converter";
import { computeActiveGutterItemId, computeNodeAncestry } from "./useNodeAncestry";
import { DOCUMENT_NODE_EXTENSIONS } from "./schema";

// Same headless-Editor technique as plugins.test.ts/commands.test.ts —
// no DOM/layout needed, these are pure queries against the document
// model.

// Undestroyed Editors leave a ProseMirror DOMObserver poll scheduled via
// setTimeout; if it fires after jsdom tears down between test files, it
// throws "document is not defined" as an unhandled error and fails the
// run despite every assertion passing. Track and destroy them below.
const editors: Editor[] = [];

afterEach(() => {
  editors.splice(0).forEach((editor) => editor.destroy());
});

function makeEditor(model: DocumentModel): Editor {
  const editor = new Editor({ extensions: [...DOCUMENT_NODE_EXTENSIONS, Text], content: documentModelToTiptapJSON(model) });
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

const MODEL: DocumentModel = {
  sections: [
    {
      key: "education",
      title: "Education",
      included: true,
      entries: [{ id: "edu-1", text: "State University", included: true }],
    },
    {
      key: "experience",
      title: "Experience",
      included: false,
      entries: [
        {
          id: "exp-1",
          text: "Engineer — Acme",
          included: true,
          bullets: [{ id: "bullet-a", text: "Shipped a thing.", included: true }],
        },
      ],
    },
  ],
};

describe("computeNodeAncestry", () => {
  it("returns the harmless default when pos isn't a number", () => {
    const editor = makeEditor(MODEL);
    expect(computeNodeAncestry(editor.state.doc, undefined)).toEqual({
      sectionKey: "",
      sectionIncluded: true,
      entryId: null,
      entryLocked: false,
      entryIncluded: true,
      entryAlignment: null,
    });
  });

  it("reports sectionIncluded: false from inside an excluded section's own entry", () => {
    const editor = makeEditor(MODEL);
    const { pos } = findNode(editor.state.doc, byId("bullet-a")); // inside "experience", which is excluded
    const ancestry = computeNodeAncestry(editor.state.doc, pos);
    expect(ancestry.sectionIncluded).toBe(false);
    expect(ancestry.entryIncluded).toBe(true); // its own entry (exp-1) is included — only the section is excluded
  });

  // Phase 31 (follow-up) — the actual bug this field exists to fix:
  // `entryHeading` (schema.ts) has no `alignment` attr of its own at
  // all; it lives on the parent `entry` node instead. A position inside
  // an entryHeading's own text has to resolve `entryAlignment` from that
  // ancestor, not from the node it's textually inside.
  it("resolves entryAlignment from the parent entry, not the entryHeading itself (which has no attrs of its own)", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "education",
          title: "Education",
          included: true,
          entries: [{ id: "edu-1", text: "State University", included: true, alignment: "center" }],
        },
      ],
    };
    const editor = makeEditor(model);
    const { pos } = findNode(editor.state.doc, byId("edu-1"));
    // entryHeading is always the entry's first child (schema.ts) — one
    // position in is inside its own text.
    expect(computeNodeAncestry(editor.state.doc, pos + 2).entryAlignment).toBe("center");
  });

  it("reports entryAlignment: null for an entry with no explicit alignment", () => {
    const editor = makeEditor(MODEL);
    const { pos } = findNode(editor.state.doc, byId("edu-1"));
    expect(computeNodeAncestry(editor.state.doc, pos + 2).entryAlignment).toBeNull();
  });
});

describe("computeActiveGutterItemId", () => {
  it("returns null when pos isn't a number", () => {
    const editor = makeEditor(MODEL);
    expect(computeActiveGutterItemId(editor.state.doc, undefined)).toBeNull();
  });

  it("resolves a position inside a bullet's own text to that bullet's gutter id", () => {
    const editor = makeEditor(MODEL);
    const { pos } = findNode(editor.state.doc, byId("bullet-a"));
    expect(computeActiveGutterItemId(editor.state.doc, pos + 1)).toBe("bullet:bullet-a");
  });

  it("resolves a position inside an entryHeading to its parent entry's gutter id, not the (nonexistent) entryHeading's own", () => {
    const editor = makeEditor(MODEL);
    const { pos: entryPos } = findNode(editor.state.doc, byId("edu-1"));
    // entryHeading is always the entry's first child (schema.ts) — one
    // position in is inside its own text.
    expect(computeActiveGutterItemId(editor.state.doc, entryPos + 2)).toBe("entry:edu-1");
  });

  it("resolves a position on a section directly (no entry/bullet ancestor) to that section's gutter id", () => {
    const editor = makeEditor(MODEL);
    const { pos } = findNode(editor.state.doc, (n) => n.type.name === "section" && n.attrs.key === "education");
    // Just inside the section, before its one entry.
    expect(computeActiveGutterItemId(editor.state.doc, pos + 1)).toBe("section:education");
  });
});
