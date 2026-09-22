import { describe, expect, it } from "vitest";

import type { Evidence, Experience } from "@/api/models";
import { buildEvidenceById, describeEvidenceSource } from "./evidenceIndex";

describe("buildEvidenceById", () => {
  it("round-trips a list into an id-keyed map", () => {
    const evidence: Evidence[] = [
      { id: "ev-1", text: "Led a team", locked: false },
      { id: "ev-2", text: "Shipped a feature", locked: false },
    ];

    const result = buildEvidenceById(evidence);

    expect(result.get("ev-1")).toEqual({ id: "ev-1", text: "Led a team", locked: false });
    expect(result.get("ev-2")).toEqual({ id: "ev-2", text: "Shipped a feature", locked: false });
    expect(result.size).toBe(2);
  });
});

describe("describeEvidenceSource", () => {
  const experience: Experience[] = [
    {
      id: "exp-1",
      company: "Acme",
      position: "Engineer",
      is_gap: false,
      projects: [{ id: "proj-1", name: "Internal tool", achievements: [], responsibilities: [] }],
    },
  ];

  it("joins company, position, and project when the evidence is tied to a project", () => {
    const evidence: Evidence = {
      id: "ev-1",
      text: "Built the API",
      experience_id: "exp-1",
      experience_project_id: "proj-1",
      locked: false,
    };

    expect(describeEvidenceSource(evidence, experience)).toBe("Acme, Engineer, Internal tool");
  });

  it("omits the project when the evidence is role-level only", () => {
    const evidence: Evidence = { id: "ev-1", text: "Led the team", experience_id: "exp-1", locked: false };

    expect(describeEvidenceSource(evidence, experience)).toBe("Acme, Engineer");
  });

  it("returns null when the evidence has no experience_id at all", () => {
    const evidence: Evidence = { id: "ev-1", text: "Acted as feature owner", locked: false };

    expect(describeEvidenceSource(evidence, experience)).toBeNull();
  });

  it("returns null when the referenced experience_id can't be found", () => {
    const evidence: Evidence = { id: "ev-1", text: "Did a thing", experience_id: "missing", locked: false };

    expect(describeEvidenceSource(evidence, experience)).toBeNull();
  });
});
