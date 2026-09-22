import { describe, expect, it } from "vitest";

import type { AssembledCV } from "@/api/models";
import {
  addBullet,
  buildDocumentFromAssembledCv,
  collapseSkillsAndTechnologiesIfNeeded,
  collapseSkillsSectionIfNeeded,
  collectDocumentSkillNames,
  toggleBulletIncluded,
  toggleEntryIncluded,
  toggleEntryPageBreak,
  toggleSectionIncluded,
  toggleSectionPageBreak,
  updateBulletText,
  updateEntryText,
  type DocumentEntry,
  type DocumentModel,
  type DocumentSection,
} from "./structuredDocument";

const CV: AssembledCV = {
  name: "Ada Lovelace",
  summary: "Engineer with a track record of shipping things.",
  contacts: [
    { id: "contact-1", label: "Email", value: "ada@example.com" },
    { id: "contact-2", label: "Phone", value: "+44 1234" },
  ],
  experience: [
    {
      experience_id: "exp-1",
      position: "Engineer",
      company: "Acme",
      period: "2020-2022",
      location: "Remote",
      is_gap: false,
      bullets: [
        { text: "Shipped a feature", evidence_id: "ev-1" },
        { text: "Owned the backend", project: "Internal tool", evidence_id: "ev-2" },
      ],
    },
    {
      experience_id: "exp-2",
      position: "Career break",
      is_gap: true,
      bullets: [],
    },
  ],
  education: [{ id: "edu-1", institution: "State University" }],
  skills: [
    { id: "skill-1", name: "Roadmapping", category: "Design", proficiency: "Expertise" },
    { id: "skill-2", name: "UX Design", category: "Design" },
    { id: "skill-3", name: "Python", category: null },
  ],
} as unknown as AssembledCV;

describe("buildDocumentFromAssembledCv", () => {
  const document = buildDocumentFromAssembledCv(CV);

  it("uses Russian section titles for a Russian-language candidate (Version 4, Phase 4.3)", () => {
    const ruDocument = buildDocumentFromAssembledCv({ ...CV, language: "ru" });

    expect(ruDocument.sections.find((s) => s.key === "summary")!.title).toBe("О себе");
    expect(ruDocument.sections.find((s) => s.key === "experience")!.title).toBe("Опыт работы");
    expect(ruDocument.sections.find((s) => s.key === "skills")!.title).toBe("Навыки");
    expect(ruDocument.sections.find((s) => s.key === "education")!.title).toBe("Образование");
  });

  it("defaults to English section titles when language is unset", () => {
    expect(document.sections.find((s) => s.key === "summary")!.title).toBe("Summary");
  });

  it("builds a single-entry summary section", () => {
    const summary = document.sections.find((s) => s.key === "summary")!;
    expect(summary.entries).toEqual([
      { id: "summary", text: CV.summary, included: true },
    ]);
  });

  it("builds Experience entries, grouping bullets by project (matching cv_markdown.py's _render_bullets_grouped_by_project), and locks is_gap entries", () => {
    const experience = document.sections.find((s) => s.key === "experience")!;
    expect(experience.entries).toHaveLength(2);

    const [role, gap] = experience.entries;
    expect(role.id).toBe("exp-1");
    expect(role.text).toBe("Engineer — Acme (2020-2022, Remote)");
    expect(role.locked).toBe(false);
    expect(role.bullets).toEqual([
      { id: "exp-1-bullet-0", text: "Shipped a feature", included: true, evidence_id: "ev-1" },
      { id: "exp-1-project-0", text: "Internal tool", included: true, kind: "subheading" },
      {
        id: "exp-1-project-0-bullet-0",
        text: "Owned the backend",
        included: true,
        evidence_id: "ev-2",
      },
    ]);

    expect(gap.id).toBe("exp-2");
    // No literal "[GAP]" text -- gap status is conveyed by `locked` alone
    // (italic styling + a disabled checkbox), so it can never leak into
    // the real exported document (which renders this text verbatim).
    expect(gap.text).toBe("Career break");
    expect(gap.locked).toBe(true);
    expect(gap.bullets).toEqual([]);
  });

  it("adds a `runs` link for the company/project name when a company_url/project_urls entry is known, leaving `.text` plain (mirrors app/cv_markdown.py's _maybe_link, but as runs — see experienceHeadingRuns' own comment for why plain-text Markdown syntax doesn't work here)", () => {
    // Found live: embedding "[Acme](url)" directly into `.text` (an
    // earlier version of this fix) rendered as the literal, unparsed
    // string on screen — DocumentEditor.tsx only turns a link into a real
    // hyperlink via `.runs` (lib/tiptap/converter.ts's contentFromRuns),
    // never by interpreting Markdown syntax inside plain `.text`.
    const withLinks: AssembledCV = {
      ...CV,
      experience: [
        {
          experience_id: "exp-1",
          position: "Engineer",
          company: "Acme",
          company_url: "https://acme.example/",
          period: "2020-2022",
          location: "Remote",
          is_gap: false,
          bullets: [
            { text: "Shipped a feature", evidence_id: "ev-1" },
            { text: "Owned the backend", project: "Internal tool", evidence_id: "ev-2" },
          ],
          project_urls: { "Internal tool": "https://internal.example/" },
        },
      ],
    } as unknown as AssembledCV;

    const linkedDocument = buildDocumentFromAssembledCv(withLinks);
    const experience = linkedDocument.sections.find((s) => s.key === "experience")!;
    const [role] = experience.entries;

    // `.text` stays the plain fallback, no embedded Markdown syntax.
    expect(role.text).toBe("Engineer — Acme (2020-2022, Remote)");
    expect(role.runs).toEqual([
      { text: "Engineer", bold: true },
      { text: " — ", bold: true },
      { text: "Acme", bold: true, link: "https://acme.example/" },
      { text: " (2020-2022, Remote)", bold: true },
    ]);

    expect(role.bullets![1]).toEqual({
      id: "exp-1-project-0",
      text: "Internal tool",
      included: true,
      kind: "subheading",
      runs: [{ text: "Internal tool", italic: true, link: "https://internal.example/" }],
    });
  });

  it("leaves the company/project name plain (no `runs`) when no url is known", () => {
    // The existing "builds Experience entries..." test above already
    // covers this (CV has no company_url/project_urls at all) — this test
    // exists to name the behavior explicitly rather than leave it as an
    // implicit side effect of a differently-focused assertion.
    const experience = document.sections.find((s) => s.key === "experience")!;
    const [role] = experience.entries;

    expect(role.runs).toBeUndefined();
    expect(role.bullets![1].runs).toBeUndefined();
    expect(role.bullets![1].text).toBe("Internal tool");
  });

  it("uses italic (not bold) runs for a linked company on a gap entry", () => {
    const withLinkedGap: AssembledCV = {
      ...CV,
      experience: [
        {
          experience_id: "exp-2",
          position: "Sabbatical",
          company: "Acme",
          company_url: "https://acme.example/",
          is_gap: true,
          bullets: [],
        },
      ],
    } as unknown as AssembledCV;

    const linkedDocument = buildDocumentFromAssembledCv(withLinkedGap);
    const [gap] = linkedDocument.sections.find((s) => s.key === "experience")!.entries;

    expect(gap.runs).toEqual([
      { text: "Sabbatical", italic: true },
      { text: " — ", italic: true },
      { text: "Acme", italic: true, link: "https://acme.example/" },
    ]);
  });

  it("builds simple list sections using entityConfigs.ts's own summarize functions", () => {
    const education = document.sections.find((s) => s.key === "education")!;
    expect(education.entries).toEqual([{ id: "edu-1", text: "State University", included: true }]);
  });

  it("builds a Contacts section the same generic way as Education/Certifications — one entry per contact, each independently includable", () => {
    // Contacts used to be folded into the un-editable header with no
    // per-item control at all; it's now a real section, same as every
    // other CV fact, positioned first (right after the header).
    expect(document.sections[0].key).toBe("contacts");
    const contacts = document.sections.find((s) => s.key === "contacts")!;
    expect(contacts.title).toBe("Contacts");
    expect(contacts.entries).toEqual([
      { id: "contact-1", text: "Email: ada@example.com", included: true },
      { id: "contact-2", text: "Phone: +44 1234", included: true },
    ]);
  });

  // Post-31 — each category (and each run of uncategorized skills) is
  // now one already-compact entry, matching cv_markdown.py's/
  // PrintSectionBlock.tsx's own rendered line exactly, instead of one
  // entry per skill plus a separate subheading marker.
  it("groups skills/technologies by category into one compact entry per group, matching PrintSectionBlock.tsx's own rendered line", () => {
    const skills = document.sections.find((s) => s.key === "skills")!;
    expect(skills.entries).toEqual([
      {
        id: "skills-0",
        text: "Design: Roadmapping (Expertise); UX Design",
        included: true,
        kind: "compact",
        page_break_before: false,
        runs: [
          { text: "Design", bold: true },
          { text: ": Roadmapping (Expertise); UX Design", bold: false },
        ],
      },
      { id: "skills-1", text: "Python", included: true, kind: "compact", page_break_before: false },
    ]);
  });

  it("every section starts fully included", () => {
    expect(document.sections.every((s) => s.included)).toBe(true);
  });
});

describe("pure edit helpers", () => {
  const document = buildDocumentFromAssembledCv(CV);

  it("toggleSectionIncluded flips only the target section", () => {
    const result = toggleSectionIncluded(document, "skills");
    expect(result.sections.find((s) => s.key === "skills")!.included).toBe(false);
    expect(result.sections.find((s) => s.key === "education")!.included).toBe(true);
  });

  it("toggleEntryIncluded flips only the target entry", () => {
    const result = toggleEntryIncluded(document, "education", "edu-1");
    expect(result.sections.find((s) => s.key === "education")!.entries[0].included).toBe(false);
  });

  // Phase 30 — manual pagination control.
  it("toggleSectionPageBreak flips only the target section's page_break_before, starting from undefined", () => {
    const result = toggleSectionPageBreak(document, "skills");
    expect(result.sections.find((s) => s.key === "skills")!.page_break_before).toBe(true);
    expect(result.sections.find((s) => s.key === "education")!.page_break_before).toBeUndefined();
  });

  it("toggleSectionPageBreak is a plain flip — toggling twice returns to false, not back to undefined", () => {
    const once = toggleSectionPageBreak(document, "skills");
    const twice = toggleSectionPageBreak(once, "skills");
    expect(twice.sections.find((s) => s.key === "skills")!.page_break_before).toBe(false);
  });

  it("toggleEntryPageBreak flips only the target entry, leaving included/locked untouched", () => {
    const result = toggleEntryPageBreak(document, "experience", "exp-1");
    const role = result.sections.find((s) => s.key === "experience")!.entries[0];
    expect(role.page_break_before).toBe(true);
    expect(role.included).toBe(true);
    const otherEntry = result.sections.find((s) => s.key === "experience")!.entries[1];
    expect(otherEntry.page_break_before).toBeUndefined();
  });

  // Phase 28 (follow-up) — reported directly: not auto-dropping a
  // career-Gap entry during generation was never meant to forbid the
  // user from excluding one by hand afterward.
  it("toggleEntryIncluded also flips a locked (career-gap) entry — locked no longer blocks the toggle", () => {
    const result = toggleEntryIncluded(document, "experience", "exp-2");
    const gapEntry = result.sections.find((s) => s.key === "experience")!.entries[1];
    expect(gapEntry.locked).toBe(true); // still locked — just not blocked from being excluded
    expect(gapEntry.included).toBe(false);
  });

  const twoCategoryDocument: DocumentModel = {
    sections: [
      {
        key: "skills",
        title: "Skills",
        included: true,
        entries: [
          { id: "cat-1", text: "Design", included: true, kind: "subheading" },
          { id: "skill-1", text: "Roadmapping", included: true },
          { id: "skill-2", text: "UX Design", included: true },
          { id: "cat-2", text: "Tools", included: true, kind: "subheading" },
          { id: "skill-3", text: "Unity", included: true },
        ],
      },
    ],
  };

  it("toggleEntryIncluded on a category header cascades to unchecking every member below it, stopping at the next header", () => {
    const result = toggleEntryIncluded(twoCategoryDocument, "skills", "cat-1");
    const entries = result.sections[0].entries;

    expect(entries.find((e) => e.id === "cat-1")!.included).toBe(false);
    expect(entries.find((e) => e.id === "skill-1")!.included).toBe(false);
    expect(entries.find((e) => e.id === "skill-2")!.included).toBe(false);
    // The next category and its own member are untouched.
    expect(entries.find((e) => e.id === "cat-2")!.included).toBe(true);
    expect(entries.find((e) => e.id === "skill-3")!.included).toBe(true);
  });

  it("re-checking a category header does NOT re-check its members — they stay however the user last left them", () => {
    const uncheckedFirst = toggleEntryIncluded(twoCategoryDocument, "skills", "cat-1");
    const recheckedHeader = toggleEntryIncluded(uncheckedFirst, "skills", "cat-1");
    const entries = recheckedHeader.sections[0].entries;

    expect(entries.find((e) => e.id === "cat-1")!.included).toBe(true);
    expect(entries.find((e) => e.id === "skill-1")!.included).toBe(false);
    expect(entries.find((e) => e.id === "skill-2")!.included).toBe(false);
  });

  it("toggleEntryIncluded on a plain (non-subheading) entry never cascades", () => {
    const result = toggleEntryIncluded(twoCategoryDocument, "skills", "skill-1");
    const entries = result.sections[0].entries;

    expect(entries.find((e) => e.id === "skill-1")!.included).toBe(false);
    expect(entries.find((e) => e.id === "skill-2")!.included).toBe(true);
    expect(entries.find((e) => e.id === "cat-1")!.included).toBe(true);
  });

  it("toggleBulletIncluded flips only the target bullet", () => {
    const result = toggleBulletIncluded(document, "experience", "exp-1", "exp-1-bullet-0");
    const entry = result.sections.find((s) => s.key === "experience")!.entries[0];
    expect(entry.bullets![0].included).toBe(false);
    expect(entry.bullets![1].included).toBe(true);
  });

  it("updateEntryText and updateBulletText update only the target text", () => {
    const withEntryEdit = updateEntryText(document, "education", "edu-1", "Edited");
    expect(withEntryEdit.sections.find((s) => s.key === "education")!.entries[0].text).toBe("Edited");

    const withBulletEdit = updateBulletText(document, "experience", "exp-1", "exp-1-bullet-0", "Edited bullet");
    const entry = withBulletEdit.sections.find((s) => s.key === "experience")!.entries[0];
    expect(entry.bullets![0].text).toBe("Edited bullet");
  });

  it("edit helpers do not mutate the original document", () => {
    toggleSectionIncluded(document, "skills");
    expect(document.sections.find((s) => s.key === "skills")!.included).toBe(true);
  });

  it("addBullet appends a new, included bullet to the target entry, leaving existing bullets untouched", () => {
    const result = addBullet(document, "experience", "exp-1", "Hand-typed new bullet");
    const entry = result.sections.find((s) => s.key === "experience")!.entries[0];

    expect(entry.bullets).toHaveLength(4); // 3 existing + 1 new
    const added = entry.bullets![3];
    expect(added.text).toBe("Hand-typed new bullet");
    expect(added.included).toBe(true);
    expect(added.evidence_id).toBeUndefined();
    // Untouched:
    expect(entry.bullets![0].text).toBe("Shipped a feature");
  });

  it("addBullet sets evidence_id when given one (an Unused Evidence item's own id)", () => {
    const result = addBullet(document, "experience", "exp-1", "From unused evidence", "ev-9");
    const entry = result.sections.find((s) => s.key === "experience")!.entries[0];

    expect(entry.bullets!.at(-1)!.evidence_id).toBe("ev-9");
  });

  it("addBullet gives every new bullet a unique id", () => {
    const once = addBullet(document, "experience", "exp-1", "First");
    const twice = addBullet(once, "experience", "exp-1", "Second");
    const entry = twice.sections.find((s) => s.key === "experience")!.entries[0];
    const ids = entry.bullets!.map((b) => b.id);

    expect(new Set(ids).size).toBe(ids.length);
  });
});

// Post-31 — one-time migration from the old one-entry-per-skill (+
// `kind: "subheading"` category marker) shape into one already-compact
// entry per category/uncategorized run, mirroring the compact line every
// export already rendered from the old shape.
describe("collapseSkillsSectionIfNeeded / collapseSkillsAndTechnologiesIfNeeded", () => {
  function section(entries: DocumentEntry[], key = "skills"): DocumentSection {
    return { key, title: "Skills", included: true, entries };
  }

  it("collapses a single category into one compact entry with a bold, runs-based label", () => {
    const legacy = section([
      { id: "cat-1", text: "Design", included: true, kind: "subheading" },
      { id: "skill-1", text: "Roadmapping", included: true },
      { id: "skill-2", text: "UX Design", included: true },
    ]);

    const result = collapseSkillsSectionIfNeeded(legacy);

    expect(result).not.toBe(legacy);
    expect(result.entries).toEqual([
      {
        id: "skills-0",
        text: "Design: Roadmapping; UX Design",
        included: true,
        kind: "compact",
        page_break_before: false,
        runs: [
          { text: "Design", bold: true },
          { text: ": Roadmapping; UX Design", bold: false },
        ],
      },
    ]);
  });

  it("collapses a flat, uncategorized run into one compact entry joined with a middle dot, no runs", () => {
    const legacy = section([
      { id: "skill-1", text: "Mentoring", included: true },
      { id: "skill-2", text: "Team Management", included: true },
    ]);

    expect(collapseSkillsSectionIfNeeded(legacy).entries).toEqual([
      { id: "skills-0", text: "Mentoring · Team Management", included: true, kind: "compact", page_break_before: false },
    ]);
  });

  it("collapses a leading flat run followed by a category into two separate compact entries, in order", () => {
    const legacy = section([
      { id: "skill-1", text: "Mentoring", included: true },
      { id: "cat-1", text: "Design", included: true, kind: "subheading" },
      { id: "skill-2", text: "Roadmapping", included: true },
    ]);

    const result = collapseSkillsSectionIfNeeded(legacy);

    expect(result.entries.map((e) => e.text)).toEqual(["Mentoring", "Design: Roadmapping"]);
    expect(result.entries.every((e) => e.kind === "compact")).toBe(true);
  });

  it("a category with every member excluded still collapses to just its bold label, no trailing colon", () => {
    const legacy = section([
      { id: "cat-1", text: "Design", included: true, kind: "subheading" },
      { id: "skill-1", text: "Roadmapping", included: false },
    ]);

    expect(collapseSkillsSectionIfNeeded(legacy).entries).toEqual([
      {
        id: "skills-0",
        text: "Design",
        included: true,
        kind: "compact",
        page_break_before: false,
        runs: [{ text: "Design", bold: true }],
      },
    ]);
  });

  it("carries a category header's own page_break_before into the compact entry", () => {
    const legacy = section([
      { id: "cat-1", text: "Design", included: true, kind: "subheading", page_break_before: true },
      { id: "skill-1", text: "Roadmapping", included: true },
    ]);

    expect(collapseSkillsSectionIfNeeded(legacy).entries[0].page_break_before).toBe(true);
  });

  it("carries only the first flat member's own page_break_before, silently absorbing a later member's", () => {
    const flagOnFirst = section([
      { id: "skill-1", text: "Mentoring", included: true, page_break_before: true },
      { id: "skill-2", text: "Team Management", included: true },
    ]);
    const flagOnLater = section([
      { id: "skill-1", text: "Mentoring", included: true },
      { id: "skill-2", text: "Team Management", included: true, page_break_before: true },
    ]);

    expect(collapseSkillsSectionIfNeeded(flagOnFirst).entries[0].page_break_before).toBe(true);
    expect(collapseSkillsSectionIfNeeded(flagOnLater).entries[0].page_break_before).toBe(false);
  });

  it("drops excluded members from the joined text entirely", () => {
    const legacy = section([
      { id: "skill-1", text: "Mentoring", included: true },
      { id: "skill-2", text: "Excluded one", included: false },
      { id: "skill-3", text: "Team Management", included: true },
    ]);

    expect(collapseSkillsSectionIfNeeded(legacy).entries[0].text).toBe("Mentoring · Team Management");
  });

  it("treats an excluded category header as if it never existed, folding its (already cascade-excluded) members' surroundings into one flat run", () => {
    const legacy = section([
      { id: "cat-1", text: "Design", included: false, kind: "subheading" },
      { id: "skill-1", text: "Roadmapping", included: false }, // cascade-excluded with its header
      { id: "skill-2", text: "Python", included: true },
    ]);

    expect(collapseSkillsSectionIfNeeded(legacy).entries).toEqual([
      { id: "skills-0", text: "Python", included: true, kind: "compact", page_break_before: false },
    ]);
  });

  it("is a no-op (same object reference) on an already-compact section", () => {
    const compact = section([
      {
        id: "skills-0",
        text: "Design: Roadmapping",
        included: true,
        kind: "compact",
        page_break_before: false,
        runs: [
          { text: "Design: ", bold: true },
          { text: "Roadmapping", bold: false },
        ],
      },
    ]);

    expect(collapseSkillsSectionIfNeeded(compact)).toBe(compact);
  });

  it("still canonicalizes a never-migrated single-skill section (no header) — not treated as already-minimal", () => {
    // Deliberately NOT a no-op: `kind: "compact"` is the only signal this
    // function trusts (see its own docstring on why a count-based guess
    // isn't used) — a lone old-shape skill has never earned that marker,
    // so it still gets folded through buildCompactSkillEntries once,
    // even though the visible result (one line, no separator needed) is
    // the same either way.
    const legacy = section([{ id: "skill-1", text: "Python", included: true }]);

    const result = collapseSkillsSectionIfNeeded(legacy);

    expect(result).not.toBe(legacy);
    expect(result.entries).toEqual([{ id: "skills-0", text: "Python", included: true, kind: "compact", page_break_before: false }]);
  });

  it("leaves a non-skills section completely untouched, even if it superficially looks collapsible", () => {
    const education = section(
      [
        { id: "edu-1", text: "State University", included: true },
        { id: "edu-2", text: "Another University", included: true },
      ],
      "education",
    );

    expect(collapseSkillsSectionIfNeeded(education)).toBe(education);
  });

  it("collapseSkillsAndTechnologiesIfNeeded migrates every skills/technologies section in the document, leaving every other section untouched by reference", () => {
    const document: DocumentModel = {
      sections: [
        section([{ id: "edu-1", text: "State University", included: true }], "education"),
        section(
          [
            { id: "cat-1", text: "Design", included: true, kind: "subheading" },
            { id: "skill-1", text: "Roadmapping", included: true },
          ],
          "skills",
        ),
        section(
          [
            {
              id: "tech-0",
              text: "Unity",
              included: true,
              kind: "compact",
              page_break_before: false,
            },
          ],
          "technologies",
        ),
      ],
    };

    const migrated = collapseSkillsAndTechnologiesIfNeeded(document);

    expect(migrated.sections[0]).toBe(document.sections[0]); // education untouched
    expect(migrated.sections[1].entries).toEqual([
      {
        id: "skills-0",
        text: "Design: Roadmapping",
        included: true,
        kind: "compact",
        page_break_before: false,
        runs: [
          { text: "Design", bold: true },
          { text: ": Roadmapping", bold: false },
        ],
      },
    ]);
    expect(migrated.sections[2]).toBe(document.sections[2]); // already-compact technologies untouched
  });
});

describe("collectDocumentSkillNames", () => {
  const document = buildDocumentFromAssembledCv(CV);

  it("reads back the flat skill names from the compact, category-grouped shape", () => {
    expect(collectDocumentSkillNames(document, "skills")).toEqual(["Roadmapping", "UX Design", "Python"]);
  });

  it("returns an empty list for a section with no entries at all", () => {
    expect(collectDocumentSkillNames(document, "technologies")).toEqual([]);
  });

  it("returns an empty list when the section is missing from the document entirely", () => {
    expect(collectDocumentSkillNames({ sections: [] }, "skills")).toEqual([]);
  });

  it("reflects a name the user added directly to the compact line", () => {
    const withAdded: DocumentModel = {
      sections: [
        {
          key: "skills",
          title: "Skills",
          included: true,
          entries: [
            {
              id: "skills-0",
              text: "Design: Roadmapping; UX Design; AI Tools",
              included: true,
              kind: "compact",
              runs: [
                { text: "Design", bold: true },
                { text: ": Roadmapping; UX Design; AI Tools", bold: false },
              ],
            },
          ],
        },
      ],
    };

    expect(collectDocumentSkillNames(withAdded, "skills")).toEqual(["Roadmapping", "UX Design", "AI Tools"]);
  });

  it("excludes a skill line the user unchecked", () => {
    const withExcluded: DocumentModel = {
      sections: [
        {
          key: "skills",
          title: "Skills",
          included: true,
          entries: [
            { id: "skills-0", text: "Python", included: false, kind: "compact" },
            { id: "skills-1", text: "Figma", included: true, kind: "compact" },
          ],
        },
      ],
    };

    expect(collectDocumentSkillNames(withExcluded, "skills")).toEqual(["Figma"]);
  });

  it("skips a category header with no members", () => {
    const emptyCategory: DocumentModel = {
      sections: [
        {
          key: "skills",
          title: "Skills",
          included: true,
          entries: [
            { id: "skills-0", text: "Design", included: true, kind: "compact", runs: [{ text: "Design", bold: true }] },
          ],
        },
      ],
    };

    expect(collectDocumentSkillNames(emptyCategory, "skills")).toEqual([]);
  });

  it("falls back to the pre-migration one-entry-per-skill shape, skipping subheading rows", () => {
    const legacyShape: DocumentModel = {
      sections: [
        {
          key: "skills",
          title: "Skills",
          included: true,
          entries: [
            { id: "cat-1", text: "Design", included: true, kind: "subheading" },
            { id: "skill-1", text: "Roadmapping (Expertise)", included: true },
            { id: "skill-2", text: "UX Design", included: true },
          ],
        },
      ],
    };

    expect(collectDocumentSkillNames(legacyShape, "skills")).toEqual(["Roadmapping", "UX Design"]);
  });
});
