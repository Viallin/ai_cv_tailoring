import { Link } from "react-router-dom";

import { useCandidates } from "@/api/candidates";
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger } from "@/components/ui/select";
import { languageLabel } from "@/lib/sections";
import { cn } from "@/lib/utils";

interface CandidatePickerProps {
  selectedId: string | null;
  onSelect: (id: string) => void;
  disabled?: boolean;
  className?: string;
}

// Version 4, Phase 4.6 (4.1) — a sentinel Select value, not a real
// candidate id, so callers (currently just CandidateWorkflowLayout.tsx's
// header dropdown) can branch on it to navigate("/") — "New Candidate"
// reachable from any candidate-scoped screen, not just the start screen.
export const NEW_CANDIDATE_OPTION = "__new_candidate__";

// Post-4.10 nav redesign — inlined directly into
// CandidateWorkflowLayout.tsx's breadcrumb as the "current profile" crumb
// (replacing a plain-text name there), instead of shown as its own
// labeled field above the breadcrumb — reported directly: showing the
// name twice (once as a crumb, once as this field's value) read as
// redundant.
//
// Split into two controls, not one: the label itself is a plain Link to
// this profile's Profile screen, and a separate small chevron opens the
// Select to switch profiles. A single combined control was tried first —
// clicking the current profile's own row in the dropdown to "go to
// Profile" — but Radix Select's onValueChange never fires for reselecting
// the value it's already showing, so that silently did nothing. Splitting
// the two actions is what actually makes "back to profile" one click
// again after the Profile/CV export tabs were removed.
export function CandidatePicker({ selectedId, onSelect, disabled, className }: CandidatePickerProps) {
  const { data: candidates, isLoading } = useCandidates();
  const current = selectedId ? candidates?.find((candidate) => candidate.id === selectedId) : undefined;
  const label = current
    ? `${current.name} — ${current.headline ?? "—"} — ${languageLabel(current.language)}`
    : "…";

  return (
    <span className={cn("inline-flex items-center gap-0.5", className)}>
      {selectedId ? (
        <Link
          to={`/candidates/${selectedId}/profile`}
          className="font-medium text-foreground hover:underline"
        >
          {label}
        </Link>
      ) : (
        <span className="font-medium text-muted-foreground">{isLoading ? "Loading…" : label}</span>
      )}
      <Select value={selectedId ?? undefined} onValueChange={onSelect} disabled={disabled ?? isLoading}>
        <SelectTrigger
          aria-label="Switch profile"
          size="sm"
          className="w-fit gap-0 border-transparent bg-transparent p-1 hover:border-input hover:bg-muted data-[state=open]:border-input data-[state=open]:bg-muted"
        />
        {/* "popper" position, not the default "item-aligned" — item-aligned
            positions the content by measuring a SelectValue node inside the
            trigger to line the selected item up under it, and this
            trigger has no SelectValue (icon-only, see above). Without a
            SelectValue to measure, that positioning silently produced a
            content node stuck in normal document flow near the bottom of
            the page instead of a floating dropdown — reported directly
            ("nothing happens" when clicking the chevron, when really the
            menu had opened, just thousands of pixels down the page).
            "popper" anchors to the trigger element itself instead, which
            works regardless of what's inside it. */}
        <SelectContent position="popper" align="start">
          {candidates?.map((candidate) => (
            <SelectItem key={candidate.id} value={candidate.id}>
              {candidate.name} — {candidate.headline ?? "—"} — {languageLabel(candidate.language)}
            </SelectItem>
          ))}
          <SelectSeparator />
          <SelectItem value={NEW_CANDIDATE_OPTION}>+ New Candidate</SelectItem>
        </SelectContent>
      </Select>
    </span>
  );
}
