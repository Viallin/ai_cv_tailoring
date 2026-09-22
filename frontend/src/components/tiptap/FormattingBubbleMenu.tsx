import { isTextSelection, type Editor } from "@tiptap/core";
import type { EditorState } from "@tiptap/pm/state";
import type { EditorView } from "@tiptap/pm/view";
import { useEditorState } from "@tiptap/react";
import { BubbleMenu } from "@tiptap/react/menus";
import { AlignCenter, AlignLeft, AlignRight, Bold, Italic, Link2, Underline } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import type { DocumentBlock } from "@/lib/structuredDocument";
import { computeNodeAncestry } from "@/lib/tiptap/useNodeAncestry";

import { LinkEditPopover } from "./LinkEditPopover";

interface FormattingBubbleMenuProps {
  editor: Editor;
}

interface ShouldShowParams {
  editor: Editor;
  view: EditorView;
  state: EditorState;
  from: number;
  to: number;
}

// Phase 31 — split out from the `shouldShow` prop below (same "pure
// function, unit-testable without mounting a real floating menu" move
// Phase 27's plugins.ts made for computeDragScope/isPositionInScope):
// jsdom has no real layout, so a mounted BubbleMenu's own floating-ui
// positioning can't be exercised in tests — this predicate can, against
// a real headless Editor's state, independent of whether anything is
// actually visible on screen.
//
// Mirrors `@tiptap/extension-bubble-menu`'s own default shouldShow
// (`isChildOfMenu` keeps the menu open once focus moves into
// LinkEditPopover's <input>, which lives inside this same menu element)
// plus this phase's own gating: never for a selection inside a `locked`
// (career-gap) entry or anything currently excluded — mirrors
// excludedSelectionGuardPlugin's own reasoning (plugins.ts) that
// excluded/locked content shouldn't offer editing affordances that read
// as live.
export function formattingBubbleMenuShouldShow(
  { editor, view, state, from, to }: ShouldShowParams,
  menuElement: HTMLElement | null,
): boolean {
  const { doc, selection } = state;
  const isEmptyTextBlock = !doc.textBetween(from, to).length && isTextSelection(selection);
  const isChildOfMenu = menuElement?.contains(document.activeElement) ?? false;
  const hasEditorFocus = view.hasFocus() || isChildOfMenu;
  if (!hasEditorFocus || selection.empty || isEmptyTextBlock || !editor.isEditable) {
    return false;
  }
  const ancestry = computeNodeAncestry(doc, from);
  return !ancestry.entryLocked && ancestry.entryIncluded && ancestry.sectionIncluded;
}

type Alignment = NonNullable<DocumentBlock["alignment"]>;

// Phase 31 (follow-up) — `entry`, not `entryHeading`: reported directly
// that alignment did nothing anywhere except Experience bullets/project
// names. Root cause — `entryHeading` (schema.ts) carries no attrs of its
// own at all; `alignment` (like `id`/`included`/`locked`/`kind`/
// `evidence_id`) lives on the *parent* `entry` node (see converter.ts's
// `entryToJSON` — the `entryHeading` JSON node has only `type`/
// `content`, no `attrs` key). Writing to `entryHeading.alignment` was a
// silent no-op every time; `bullet` nodes *do* carry their own
// `alignment` directly, which is exactly why that path alone "worked."
//
// A text selection can still span both an entry's heading and one or
// more of its bullets (a real, valid ProseMirror TextSelection — nothing
// in the schema stops a shift-click/drag from crossing that boundary,
// unlike the *structural* entry/section boundaries dragScopeGuardPlugin
// enforces for node drags), so both types still need updating in one
// chain — `updateAttributes` is a no-op for any type that isn't actually
// present in the selection, same reasoning as before, just the correct
// pair of type names this time.
const ALIGNABLE_NODE_TYPES = ["entry", "bullet"] as const;

function setAlignment(editor: Editor, alignment: Alignment) {
  const chain = editor.chain().focus();
  for (const type of ALIGNABLE_NODE_TYPES) {
    chain.updateAttributes(type, { alignment });
  }
  chain.run();
}

function isAlignment(editor: Editor, alignment: Alignment): boolean {
  return ALIGNABLE_NODE_TYPES.some((type) => editor.isActive(type, { alignment }));
}

// Phase 31 — Bold/Italic/Underline/Align/Link, shown for any non-empty
// text selection across every section (Contacts/Education/Certifications/
// Awards/Publications/Volunteer/Portfolio Links/Skills-Technologies/
// Summary/Experience alike — see development_plan.md's Phase 31 for why
// this widened past the original Summary/Experience-only draft). The one
// structural exclusion, not a section one: a selection inside a `locked`
// (career-gap) entry, or anything currently excluded — mirrors
// excludedSelectionGuardPlugin's own reasoning (plugins.ts) that excluded/
// locked content shouldn't offer editing affordances that read as live.
export function FormattingBubbleMenu({ editor }: FormattingBubbleMenuProps) {
  const [linkEditorOpen, setLinkEditorOpen] = useState(false);
  const elementRef = useRef<HTMLDivElement | null>(null);

  // Same staleness class LinkHoverCard.tsx's own `href` comment documents:
  // `shouldShow` stays `true` (the menu never hides) while a selection
  // moves from one already-qualifying spot to another, and BubbleMenu only
  // repositions in that case rather than necessarily re-rendering these
  // children — a direct `editor.isActive(...)`/`.getAttributes(...)` read
  // here would keep showing the *previous* selection's formatting state.
  // useEditorState subscribes to the editor's own transactions directly
  // (selection moves included), independent of BubbleMenu's own re-render
  // cadence, so every value below always reflects the selection right now.
  const format = useEditorState({
    editor,
    selector: ({ editor }) => ({
      bold: editor.isActive("bold"),
      italic: editor.isActive("italic"),
      underline: editor.isActive("underline"),
      link: editor.isActive("link"),
      linkHref: (editor.getAttributes("link").href as string | undefined) ?? "",
      alignLeft: isAlignment(editor, "left"),
      alignCenter: isAlignment(editor, "center"),
      alignRight: isAlignment(editor, "right"),
    }),
  });

  const openLinkEditor = () => setLinkEditorOpen(true);
  const closeLinkEditor = () => setLinkEditorOpen(false);

  const applyLink = (url: string) => {
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
    closeLinkEditor();
  };

  return (
    <BubbleMenu
      ref={elementRef}
      editor={editor}
      pluginKey="formattingBubbleMenu"
      shouldShow={(params) => formattingBubbleMenuShouldShow(params, elementRef.current)}
      options={{ onHide: () => setLinkEditorOpen(false) }}
      className="flex items-center gap-0.5 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-md"
    >
      {linkEditorOpen ? (
        <LinkEditPopover initialUrl={format.linkHref} onApply={applyLink} onCancel={closeLinkEditor} />
      ) : (
        <>
          <Button
            type="button"
            variant={format.bold ? "secondary" : "ghost"}
            size="icon-sm"
            aria-label="Bold"
            aria-pressed={format.bold}
            onClick={() => editor.chain().focus().toggleBold().run()}
          >
            <Bold />
          </Button>
          <Button
            type="button"
            variant={format.italic ? "secondary" : "ghost"}
            size="icon-sm"
            aria-label="Italic"
            aria-pressed={format.italic}
            onClick={() => editor.chain().focus().toggleItalic().run()}
          >
            <Italic />
          </Button>
          <Button
            type="button"
            variant={format.underline ? "secondary" : "ghost"}
            size="icon-sm"
            aria-label="Underline"
            aria-pressed={format.underline}
            onClick={() => editor.chain().focus().toggleUnderline().run()}
          >
            <Underline />
          </Button>
          <div className="mx-0.5 h-5 w-px bg-border" role="separator" aria-orientation="vertical" />
          <Button
            type="button"
            variant={format.alignLeft ? "secondary" : "ghost"}
            size="icon-sm"
            aria-label="Align left"
            aria-pressed={format.alignLeft}
            onClick={() => setAlignment(editor, "left")}
          >
            <AlignLeft />
          </Button>
          <Button
            type="button"
            variant={format.alignCenter ? "secondary" : "ghost"}
            size="icon-sm"
            aria-label="Align center"
            aria-pressed={format.alignCenter}
            onClick={() => setAlignment(editor, "center")}
          >
            <AlignCenter />
          </Button>
          <Button
            type="button"
            variant={format.alignRight ? "secondary" : "ghost"}
            size="icon-sm"
            aria-label="Align right"
            aria-pressed={format.alignRight}
            onClick={() => setAlignment(editor, "right")}
          >
            <AlignRight />
          </Button>
          <div className="mx-0.5 h-5 w-px bg-border" role="separator" aria-orientation="vertical" />
          <Button
            type="button"
            variant={format.link ? "secondary" : "ghost"}
            size="icon-sm"
            aria-label={format.link ? "Remove link" : "Insert link"}
            aria-pressed={format.link}
            onClick={() => {
              if (format.link) {
                editor.chain().focus().extendMarkRange("link").unsetLink().run();
              } else {
                openLinkEditor();
              }
            }}
          >
            <Link2 />
          </Button>
        </>
      )}
    </BubbleMenu>
  );
}
