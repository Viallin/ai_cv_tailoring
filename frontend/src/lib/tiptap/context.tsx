import { createContext, useContext } from "react";

import type { BulletProvenance, SummaryProvenance } from "@/api/models";
import type { GutterItem } from "@/lib/tiptap/gutterRegistry";

// Phase 26 — cross-cutting data every NodeView (components/tiptap/*)
// needs but can't get from its own `node.attrs`: `provenanceByEvidenceId`
// (for the Sparkles rationale popover + revert-to-original — see
// DocumentExperienceSection.tsx's old isSubstantiveEdit for the
// precedent this mirrors) and the toggle/add-bullet/revert callbacks
// that mutate the DocumentModel mirror DocumentEditor.tsx owns.
//
// React Context, not `editor.storage` (a plain mutable bag with no
// React reactivity — a NodeView reading it wouldn't re-render when
// `provenance` changes just because a React prop changed) or
// `extension.configure()` (captured once at editor-construction time,
// can't be hot-swapped without tearing the editor down and losing
// cursor/undo state).
//
// This context is deliberately *flat* — one Provider at the top, wrapping
// `<EditorContent>`, never re-provided/overridden by SectionNodeView or
// EntryNodeView for their own children. A first pass tried exactly that
// (an ambient `sectionKey`/`entryId` re-provided one nesting level at a
// time) and it doesn't work: Tiptap's ReactNodeViewRenderer mounts every
// NodeView in the document as its own portal into the single editor-wide
// React tree, so a NodeView nested inside another NodeView's contentDOM
// at the *DOM* level is not a descendant of that other NodeView's own
// *React component* subtree — a Context.Provider re-provided inside one
// NodeView is invisible to NodeViews nested under it. Found from a real
// failing test (see lib/tiptap/useNodeAncestry.ts's docstring for the
// full story) — `sectionKey`/`entryId`/`entryLocked` are computed per
// NodeView instead, from the live ProseMirror document via
// useNodeAncestry, and passed explicitly into these callbacks by every
// caller.
export interface DocumentEditorNodeViewContextValue {
  provenanceByEvidenceId: Map<string, BulletProvenance>;
  // The tailored summary's own before/after (BulletProvenanceReport.summary)
  // — undefined when there's no candidate original to compare against, or
  // the tailored summary came out identical to it (see build_report's own
  // docstring for why those two cases both mean "nothing to show here").
  // EntryNodeView reads this directly rather than joining by id — unlike
  // every bullet's evidence_id, there's exactly one summary entry per
  // document, so no lookup map is needed.
  summaryProvenance: SummaryProvenance | undefined;
  // Post-29 fix — the current template's bullet-prefix character (e.g.
  // "–" for Classic, "•" for Modern — see cvTemplates.ts's CvTemplate).
  // A real, reported WYSIWYG gap: BulletNodeView.tsx never rendered this
  // at all — the on-screen editor showed bare paragraphs where every
  // actual export (PrintExperienceSection.tsx's `{bulletChar} {...}`,
  // matching app/cv_pdf.py/cv_docx.py's own literal-character-prefix
  // convention, see Phase 16c's "not pixel-real gap" note) has always
  // shown a real bullet marker.
  bulletChar: string;
  onToggleSection: (sectionKey: string) => void;
  onToggleEntry: (sectionKey: string, entryId: string) => void;
  onToggleBullet: (sectionKey: string, entryId: string, bulletId: string) => void;
  // Phase 30 — manual pagination control (structuredDocument.ts's
  // toggleSectionPageBreak/toggleEntryPageBreak). Deliberately separate
  // from onToggleSection/onToggleEntry above (a different flag,
  // page_break_before, not included) rather than a shared "toggle any
  // boolean field" callback — keeps each NodeView's own call sites
  // reading as plainly as the include-toggle ones already do.
  onToggleSectionPageBreak: (sectionKey: string) => void;
  onToggleEntryPageBreak: (sectionKey: string, entryId: string) => void;
  onAddBullet: (sectionKey: string, entryId: string) => void;
  onRevertBullet: (sectionKey: string, entryId: string, bulletId: string, originalText: string) => void;
  onRevertSummary: (originalText: string) => void;
  // Phase 28 — bottom-up registration into the shared DocumentGutter
  // overlay (lib/tiptap/gutterRegistry.ts's own docstring explains why
  // this rides the existing top-level Context rather than needing a new
  // mechanism: only *re-providing* a nested Context fails across NodeView
  // boundaries, reading one already-top-level Provider's value doesn't).
  registerGutterItem: (item: GutterItem) => void;
  unregisterGutterItem: (id: string) => void;
}

const DocumentEditorNodeViewContext = createContext<DocumentEditorNodeViewContextValue | null>(null);

export const DocumentEditorNodeViewProvider = DocumentEditorNodeViewContext.Provider;

export function useDocumentEditorNodeViewContext(): DocumentEditorNodeViewContextValue {
  const ctx = useContext(DocumentEditorNodeViewContext);
  if (ctx == null) {
    throw new Error("useDocumentEditorNodeViewContext must be used within a DocumentEditorNodeViewProvider");
  }
  return ctx;
}
