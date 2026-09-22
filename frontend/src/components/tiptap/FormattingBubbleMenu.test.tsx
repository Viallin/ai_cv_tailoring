import { Editor } from "@tiptap/core";
import { Bold } from "@tiptap/extension-bold";
import { Text } from "@tiptap/extension-text";
import type { Node as PMNode } from "@tiptap/pm/model";
import { TextSelection } from "@tiptap/pm/state";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DocumentModel } from "@/lib/structuredDocument";
import { documentModelToTiptapJSON } from "@/lib/tiptap/converter";
import { DOCUMENT_NODE_EXTENSIONS } from "@/lib/tiptap/schema";

import { formattingBubbleMenuShouldShow } from "./FormattingBubbleMenu";

// Phase 31 — formattingBubbleMenuShouldShow is a pure function (see its
// own docstring for why it's split out this way, same move Phase 27's
// plugins.ts made for computeDragScope/isPositionInScope): exercised
// here against a real headless Editor's state, no mounted floating menu
// or DOM layout needed. `view.hasFocus()` is mocked `true` throughout —
// a headless Editor's detached DOM view never has real jsdom focus, and
// this file isn't testing focus handling itself (that's the
// `isChildOfMenu` branch's job, exercised once explicitly below).

function makeEditor(model: DocumentModel): Editor {
  // Deliberately no DocumentGuards here — excludedSelectionGuardPlugin
  // would relocate a selection dispatched *into* excluded content before
  // this file's own excluded-entry test could ever observe it there;
  // that guard has its own coverage (Phase 26). This file is testing
  // formattingBubbleMenuShouldShow's own gating logic in isolation.
  return new Editor({
    extensions: [...DOCUMENT_NODE_EXTENSIONS, Text, Bold],
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

// shouldShow's own {editor, view, state, from, to} shape.
function paramsFor(editor: Editor) {
  const { from, to } = editor.state.selection;
  return { editor, view: editor.view, state: editor.state, from, to };
}

describe("formattingBubbleMenuShouldShow", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows for a real (non-empty) selection in an ordinary entry", () => {
    const editor = makeEditor(MODEL);
    vi.spyOn(editor.view, "hasFocus").mockReturnValue(true);
    selectTextRange(editor, "edu-1", 0, 5);

    expect(formattingBubbleMenuShouldShow(paramsFor(editor), null)).toBe(true);
  });

  it("hides for a collapsed cursor (no real selection)", () => {
    const editor = makeEditor(MODEL);
    vi.spyOn(editor.view, "hasFocus").mockReturnValue(true);
    collapseCursor(editor, "edu-1", 2);

    expect(formattingBubbleMenuShouldShow(paramsFor(editor), null)).toBe(false);
  });

  it("hides for a selection inside a locked (career-gap) entry", () => {
    const editor = makeEditor(MODEL);
    vi.spyOn(editor.view, "hasFocus").mockReturnValue(true);
    selectTextRange(editor, "exp-gap", 0, 6);

    expect(formattingBubbleMenuShouldShow(paramsFor(editor), null)).toBe(false);
  });

  it("hides for a selection inside excluded (included: false) content", () => {
    const editor = makeEditor(MODEL);
    vi.spyOn(editor.view, "hasFocus").mockReturnValue(true);
    selectTextRange(editor, "edu-excluded", 0, 8);

    expect(formattingBubbleMenuShouldShow(paramsFor(editor), null)).toBe(false);
  });

  it("hides when the editor view has no focus and the menu element isn't focused either", () => {
    const editor = makeEditor(MODEL);
    // hasFocus left at its real (false) value — a detached headless view.
    selectTextRange(editor, "edu-1", 0, 5);

    expect(formattingBubbleMenuShouldShow(paramsFor(editor), null)).toBe(false);
  });

  it("stays shown once focus moves into the menu's own DOM (isChildOfMenu) — needed for LinkEditPopover's <input>", () => {
    const editor = makeEditor(MODEL);
    selectTextRange(editor, "edu-1", 0, 5);

    const menuElement = document.createElement("div");
    document.body.appendChild(menuElement);
    const input = document.createElement("input");
    menuElement.appendChild(input);
    input.focus();
    expect(document.activeElement).toBe(input);

    // hasFocus still false (real value) — only isChildOfMenu keeps this shown.
    expect(formattingBubbleMenuShouldShow(paramsFor(editor), menuElement)).toBe(true);
  });
});
