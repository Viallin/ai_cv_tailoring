import { describe, expect, it } from "vitest";

import type { BulletProvenanceReport } from "@/api/models";
import { buildProvenanceByEvidenceId } from "./bulletProvenanceIndex";

describe("buildProvenanceByEvidenceId", () => {
  it("round-trips a report's bullets into an evidence_id-keyed map", () => {
    const report: BulletProvenanceReport = {
      bullets: [
        {
          evidence_id: "ev-1",
          original_text: "Led a team",
          rewritten_text: "Led a cross-functional team",
          action: "rewrite",
          locked: false,
          rationale: "Sharpen the leadership angle.",
        },
        {
          evidence_id: "ev-2",
          original_text: "Shipped a feature",
          rewritten_text: "Shipped a feature",
          action: "keep",
          locked: false,
        },
      ],
      unused_evidence: [],
    };

    const result = buildProvenanceByEvidenceId(report);

    expect(result.get("ev-1")?.rewritten_text).toBe("Led a cross-functional team");
    expect(result.get("ev-2")?.action).toBe("keep");
    expect(result.get("ev-3")).toBeUndefined();
    expect(result.size).toBe(2);
  });

  it("handles a null report gracefully", () => {
    const result = buildProvenanceByEvidenceId(null);

    expect(result.size).toBe(0);
  });
});
