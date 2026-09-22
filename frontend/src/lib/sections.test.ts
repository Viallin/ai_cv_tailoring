import { describe, expect, it } from "vitest";

import { SECTION_TITLES_EN, SECTION_TITLES_RU, languageLabel, sectionTitlesFor } from "./sections";

describe("sectionTitlesFor", () => {
  it("returns the matching locale", () => {
    expect(sectionTitlesFor("ru")).toBe(SECTION_TITLES_RU);
    expect(sectionTitlesFor("en")).toBe(SECTION_TITLES_EN);
  });

  it("falls back to English for an unknown language", () => {
    expect(sectionTitlesFor("fr")).toBe(SECTION_TITLES_EN);
    expect(sectionTitlesFor("")).toBe(SECTION_TITLES_EN);
  });

  it("every locale has the same key set and order", () => {
    // A locale table missing a key would render `undefined` for that
    // section's heading wherever a caller looks it up for that language.
    expect(Object.keys(SECTION_TITLES_RU)).toEqual(Object.keys(SECTION_TITLES_EN));
  });
});

describe("languageLabel", () => {
  it("returns a human-readable name for a known language", () => {
    expect(languageLabel("en")).toBe("English");
    expect(languageLabel("ru")).toBe("Russian");
  });

  it("falls back to the raw code for an unknown language", () => {
    expect(languageLabel("fr")).toBe("fr");
  });
});
