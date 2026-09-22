import { describe, expect, it } from "vitest";

import { CV_TEMPLATES, isValidTemplate } from "./cvTemplates";

describe("CV_TEMPLATES", () => {
  it("ships at least two starter templates", () => {
    expect(CV_TEMPLATES.length).toBeGreaterThanOrEqual(2);
  });

  it("every template has every required CSS var key", () => {
    for (const template of CV_TEMPLATES) {
      expect(isValidTemplate(template)).toBe(true);
    }
  });

  it("template ids are unique", () => {
    const ids = CV_TEMPLATES.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("flags a template missing a required CSS var key", () => {
    const incomplete = { id: "x", label: "X", cssVars: { "--cv-heading-font": "serif" }, bulletChar: "-" };
    expect(isValidTemplate(incomplete)).toBe(false);
  });

  it("every template has a plain bullet character", () => {
    for (const template of CV_TEMPLATES) {
      expect(template.bulletChar.length).toBeGreaterThan(0);
    }
  });
});
