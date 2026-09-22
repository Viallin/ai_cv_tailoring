import { Bold } from "@tiptap/extension-bold";
import { Italic } from "@tiptap/extension-italic";
import { Link } from "@tiptap/extension-link";
import { Text } from "@tiptap/extension-text";
import { Underline } from "@tiptap/extension-underline";
import { UndoRedo } from "@tiptap/extensions";
import { EditorContent, useEditor } from "@tiptap/react";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";

import type { ExportFormat } from "@/api/export";
import type { AssembledCV, BulletProvenanceReport } from "@/api/models";
import { A4Page } from "@/components/A4Page";
import { CvPrintHeader } from "@/components/CvPrintHeader";
import { DocumentGutter } from "@/components/tiptap/DocumentGutter";
import { FormattingBubbleMenu } from "@/components/tiptap/FormattingBubbleMenu";
import { LinkHoverCard } from "@/components/tiptap/LinkHoverCard";
import { PageBreakGuide } from "@/components/tiptap/PageBreakGuide";
import { buildProvenanceByEvidenceId } from "@/lib/bulletProvenanceIndex";
import { DEFAULT_TEMPLATE_ID, NO_TEMPLATE_ID, TEMPLATE_CHOICES } from "@/lib/cvTemplates";
import {
  addBullet,
  buildDocumentFromAssembledCv,
  toggleBulletIncluded,
  toggleEntryIncluded,
  toggleEntryPageBreak,
  toggleSectionIncluded,
  toggleSectionPageBreak,
  updateBulletText,
  updateEntryText,
  type DocumentModel,
} from "@/lib/structuredDocument";
import { documentModelToTiptapJSON, tiptapJSONToDocumentModel } from "@/lib/tiptap/converter";
import { DocumentEditorNodeViewProvider, type DocumentEditorNodeViewContextValue } from "@/lib/tiptap/context";
import { GutterRegistry } from "@/lib/tiptap/gutterRegistry";
import { DocumentGuards, DragAutoScroll, DragScopeFeedback } from "@/lib/tiptap/plugins";
import { DOCUMENT_NODE_EXTENSIONS } from "@/lib/tiptap/schema";

interface DocumentEditorProps {
  assembledCv: AssembledCV | null;
  // Phase 17b — the just-generated CV's bullet provenance (rationale +
  // original text per AI-edited bullet), joined against DocumentBlock.
  // evidence_id inside BulletNodeView. null/omitted before any CV has
  // been generated, same lifecycle as assembledCv; optional (like
  // onModelChange) so existing callers/tests that don't care about
  // provenance don't all need updating.
  provenance?: BulletProvenanceReport | null;
  // Phase 20 — when reopening a saved CVDraft, seed the editor with the
  // already-edited document instead of rebuilding fresh from assembledCv
  // (which would discard every toggle/reorder/edited-text change the
  // draft had). Consulted exactly once per mount (a ref guard, not a
  // dependency on this prop's own identity) — DraftScreen remounts
  // wholesale when navigating to a different draftId, so "once per
  // mount" is exactly "once per draft," and a stray identity change from
  // e.g. a background query refetch never resets in-progress edits.
  initialDocument?: DocumentModel | null;
  // Phase 16c: DocumentEditor still owns its DocumentModel state
  // internally exactly as before (not lifted/controlled) — this is just
  // a live mirror so CvWorkflowView's (now sole) export control can read
  // the current edited document without rewriting every mutation call
  // site below into a controlled-component shape.
  onModelChange?: (model: DocumentModel | null) => void;
  // Post-31 follow-up — forwarded straight to CvPrintHeader; see that
  // component's own prop docstring. Omitted here too (like onModelChange)
  // for callers that don't want an editable header at all.
  onHeadlineChange?: (value: string) => void;
  // Which of TEMPLATE_CHOICES to render the on-screen preview with.
  // Controlled by the caller (DraftScreen) rather than owned here — the
  // single Template picker now lives in ExportButton's Export card, so
  // this component and that one both read the same lifted state instead
  // of each keeping an independent, unsynced default.
  templateId?: string;
  // Post-29 fix — which export format PageBreakGuide should render a
  // guide *for*: the dashed lines are a real report of PDF pagination
  // specifically (asked from the backend's own reportlab renderer as of
  // the on-screen page-break-prediction fix — see PageBreakGuide.tsx's
  // own docstring) and would be actively misleading for "docx" (paginated
  // later by whatever opens it, an independent layout engine) or "md"
  // (never paginated at all). Defaults to "pdf" — same default
  // ExportButton's own local state used before this was lifted, so a
  // caller that doesn't pass this (existing tests) still gets today's
  // guide behavior.
  exportFormat?: ExportFormat;
}

// Phase 18b — the one thing outside this component (UnusedEvidencePanel,
// via CvWorkflowView's "Add to Role") that needs to mutate the
// DocumentModel this component deliberately keeps un-lifted (Phase 16c's
// own precedent). A ref-based imperative escape hatch, not a second
// controlled-state path — see the forwardRef below.
export interface DocumentEditorHandle {
  addBulletFromEvidence: (experienceId: string, text: string, evidenceId: string) => void;
  // Phase 24 — ExcludedContentPanel's "Restore" action, same escape
  // hatch as addBulletFromEvidence above. `bulletId` omitted restores a
  // whole entry (toggleEntryIncluded); present, it restores just that
  // one bullet (toggleBulletIncluded) — mirrors the two shapes
  // lib/excludedContent.ts's ExcludedContentItem can describe. Reuses
  // the existing toggle* functions rather than a new "set included"
  // mutation — restoring is always flipping a currently-false flag back
  // on, exactly what the toggle already does.
  restoreContent: (sectionKey: string, entryId: string, bulletId?: string) => void;
}

// Phase 26 — the Tiptap extension list: the custom section/entry/
// entryHeading/bullet nodes (lib/tiptap/schema.ts), the built-in Text
// leaf every textblock here needs, undo/redo (today's per-field inputs
// got free native undo — dropping it would regress "functionally
// equivalent to today"), and the guard plugins (id hygiene,
// excluded-content selection guard, Phase 27's drag-scope guard — see
// lib/tiptap/plugins.ts). No StarterKit — this is a fully custom,
// minimal schema; Phase 31 below adds exactly the four marks the
// BubbleMenu exposes, nothing StarterKit would otherwise bundle
// unasked (headings/lists/code/strike/etc.).
//
// Phase 27 — DragScopeFeedback (lib/tiptap/plugins.ts) draws the
// drop-position line during a native node drag (schema.ts's
// `draggable: true` on section/entry/bullet) and doubles as scope
// feedback — dimming out illegal drop targets, turning the line red
// with an explanatory tooltip over one — which is also why it replaces
// `@tiptap/extensions`' stock `Dropcursor` outright rather than running
// both (see that file's own comment). DragAutoScroll scrolls the window
// while a drag is held near the top/bottom edge, or via the mouse
// wheel — native browser handling for either doesn't fire on its own
// here, see that file's own comment for why.
//
// Phase 31 — Bold/Italic/Underline/Link marks, applying to every
// textblock (entryHeading/bullet) since neither restricts `marks` in
// its NodeSpec — no per-section gating at the schema level; scope is
// enforced by which sections actually get a BubbleMenu-driven UI to
// apply them (all of them, this phase — see development_plan.md).
// `openOnClick: false` — clicking into link text places a cursor for
// normal editing, same as any other text; navigation is LinkHoverCard's
// own explicit "Open" action, not a side effect of clicking. `target`/
// `rel` mirror the read-only renderers' own long-standing convention
// (textRuns.tsx, linkify.tsx) so an editor-applied link opens exactly
// like every other link this app already renders.
const EDITOR_EXTENSIONS = [
  ...DOCUMENT_NODE_EXTENSIONS,
  Text,
  UndoRedo,
  DocumentGuards,
  DragAutoScroll,
  DragScopeFeedback,
  Bold,
  Italic,
  Underline,
  Link.configure({
    openOnClick: false,
    // Deliberately off — a bare URL typed into a bullet only becomes a
    // real link mark via an explicit BubbleMenu action, not silently as
    // you type. The read-only renderers' own bare-URL detection
    // (linkifyText/linkifyContactLine) is a separate, render-time-only
    // mechanism for content this phase's UI never touched; it's
    // unaffected either way.
    autolink: false,
    HTMLAttributes: { target: "_blank", rel: "noreferrer" },
  }),
];

// Top-level orchestrator: owns the DocumentModel state (re-derived
// whenever a fresh assembledCv arrives — same re-sync-on-prop-change
// pattern ProfileHeader.tsx established in Phase 15b-i) and the one
// Tiptap editor every section/entry/bullet renders inside.
//
// Two separate write paths into the same DocumentModel mirror (Phase
// 26's design — see development_plan.md): free-text edits (typing) are
// owned entirely by the live ProseMirror EditorState, read back out via
// `onUpdate`; every other mutation (checkbox toggle, "+ Add Bullet",
// Sparkles "Revert to original", the imperative handle below) still
// runs through the existing pure helpers in structuredDocument.ts
// against the DocumentModel mirror, then gets pushed into the editor via
// `setContent(..., { emitUpdate: false })` — safe because these are all
// button-driven, with no live text cursor to preserve at that instant.
// This keeps structuredDocument.ts (and its existing tests) the sole
// owner of the toggle/exclude-cascade/add-bullet business rules; Tiptap
// only ever accepts externally-pushed content, never reimplements them.
export const DocumentEditor = forwardRef<DocumentEditorHandle, DocumentEditorProps>(function DocumentEditor(
  {
    assembledCv,
    provenance = null,
    initialDocument = null,
    onModelChange,
    onHeadlineChange,
    templateId = DEFAULT_TEMPLATE_ID,
    exportFormat = "pdf",
  },
  ref,
) {
  const [model, setModelState] = useState<DocumentModel | null>(null);
  const modelRef = useRef<DocumentModel | null>(null);
  modelRef.current = model;
  const hasSeededInitialDocument = useRef(false);
  // Phase 28 — one registry per DocumentEditor instance (not a module-level
  // singleton — see plugins.ts's own precedent for why a factory beats a
  // singleton whenever real per-instance mutable state is involved), fed
  // into DocumentGutter via useSyncExternalStore and into every NodeView
  // via the same top-level Context every other callback already rides.
  const gutterRegistry = useMemo(() => new GutterRegistry(), []);
  // Phase 29 — A4Page's own DOM node, handed to PageBreakGuide so it can
  // walk the page's real rendered DOM directly (see that file's own
  // docstring for why it needs the page element itself, not a shared
  // overlay coordinate space like DocumentGutter's). React state (set via
  // A4Page's `ref` callback below) rather than a plain `useRef` —
  // PageBreakGuide.tsx's own docstring has the full story: a `useRef`
  // here reads as null on that component's first measurement, every
  // time, since PageBreakGuide is A4Page's own *descendant* and refs on
  // an ancestor attach after a descendant's layout effects already ran.
  const [pageEl, setPageEl] = useState<HTMLDivElement | null>(null);

  const editor = useEditor(
    {
      extensions: EDITOR_EXTENSIONS,
      content: { type: "doc", content: [] },
      onUpdate: ({ editor: liveEditor }) => {
        setModelState(tiptapJSONToDocumentModel(liveEditor.getJSON()));
      },
    },
    [],
  );
  // Phase 27 (follow-up #5) — a real Chromium quirk, not a CSS bug:
  // `DragHandle.tsx`'s own icon starts at `opacity-0`, revealed via
  // `group-hover:opacity-100` (CSS-only, no JS) — and Chromium can skip
  // recomputing the *cursor* for a newly-interactive spot like that
  // unless the page has an actual `mousemove` listener registered
  // anywhere, in which case it reliably keeps recomputing cursor +
  // hit-test on every move. `cursor-grab` itself was never wrong
  // (confirmed live — correct element, correct computed `cursor: grab`,
  // correct `user-select: none`); the browser was just never repainting
  // it. Confirmed directly: a user-added diagnostic `mousemove` listener
  // (logging which element the pointer was over, nothing else)
  // incidentally fixed the cursor for the rest of that page load, and
  // it broke again on reload once that listener was gone. This is that
  // same fix, kept permanently instead of needing DevTools open — the
  // handler body doesn't need to do anything, only exist.
  //
  // Phase 28 (follow-up) — reported working again despite this listener
  // never having been touched or removed. The one real difference from
  // the diagnostic script that *did* fix it live: this registers with
  // `{ passive: true }`, the diagnostic didn't. If Chromium's own
  // recompute heuristic specifically keys off a listener that *could*
  // call `preventDefault()` (which a passive one, by its own contract,
  // never will), a passive listener might simply not count for it —
  // untested against the real quirk (still not something this
  // environment's tooling can observe), but free to try: the handler is
  // a true no-op either way, so dropping `passive` costs nothing
  // (no `preventDefault()` call to make passive-mode's optimization
  // relevant in the first place).
  useEffect(() => {
    const handler = () => {};
    window.addEventListener("mousemove", handler);
    return () => window.removeEventListener("mousemove", handler);
  }, []);

  // Pushes a non-keystroke mutation's result both into the DocumentModel
  // mirror and into the live editor (suppressing onUpdate — this isn't a
  // keystroke, there's no ProseMirror selection to preserve or feedback
  // loop to avoid beyond this one call).
  const applyModel = (next: DocumentModel | null) => {
    setModelState(next);
    if (editor && !editor.isDestroyed) {
      editor.commands.setContent(documentModelToTiptapJSON(next ?? { sections: [] }), { emitUpdate: false });
    }
  };

  useEffect(() => {
    if (initialDocument != null && !hasSeededInitialDocument.current) {
      hasSeededInitialDocument.current = true;
      applyModel(initialDocument);
      return;
    }
    if (initialDocument == null) {
      applyModel(assembledCv ? buildDocumentFromAssembledCv(assembledCv) : null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- initialDocument is intentionally consulted only once (see its prop docstring); every caller that omits it keeps the original assembledCv-driven rebuild
  }, [assembledCv, editor]);

  useEffect(() => {
    onModelChange?.(model);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onModelChange is a stable setter from CvWorkflowView
  }, [model]);

  useImperativeHandle(
    ref,
    () => ({
      addBulletFromEvidence: (experienceId, text, evidenceId) => {
        if (modelRef.current) {
          applyModel(addBullet(modelRef.current, "experience", experienceId, text, evidenceId));
        }
      },
      restoreContent: (sectionKey, entryId, bulletId) => {
        if (modelRef.current == null) {
          return;
        }
        applyModel(
          bulletId != null
            ? toggleBulletIncluded(modelRef.current, sectionKey, entryId, bulletId)
            : toggleEntryIncluded(modelRef.current, sectionKey, entryId),
        );
      },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- applyModel closes over `editor`, which is stable for the component's lifetime (useEditor's own deps array is `[]`)
    [],
  );

  const template = TEMPLATE_CHOICES.find((t) => t.id === templateId) ?? TEMPLATE_CHOICES[0];

  // Keyed on `provenance` and `template.bulletChar` (both stable-ish
  // props/derived values), not `buildProvenanceByEvidenceId(provenance)`
  // (a fresh Map every render) — NodeViews are mounted by ProseMirror's
  // own update cycle, not React's normal parent-render-drives-child-
  // render flow, so they only ever pick up a provenance/bulletChar
  // change via this Context value's *identity* changing; recomputing it
  // every render would defeat that (no reactivity gained) and
  // memoizing on the Map would never skip a recompute (a new Map every
  // render never `===` the last one) — see lib/tiptap/context.tsx's own
  // docstring on why Context, not editor.storage, is what makes this
  // reactive at all.
  const nodeViewContext: DocumentEditorNodeViewContextValue = useMemo(
    () => ({
      provenanceByEvidenceId: buildProvenanceByEvidenceId(provenance),
      summaryProvenance: provenance?.summary ?? undefined,
      bulletChar: template.bulletChar,
      onToggleSection: (sectionKey) => {
        if (modelRef.current) {
          applyModel(toggleSectionIncluded(modelRef.current, sectionKey));
        }
      },
      onToggleEntry: (sectionKey, entryId) => {
        if (modelRef.current) {
          applyModel(toggleEntryIncluded(modelRef.current, sectionKey, entryId));
        }
      },
      onToggleSectionPageBreak: (sectionKey) => {
        if (modelRef.current) {
          applyModel(toggleSectionPageBreak(modelRef.current, sectionKey));
        }
      },
      onToggleEntryPageBreak: (sectionKey, entryId) => {
        if (modelRef.current) {
          applyModel(toggleEntryPageBreak(modelRef.current, sectionKey, entryId));
        }
      },
      onToggleBullet: (sectionKey, entryId, bulletId) => {
        if (modelRef.current) {
          applyModel(toggleBulletIncluded(modelRef.current, sectionKey, entryId, bulletId));
        }
      },
      onAddBullet: (sectionKey, entryId) => {
        if (modelRef.current) {
          applyModel(addBullet(modelRef.current, sectionKey, entryId, ""));
        }
      },
      onRevertBullet: (sectionKey, entryId, bulletId, originalText) => {
        if (modelRef.current) {
          applyModel(updateBulletText(modelRef.current, sectionKey, entryId, bulletId, originalText));
        }
      },
      onRevertSummary: (originalText) => {
        if (modelRef.current) {
          applyModel(updateEntryText(modelRef.current, "summary", "summary", originalText));
        }
      },
      registerGutterItem: gutterRegistry.register,
      unregisterGutterItem: gutterRegistry.unregister,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- applyModel/modelRef/gutterRegistry are stable for the component's lifetime; provenance/template.bulletChar are the real dependencies
    [provenance, template.bulletChar],
  );

  if (model == null || editor == null) {
    return <p className="text-sm text-muted-foreground">Generate a CV to preview it here.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        {/* Phase 28 (follow-up) — DocumentGutter renders *inside* A4Page
            now (a plain extra child, like CvPrintHeader), not as a
            separate flex sibling reserving its own layout column — see
            gutterLayout.ts's own docstring for why that first version was
            reported as a mistake and reverted. A4Page goes back to
            self-centering via its own CSS (`margin: 0 auto`, index.css),
            same as PrintPreview.tsx already relies on. */}
        <A4Page ref={setPageEl} template={template}>
          {assembledCv && <CvPrintHeader cv={assembledCv} onHeadlineChange={onHeadlineChange} />}
          <DocumentGutter registry={gutterRegistry} editor={editor} />
          <DocumentEditorNodeViewProvider value={nodeViewContext}>
            <EditorContent editor={editor} />
            {/* Phase 31 — two independent floating surfaces, mutually
                exclusive by construction: FormattingBubbleMenu only shows
                for a real (non-empty) text selection, LinkHoverCard only
                for a collapsed cursor resting inside an existing link
                mark — see each component's own shouldShow. */}
            <FormattingBubbleMenu editor={editor} />
            <LinkHoverCard editor={editor} />
          </DocumentEditorNodeViewProvider>
          {/* Rendered last so its dotted lines paint over both the
              editor content and DocumentGutter's own overlay — harmless
              either way since every layer here but the real text is
              `pointer-events: none`. */}
          {assembledCv && (
            <PageBreakGuide
              pageEl={pageEl}
              editor={editor}
              registry={gutterRegistry}
              format={exportFormat}
              assembledCv={assembledCv}
              documentRef={modelRef}
              templateId={templateId === NO_TEMPLATE_ID ? null : templateId}
            />
          )}
        </A4Page>
      </div>
    </div>
  );
});
