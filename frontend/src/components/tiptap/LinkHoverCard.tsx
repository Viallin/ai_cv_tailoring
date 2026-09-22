import type { Editor } from "@tiptap/core";
import type { EditorState } from "@tiptap/pm/state";
import type { EditorView } from "@tiptap/pm/view";
import { useEditorState } from "@tiptap/react";
import { BubbleMenu } from "@tiptap/react/menus";
import { Copy, ExternalLink, Pencil, Unlink } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { computeNodeAncestry } from "@/lib/tiptap/useNodeAncestry";

import { LinkEditPopover } from "./LinkEditPopover";

interface LinkHoverCardProps {
  editor: Editor;
}

interface ShouldShowParams {
  editor: Editor;
  view: EditorView;
  state: EditorState;
}

// Phase 31 — see FormattingBubbleMenu.tsx's identical split for why this
// is a standalone, unit-testable function rather than an inline prop:
// jsdom can't exercise a real floating menu's layout, but this predicate
// needs nothing but a headless Editor's state. Collapsed-selection only
// (`state.selection.empty`) — a real range selection is
// FormattingBubbleMenu's surface instead, even one that happens to land
// on link text; the two are mutually exclusive by construction.
export function linkHoverCardShouldShow({ editor, view, state }: ShouldShowParams, menuElement: HTMLElement | null): boolean {
  const { doc, selection } = state;
  const isChildOfMenu = menuElement?.contains(document.activeElement) ?? false;
  const hasEditorFocus = view.hasFocus() || isChildOfMenu;
  if (!hasEditorFocus || !selection.empty || !editor.isEditable || !editor.isActive("link")) {
    return false;
  }
  const ancestry = computeNodeAncestry(doc, selection.from);
  return !ancestry.entryLocked && ancestry.entryIncluded && ancestry.sectionIncluded;
}

// Phase 31 — Google-Docs-style link chip: shown whenever the cursor sits
// (collapsed, no selection) inside existing link-marked text, distinct
// from FormattingBubbleMenu (which only ever shows for a real, non-empty
// selection — see that component's own shouldShow; the two are mutually
// exclusive by construction, empty vs. non-empty selection). Clicking
// into link text edits its *display text* normally
// (Link.configure({openOnClick: false}) in DocumentEditor.tsx) — this
// card is the explicit surface for everything else you'd want to do
// with the link itself: open it, copy it, change its URL, or remove it.
export function LinkHoverCard({ editor }: LinkHoverCardProps) {
  const [editing, setEditing] = useState(false);
  const elementRef = useRef<HTMLDivElement | null>(null);

  // Found live: clicking straight from one linked word into a different
  // one (no click elsewhere in between) left this card showing the FIRST
  // link's href — `shouldShow` stays `true` across that move (the menu
  // never hides), and `@tiptap/react/menus`'s BubbleMenu only repositions
  // itself in that case, it doesn't necessarily re-render these children
  // just because the cursor moved to a new mark. `href` only ever
  // "corrected itself" once some unrelated local state change (e.g.
  // finishing an edit, which flips `editing`) happened to force a
  // re-render — and then stuck at *that* link's href for everything after,
  // same bug either way. useEditorState subscribes directly to the
  // editor's own transactions (selection moves included), independent of
  // BubbleMenu's own re-render cadence, so this is always the link
  // actually under the cursor right now.
  const href = useEditorState({
    editor,
    selector: ({ editor }) => (editor.getAttributes("link").href as string | undefined) ?? "",
  });

  const stopEdit = () => setEditing(false);

  const applyUrl = (url: string) => {
    editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
    stopEdit();
  };

  const removeLink = () => {
    editor.chain().focus().extendMarkRange("link").unsetLink().run();
  };

  const openLink = () => {
    window.open(href, "_blank", "noopener,noreferrer");
  };

  const copyLink = () => {
    // Best-effort — clipboard access can legitimately be denied
    // (permissions, insecure context); the card already displays the raw
    // URL right there to copy by hand, so a rejected promise here isn't
    // worth surfacing as an error for a non-critical convenience action.
    void navigator.clipboard?.writeText(href);
  };

  return (
    <BubbleMenu
      ref={elementRef}
      editor={editor}
      pluginKey="linkHoverCard"
      shouldShow={(params) => linkHoverCardShouldShow(params, elementRef.current)}
      options={{ onHide: () => setEditing(false) }}
      className="flex items-center gap-1 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-md"
    >
      {editing ? (
        <LinkEditPopover initialUrl={href} onApply={applyUrl} onCancel={stopEdit} />
      ) : (
        <>
          <span className="max-w-48 truncate px-1.5 text-xs text-muted-foreground" title={href}>
            {href}
          </span>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Open link in a new tab" onClick={openLink}>
            <ExternalLink />
          </Button>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Copy link" onClick={copyLink}>
            <Copy />
          </Button>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Edit link" onClick={() => setEditing(true)}>
            <Pencil />
          </Button>
          <Button type="button" variant="ghost" size="icon-sm" aria-label="Remove link" onClick={removeLink}>
            <Unlink />
          </Button>
        </>
      )}
    </BubbleMenu>
  );
}
