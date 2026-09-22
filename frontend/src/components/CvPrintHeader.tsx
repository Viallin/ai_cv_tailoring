import type { AssembledCV } from "@/api/models";

interface CvPrintHeaderProps {
  cv: AssembledCV;
  // Post-31 follow-up — when provided, the headline (role title) renders
  // as an inline text input instead of a plain paragraph, so a person can
  // edit it right where it appears in the on-screen preview
  // (DocumentEditor.tsx passes this; DraftScreen.tsx owns the actual
  // `assembled_cv.headline` state/autosave, same debounce as Vacancy
  // title). A first version of this feature put the edit control in a
  // separate form field above the CV instead — reported directly as
  // unintuitive ("let me edit it here", pointing at the header itself) —
  // this replaces that. Every other caller omits it and gets the
  // original read-only text — actual export never goes through this
  // component at all (app/cv_pdf.py/app/cv_docx.py build the exported
  // header server-side, straight from AssembledCV).
  onHeadlineChange?: (value: string) => void;
}

// On-screen A4-preview counterpart to CvHeader.tsx — same fields
// (name/headline), and still always driven by whatever AssembledCV this
// component is
// handed rather than owning its own edit state (`onHeadlineChange`
// forwards every keystroke straight back to the caller). `name` stays
// genuinely read-only here — only `headline` is ever user-edited, and
// only via the callback above, never as raw content inside
// `document.sections` (`PrintDocument` still has no header fields at
// all). Plain <h1> so it inherits the template's heading font/weight via
// index.css's .cv-a4-page h1 rule, same as every other heading on the
// printed page; the headline input matches via `font: inherit` since a
// bare <input> doesn't pick that up from its surroundings the way a <p>
// does.
//
// Contacts used to render here too, unconditionally — moved out into
// its own "Contacts" section (right after the header, before Summary;
// see app/cv_markdown.py's SECTION_TITLES and structuredDocument.ts's
// buildDocumentFromAssembledCv) at the user's request, so each contact
// can be independently included/excluded per application the same way
// every other section's entries already can, instead of always showing
// every contact with no way to drop an irrelevant one (e.g. "Work
// Authorization") for a given export. The Contacts section renders those
// entries now, with the same bare-domain-link handling this component
// used to do itself (see linkify.tsx's linkifyContactLine).
export function CvPrintHeader({ cv, onHeadlineChange }: CvPrintHeaderProps) {
  return (
    <header className="space-y-1">
      <h1>{cv.name}</h1>
      {onHeadlineChange ? (
        <textarea
          aria-label="Role title"
          value={cv.headline ?? ""}
          onChange={(event) => onHeadlineChange(event.target.value)}
          // A long headline must wrap the same way the read-only <p> below
          // wraps it (and the way the server-side export renders it) — a
          // single-line <input> can't do that, it just clips/scrolls the
          // overflow invisibly instead of moving it to a second line
          // (reported directly, from a screenshot: text cut off mid-word
          // at the pane edge). `rows={1}` plus `field-sizing-content`
          // keeps it one line tall for a short headline and grows with
          // wrapped lines for a long one, with no manual resize-on-input
          // handler needed. Enter is suppressed below since this is one
          // logical line of text that happens to wrap, not a multi-line
          // field — a literal newline here would look fine on screen but
          // desync from the exported single-line header.
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
            }
          }}
          rows={1}
          placeholder="Add a role title…"
          style={{ font: "inherit" }}
          // No border/ring even on focus, deliberately — every other piece
          // of editable CV text here is a chrome-less Tiptap
          // contentEditable (no box around it while typing either), and a
          // framed input reads as a distinct, alien kind of "form field"
          // sitting inside what's supposed to look like the CV itself
          // (reported directly, from a screenshot: "why does it have a
          // frame... other sections don't have this kind of visual aid").
          // Browsers give a plain <textarea> a default border, focus
          // outline, and resize handle unlike a <p> — all explicitly
          // zeroed out here, not just the outline.
          className="field-sizing-content -mx-1 w-full resize-none overflow-hidden rounded border-0 bg-transparent px-1 italic text-inherit outline-none placeholder:not-italic placeholder:text-muted-foreground"
        />
      ) : (
        cv.headline && <p className="italic">{cv.headline}</p>
      )}
    </header>
  );
}
