import { Editor } from "@tiptap/core";
import { Bold } from "@tiptap/extension-bold";
import { Italic } from "@tiptap/extension-italic";
import { Link } from "@tiptap/extension-link";
import { Text } from "@tiptap/extension-text";
import { Underline } from "@tiptap/extension-underline";
import type { Node as PMNode } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import { describe, expect, it } from "vitest";

import type { DocumentModel } from "@/lib/structuredDocument";
import { documentModelToTiptapJSON, tiptapJSONToDocumentModel } from "./converter";
import { DocumentGuards } from "./plugins";
import { DOCUMENT_NODE_EXTENSIONS } from "./schema";

// Phase 31 — the mark extensions DocumentEditor.tsx wires up
// (components/DocumentEditor.tsx's own EDITOR_EXTENSIONS), exercised
// against a real, headless Editor instance driving this app's actual
// section/entry/entryHeading/bullet schema — same pattern
// commands.test.ts already established for Enter/Backspace: no DOM
// event synthesis, direct command calls and a hand-built selection.

function makeEditor(model: DocumentModel): Editor {
  return new Editor({
    extensions: [
      ...DOCUMENT_NODE_EXTENSIONS,
      Text,
      DocumentGuards,
      Bold,
      Italic,
      Underline,
      Link.configure({ openOnClick: false, autolink: false }),
    ],
    content: documentModelToTiptapJSON(model),
  });
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

// Selects `[fromOffset, toOffset)` of an entry's or a bullet's own text.
// A bullet wraps text directly (content: "text*"), so its text starts one
// position past the bullet node itself; an entry does *not* — its
// text-bearing child is entryHeading (content: "entryHeading bullet*",
// schema.ts), one level deeper still — same distinction
// commands.test.ts's own setCursorInText documents.
function selectTextRange(editor: Editor, nodeId: string, fromOffset: number, toOffset: number) {
  const { node, pos } = findNode(editor.state.doc, byId(nodeId));
  const textStart = pos + (node.type.name === "entry" ? 2 : 1);
  editor.view.dispatch(
    editor.state.tr.setSelection(TextSelection.create(editor.state.doc, textStart + fromOffset, textStart + toOffset)),
  );
}

const ONE_BULLET_MODEL: DocumentModel = {
  sections: [
    {
      key: "education",
      title: "Education",
      included: true,
      entries: [{ id: "edu-1", text: "State University, magna cum laude", included: true }],
    },
  ],
};

describe("Phase 31 marks", () => {
  it("toggleBold on a selected range produces a bold TextRun on read-back", () => {
    const editor = makeEditor(ONE_BULLET_MODEL);
    // "State" is offsets [0, 5) of "State University, magna cum laude"
    selectTextRange(editor, "edu-1", 0, 5);
    editor.commands.toggleBold();

    const model = tiptapJSONToDocumentModel(editor.getJSON());
    const entry = model.sections[0].entries[0];
    expect(entry.text).toBe("State University, magna cum laude"); // plain text unaffected
    expect(entry.runs).toEqual([
      { text: "State", bold: true },
      { text: " University, magna cum laude" },
    ]);
  });

  it("toggleItalic and toggleUnderline compose on an overlapping range", () => {
    const editor = makeEditor(ONE_BULLET_MODEL);
    selectTextRange(editor, "edu-1", 0, 5);
    editor.commands.toggleBold();
    editor.commands.toggleItalic();
    selectTextRange(editor, "edu-1", 3, 8);
    editor.commands.toggleUnderline();

    const entry = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries[0];
    // The two ranges only partly overlap ([0,5) bold+italic, [3,8)
    // underline): "Sta" stays bold+italic only, "te" picks up all three
    // (the actual overlap), " Un" is underline-only (never bolded), then
    // plain text — four runs, not a uniform middle one.
    expect(entry.runs).toEqual([
      { text: "Sta", bold: true, italic: true },
      { text: "te", bold: true, italic: true, underline: true },
      { text: " Un", underline: true },
      { text: "iversity, magna cum laude" },
    ]);
  });

  it("setLink on a selected range produces a run carrying href", () => {
    const editor = makeEditor(ONE_BULLET_MODEL);
    selectTextRange(editor, "edu-1", 0, 5);
    editor.commands.setLink({ href: "https://example.edu" });

    const entry = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries[0];
    expect(entry.runs).toEqual([
      { text: "State", link: "https://example.edu" },
      { text: " University, magna cum laude" },
    ]);
  });

  it("extendMarkRange + unsetLink removes the mark from the whole link, cursor placed anywhere inside it", () => {
    const editor = makeEditor(ONE_BULLET_MODEL);
    selectTextRange(editor, "edu-1", 0, 5);
    editor.commands.setLink({ href: "https://example.edu" });

    // Collapse the cursor to the middle of the linked span, then remove
    // via extendMarkRange — mirrors LinkHoverCard.tsx's own command.
    selectTextRange(editor, "edu-1", 2, 2);
    editor.commands.extendMarkRange("link");
    editor.commands.unsetLink();

    const entry = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries[0];
    expect(entry.runs).toBeUndefined();
    expect(entry.text).toBe("State University, magna cum laude");
  });

  it("a block with no marks applied still round-trips with runs undefined", () => {
    const editor = makeEditor(ONE_BULLET_MODEL);
    const entry = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries[0];
    expect(entry.runs).toBeUndefined();
  });
});

// Phase 31 (follow-up), reported directly: "Alignment doesn't work in
// summary, contacts, key projects, headers of the roles... Basically, it
// works only for project names and experience bullets." Root cause:
// `entryHeading` (schema.ts) carries no attrs of its own — `alignment`
// lives on the *parent* `entry` node — so
// `editor.commands.updateAttributes("entryHeading", {alignment})`
// (FormattingBubbleMenu.tsx's original, wrong target) was a silent
// no-op for every entry's own heading text; only `bullet` nodes (which
// do carry their own `alignment`) ever visibly worked. These tests drive
// the exact command FormattingBubbleMenu.tsx now issues
// (`updateAttributes("entry", ...)`) and confirm it actually reaches the
// DocumentModel — the same round-trip a live Align-button click
// produces end to end.
describe("Phase 31 alignment (follow-up)", () => {
  it("updateAttributes('entry', ...) on a selection inside an entry's heading sets DocumentEntry.alignment", () => {
    const editor = makeEditor(ONE_BULLET_MODEL);
    selectTextRange(editor, "edu-1", 0, 5); // "State" — inside entryHeading's own text
    editor.commands.updateAttributes("entry", { alignment: "center" });

    const entry = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries[0];
    expect(entry.alignment).toBe("center");
  });

  it("updateAttributes('entryHeading', ...) — the original, wrong target — is a silent no-op (documents the actual bug)", () => {
    const editor = makeEditor(ONE_BULLET_MODEL);
    selectTextRange(editor, "edu-1", 0, 5);
    editor.commands.updateAttributes("entryHeading", { alignment: "center" });

    const entry = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries[0];
    expect(entry.alignment).toBeUndefined();
  });

  it("isActive('entry', {alignment}) reflects the enclosing entry's alignment from a cursor inside its heading text", () => {
    const editor = makeEditor(ONE_BULLET_MODEL);
    selectTextRange(editor, "edu-1", 0, 5);
    editor.commands.updateAttributes("entry", { alignment: "right" });
    selectTextRange(editor, "edu-1", 10, 10); // collapsed cursor elsewhere in the same heading

    expect(editor.isActive("entry", { alignment: "right" })).toBe(true);
    expect(editor.isActive("entry", { alignment: "left" })).toBe(false);
  });

  it("a bullet's own alignment is independent of its parent entry's", () => {
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
              bullets: [{ id: "exp-1-bullet-0", text: "Shipped a thing.", included: true }],
            },
          ],
        },
      ],
    };
    const editor = makeEditor(model);
    selectTextRange(editor, "exp-1-bullet-0", 0, 7); // "Shipped" — inside the bullet's own text
    editor.commands.updateAttributes("bullet", { alignment: "center" });

    const entry = tiptapJSONToDocumentModel(editor.getJSON()).sections[0].entries[0];
    expect(entry.alignment).toBeUndefined(); // the entry's own heading is untouched
    expect(entry.bullets?.[0].alignment).toBe("center");
  });
});
