import { describe, expect, it } from "vitest";

import { buildAdvisoryChips, findBulletCountOutliers } from "./advisories";
import type { DocumentModel } from "./structuredDocument";

function role(id: string, bulletCount: number, opts: { included?: boolean; locked?: boolean } = {}) {
  return {
    id,
    text: `Role ${id}`,
    included: opts.included ?? true,
    locked: opts.locked ?? false,
    bullets: Array.from({ length: bulletCount }, (_, i) => ({
      id: `${id}-bullet-${i}`,
      text: "A reasonably normal bullet describing an achievement.",
      included: true,
    })),
  };
}

function documentWithExperience(entries: ReturnType<typeof role>[]): DocumentModel {
  return {
    sections: [{ key: "experience", title: "Experience", included: true, entries }],
  };
}

describe("findBulletCountOutliers", () => {
  it("flags a non-gap role with zero included bullets", () => {
    const document = documentWithExperience([role("exp-1", 3), role("exp-2", 0)]);
    const outliers = findBulletCountOutliers(document);
    expect(outliers.map((o) => o.id)).toContain("outlier-empty-exp-2");
  });

  it("never flags a locked (career gap) entry with zero bullets", () => {
    const document = documentWithExperience([role("exp-1", 3), role("exp-2", 0, { locked: true })]);
    const outliers = findBulletCountOutliers(document);
    expect(outliers.map((o) => o.id)).not.toContain("outlier-empty-exp-2");
  });

  it("flags a role with notably more bullets than the rest", () => {
    const document = documentWithExperience([role("exp-1", 2), role("exp-2", 3), role("exp-3", 12)]);
    const outliers = findBulletCountOutliers(document);
    expect(outliers.map((o) => o.id)).toContain("outlier-many-exp-3");
  });

  it("doesn't flag a role that's merely a little above average", () => {
    const document = documentWithExperience([role("exp-1", 4), role("exp-2", 5), role("exp-3", 6)]);
    expect(findBulletCountOutliers(document)).toEqual([]);
  });

  it("returns nothing when the Experience section is toggled off", () => {
    const document = documentWithExperience([role("exp-1", 0)]);
    document.sections[0].included = false;
    expect(findBulletCountOutliers(document)).toEqual([]);
  });
});

describe("buildAdvisoryChips", () => {
  // Phase 31 (follow-up) — buildAdvisoryChips is now a thin pass-through
  // to findBulletCountOutliers; the page-count and empty-section checks
  // it used to also combine were removed outright (see advisories.ts's
  // own comment for why), so this just confirms the delegation, not a
  // shape of its own.
  it("delegates to findBulletCountOutliers", () => {
    const document = documentWithExperience([role("exp-1", 3), role("exp-2", 0)]);
    expect(buildAdvisoryChips(document)).toEqual(findBulletCountOutliers(document));
  });

  it("returns an empty array when there's nothing to flag", () => {
    const document = documentWithExperience([role("exp-1", 3), role("exp-2", 4)]);
    expect(buildAdvisoryChips(document)).toEqual([]);
  });
});
