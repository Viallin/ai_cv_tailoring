import { NodeViewContent, NodeViewWrapper, type NodeViewProps } from "@tiptap/react";
import { Sparkles, X } from "lucide-react";
import { useRef, useState } from "react";

import type { BulletProvenance } from "@/api/models";
import { DragHandle } from "@/components/tiptap/DragHandle";
import { Button } from "@/components/ui/button";
import { Popover, PopoverAnchor, PopoverClose, PopoverContent } from "@/components/ui/popover";
import { useDocumentEditorNodeViewContext } from "@/lib/tiptap/context";
import { HANDLE_LEFT_PX } from "@/lib/tiptap/gutterLayout";
import { useGutterItem } from "@/lib/tiptap/useGutterItem";
import { useNodeAncestry } from "@/lib/tiptap/useNodeAncestry";
import { cn } from "@/lib/utils";

// Mirrors DocumentExperienceSection.tsx's old isSubstantiveEdit exactly
// — see its docstring for the full rationale (why "keep" actions and
// locked bullets never count, why the *live* text is compared rather
// than provenance.rewritten_text).
function isSubstantiveEdit(text: string, provenance: BulletProvenance | undefined): provenance is BulletProvenance {
  return (
    provenance != null &&
    !provenance.locked &&
    (provenance.action === "rewrite" || provenance.action === "enhance") &&
    text.trim() !== provenance.original_text.trim()
  );
}

const ARIA_LABEL_TEXT_MAX_LENGTH = 60;

// Phase 28 — folds a bullet's own text into its checkbox's aria-label
// (previously a bare "Include this bullet"/"Include this project
// heading", ambiguous once every bullet's checkbox lands in one shared
// gutter instead of sitting next to its own row's text) — truncated,
// since a bullet's text has no length limit and an aria-label doesn't
// need the whole thing to be useful.
function summarizeForAriaLabel(text: string): string {
  const trimmed = text.trim();
  if (trimmed.length <= ARIA_LABEL_TEXT_MAX_LENGTH) {
    return trimmed;
  }
  return `${trimmed.slice(0, ARIA_LABEL_TEXT_MAX_LENGTH)}…`;
}

// Phase 26 — an Experience bullet (or, when `kind === "subheading"`, a
// project heading — DocumentExperienceSection.tsx's old BulletRow
// convention: italic, no bullet marker). Unlike EntryHeadingNodeView, a
// bullet carries its own full attrs (`included`/`kind`/`evidence_id`/
// `locked`), so only sectionKey/entryId (from useNodeAncestry — no
// ambient context, see lib/tiptap/context.tsx's docstring) are needed
// beyond its own node. `cv-print-bullet` on the outer `<p>` matches
// PrintExperienceSection.tsx's own class on the equivalent element
// exactly.
//
// Post-29 fix: this line used to also carry `text-sm` — a real,
// confirmed WYSIWYG break, found while calibrating Phase 29's on-screen
// page-break guide against a real export. Neither `.cv-print-bullet`
// nor `.cv-print-entry` carry any font-size rule of their own
// (index.css only ever touches them for `break-inside: avoid`), and
// PrintExperienceSection.tsx/PrintSectionBlock.tsx — the components
// Playwright's `page.pdf()` actually screenshots (app/cv_pdf_playwright.py)
// — never applied `text-sm` on their own equivalent `<p>` either, so a
// bullet's *real* exported size was always the inherited base 16px/24px
// line-height, not this component's on-screen-only 14px/20px. That ~14%
// font-size (and compounding line-height) difference was enough, across
// a bullet-heavy Experience entry, to make the same content measurably
// taller in the real PDF than anything rendered on screen — the direct
// cause of the on-screen guide predicting a later, wrong break position
// than the real export (confirmed by extracting exact text positions
// from a real generated PDF and comparing). Removing it doesn't just
// fix the guide's math — the on-screen editor now visually shows what
// export has *always* actually produced, closing a gap that predates
// this phase (present since whichever pass first added `text-sm` here,
// never matched on the PrintExperienceSection.tsx side it was already
// documented above as mirroring "exactly").
//
// Excluded (`included: false`) is hidden on this node's own wrapper,
// independent of whatever its parent entry's `included` is — the same
// two independent layers (entry-level, bullet-level) Phase 24 already
// had via two separate `.filter()` calls. `<NodeViewContent>`'s own
// `contentEditable` toggle (not the outer wrapper's — see
// lib/tiptap/plugins.ts's docstring on why display:none alone isn't
// sufficient) is what actually matters for the caret-guard; the
// `hidden` class on the wrapper is what makes the drag handle/text
// disappear alongside it.
//
// Phase 28 — checkbox + Sparkles trigger both moved to DocumentGutter
// (components/tiptap/DocumentGutter.tsx); DocumentRow.tsx (which used to
// render checkbox+drag-handle+sparkles+text as one flex row) is gone —
// this row is now just the drag handle plus text, inlined directly since
// it's no longer shared with anything else. Registration here only gates
// on this bullet's *own* `included` (matching this row's own `hidden`
// class); whether an ancestor entry/section is also excluded is
// DocumentGutter's own concern, re-checked fresh against the live doc on
// every remeasure rather than trusted from this component's own render —
// see useGutterItem.ts's docstring for the real staleness bug that
// distinction fixes.
//
// Phase 28 (follow-up) — reported directly: the flex row's own `gap-2`
// between the handle and the text was shifting the bullet's own text
// right by the handle's width, the same "don't move the actual content"
// problem the checkbox/Sparkles relocation was supposed to solve, not
// something specific to them. The handle moved from a normal-flow flex
// child to `position: absolute` at gutterLayout.ts's HANDLE_LEFT_PX (into
// the page's own blank left margin, aligned with DocumentGutter's own
// checkbox/Sparkles cluster).
//
// Phase 31 (follow-up) restructured the chrome/content relationship
// entirely — reported directly: "Bubble menu doesn't appear in the
// experience bullets." Root cause, confirmed live against a real bullet:
// selecting text with a real double-click correctly produced a native
// browser Selection (`window.getSelection()` showed the right text), but
// ProseMirror's *own* `state.selection` never picked it up — it stayed
// (or fell back to) an `AllSelection` spanning the entire document, not
// a `TextSelection` over the clicked word, so `shouldShow` never saw a
// usable range. Selecting inside an *entryHeading* (a role's own title)
// worked correctly throughout — narrowing the difference to this
// component specifically. The previous version wrapped `<NodeViewContent>`
// inside one shared `contentEditable={false}` `<span>` alongside
// `DragHandle` and the bulletChar marker — chrome as an *ancestor* of
// the real content, not a sibling. `EntryNodeView.tsx`'s own chrome
// (Phase 27) already established the correct shape for this — a
// `contentEditable={false}` element as `<NodeViewContent>`'s *sibling*,
// never its wrapper — but that fix was originally understood as being
// about drag mechanics specifically (`stopEvent()`/`onDragStart`
// hijacking, see schema.ts's `TiptapEntryHeading` comment), not
// something that also matters for plain text selection; it turns out to
// be the same underlying rule either way: ProseMirror's own DOM↔position
// mapping (used for reading a native Selection back into document
// positions, not just drag/drop hit-testing) gets confused when a node's
// real editable content sits inside a `contentEditable={false}` ancestor
// within the node's own wrapper, not just when starting a drag.
//
// Fixed the same way EntryNodeView already had it: `group`/`relative`
// moved from the old inner `<span>` onto the outer `<p>`
// (`NodeViewWrapper`, a real block box immune to the inline-fragments-
// across-line-boxes problem the old forced-`block` span was working
// around in the first place — a `<p>` never needed that workaround) —
// `NodeViewWrapper` doesn't reliably forward a `ref` (it's a plain
// `React.FC`, not built with `forwardRef` — confirmed against
// `@tiptap/react`'s own type signature), so `anchorRef` stays on a small
// dedicated `<span>` instead, now holding *only* `DragHandle`, sibling
// to (not wrapping) `<NodeViewContent>` — mirrors EntryNodeView's own
// chrome div, which "only needs `group`... and `anchorRef`... no
// positioning of its own, so it collapses to zero height, which is
// fine: only its own `top`... is ever read." The bulletChar marker span
// is also now a sibling, with its own explicit `contentEditable={false}`
// (previously inherited from the now-removed wrapper). One accepted UX
// tradeoff, same one EntryNodeView's own docstring already accepts for
// entries: hovering the handle's own small chrome span still reveals it
// (via the outer `<p>`'s `group` class, which covers every descendant
// regardless of which sibling branch they're in — unlike EntryNodeView,
// this actually still covers the *whole row* including the text, since
// `group` lives on the row's own outer element here, not a child chrome
// div) — no regression here after all, just a structurally different
// route to the same "hover anywhere in the row reveals the handle"
// behavior.
export function BulletNodeView({ node, editor, getPos }: NodeViewProps) {
  const ctx = useDocumentEditorNodeViewContext();
  const { sectionKey, entryId } = useNodeAncestry({ editor, getPos });
  const included = node.attrs.included !== false;
  const isSubheading = node.attrs.kind === "subheading";
  const evidenceId = node.attrs.evidence_id as string | null;
  const provenance = evidenceId ? ctx.provenanceByEvidenceId.get(evidenceId) : undefined;
  const edited = isSubstantiveEdit(node.textContent, provenance);
  const bulletId = node.attrs.id as string;
  const anchorRef = useRef<HTMLSpanElement>(null);
  const [provenancePopoverOpen, setProvenancePopoverOpen] = useState(false);
  // Phase 31 (follow-up), reported directly from two screenshots: the
  // AI-edit provenance popover overlapped the bullet text it was
  // explaining, and clipped off-screen on a narrow viewport — both
  // symptoms of the same root cause. `sparkles` (below) is handed to
  // `useGutterItem`, and DocumentGutter.tsx renders it inside *its own*
  // overlay, positioned at the page's left margin — meaning Radix's
  // default anchor (the Popover's own trigger, the small Sparkles icon)
  // was a narrow point sitting in that margin, not the bullet row it was
  // meant to annotate; centering a fixed ~320px card on that point let
  // roughly half of it hang off whichever side had less room. Fixed by
  // giving the Popover an explicit *virtual* anchor (`Popover.Anchor`'s
  // own `virtualRef` prop — any object satisfying `getBoundingClientRect()`,
  // not necessarily a rendered child) pointing at the real bullet `<p>`
  // itself (`anchorRef.current`'s own closest `.cv-print-bullet`
  // ancestor — `anchorRef` already exists for `useGutterItem`'s
  // measurement, so this reuses it rather than adding a second ref).
  // `PopoverContent` then sizes itself to `var(--radix-popper-anchor-width)`
  // — a real CSS custom property Radix sets from that same anchor's own
  // measured width (confirmed directly in `@radix-ui/react-popper`'s own
  // source) — so the card exactly spans the bullet row's own width, i.e.
  // the full A4 page's content width, not a fixed size. `side="bottom"`
  // with Radix's own default collision avoidance flips to `"top"`
  // automatically when there's no room below — "strictly above or
  // below," never to the side, for free.
  //
  // A real, found-live gotcha: `@radix-ui/react-popover`'s own
  // `PopoverTrigger` (when no `Popover.Anchor` is rendered *yet*)
  // implicitly wraps itself in its own anchor registration on the
  // component's very first render — before the `hasCustomAnchor` context
  // flag `Popover.Anchor`'s own effect sets can propagate — and that
  // first registration is never retracted (`PopperAnchor`'s unmount
  // path only calls its registration callback when attaching a node,
  // never on detach). Reordering `Popover.Anchor` before `PopoverTrigger`
  // in JSX didn't help (same race, still loses). Sidestepped entirely by
  // not rendering `Popover.Anchor`'s sibling `PopoverTrigger` at all —
  // the Sparkles button below is a plain, manually-controlled trigger
  // (`provenancePopoverOpen` state + `onClick`), so there's no second
  // component ever competing to register itself as the anchor.
  const bulletAnchor = useRef<{ getBoundingClientRect: () => DOMRect }>({
    getBoundingClientRect: () => anchorRef.current?.closest(".cv-print-bullet")?.getBoundingClientRect() ?? new DOMRect(),
  });

  const summary = summarizeForAriaLabel(node.textContent);
  const baseLabel = isSubheading ? "Include this project heading" : "Include this bullet";
  // Phase 31 (follow-up) — see EntryHeadingNodeView.tsx's identical
  // comment: FormattingBubbleMenu's Align buttons wrote the attr
  // correctly, but nothing ever rendered it on screen.
  const alignment = (node.attrs.alignment as "left" | "center" | "right" | null) || undefined;

  // Only this bullet's *own* `included` gates registration here — whether
  // its ancestor entry/section is also excluded is DocumentGutter's own
  // concern (computeNodeAncestry, checked fresh on every remeasure — see
  // useGutterItem.ts's docstring for why that can't safely be decided at
  // this component's own render time).
  useGutterItem(
    `bullet:${bulletId}`,
    anchorRef,
    getPos,
    included
      ? {
          checkbox: {
            checked: true, // an invisible-in-the-gutter row is, by construction, always the included case — see the doc comment above
            onToggle: () => ctx.onToggleBullet(sectionKey, entryId as string, bulletId),
            ariaLabel: summary ? `${baseLabel}: ${summary}` : baseLabel,
          },
          sparkles: edited ? (
            <Popover open={provenancePopoverOpen} onOpenChange={setProvenancePopoverOpen}>
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                aria-label="AI-edited bullet — view original text and rationale"
                aria-haspopup="dialog"
                aria-expanded={provenancePopoverOpen}
                onClick={() => setProvenancePopoverOpen((current) => !current)}
              >
                <Sparkles />
              </Button>
              <PopoverAnchor virtualRef={bulletAnchor} />
              <PopoverContent
                side="bottom"
                align="center"
                collisionPadding={16}
                className="space-y-3 p-4"
                style={{ width: "var(--radix-popper-anchor-width)" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-medium text-muted-foreground uppercase">
                    {provenance?.action === "rewrite" ? "Rewritten" : "Enhanced"}
                  </p>
                  <PopoverClose asChild>
                    <Button type="button" variant="ghost" size="icon-xs" aria-label="Close">
                      <X />
                    </Button>
                  </PopoverClose>
                </div>
                <div className="rounded bg-muted p-2 text-sm text-muted-foreground">
                  <span className="font-medium text-foreground">Original: </span>
                  {provenance?.original_text}
                </div>
                {provenance?.rationale && <p className="text-sm">{provenance.rationale}</p>}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="w-full"
                  onClick={() =>
                    provenance && ctx.onRevertBullet(sectionKey, entryId as string, bulletId, provenance.original_text)
                  }
                >
                  Revert to original
                </Button>
              </PopoverContent>
            </Popover>
          ) : undefined,
        }
      : null,
  );

  return (
    <NodeViewWrapper
      as="p"
      // Post-30 — `cv-print-subheading` is inert on screen (index.css's
      // matching `break-after: avoid-page` rule is scoped to `@media
      // print`) but doubles as the exact DOM signal PageBreakGuide.tsx's
      // measureUnits reads to decide which bullet inside a multi-line
      // Experience entry, if any, also deserves its own `keepWithNext` —
      // the same class PrintExperienceSection.tsx adds for the real,
      // print-only CSS effect, so both stay driven by one shared marker
      // instead of two independently-maintained copies of "is this a
      // project subheading" (see that component's own comment on the
      // same class).
      //
      // Phase 31 (follow-up) — `group`/`relative` moved here from the old
      // inner chrome span (this file's own top-of-file comment has the
      // full story: fixing a real selection bug, not a styling
      // preference). `relative` gives `DragHandle` (still `position:
      // absolute`, unchanged) a stable anchor that can't fragment across
      // line boxes, the same guarantee the old forced-`block` span used
      // to provide, but for free — a `<p>` is already a block box.
      // `group` here covers the *whole row*, text included, so hovering
      // anywhere in the bullet still reveals the handle exactly as
      // before.
      className={cn(
        "group relative cv-print-bullet",
        isSubheading && "cv-print-subheading",
        !included && "hidden",
      )}
      style={{ textAlign: alignment }}
      // On-screen page-break-prediction fix (follow-up to Version 4,
      // Phase 4.9) — PageBreakGuide.tsx correlates a backend-reported
      // "this bullet id starts page N" back to this exact DOM node via
      // this attribute, now that page breaks are computed by the real
      // reportlab renderer (app/cv_pdf.py::compute_page_breaks) instead
      // of approximated from measuring this component's own on-screen
      // layout.
      data-bullet-id={bulletId}
    >
      {/* Phase 31 (follow-up) — a small, dedicated chrome span holding
          only DragHandle: a sibling of NodeViewContent now, never its
          wrapper (this file's own top-of-file comment explains why that
          distinction is the actual fix, not a refactor for its own
          sake). `contentEditable={false}` still matters here for the
          same drag-mechanics reason Phase 28 originally found (a plain
          `<span draggable>` inside a genuinely editable region is exactly
          the case browsers won't reliably start a native drag from) —
          that reasoning was correct, it just didn't need to extend to
          wrapping the real content too. `anchorRef` (DocumentGutter's own
          measurement point) stays here rather than moving to the outer
          `<p>` — `NodeViewWrapper` doesn't reliably forward a `ref` (a
          plain `React.FC`, not built with `forwardRef`) — mirrors
          EntryNodeView.tsx's own chrome div, which "collapses to zero
          height... only its own `top`... is ever read." */}
      <span ref={anchorRef} contentEditable={false}>
        <DragHandle
          ariaLabel={isSubheading ? "Drag to reorder this project heading" : "Drag to reorder this bullet"}
          className="absolute top-0"
          style={{ left: HANDLE_LEFT_PX }}
          onDragSelect={() => {
            const pos = getPos();
            if (typeof pos === "number") editor.commands.setNodeSelection(pos);
          }}
        />
      </span>
      {/* Post-29 fix — reported directly: the on-screen editor never
          rendered a bullet marker at all, while every real export
          (PrintExperienceSection.tsx's own `{bulletChar} {...}`) always
          has. A subheading (a project-name line grouping the bullets
          below it) gets no marker either way, matching that component's
          identical `bullet.kind === "subheading"` branch exactly. Plain
          text, not part of `NodeViewContent` — the one contentEditable
          region ProseMirror actually manages — so it's never
          selectable/editable/deletable as real document content, just a
          decorative prefix; `aria-hidden` keeps a screen reader from
          announcing a literal "dash" before every bullet, the same
          silent-marker experience a real CSS list bullet gives for free.
          Phase 31 (follow-up) — now a sibling of NodeViewContent rather
          than a child of the old chrome span, so it needs its own
          explicit `contentEditable={false}` (previously inherited). */}
      {!isSubheading && (
        <span aria-hidden="true" contentEditable={false}>
          {ctx.bulletChar}{" "}
        </span>
      )}
      <NodeViewContent<"span"> as="span" className={cn(isSubheading && "italic")} contentEditable={included} />
    </NodeViewWrapper>
  );
}
