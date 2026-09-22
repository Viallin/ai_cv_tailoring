import type { AdvisoryChip } from "@/lib/advisories";

interface AdvisoryChipsProps {
  chips: AdvisoryChip[];
}

// Read-only, no actions — same "informational, never exported" treatment
// as GapsPanel/UnusedEvidencePanel.
//
// Phase 31 (follow-up) — moved out of the CV column (below the A4 page)
// into the right-hand action rail, in its own Card, matching GapsPanel/
// ExcludedContentPanel/UnusedEvidencePanel's own shape exactly — reported
// directly that this read as much more noticeable sitting there, below
// Gaps, than as an unlabeled row of pills under the page. `chips` is now
// computed once in DraftScreen.tsx (`buildAdvisoryChips`) rather than
// here from a raw `document` prop, the same "Card is owned by the
// caller, this component is just the content" split every sibling panel
// already uses — DraftScreen.tsx only renders this Card at all when
// there's something to show (an empty "Worth a look" card with nothing
// under it isn't worth the vertical space an always-visible one costs
// on every other draft), so this component can assume `chips` is
// non-empty and doesn't need its own null/empty handling anymore.
//
// Second follow-up, reported directly from a screenshot: each item here
// still looked visually distinct from its new siblings — a fully-rounded
// pill with no background fill, next to GapsPanel's/ExcludedContentPanel's/
// UnusedEvidencePanel's own `rounded-lg border bg-muted/40 p-3` item
// boxes right above and below it in the same rail. `rounded-full`/no-fill
// was a leftover from when this rendered as a compact inline row under
// the page, not a deliberate choice for its new context — now matches
// that exact class string, one item per line (`space-y-2`, not
// `flex-wrap`) rather than a wrapped row of badges, the same list shape
// its neighbors use.
export function AdvisoryChips({ chips }: AdvisoryChipsProps) {
  return (
    <ul className="space-y-2 text-sm">
      {chips.map((chip) => (
        <li key={chip.id} className="rounded-lg border bg-muted/40 p-3">
          {chip.message}
        </li>
      ))}
    </ul>
  );
}
