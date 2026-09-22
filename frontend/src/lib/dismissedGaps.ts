import type { Gap, MatchResult } from "@/api/models";

// Phase 18: dismissing a gap is session-local, client-side state — there's
// nowhere server-side to persist it until Phase 20's CVDraft exists (see
// domain/models.py's Gap.status docstring). Every fresh MatchResult (a
// generate or a recheck) comes back with every Gap at status "open"; this
// re-stamps "skipped" onto whichever ones match a previously-dismissed
// requirement_text — the same stable key RequirementMatch/Gap already use
// elsewhere — before the result is stored/rendered.
export function applyDismissed(matchResult: MatchResult, dismissed: Set<string>): MatchResult {
  if (dismissed.size === 0) {
    return matchResult;
  }
  const gaps: Gap[] = (matchResult.gaps ?? []).map((gap) =>
    dismissed.has(gap.requirement_text) ? { ...gap, status: "skipped" } : gap,
  );
  return { ...matchResult, gaps };
}
