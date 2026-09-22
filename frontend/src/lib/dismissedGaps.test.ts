import { describe, expect, it } from "vitest";

import type { MatchResult } from "@/api/models";
import { applyDismissed } from "./dismissedGaps";

describe("applyDismissed", () => {
  it("stamps status: skipped onto a gap whose requirement_text is dismissed", () => {
    const matchResult: MatchResult = {
      matches: [],
      gaps: [
        { requirement_text: "AWS certification", description: "No cloud cert found.", severity: "high", status: "open" },
        { requirement_text: "Docker", description: "No Docker experience.", severity: "medium", status: "open" },
      ],
      missing_keywords: [],
    };

    const result = applyDismissed(matchResult, new Set(["AWS certification"]));

    expect(result.gaps![0].status).toBe("skipped");
    expect(result.gaps![1].status).toBe("open");
  });

  it("returns the original object unchanged when nothing is dismissed", () => {
    const matchResult: MatchResult = { matches: [], gaps: [], missing_keywords: [] };

    const result = applyDismissed(matchResult, new Set());

    expect(result).toBe(matchResult);
  });

  it("doesn't touch a gap that isn't dismissed", () => {
    const matchResult: MatchResult = {
      matches: [],
      gaps: [{ requirement_text: "Docker", description: "No Docker experience.", severity: "medium", status: "open" }],
      missing_keywords: [],
    };

    const result = applyDismissed(matchResult, new Set(["AWS certification"]));

    expect(result.gaps![0].status).toBe("open");
  });
});
