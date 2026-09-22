import { describe, expect, it } from "vitest";

import {
  collectEditedBulletText,
  collectExcludedEvidenceIds,
  collectManualBulletText,
  collectUsedEvidenceIds,
} from "./documentEvidence";
import type { DocumentModel } from "./structuredDocument";

function makeDocument(overrides: Partial<DocumentModel["sections"][number]> = {}): DocumentModel {
  return {
    sections: [
      {
        key: "experience",
        title: "Experience",
        included: true,
        entries: [
          {
            id: "exp-1",
            text: "Engineer — Acme",
            included: true,
            bullets: [
              { id: "exp-1-bullet-0", text: "Shipped v1", included: true, evidence_id: "ev-1" },
              { id: "exp-1-bullet-1", text: "Excluded bullet", included: false, evidence_id: "ev-2" },
              { id: "exp-1-bullet-2", text: "Hand-typed, no link", included: false },
            ],
          },
        ],
        ...overrides,
      },
    ],
  };
}

describe("collectExcludedEvidenceIds", () => {
  it("collects the evidenceId of an excluded bullet only", () => {
    const result = collectExcludedEvidenceIds(makeDocument());

    expect(result).toEqual(["ev-2"]);
  });

  it("ignores a hand-typed bullet with no evidenceId, even when excluded", () => {
    // Covered by the fixture's exp-1-bullet-2 above — asserted via the
    // exact-match check in the first test, this test just documents intent.
    const result = collectExcludedEvidenceIds(makeDocument());

    expect(result).not.toContain(undefined);
    expect(result.length).toBe(1);
  });

  it("excludes every bullet's evidence when the whole role entry is excluded", () => {
    const document = makeDocument();
    document.sections[0].entries[0].included = false;

    const result = collectExcludedEvidenceIds(document);

    expect(result.sort()).toEqual(["ev-1", "ev-2"]);
  });

  it("excludes every bullet's evidence when the whole Experience section is excluded", () => {
    const document = makeDocument({ included: false });

    const result = collectExcludedEvidenceIds(document);

    expect(result.sort()).toEqual(["ev-1", "ev-2"]);
  });

  it("returns an empty list when there's no experience section at all", () => {
    const result = collectExcludedEvidenceIds({ sections: [] });

    expect(result).toEqual([]);
  });

  it("returns an empty list when nothing is excluded", () => {
    const document = makeDocument();
    document.sections[0].entries[0].bullets![1].included = true;
    document.sections[0].entries[0].bullets![2].included = true;

    const result = collectExcludedEvidenceIds(document);

    expect(result).toEqual([]);
  });
});

describe("collectEditedBulletText", () => {
  it("maps every evidence-linked bullet's evidence_id to its current text, regardless of included state", () => {
    const result = collectEditedBulletText(makeDocument());

    expect(result).toEqual({ "ev-1": "Shipped v1", "ev-2": "Excluded bullet" });
  });

  it("reflects a hand-edited bullet's rewritten text, not whatever it originally said", () => {
    const document = makeDocument();
    document.sections[0].entries[0].bullets![0].text = "Shipped v1, using AI tools daily";

    const result = collectEditedBulletText(document);

    expect(result["ev-1"]).toBe("Shipped v1, using AI tools daily");
  });

  it("ignores a hand-typed bullet with no evidence_id", () => {
    const result = collectEditedBulletText(makeDocument());

    expect(Object.keys(result)).toEqual(["ev-1", "ev-2"]);
  });

  it("returns an empty object when there's no experience section at all", () => {
    const result = collectEditedBulletText({ sections: [] });

    expect(result).toEqual({});
  });
});

describe("collectManualBulletText", () => {
  it("collects an included hand-typed bullet's text", () => {
    const document = makeDocument();
    document.sections[0].entries[0].bullets![2].included = true;

    const result = collectManualBulletText(document);

    expect(result).toEqual(["Hand-typed, no link"]);
  });

  it("ignores an excluded hand-typed bullet", () => {
    // Covered by the fixture's default included: false — asserted via the
    // exact-match check below.
    const result = collectManualBulletText(makeDocument());

    expect(result).toEqual([]);
  });

  it("ignores an evidence-linked bullet even when included", () => {
    const document = makeDocument();
    document.sections[0].entries[0].bullets![2].included = true;
    document.sections[0].entries[0].bullets![2].text = "";

    const result = collectManualBulletText(document);

    // Blank hand-typed text is skipped too — nothing useful to send.
    expect(result).toEqual([]);
  });

  it("drops a hand-typed bullet whose role entry or section is excluded, even if the bullet itself is included", () => {
    const document = makeDocument();
    document.sections[0].entries[0].bullets![2].included = true;
    document.sections[0].entries[0].included = false;

    const result = collectManualBulletText(document);

    expect(result).toEqual([]);
  });

  it("returns an empty list when there's no experience section at all", () => {
    const result = collectManualBulletText({ sections: [] });

    expect(result).toEqual([]);
  });
});

describe("collectUsedEvidenceIds", () => {
  it("collects every bullet's evidence_id, regardless of included state", () => {
    // Regression: UnusedEvidencePanel's "Add to Role" kept adding
    // duplicate bullets for the same Evidence because nothing tracked
    // which ids already had a bullet. Unlike collectExcludedEvidenceIds,
    // this doesn't care whether the bullet/entry/section is included —
    // an excluded bullet still counts as "already added."
    const result = collectUsedEvidenceIds(makeDocument());

    expect(result.sort()).toEqual(["ev-1", "ev-2"]);
  });

  it("ignores a hand-typed bullet with no evidence_id", () => {
    const result = collectUsedEvidenceIds(makeDocument());

    expect(result).not.toContain(undefined);
    expect(result.length).toBe(2);
  });

  it("still counts a bullet whose role entry or section is excluded", () => {
    const document = makeDocument({ included: false });
    document.sections[0].entries[0].included = false;

    const result = collectUsedEvidenceIds(document);

    expect(result.sort()).toEqual(["ev-1", "ev-2"]);
  });

  it("returns an empty list when there's no experience section at all", () => {
    const result = collectUsedEvidenceIds({ sections: [] });

    expect(result).toEqual([]);
  });
});
