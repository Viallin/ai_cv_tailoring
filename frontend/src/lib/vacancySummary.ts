import type { MatchResult } from "@/api/models";

// Whether one of a Vacancy's top-level `keywords` counts as "covered" by
// the candidate — i.e. worth highlighting in JobDescriptionSummary's Hard
// Skills row. Reuses `matchResult.missing_keywords` rather than a second,
// ad-hoc check: the Matching stage (03_cv_jd_matcher_v1.md) already scans
// every job-wide keyword against Evidence and the candidate's Skills/
// Technologies/Languages/Certifications lists and reports exactly the ones
// it found nowhere — see MatchResult.missing_keywords's own docstring.
// Piggybacking on that keeps "what you have" (this) and "what's missing"
// (GapsPanel's own missing-keywords line) provably in sync, and needs no
// backend/LLM schema change of its own — see JobDescriptionSummary.tsx's
// docstring for why this stayed frontend-only. Defaults to "not covered"
// when there's no match result yet (nothing regenerated/checked this
// session) rather than assuming coverage — an unhighlighted chip is a
// silent "unknown," never a false claim of a match.
//
// Case-insensitive on purpose — verified live against a real seeded draft
// (candidate 595187d6, Mob Control JD) where `missing_keywords` echoed a
// job-wide keyword back with different casing ("4X games" vs. the
// top-level list's "4X Games", "Visuals" vs. "visuals"): the Matching
// stage (03_cv_jd_matcher_v1.md) copies keyword text loosely, not a
// guaranteed-identical id, so an exact-string check silently marked those
// as "covered" — a false claim of a match. Deliberately stops at case
// normalization rather than fuzzy/substring matching (e.g. "engineers" vs.
// "Engineering") — real wording drift like that is a JD-parsing artifact
// (02_jd_parser_v1.md's Title-Case-keywords rule doesn't yet cover the
// keywords `missing_keywords` itself echoes), not something safe to paper
// over client-side without risking the opposite mistake, a false "covered".
export function isKeywordCovered(keyword: string, matchResult: MatchResult | null): boolean {
  if (matchResult == null) {
    return false;
  }
  const missing = new Set((matchResult.missing_keywords ?? []).map((entry) => entry.toLowerCase()));
  return !missing.has(keyword.toLowerCase());
}
