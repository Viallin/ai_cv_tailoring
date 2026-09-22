import type { Editor } from "@tiptap/react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";

import { fetchPageBreaks } from "@/api/export";
import type { ExportFormat } from "@/api/export";
import type { AssembledCV } from "@/api/models";
import type { GutterRegistry } from "@/lib/tiptap/gutterRegistry";
import type { DocumentModel } from "@/lib/structuredDocument";
import { cn } from "@/lib/utils";

interface PageBreakGuideProps {
  // The `.cv-a4-page` DOM node itself (or null before it's mounted) —
  // this component needs to *find* the real DOM elements a backend-
  // reported break's id refers to (data-section-key/data-entry-id/
  // data-bullet-id), not just share a coordinate space.
  //
  // A plain value, not a `RefObject` DocumentEditor.tsx hands down — a
  // real, live-measurement-confirmed bug: A4Page (the ref's owner) is
  // this component's own *ancestor*, and React attaches a host node's
  // ref bottom-up, alongside layout effects, in the same per-fiber
  // commit step — a descendant's own `useLayoutEffect` (this
  // component's own first `remeasure()` call) reliably fires *before*
  // an ancestor's ref gets attached, so `pageRef.current` read from a
  // component-mount-time layout effect this way is always null on the
  // very first render, every time. Lifting the node into DocumentEditor's
  // own React state (set via a callback ref on A4Page) instead of a
  // RefObject sidesteps the ordering problem entirely: the state update
  // that callback triggers schedules a real re-render, so this component
  // picks up the real node on its next pass regardless of commit order.
  pageEl: HTMLDivElement | null;
  editor: Editor;
  // The same registry DocumentGutter.tsx reads (DocumentEditor.tsx hands
  // both the one instance) — see the `useSyncExternalStore` call below
  // for why this, not `editor.on("update")` alone, is a real remeasure
  // trigger here too (a node register/unregister call is a *structural*
  // edit `editor.on("update")` also fires for, but registering it
  // separately keeps this component's trigger list identical to
  // DocumentGutter.tsx's own, rather than assuming one implies the other).
  registry: GutterRegistry;
  // Post-29 fix — which export format is currently selected (DraftScreen,
  // lifted the same way templateId already was). The dashed-line guide
  // below is only ever a claim about *PDF* pagination — DOCX is
  // paginated later, by whatever opens it (Word/LibreOffice/Google
  // Docs), using that program's own independent text-layout engine
  // (python-docx never computes page breaks at all), so there is no
  // "real DOCX break position" to report here, live or otherwise. A
  // plain `.md` export isn't paginated at all, ever. Showing dashed
  // lines for either would be confidently wrong rather than merely
  // approximate, so this format switches to a plain disclaimer (docx)
  // or nothing (md) instead of asking the backend at all.
  format: ExportFormat;
  // The three things POST /export/page-breaks needs, mirroring
  // ExportRequest's own shape (api/routes/export.py) — assembledCv/
  // templateId are plain props (rarely change mid-edit); documentRef is
  // a ref, not a prop, specifically so *every* keystroke doesn't need to
  // flow through this component's own props/re-render cycle — DocumentEditor.tsx
  // already keeps `modelRef.current` in sync with the live editor on
  // every update (see that component's own docstring), so reading it
  // fresh inside the debounced fetch below is simpler and cheaper than
  // adding a second, parallel prop-threading path for the same value.
  assembledCv: AssembledCV;
  documentRef: React.RefObject<DocumentModel | null>;
  templateId: string | null;
}

// Version 4, follow-up to Phase 4.9 — asks the real backend renderer
// where pages will actually break (POST /export/page-breaks,
// app/cv_pdf.py::compute_page_breaks), debounced on every edit, rather
// than approximating from the live browser DOM the way this component
// used to (Phase 29). That DOM-measurement approach was only ever valid
// while templated PDF export was itself a Playwright screenshot of this
// exact on-screen render — Phase 4.9 replaced that with a genuinely
// separate, browser-free reportlab renderer using different fonts
// (DejaVu vs. the on-screen preview's Geist/Georgia), so measuring the
// DOM here started measuring the wrong thing entirely, for every export,
// not just Cyrillic ones (reported directly, from real live testing —
// this rewrite is that fix).
//
// Rendered as a sibling overlay inside `.cv-a4-page`,
// `position: absolute; inset: 0`, `pointer-events: none` throughout —
// same shape as DocumentGutter.tsx (Phase 28), purely decorative, never
// intercepts a click/selection meant for the real editor content
// underneath.
//
// Deliberately simplified from the old DOM-measurement version in one
// way: it no longer distinguishes a *manual* page_break_before break
// (solid line, "manual" label) from a predicted one (dashed) — every
// break renders the same dashed style now. The backend has everything
// needed to restore that distinction (whether a PageBreak flowable
// immediately preceded the tagged element) if it's missed; left out
// here to keep this rewrite's scope to the actual reported bug, not
// bundle in an unrelated nicety.
const DEBOUNCE_MS = 400;

// A backend-reported "line" id can belong to either an entry or a
// bullet — they're never ambiguous in practice (both come from the same
// globally-unique id space the frontend generates), so one combined
// selector avoids needing the backend to also tell us which of the two
// it is.
function findBreakElement(pageEl: HTMLElement, kind: string, elementId: string): HTMLElement | null {
  const escaped = CSS.escape(elementId);
  if (kind === "section") {
    return pageEl.querySelector<HTMLElement>(`[data-section-key="${escaped}"]`);
  }
  return pageEl.querySelector<HTMLElement>(`[data-entry-id="${escaped}"], [data-bullet-id="${escaped}"]`);
}

interface PositionedBreak {
  top: number;
  page: number;
}

export function PageBreakGuide({ pageEl, editor, registry, format, assembledCv, documentRef, templateId }: PageBreakGuideProps) {
  const [positioned, setPositioned] = useState<PositionedBreak[]>([]);
  const showRealGuide = format === "pdf";
  // See this file's own docstring on `registry` for why this, alongside
  // `editor.on("update"/"selectionUpdate")` below, is a real trigger
  // here too, not just DocumentGutter.tsx's own concern.
  const items = useSyncExternalStore(registry.subscribe, registry.getSnapshot);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Guards against a slower *earlier* request's response landing after a
  // faster *later* one already did — without this, rapid edits could
  // flicker the guide back to a stale position right after a fresh,
  // correct one was drawn.
  const requestIdRef = useRef(0);

  const remeasure = useCallback(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    if (!pageEl || !showRealGuide) {
      setPositioned([]);
      return;
    }
    debounceRef.current = setTimeout(() => {
      const document = documentRef.current;
      if (!document) {
        return;
      }
      const requestId = ++requestIdRef.current;
      fetchPageBreaks(assembledCv, document, templateId)
        .then((breaks) => {
          if (requestId !== requestIdRef.current || !pageEl) {
            return; // superseded by a newer edit, or unmounted mid-flight
          }
          const pageRect = pageEl.getBoundingClientRect();
          const next: PositionedBreak[] = [];
          for (const b of breaks) {
            const el = findBreakElement(pageEl, b.kind, b.element_id);
            if (!el) {
              continue; // e.g. a legacy-grouped-section line the backend can't attribute an id to (see compute_page_breaks's own docstring) — not expected to happen for a kind:"section"/reported entry/bullet id, but never fatal either way
            }
            const rect = el.getBoundingClientRect();
            next.push({ top: rect.top - pageRect.top, page: b.page });
          }
          setPositioned(next);
        })
        .catch(() => {
          // A network hiccup on this purely decorative, best-effort
          // feature shouldn't surface as a toast/error — leave whatever
          // was last successfully drawn in place rather than clearing it.
        });
    }, DEBOUNCE_MS);
  }, [pageEl, showRealGuide, assembledCv, documentRef, templateId]);

  useLayoutEffect(() => {
    remeasure();
  }, [items, remeasure]);

  useEffect(() => {
    editor.on("update", remeasure);
    editor.on("selectionUpdate", remeasure);
    return () => {
      editor.off("update", remeasure);
      editor.off("selectionUpdate", remeasure);
    };
  }, [editor, remeasure]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, []);

  if (!showRealGuide) {
    // "md" gets nothing at all — a plain-text export was never
    // paginated to begin with, so even a disclaimer would imply a
    // concept that doesn't apply. "docx" gets an honest disclaimer
    // instead of dashed lines this component has no way to place
    // accurately (see the `format` prop's own docstring).
    // marginTop: 0 — see the docstring on the real-guide return below;
    // this branch is exactly as much a non-first child of `.cv-a4-page`
    // as that one is, so it needs the identical cancellation even though
    // it isn't position-critical here (a disclaimer, not a measured
    // line) — left uncancelled it would just render 24px lower than
    // `top-2` actually asks for.
    return format === "docx" ? (
      <div
        className="pointer-events-none absolute top-2 right-2 max-w-40 text-right"
        style={{ marginTop: 0 }}
        aria-hidden="true"
      >
        <span className="bg-white px-1 text-[10px] leading-tight tracking-wide text-black/45">
          Page breaks are approximate for Word — the exact split depends on what opens it.
        </span>
      </div>
    ) : null;
  }

  return (
    // Post-29 fix #5 — reported directly, then confirmed via a precise
    // live measurement (comparing this overlay's own rendered
    // `getBoundingClientRect()` against `.cv-a4-page`'s): every line
    // rendered a real, consistent 24px *below* its own computed
    // position — not a legibility issue, an actual coordinate-frame bug.
    // `.cv-a4-page > * + *` (index.css) gives every child but the
    // *first* a `margin-top: 1.5rem`, and this overlay is not that first
    // child — left uncancelled, that stray margin shifts this whole
    // overlay, and every line positioned inside it via `top`, 24px below
    // the frame those positions were actually measured against.
    // `DocumentGutter.tsx` hit this identical pitfall first (Phase 28)
    // and already cancels it on its own overlay for exactly this reason
    // — `marginTop: 0` here is that same cancellation.
    <div className="pointer-events-none absolute inset-0" style={{ marginTop: 0 }} aria-hidden="true">
      {positioned.map(({ top, page }, index) => (
        // Post-29 fix #4 — reported directly, then confirmed with a live
        // diagnostic: a bare 1px dashed line sitting flush against the
        // next page's first heading read as genuinely ambiguous —
        // nothing distinguished "this line separates the two" from
        // "this line belongs to the heading below it." The label sits
        // *below* the line (not above it) with a ↓ and more visual
        // weight so reading direction alone disambiguates it.
        // Post-29 fix #6 — reported directly: `left-2` put the label
        // right where DocumentGutter's own checkbox/drag-handle/Sparkles
        // cluster lives — `right-2` instead; nothing else on this page
        // ever renders chrome on the right.
        <div key={index} className="absolute right-0 left-0 border-t-2 border-dashed border-black/30" style={{ top }}>
          <span className={cn("absolute top-1 right-2 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide uppercase shadow-sm", "bg-white text-black/60")}>
            ↓ Page {page}
          </span>
        </div>
      ))}
    </div>
  );
}
