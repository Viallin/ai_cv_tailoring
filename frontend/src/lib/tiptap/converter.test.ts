import { describe, expect, it } from "vitest";

import type { DocumentModel } from "@/lib/structuredDocument";
import { documentModelToTiptapJSON, tiptapJSONToDocumentModel } from "./converter";

// Phase 26 — documentModelToTiptapJSON/tiptapJSONToDocumentModel is meant
// to be a total, lossless bijection with no per-section/per-kind
// special-casing (see the design notes in development_plan.md's Phase
// 26). These fixtures cover every DocumentBlock shape that actually
// occurs in the app: a plain section entry, a category-grouped Skills
// entry (kind: "subheading"), an Experience role with project-grouped
// bullets (kind: "subheading" one level down), a locked Gap entry, an
// excluded entry/bullet, an evidence_id-bearing bullet, and Phase 25's
// runs/alignment passthrough fields.

function roundTrip(model: DocumentModel): DocumentModel {
  return tiptapJSONToDocumentModel(documentModelToTiptapJSON(model));
}

describe("documentModelToTiptapJSON", () => {
  it("maps a plain section entry to an entry node wrapping an entryHeading with the text as its content", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "summary",
          title: "Summary",
          included: true,
          entries: [{ id: "summary", text: "Engineer.", included: true }],
        },
      ],
    };

    expect(documentModelToTiptapJSON(model)).toEqual({
      type: "doc",
      content: [
        {
          type: "section",
          attrs: { key: "summary", title: "Summary", included: true, page_break_before: null },
          content: [
            {
              type: "entry",
              attrs: {
                id: "summary",
                included: true,
                page_break_before: null,
                locked: null,
                kind: null,
                evidence_id: null,
                alignment: null,
              },
              content: [{ type: "entryHeading", content: [{ type: "text", text: "Engineer." }] }],
            },
          ],
        },
      ],
    });
  });

  it("maps empty text to no content, not a zero-length text node", () => {
    const model: DocumentModel = {
      sections: [{ key: "summary", title: "Summary", included: true, entries: [{ id: "summary", text: "", included: true }] }],
    };

    const json = documentModelToTiptapJSON(model);
    expect(json.content![0].content![0].content![0].content).toEqual([]);
  });

  it("maps an Experience entry's bullets as sibling nodes after entryHeading, project headings included", () => {
    const model: DocumentModel = {
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
                { id: "exp-1-project-0", text: "Project X", included: true, kind: "subheading" },
                { id: "exp-1-project-0-bullet-0", text: "Shipped a thing.", included: true, evidence_id: "ev-1" },
              ],
            },
          ],
        },
      ],
    };

    const json = documentModelToTiptapJSON(model);
    const entryNode = json.content![0].content![0];
    expect(entryNode.content).toHaveLength(3); // entryHeading + 2 bullets
    expect(entryNode.content![1]).toMatchObject({ type: "bullet", attrs: { kind: "subheading" } });
    expect(entryNode.content![2]).toMatchObject({ type: "bullet", attrs: { evidence_id: "ev-1" } });
  });
});

describe("tiptapJSONToDocumentModel round-trip", () => {
  it("round-trips a plain entry with no bullets key (matches every non-Experience builder's own shape)", () => {
    const model: DocumentModel = {
      sections: [
        { key: "summary", title: "Summary", included: true, entries: [{ id: "summary", text: "Engineer.", included: true }] },
      ],
    };

    expect(roundTrip(model)).toEqual(model);
  });

  it("round-trips a category-grouped Skills subheading entry", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "skills",
          title: "Skills",
          included: true,
          entries: [
            { id: "skills-category-0", text: "Languages", included: true, kind: "subheading" },
            { id: "skill-1", text: "TypeScript", included: true },
          ],
        },
      ],
    };

    expect(roundTrip(model)).toEqual(model);
  });

  it("round-trips a locked (Gap) Experience entry", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "experience",
          title: "Experience",
          included: true,
          // No `bullets` key — matches buildExperienceSection's own output
          // for an entry with none (`bullets: []` also round-trips fine,
          // just not through `toEqual`: an *empty* array and an *absent*
          // key are functionally identical everywhere they're consumed,
          // see converter.ts's own docstring on this deliberate,
          // accepted simplification).
          entries: [{ id: "exp-gap", text: "Career gap (2020–2021)", included: true, locked: true }],
        },
      ],
    };

    expect(roundTrip(model)).toEqual(model);
  });

  it("normalizes an explicit empty bullets array to an absent key (documented, harmless deviation — see converter.ts)", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "experience",
          title: "Experience",
          included: true,
          entries: [{ id: "exp-1", text: "Engineer — Acme", included: true, bullets: [] }],
        },
      ],
    };

    expect(roundTrip(model).sections[0].entries[0].bullets).toBeUndefined();
  });

  it("round-trips an excluded entry and an excluded bullet (included: false stays in the model, not dropped)", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "education",
          title: "Education",
          included: true,
          entries: [{ id: "edu-1", text: "State University", included: false }],
        },
        {
          key: "experience",
          title: "Experience",
          included: true,
          entries: [
            {
              id: "exp-1",
              text: "Engineer — Acme",
              included: true,
              bullets: [{ id: "exp-1-bullet-0", text: "Shipped a thing.", included: false }],
            },
          ],
        },
      ],
    };

    expect(roundTrip(model)).toEqual(model);
  });

  it("round-trips alignment unchanged (a plain node attr, not mark-derived)", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "summary",
          title: "Summary",
          included: true,
          entries: [{ id: "summary", text: "Engineer.", included: true, alignment: "center" }],
        },
      ],
    };

    expect(roundTrip(model)).toEqual(model);
  });

  // Phase 31 — runs are no longer an opaque passthrough attr; they're
  // derived from the actual marks the outbound conversion put on the
  // text content (contentFromRuns/runsFromContent, converter.ts). A
  // round-trip is only byte-identical when every field a run declares is
  // actually mark-representable — `bold: false` (or any explicitly-false
  // flag) has no corresponding mark to emit, so it's absent, not `false`,
  // on the way back out. This is a deliberate, documented behavior
  // change from the pre-Phase-31 shape (see converter.ts's own comment):
  // TextRun's fields are all optional, and every consumer (renderBlockText,
  // every backend renderer) already treats "absent" and "false" as
  // identical, so this loses no real information.
  it("round-trips runs, normalizing explicit-false flags to absent (marks have no way to represent them)", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "summary",
          title: "Summary",
          included: true,
          entries: [
            {
              id: "summary",
              text: "Engineer.",
              included: true,
              runs: [
                { text: "Engineer", bold: true },
                { text: ".", italic: true, underline: true, link: "https://example.com" },
              ],
            },
          ],
        },
      ],
    };

    expect(roundTrip(model)).toEqual(model);
  });

  it("emits real marks for a run's formatting, not an opaque runs attr", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "summary",
          title: "Summary",
          included: true,
          entries: [
            {
              id: "summary",
              text: "Bold link.",
              included: true,
              runs: [{ text: "Bold link.", bold: true, link: "https://example.com" }],
            },
          ],
        },
      ],
    };

    const json = documentModelToTiptapJSON(model);
    const headingContent = json.content![0].content![0].content![0].content;
    expect(headingContent).toEqual([
      {
        type: "text",
        text: "Bold link.",
        marks: [{ type: "bold" }, { type: "link", attrs: { href: "https://example.com" } }],
      },
    ]);
  });

  it("returns undefined runs for a block with no marks (doesn't bloat every untouched draft)", () => {
    const model: DocumentModel = {
      sections: [
        { key: "summary", title: "Summary", included: true, entries: [{ id: "summary", text: "Plain.", included: true }] },
      ],
    };

    expect(roundTrip(model).sections[0].entries[0].runs).toBeUndefined();
  });

  it("round-trips a whole realistic document (sections, category grouping, project-grouped bullets, evidence_id) unchanged", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "summary",
          title: "Summary",
          included: true,
          entries: [{ id: "summary", text: "Engineer with a track record.", included: true }],
        },
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
                { id: "exp-1-bullet-0", text: "Shipped a thing.", included: true, evidence_id: "ev-1" },
                { id: "exp-1-project-0", text: "Project X", included: true, kind: "subheading" },
                { id: "exp-1-project-0-bullet-0", text: "Led the launch.", included: true, evidence_id: "ev-2" },
              ],
            },
          ],
        },
        {
          key: "skills",
          title: "Skills",
          included: true,
          entries: [
            { id: "skills-category-0", text: "Languages", included: true, kind: "subheading" },
            { id: "skill-1", text: "TypeScript", included: true },
            { id: "skill-2", text: "Python", included: true },
          ],
        },
        { key: "education", title: "Education", included: true, entries: [] },
      ],
    };

    expect(roundTrip(model)).toEqual(model);
  });

  // Phase 30 — manual pagination control.
  it("round-trips page_break_before on both a section and an entry", () => {
    const model: DocumentModel = {
      sections: [
        {
          key: "education",
          title: "Education",
          included: true,
          page_break_before: true,
          entries: [{ id: "edu-1", text: "State University", included: true, page_break_before: true }],
        },
      ],
    };

    expect(roundTrip(model)).toEqual(model);
  });

  it("omits page_break_before from the reconstructed model when absent (matches every other optional field's own undefined-not-false convention)", () => {
    const model: DocumentModel = {
      sections: [
        { key: "summary", title: "Summary", included: true, entries: [{ id: "summary", text: "Engineer.", included: true }] },
      ],
    };

    const result = roundTrip(model);
    expect(result.sections[0].page_break_before).toBeUndefined();
    expect(result.sections[0].entries[0].page_break_before).toBeUndefined();
  });
});
