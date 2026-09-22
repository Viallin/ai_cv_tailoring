import { Editor } from "@tiptap/core";
import { Text } from "@tiptap/extension-text";
import type { Node as PMNode } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import { afterEach, describe, expect, it } from "vitest";

import type { DocumentModel } from "@/lib/structuredDocument";
import { documentModelToTiptapJSON, tiptapJSONToDocumentModel } from "./converter";
import { handleBackspace, splitBulletSibling, splitEntryHeadingSibling } from "./commands";
import { DocumentGuards } from "./plugins";
import { DOCUMENT_NODE_EXTENSIONS } from "./schema";

// Phase 26 — the Enter/Backspace boundary rules from development_plan.md's
// Phase 26, exercised against a real, headless Editor instance (no DOM
// event synthesis — jsdom has no real Selection/Range tied to layout, so
// these call the exported command functions directly, exactly the layer
// schema.ts's addKeyboardShortcuts wires to `Enter`/`Backspace`).

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

// `nodeId` is an entry's or a bullet's own id. A bullet directly wraps
// text (content: "text*"), so its text starts one position in; an entry
// does *not* — its text-bearing child is entryHeading (content:
// "entryHeading bullet*", see schema.ts), one level deeper still.
function setCursorInText(editor: Editor, nodeId: string, offsetFromStart: number) {
  const { node, pos } = findNode(editor.state.doc, byId(nodeId));
  const textStart = node.type.name === "entry" ? pos + 2 : pos + 1;
  const textPos = textStart + offsetFromStart;
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, textPos)));
}

const TWO_BULLET_EXPERIENCE: DocumentModel = {
  sections: [
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
      ],
    },
  ],
};

describe("splitBulletSibling", () => {
  it("splits the bullet's text at the cursor into a new sibling bullet", () => {
    const editor = makeEditor(TWO_BULLET_EXPERIENCE);
    setCursorInText(editor, "bullet-a", "Shipped a".length); // right after "Shipped a"

    expect(splitBulletSibling(editor)).toBe(true);

    const model = tiptapJSONToDocumentModel(editor.getJSON());
    const bullets = model.sections[0].entries[0].bullets!;
    expect(bullets).toHaveLength(3);
    expect(bullets[0].text).toBe("Shipped a");
    expect(bullets[1].text).toBe(" thing.");
    expect(bullets[2].text).toBe("Shipped another thing.");
  });

  it("gives the new sibling bullet fresh, reset attrs — not a continuation of a subheading/evidence-linked bullet", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "experience",
          title: "Experience",
          included: true,
          entries: [
            {
              id: "exp-1",
              text: "Engineer — Acme",
              included: true,
              bullets: [{ id: "bullet-a", text: "Project X", included: true, kind: "subheading" }],
            },
          ],
        },
      ],
    };
    const editor = makeEditor(model);
    setCursorInText(editor, "bullet-a", "Project".length);

    expect(splitBulletSibling(editor)).toBe(true);

    const bullets = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries[0].bullets!;
    expect(bullets[0]).toMatchObject({ text: "Project", kind: "subheading" }); // original keeps its own identity
    expect(bullets[1]).toMatchObject({ text: " X", kind: undefined, evidence_id: undefined }); // new sibling is a fresh, plain bullet
  });

  it("does nothing when the cursor isn't inside a bullet", () => {
    const editor = makeEditor(TWO_BULLET_EXPERIENCE);
    setCursorInText(editor, "exp-1", "Engineer".length); // inside the entryHeading, not a bullet

    expect(splitBulletSibling(editor)).toBe(false);
  });
});

describe("splitEntryHeadingSibling", () => {
  it("splits the parent entry — the new entry starts empty, with the original entry's bullets staying on the first entry", () => {
    const editor = makeEditor(TWO_BULLET_EXPERIENCE);
    setCursorInText(editor, "exp-1", "Engineer — Acme".length); // cursor at the end of the heading

    expect(splitEntryHeadingSibling(editor)).toBe(true);

    const entries = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries;
    expect(entries).toHaveLength(2);
    expect(entries[0]).toMatchObject({ text: "Engineer — Acme" });
    expect(entries[0].bullets).toHaveLength(2); // untouched
    expect(entries[1]).toMatchObject({ text: "", locked: undefined, kind: undefined });
    expect(entries[1].bullets ?? []).toHaveLength(0);
  });

  it("does nothing when the cursor isn't inside an entryHeading", () => {
    const editor = makeEditor(TWO_BULLET_EXPERIENCE);
    setCursorInText(editor, "bullet-a", 2);

    expect(splitEntryHeadingSibling(editor)).toBe(false);
  });
});

describe("handleBackspace", () => {
  it("is a no-op at the start of the first bullet under an entry (would splice into the entry's own heading line)", () => {
    const editor = makeEditor(TWO_BULLET_EXPERIENCE);
    setCursorInText(editor, "bullet-a", 0);

    expect(handleBackspace(editor)).toBe(true); // handled (swallowed), not delegated further
    const entries = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries;
    expect(entries[0].bullets).toHaveLength(2); // unchanged
    expect(entries[0].text).toBe("Engineer — Acme"); // unchanged
  });

  it("joins into the previous bullet when at the start of a non-first bullet", () => {
    const editor = makeEditor(TWO_BULLET_EXPERIENCE);
    setCursorInText(editor, "bullet-b", 0);

    expect(handleBackspace(editor)).toBe(true);
    const bullets = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries[0].bullets!;
    expect(bullets).toHaveLength(1);
    expect(bullets[0].text).toBe("Shipped a thing.Shipped another thing.");
  });

  it("is a no-op at the start of the first entry in its section (never merges into the previous section)", () => {
    const model: DocumentModel = {
      sections: [
        { key: "summary", title: "Summary", included: true, entries: [{ id: "summary", text: "Intro.", included: true }] },
        {
          key: "education",
          title: "Education",
          included: true,
          entries: [{ id: "edu-1", text: "State University", included: true }],
        },
      ],
    };
    const editor = makeEditor(model);
    setCursorInText(editor, "edu-1", 0);

    expect(handleBackspace(editor)).toBe(true);
    const model2 = tiptapJSONToDocumentModel(editor.getJSON());
    expect(model2.sections[0].entries[0].text).toBe("Intro."); // untouched
    expect(model2.sections[1].entries[0].text).toBe("State University"); // untouched
  });

  it("joins two entries within the same section when at the start of a non-first entry", () => {
    const model: DocumentModel = {
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
      ],
    };
    const editor = makeEditor(model);
    setCursorInText(editor, "edu-2", 0);

    expect(handleBackspace(editor)).toBe(true);
    const entries = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries;
    expect(entries).toHaveLength(1);
    expect(entries[0].text).toBe("State UniversityCommunity College");
  });

  it("never merges a locked (Gap) entry with its previous sibling", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "experience",
          title: "Experience",
          included: true,
          entries: [
            { id: "exp-1", text: "Engineer — Acme", included: true, bullets: [] },
            { id: "gap-1", text: "Career gap", included: true, locked: true, bullets: [] },
          ],
        },
      ],
    };
    const editor = makeEditor(model);
    setCursorInText(editor, "gap-1", 0);

    expect(handleBackspace(editor)).toBe(true);
    const entries = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries;
    expect(entries).toHaveLength(2); // both survive, untouched
  });

  it("does nothing (falls through) when there's a real selection, or the cursor isn't at the start of the block", () => {
    const editor = makeEditor(TWO_BULLET_EXPERIENCE);
    setCursorInText(editor, "bullet-b", 2); // mid-text, not at start

    expect(handleBackspace(editor)).toBe(false);
  });
});

describe("idIntegrityPlugin (via commands, in appendTransaction)", () => {
  it("assigns a fresh, unique id to a freshly-split bullet", () => {
    const editor = makeEditor(TWO_BULLET_EXPERIENCE);
    setCursorInText(editor, "bullet-a", "Shipped a".length);
    splitBulletSibling(editor);

    const bullets = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries[0].bullets!;
    const ids = bullets.map((b) => b.id);
    expect(new Set(ids).size).toBe(ids.length); // all unique
    expect(ids.every((id) => Boolean(id))).toBe(true); // none null/empty
  });

  it("assigns a fresh, unique id to a freshly-split entry", () => {
    const editor = makeEditor(TWO_BULLET_EXPERIENCE);
    setCursorInText(editor, "exp-1", "Engineer — Acme".length);
    splitEntryHeadingSibling(editor);

    const entries = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries;
    expect(entries[1].id).not.toBe(entries[0].id);
    expect(entries[1].id).toBeTruthy();
  });
});

describe("excludedSelectionGuardPlugin (via a real transaction)", () => {
  it("relocates a selection that resolves inside an excluded bullet", () => {
    const model: DocumentModel = {
      sections: [
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
                { id: "bullet-a", text: "Shipped a thing.", included: false },
                { id: "bullet-b", text: "Shipped another thing.", included: true },
              ],
            },
          ],
        },
      ],
    };
    const editor = makeEditor(model);
    const { pos } = findNode(editor.state.doc, byId("bullet-a"));
    const insidePos = pos + 3;

    editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, insidePos)));

    const { pos: excludedPos, node: excludedNode } = findNode(editor.state.doc, byId("bullet-a"));
    const excludedEnd = excludedPos + excludedNode.nodeSize;
    const { from } = editor.state.selection;
    expect(from < excludedPos || from >= excludedEnd).toBe(true); // relocated outside the excluded node's range
  });
});
