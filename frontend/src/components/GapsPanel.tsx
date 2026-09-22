import type { Gap, MatchResult } from "@/api/models";
import { Button } from "@/components/ui/button";

// Read-only, never exported — ports ui/main_window.py's _gaps_html
// field-for-field (docs/phase_8_wireframes_spec.md's Phase 8.2 spec):
// high/medium gaps shown individually (high first), a colored severity
// tag, an indented suggested_action line if present; low-severity gaps
// collapse into one trailing count line; a trailing missing-keywords line
// if any. Real JSX, not dangerouslySetInnerHTML — there's no reason to
// route through an HTML string the way a QLabel required.
const SEVERITY_ORDER: Record<Gap["severity"], number> = { high: 0, medium: 1, low: 2 };

interface GapsPanelProps {
  matchResult: MatchResult | null;
  // Phase 18 — omitted entirely before a CV has been generated (no
  // dismiss affordance makes sense with no gaps yet); CvWorkflowView wires
  // this to a session-local Set<requirement_text> (lib/dismissedGaps.ts).
  onDismiss?: (requirementText: string) => void;
}

export function GapsPanel({ matchResult, onDismiss }: GapsPanelProps) {
  if (matchResult == null) {
    return null;
  }

  const gaps = matchResult.gaps ?? [];
  const missingKeywords = matchResult.missing_keywords ?? [];
  const skillsToAdd = matchResult.skills_to_add ?? [];

  if (gaps.length === 0 && missingKeywords.length === 0 && skillsToAdd.length === 0) {
    return <p className="text-sm">No notable gaps found for this vacancy.</p>;
  }

  // Low-severity gaps never show individually (dismissed or not — they're
  // already collapsed), so "dismissed" only tracks the ones that would
  // otherwise be shown.
  const nonLow = gaps.filter((gap) => gap.severity === "high" || gap.severity === "medium");
  const shown = nonLow
    .filter((gap) => gap.status !== "skipped")
    .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);
  const dismissedCount = nonLow.filter((gap) => gap.status === "skipped").length;
  const lowCount = gaps.filter((gap) => gap.severity === "low").length;

  return (
    <div className="space-y-2 text-sm">
      {shown.map((gap, index) => (
        <div key={index} className="space-y-1.5 rounded-lg border bg-muted/40 p-3">
          <span
            className={
              gap.severity === "high" ? "font-bold text-[#e05252]" : "font-bold text-[#d9a441]"
            }
          >
            {gap.severity === "high" ? "HIGH" : "MED"}
          </span>
          <p>
            {gap.description} (for: {gap.requirement_text})
          </p>
          {gap.suggested_action && <p className="text-xs text-gray-500">→ {gap.suggested_action}</p>}
          {onDismiss && (
            <Button
              type="button"
              variant="ghost"
              size="xs"
              className="-ml-2 text-muted-foreground"
              onClick={() => onDismiss(gap.requirement_text)}
            >
              Dismiss
            </Button>
          )}
        </div>
      ))}
      {dismissedCount > 0 && <p className="text-gray-500">+ {dismissedCount} dismissed</p>}
      {lowCount > 0 && (
        <p className="text-gray-500">+ {lowCount} more, low priority · collapsed</p>
      )}
      {missingKeywords.length > 0 && (
        <p className="text-gray-500">Missing keywords: {missingKeywords.join(", ")}</p>
      )}
      {skillsToAdd.length > 0 && (
        <p className="text-gray-500">
          Already backed by your experience — add to your Skills list:{" "}
          {skillsToAdd.map((item) => item.keyword).join(", ")}
        </p>
      )}
    </div>
  );
}
