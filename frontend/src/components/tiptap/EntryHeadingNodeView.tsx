import { NodeViewContent, NodeViewWrapper, type NodeViewProps } from "@tiptap/react";
import { useEffect, useState } from "react";

import { useDocumentEditorNodeViewContext } from "@/lib/tiptap/context";
import { useNodeAncestry } from "@/lib/tiptap/useNodeAncestry";

// Phase 26 — an entry's own heading/line text. Default styling depends
// on which section this entry belongs to (from useNodeAncestry — this
// node has no attrs of its own beyond `kind`, and no ambient context
// either, see lib/tiptap/context.tsx's docstring): Experience role
// headings are always bold, or italic for a locked Gap entry
// (DocumentExperienceSection.tsx's old ExperienceEntryRow); every other
// section's entries are plain unless `kind === "subheading"` (a Skills/
// Technologies category header — DocumentSectionBlock.tsx's old
// SectionEntryRow uses the same rule). No `cv-print-entry` class here —
// that lives on EntryNodeView's own wrapper (matching
// PrintExperienceSection.tsx's div, not this `<p>`).
//
// Phase 27 (revised) — no checkbox, no drag handle, no DocumentRow here
// anymore: both the "include this entry" toggle and the drag handle
// moved up to EntryNodeView.tsx, which owns `included`/`locked`/the
// entry's own `id` directly (no ancestor-walking needed there) and,
// critically, is the node that's actually draggable — see
// schema.ts's TiptapEntryHeading comment for the two real bugs that
// came from this chrome living here instead.
//
// Phase 28 — the `pl-12` this used to carry (handle + gap + checkbox +
// gap, reserved so the heading text wouldn't sit under that inline
// chrome) is gone entirely, in two steps: the checkbox moved out first
// (shrinking it to `pl-6`, handle + gap only), then the handle itself
// moved to `position: absolute` at a negative offset into the page's own
// blank left margin (EntryNodeView.tsx, gutterLayout.ts's
// HANDLE_LEFT_PX) once it became clear *any* reserved inline space here
// was the actual problem being reported, not just the checkbox's share
// of it. Heading text now starts flush with the page's own left margin —
// the same position PrintExperienceSection.tsx/PrintSectionBlock.tsx
// already rendered it at, closing Phase 26's "not pixel-real" gap for
// good, not just partway.
export function EntryHeadingNodeView({ node, editor, getPos }: NodeViewProps) {
  const ctx = useDocumentEditorNodeViewContext();
  // Phase 31 (follow-up) — reported directly, a second time, after the
  // `entry`-vs-`entryHeading` attr-target fix above: alignment now
  // reached the DocumentModel correctly (confirmed directly against the
  // live editor's own JSON) but *still* didn't repaint on screen. Root
  // cause: `entryAlignment` comes from the *parent* `entry` node's
  // attrs, not this node's own — and a transaction that only changes an
  // ancestor's attrs leaves this `entryHeading` node's own object
  // unchanged, so Tiptap's NodeView reconciliation has no reason to
  // re-render this component at all. This is exactly the "stale
  // ancestor fact" pitfall `useNodeAncestry.ts`'s own docstring already
  // documents for `DocumentGutter`'s remeasure (a NodeView whose own
  // node didn't change isn't guaranteed to re-render when an ancestor's
  // did) — that docstring's fix (read fresh from the live doc, driven by
  // `editor.on("update")`) applies here too, just via a local
  // force-re-render instead of an external store, since this only needs
  // to affect this one NodeView instance's own render.
  const [, forceUpdate] = useState(0);
  useEffect(() => {
    const rerender = () => forceUpdate((count) => count + 1);
    editor.on("update", rerender);
    return () => {
      editor.off("update", rerender);
    };
  }, [editor]);

  const { sectionKey, entryLocked, entryAlignment } = useNodeAncestry({ editor, getPos });
  const isExperience = sectionKey === "experience";
  const isSubheading = node.attrs.kind === "subheading";
  const textClassName = isExperience ? (entryLocked ? "italic" : "font-bold") : isSubheading ? "font-bold" : undefined;
  // Post-29 fix — reported directly: Contacts/Key Projects/Education/
  // Skills/etc. entries never showed a bullet marker on screen, while
  // PrintSectionBlock.tsx's own equivalent `<p>` always prefixes an
  // ungrouped entry with `{bulletChar} ` (its one other branch — a
  // Skills/Technologies `subheading` category and the members under it —
  // compacts onto one bold-label line with no per-item marker at all,
  // which this mirrors by skipping the prefix for a `subheading` entry
  // itself). An Experience role heading gets no prefix either way,
  // matching PrintExperienceSection.tsx's own plain `<p>` for it. Known,
  // accepted residual gap: an ordinary (non-subheading) *member* row
  // that export would compact under a preceding subheading category
  // still shows a marker here, since on screen it's still its own
  // individually-editable row either way — the compacting itself is a
  // pre-existing, out-of-scope structural difference this fix doesn't
  // touch.
  //
  // Post-30 polish, reported directly: Summary was getting a bullet
  // marker here too — matched every other section's own convention
  // structurally, but Summary isn't a list, it's prose (one paragraph,
  // sometimes a few) and was never treated as one anywhere else: neither
  // export path ever prefixed it (cv_markdown.py's `_block_markdown_text`
  // branch has no "- "/bulletChar of its own, and PrintSectionBlock.tsx
  // is fixed the same way below). Scoped to the section key, not `kind`
  // — Summary entries never have `kind === "subheading"` either way, so
  // this is a genuinely new exclusion, not already implied by one above.
  const isSummary = sectionKey === "summary";
  // Post-31 — Skills/Technologies entries are no longer one row per
  // skill (see structuredDocument.ts's buildCompactSkillEntries): each
  // entry is already a whole compact, pre-joined line ("Design:
  // Roadmapping; Level Design", or "Mentoring · Team Management · ...")
  // matching PrintSectionBlock.tsx's own export rendering exactly, which
  // never gives that line a bullet marker either. `kind` is never
  // `"subheading"` for these anymore, so this needs its own exclusion,
  // same shape as Summary's just above. Known, accepted gap: a
  // category entry's own bold "Design:" label (carried via `runs` for
  // export — see buildCompactSkillEntries's docstring) doesn't render
  // bold *here* — the live editor has no rich-text rendering for `runs`
  // yet at all (Phase 25's own scope note: "no editor UI to produce this
  // yet"), so this shows as one plain, unstyled line on screen even
  // though export renders it correctly.
  const isSkillsOrTechnologies = sectionKey === "skills" || sectionKey === "technologies";
  const showBulletChar = !isExperience && !isSubheading && !isSummary && !isSkillsOrTechnologies;
  // Phase 31 (follow-up, reported directly: "I don't see that alignment
  // buttons do anything to the text in the editor") — FormattingBubbleMenu's
  // Align buttons correctly wrote `alignment` somewhere (confirmed via
  // export, and via the DocumentModel itself), but no NodeView ever read
  // it back into a visual style here. `alignment` only ever reached the
  // read-only Print*/export renderers (PrintExperienceSection.tsx,
  // PrintSectionBlock.tsx's alignmentStyle), never the live, editable
  // Tiptap surface itself.
  //
  // Second follow-up, reported directly: still nothing, for every
  // section *except* Experience bullets/project names. Root cause: this
  // node's own `node.attrs.alignment` doesn't exist at all —
  // `entryHeading` (schema.ts) carries no attrs of its own; `id`/
  // `included`/`locked`/`kind`/`evidence_id`/`alignment` all live on the
  // *parent* `entry` node instead (see converter.ts's `entryToJSON`: the
  // `entryHeading` JSON node has only `type`/`content`, no `attrs` key
  // at all). `bullet` nodes *do* carry their own `alignment`
  // (`blockAttributes()`), which is exactly why alignment "worked" there
  // and nowhere else — FormattingBubbleMenu.tsx's `setAlignment` was
  // writing to a schema attr (`entryHeading.alignment`) that plainly
  // doesn't exist, a silent no-op every single time. Fixed at both
  // ends: FormattingBubbleMenu.tsx now targets `entry` (not
  // `entryHeading`), and this component reads `entryAlignment` off
  // `useNodeAncestry`'s own walk to the parent entry — the same
  // ancestor-lookup already used for `sectionKey`/`entryLocked`, not a
  // new mechanism. `|| undefined`, not a bare read — the unset value is
  // `null`, and React's `style` prop treats `null`/`undefined`
  // identically, but `undefined` is the more honest way to say "no
  // explicit value" here.
  const alignment = entryAlignment || undefined;

  return (
    <NodeViewWrapper as="p" className={textClassName} style={{ textAlign: alignment }}>
      {showBulletChar && <span aria-hidden="true">{ctx.bulletChar} </span>}
      <NodeViewContent<"span"> as="span" />
    </NodeViewWrapper>
  );
}
