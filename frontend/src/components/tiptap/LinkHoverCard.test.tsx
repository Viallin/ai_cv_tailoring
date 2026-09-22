import { Editor } from "@tiptap/core";
import { Link } from "@tiptap/extension-link";
import { Text } from "@tiptap/extension-text";
import type { Node as PMNode } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DocumentModel } from "@/lib/structuredDocument";
import { documentModelToTiptapJSON } from "@/lib/tiptap/converter";
import { DOCUMENT_NODE_EXTENSIONS } from "@/lib/tiptap/schema";

import { linkHoverCardShouldShow } from "./LinkHoverCard";

// Phase 31 — see FormattingBubbleMenu.test.tsx's identical header for why
// this exercises the exported pure predicate against a real headless
// Editor rather than a mounted floating menu (jsdom has no real layout),
// and why `view.hasFocus()` is mocked true throughout except the one
// isChildOfMenu-specific case.

// Undestroyed Editors leave a ProseMirror DOMObserver poll scheduled via
// setTimeout; if it fires after jsdom tears down between test files, it
// throws "document is not defined" as an unhandled error and fails the
// run despite every assertion passing. Track and destroy them below.
const editors: Editor[] = [];

function makeEditor(model: DocumentModel): Editor {
  // No DocumentGuards, same reasoning as FormattingBubbleMenu.test.tsx —
  // isolating this predicate's own logic from the separate
  // excludedSelectionGuardPlugin (Phase 26, already covered elsewhere).
  const editor = new Editor({
    extensions: [...DOCUMENT_NODE_EXTENSIONS, Text, Link.configure({ openOnClick: false, autolink: false })],
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

function selectTextRange(editor: Editor, nodeId: string, fromOffset: number, toOffset: number) {
  const { node, pos } = findNode(editor.state.doc, byId(nodeId));
  const textStart = pos + (node.type.name === "entry" ? 2 : 1);
  editor.view.dispatch(
    editor.state.tr.setSelection(TextSelection.create(editor.state.doc, textStart + fromOffset, textStart + toOffset)),
  );
}

function collapseCursor(editor: Editor, nodeId: string, offset: number) {
  selectTextRange(editor, nodeId, offset, offset);
}

const MODEL: DocumentModel = {
  sections: [
    {
      key: "education",
      title: "Education",
      included: true,
      entries: [
        { id: "edu-1", text: "State University", included: true },
        { id: "edu-excluded", text: "Excluded College", included: false },
      ],
    },
    {
      key: "experience",
      title: "Experience",
      included: true,
      entries: [{ id: "exp-gap", text: "Career gap (2020–2021)", included: true, locked: true }],
    },
  ],
};

function paramsFor(editor: Editor) {
  return { editor, view: editor.view, state: editor.state };
}

function applyLinkTo(editor: Editor, nodeId: string, fromOffset: number, toOffset: number, href: string) {
  selectTextRange(editor, nodeId, fromOffset, toOffset);
  editor.commands.setLink({ href });
}

describe("linkHoverCardShouldShow", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    editors.splice(0).forEach((editor) => editor.destroy());
  });

  it("shows for a collapsed cursor inside an existing link", () => {
    const editor = makeEditor(MODEL);
    vi.spyOn(editor.view, "hasFocus").mockReturnValue(true);
    applyLinkTo(editor, "edu-1", 0, 5, "https://state.edu");
    collapseCursor(editor, "edu-1", 2); // inside "State"

    expect(linkHoverCardShouldShow(paramsFor(editor), null)).toBe(true);
  });

  it("hides for a collapsed cursor outside any link", () => {
    const editor = makeEditor(MODEL);
    vi.spyOn(editor.view, "hasFocus").mockReturnValue(true);
    applyLinkTo(editor, "edu-1", 0, 5, "https://state.edu");
    collapseCursor(editor, "edu-1", 10); // well past "State"

    expect(linkHoverCardShouldShow(paramsFor(editor), null)).toBe(false);
  });

  it("hides for a real (non-empty) selection, even one that lands entirely on link text — that's FormattingBubbleMenu's surface instead", () => {
    const editor = makeEditor(MODEL);
    vi.spyOn(editor.view, "hasFocus").mockReturnValue(true);
    applyLinkTo(editor, "edu-1", 0, 5, "https://state.edu");
    selectTextRange(editor, "edu-1", 0, 5); // re-select the same linked span

    expect(linkHoverCardShouldShow(paramsFor(editor), null)).toBe(false);
  });

  it("hides for a cursor inside a locked (career-gap) entry, even if it were somehow linked", () => {
    const editor = makeEditor(MODEL);
    vi.spyOn(editor.view, "hasFocus").mockReturnValue(true);
    applyLinkTo(editor, "exp-gap", 0, 6, "https://example.com");
    collapseCursor(editor, "exp-gap", 2);

    expect(linkHoverCardShouldShow(paramsFor(editor), null)).toBe(false);
  });

  it("hides for a cursor inside excluded (included: false) content", () => {
    const editor = makeEditor(MODEL);
    vi.spyOn(editor.view, "hasFocus").mockReturnValue(true);
    applyLinkTo(editor, "edu-excluded", 0, 8, "https://example.com");
    collapseCursor(editor, "edu-excluded", 2);

    expect(linkHoverCardShouldShow(paramsFor(editor), null)).toBe(false);
  });

  it("stays shown once focus moves into the card's own DOM (isChildOfMenu) — needed for the Edit sub-form", () => {
    const editor = makeEditor(MODEL);
    applyLinkTo(editor, "edu-1", 0, 5, "https://state.edu");
    collapseCursor(editor, "edu-1", 2);

    const menuElement = document.createElement("div");
    document.body.appendChild(menuElement);
    const input = document.createElement("input");
    menuElement.appendChild(input);
    input.focus();

    expect(linkHoverCardShouldShow(paramsFor(editor), menuElement)).toBe(true);
  });
});
