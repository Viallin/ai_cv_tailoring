import { useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface LinkEditPopoverProps {
  initialUrl?: string;
  onApply: (url: string) => void;
  onCancel: () => void;
}

// Phase 31 — the one URL-entry form shared by both "insert a new link"
// (FormattingBubbleMenu's Link button, no existing mark on the
// selection) and "edit an existing link's URL" (LinkHoverCard's Edit
// button) — same field, same validation, only the caller and what it
// does with the result differ.
//
// Deliberately plain markup, not a Radix `Popover` — rendered as an
// ordinary DOM child of whichever `BubbleMenu` instance hosts it.
// `@tiptap/extension-bubble-menu`'s own default `shouldShow` already
// treats any element inside its own menu container as "still focused"
// (`element.contains(document.activeElement)`) even once the ProseMirror
// view itself loses DOM focus to this input — see FormattingBubbleMenu.tsx's
// and LinkHoverCard.tsx's own `shouldShow`, which replicate that same
// check. A Radix Popover manages its own portal/focus trap outside the
// menu's DOM subtree entirely, which would fight that mechanism instead
// of cooperating with it — confirmed not worth the fight for one input
// and two buttons.
export function LinkEditPopover({ initialUrl = "", onApply, onCancel }: LinkEditPopoverProps) {
  const [url, setUrl] = useState(initialUrl);
  const trimmed = url.trim();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (trimmed.length > 0) {
      onApply(trimmed);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
    }
  };

  return (
    <form onSubmit={submit} className="flex items-center gap-1.5">
      {/* eslint-disable-next-line jsx-a11y/no-autofocus -- this form only ever mounts in direct response to the user's own click (Link/Edit button); autofocus here is the whole point, not a page-load surprise */}
      <Input
        value={url}
        onChange={(event) => setUrl(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="https://…"
        autoFocus
        className="h-7 w-56 text-xs"
        aria-label="Link URL"
      />
      <Button type="submit" size="sm" variant="secondary" disabled={trimmed.length === 0}>
        Apply
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
    </form>
  );
}
