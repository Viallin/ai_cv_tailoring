import { describe, expect, it } from "vitest";

import type { MatchResult } from "@/api/models";
import { isKeywordCovered } from "./vacancySummary";

describe("isKeywordCovered", () => {
  it("treats a keyword as not covered when there's no match result yet", () => {
    // No highlighting rather than a false "you have this" claim.
    expect(isKeywordCovered("A/B Testing", null)).toBe(false);
  });

  it("treats a keyword as covered when it isn't in missing_keywords", () => {
    const matchResult: MatchResult = { matches: [], gaps: [], missing_keywords: ["Roadmapping"] };
    expect(isKeywordCovered("A/B Testing", matchResult)).toBe(true);
  });

  it("treats a keyword as not covered when it is in missing_keywords", () => {
    const matchResult: MatchResult = { matches: [], gaps: [], missing_keywords: ["Roadmapping"] };
    expect(isKeywordCovered("Roadmapping", matchResult)).toBe(false);
  });

  it("matches case-insensitively — missing_keywords doesn't always echo the same casing", () => {
    const matchResult: MatchResult = { matches: [], gaps: [], missing_keywords: ["4X games"] };
    expect(isKeywordCovered("4X Games", matchResult)).toBe(false);
  });
});
