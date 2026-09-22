import { describe, expect, it } from "vitest";

import { collectExcludedContent } from "./excludedContent";
import type { DocumentModel } from "./structuredDocument";

describe("collectExcludedContent", () => {
  it("returns nothing when every section/entry/bullet is included", () => {
    const document: DocumentModel = {
      sections: [
        {
          key: "education",
          title: "Education",
          included: true,
          entries: [{ id: "edu-1", text: "State University", included: true }],
        },
      ],
    };

    expect(collectExcludedContent(document)).toEqual([]);
  });

  it("lists an excluded flat-section entry (e.g. Education/Skills) by its own text", () => {
    const document: DocumentModel = {
      sections: [
        {
          key: "education",
          title: "Education",
          included: true,
          entries: [
            { id: "edu-1", text: "State University", included: true },
            { id: "edu-2", text: "Community College", included: false },
          ],
        },
      ],
    };

    expect(collectExcludedContent(document)).toEqual([
      { sectionKey: "education", sectionTitle: "Education", entryId: "edu-2", text: "Community College" },
    ]);
  });

  it("lists an excluded Experience bullet, keyed by both entry and bullet id", () => {
    const document: DocumentModel = {
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
                { id: "exp-1-bullet-0", text: "Shipped a feature", included: true },
                { id: "exp-1-bullet-1", text: "Owned the backend", included: false },
              ],
            },
          ],
        },
      ],
    };

    expect(collectExcludedContent(document)).toEqual([
      {
        sectionKey: "experience",
        sectionTitle: "Experience",
        entryId: "exp-1",
        bulletId: "exp-1-bullet-1",
        text: "Owned the backend",
      },
    ]);
  });

  it("lists an excluded Experience role once, without also listing its still-included bullets", () => {
    const document: DocumentModel = {
      sections: [
        {
          key: "experience",
          title: "Experience",
          included: true,
          entries: [
            {
              id: "exp-1",
              text: "Engineer — Acme",
              included: false,
              bullets: [{ id: "exp-1-bullet-0", text: "Shipped a feature", included: true }],
            },
          ],
        },
      ],
    };

    expect(collectExcludedContent(document)).toEqual([
      { sectionKey: "experience", sectionTitle: "Experience", entryId: "exp-1", text: "Engineer — Acme" },
    ]);
  });

  it("skips a fully-excluded section entirely — its own checkbox is already a working restore path", () => {
    const document: DocumentModel = {
      sections: [
        {
          key: "education",
          title: "Education",
          included: false,
          entries: [{ id: "edu-1", text: "State University", included: false }],
        },
      ],
    };

    expect(collectExcludedContent(document)).toEqual([]);
  });
});
