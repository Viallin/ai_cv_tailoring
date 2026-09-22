import type { AssembledCV, AssembledExperienceEntry, TailoredBullet } from "@/api/models";
import { ENTITY_CONFIGS } from "@/lib/entityConfigs";
import { SECTION_KEYS, sectionTitlesFor } from "@/lib/sections";

// Phase 16a — the on-screen A4 preview/editor's own data model, built
// purely client-side from AssembledCV (already sent on every successful
// generate). Not wired to /export yet (see the Phase 16a plan's "why 16a
// doesn't wire the new editor into Export" note) — this is preview-only
// state, ephemeral per generate, matching the confirmed "ephemeral for
// now" scope for all of Phase 16's edit state.
//
// The section/entry/bullet text and grouping here are built to match
// app/cv_markdown.py's actual CV-rendering conventions exactly (category-
// grouped skills/technologies, project-grouped Experience bullets) —
// not entityConfigs.ts's flat single-line summaries, which are for the
// profile-editing CRUD UI and were mistakenly reused here in the first
// pass, producing "Skill Name (Category)" instead of a real category
// subheading. `render_templated_docx` (app/cv_docx.py) mirrors this same
// structure so PDF/DOCX output stays consistent with each other.

// Phase 25 — one inline-styled span within a DocumentBlock. Structural
// mirror of domain/models.py's TextRun (same field-name-must-match-
// exactly rule as DocumentBlock's own evidence_id comment below).
export interface TextRun {
  text: string;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  link?: string;
}

export interface DocumentBlock {
  id: string;
  text: string;
  included: boolean;
  // is_gap Experience entries: never silently dropped *during
  // generation* — the invariant domain/models.py's Experience.is_gap
  // docstring actually describes. Does NOT mean the user can't exclude
  // one by hand afterward (Phase 28 follow-up: toggleEntryIncluded below
  // used to also block on this flag; reported directly that generation
  // not auto-dropping a gap was never meant to forbid excluding it too —
  // that's the user's own call). `locked` still means something for
  // structural editing (commands.ts's backspace-merge guard) and default
  // styling (EntryHeadingNodeView's italic) — only "can't be excluded"
  // is gone.
  locked?: boolean;
  // "subheading" = a category name (Skills/Technologies) or a project
  // name (Experience bullets) — rendered without a bullet marker,
  // distinctly styled by whichever component consumes it. Absent/"item"
  // = a normal bulleted line. Mirrors cv_markdown.py's own flat "slots"
  // approach (_render_grouped_by_category / _render_bullets_grouped_by_
  // project) rather than a third level of nesting.
  //
  // Post-31 — "compact" is a third value, entry-level only (never a
  // bullet): the whole entry is already a pre-joined, final line
  // (buildCompactSkillEntries below) — PrintSectionBlock.tsx checks for
  // it *before* its usual subheading-grouping pass and, when every
  // included entry in a section carries it, skips grouping entirely and
  // renders each entry standalone instead. Without that check, a
  // section with two already-compact entries (e.g. two separate
  // category lines) would get silently re-joined onto *one* line by the
  // same "flatten a run of ungrouped entries" logic that's exactly right
  // for the pre-Post-31 shape this value doesn't apply to.
  kind?: "item" | "subheading" | "compact";
  // Phase 17b — only set on Experience bullets (TailoredBullet.evidence_id,
  // see domain/models.py's docstring). Lets the editor join a bullet block
  // back to its BulletProvenance (lib/bulletProvenanceIndex.ts) for the
  // edited-bullet highlight/rationale popover/revert-to-original.
  // snake_case, not evidenceId — this whole shape crosses the JS/Python
  // boundary verbatim (see domain.models.PrintDocumentBlock's docstring),
  // no camelCase/snake_case translation exists anywhere on it; a camelCase
  // field here was silently dropped by the backend on every save,
  // disabling the Sparkles marker entirely — a real bug found from a
  // real generated draft that never showed one.
  evidence_id?: string;
  // Phase 25 — rich-run content model, no editor UI to produce this yet
  // (Phase 31; the A4 block editor — DocumentSectionBlock.tsx/
  // DocumentExperienceSection.tsx — still only edits `text` as one plain
  // string). `undefined` for every block today. When set, authoritative
  // over `text` for rendering — see domain.models.PrintDocumentBlock.runs's
  // docstring; only the read-only print/export renderers
  // (PrintExperienceSection.tsx, and PrintSectionBlock.tsx's Summary
  // case — see lib/textRuns.tsx) consume it this phase.
  runs?: TextRun[];
  // Paragraph-level, not a run — mirrors python-docx's `paragraph.alignment`.
  alignment?: "left" | "center" | "right";
}

export interface DocumentEntry extends DocumentBlock {
  // Only present for Experience entries — every other section's entries
  // are flat, single-line blocks with no nested structure.
  bullets?: DocumentBlock[];
  // Phase 30 — manual pagination control, confirmed with the user
  // directly: the automatic break-after/break-inside CSS rules
  // (index.css's `@media print` block, Phase 16c) are "hidden rules" a
  // person can't see or override from the editor — the only way to know
  // where a page will actually break is to export and look. This is the
  // deliberate escape hatch: when true, every export format forces a
  // real page break immediately before this entry. On `DocumentEntry`
  // (not the shared `DocumentBlock`, which bullets also use) since it's
  // only ever meaningful at entry granularity — a bullet-level version
  // was considered and explicitly ruled out for simplicity (see
  // docs/development_plan.md's Phase 30 notes).
  page_break_before?: boolean;
}

export interface DocumentSection {
  key: string;
  title: string;
  included: boolean;
  entries: DocumentEntry[];
  // Phase 30 — same manual-break escape hatch as
  // DocumentEntry.page_break_before, one level up: forces a break
  // immediately before this whole section (heading included).
  page_break_before?: boolean;
}

export interface DocumentModel {
  sections: DocumentSection[];
}

// entityConfigs.ts's `listField` values already match AssembledCV's own
// (underscored) field names (e.g. "portfolio_links", not the hyphenated
// pathSegment used in URLs) — so entries can be looked up directly by
// listField, no separate name-mapping table needed.
function summarizerFor(sectionKey: string): ((item: unknown) => string) | null {
  const config = ENTITY_CONFIGS.find((c) => c.listField === sectionKey);
  return config ? (config.summarize as (item: unknown) => string) : null;
}

// Matches ExperienceSection.tsx's summarizeExperience convention (Phase
// 15b-ii), adapted for AssembledExperienceEntry's shape (no `id`, only
// `experience_id`; bullets are TailoredBullet, not domain Experience
// bullets) — with one deliberate difference: no literal "[GAP]" suffix.
// ExperienceSection.tsx's own copy is Profile Explorer display text only,
// never exported; this one becomes DocumentBlock.text (buildExperienceSection
// below), which flows verbatim into the real exported document
// (app/cv_markdown.py::render_sections_from_document) and into write-back
// proposals (app/graph_writeback.py) — a real bug found via a real export:
// "[GAP]" was showing up as literal text in people's actual CVs. Gap
// status is already conveyed by `locked` (italic styling + a disabled,
// clearly-labeled checkbox in DocumentExperienceSection.tsx) — the same
// convention ui/main_window.py's own export has always used, with no
// bracket tag needed.
//
// Deliberately plain — never embeds a `[text](url)` link for `company_url`
// (Post-4.10 follow-up). This becomes `DocumentBlock.text`, the *fallback*
// `contentFromRuns` (lib/tiptap/converter.ts) renders only when `.runs` is
// absent; embedding Markdown syntax here doesn't get interpreted by
// anything on the frontend the way app/markdown_inline.py's
// parse_inline_runs interprets it server-side — found live: a company
// hyperlinked this way showed up on screen as the literal, unrendered
// "[Kefir](https://kefirgames.com/)" text. `experienceHeadingRuns` below
// is the real fix — a linked company belongs in `.runs`, not folded into
// this plain-text fallback.
//
// Exported for UnusedEvidencePanel.tsx's "Add to <Role>" button label —
// same summarized role text this file already builds for the role's own
// entry heading, so the button reads consistently with what's on screen.
export function summarizeAssembledExperience(entry: AssembledExperienceEntry): string {
  const company = entry.company ? ` — ${entry.company}` : "";
  const periodAndLocation = [entry.period, entry.location].filter(Boolean).join(", ");
  const period = periodAndLocation ? ` (${periodAndLocation})` : "";
  return `${entry.position}${company}${period}`;
}

// The `runs` counterpart to summarizeAssembledExperience above — only
// built when there's an actual link to add (entry.company_url), so every
// other entry keeps rendering exactly as before (plain `.text`, styled by
// EntryHeadingNodeView.tsx's structural bold/italic CSS, no runs needed at
// all). `bold`/`italic` are set on every run here (matching
// summarizeAssembledExperience's own always-em-dash-separated shape,
// deliberately not app/cv_markdown.py's gap-only comma convention — the
// two already disagree on that; this only needs to agree with its own
// plain-text sibling above) so app/cv_markdown.py:_serialize_runs' flat
// (non-templated) PDF/DOCX bridge keeps the same bold/italic heading look
// once `.runs` — authoritative over the automatic wrapping the runs-less
// branch would otherwise apply — is set at all; that function's own
// docstring already documents `link` taking priority over `bold`/`italic`
// on the *same* run when serializing back to flat Markdown (so the linked
// company name itself renders as a plain, unbold link there) — the
// templated DOCX/Playwright PDF paths render every run's full attribute
// set faithfully instead, with no such collapsing.
function experienceHeadingRuns(entry: AssembledExperienceEntry): TextRun[] | undefined {
  if (!entry.company || !entry.company_url) return undefined;
  const style = entry.is_gap ? { italic: true } : { bold: true };
  const periodAndLocation = [entry.period, entry.location].filter(Boolean).join(", ");
  const runs: TextRun[] = [
    { text: entry.position, ...style },
    { text: " — ", ...style },
    { text: entry.company, ...style, link: entry.company_url },
  ];
  if (periodAndLocation) {
    runs.push({ text: ` (${periodAndLocation})`, ...style });
  }
  return runs;
}

// Mirrors app/cv_markdown.py's _render_bullets_grouped_by_project exactly:
// bullets sharing a `project` tag are gathered under one italic
// "*Project Name*"-equivalent subheading block, inserted at the position
// of that project's *first* bullet, even if its bullets are interleaved
// with others in the source list — repeating the heading for every
// occurrence would be noisier than useful. Untagged bullets stay plain
// items in their original relative position.
//
// `projectUrls` (Post-4.10 follow-up, AssembledExperienceEntry.project_urls)
// adds a `link` run to a project heading whose project has a known URL —
// same `.text` (plain fallback) + `.runs` (the real link) split
// experienceHeadingRuns uses for the company name above, and for the same
// reason: `.text` alone is a dead end here since nothing on the frontend
// interprets `[text](url)` syntax embedded in it. A project heading is
// always italic (BulletNodeView.tsx's `kind === "subheading"` styling,
// unconditional — never bold, unlike the company case, which depends on
// gap status), so the run needs no `entry`/gap context, unlike
// experienceHeadingRuns.
function buildExperienceBullets(
  entryId: string,
  bullets: TailoredBullet[],
  projectUrls: Record<string, string>,
): DocumentBlock[] {
  const projectBullets = new Map<string, TailoredBullet[]>();
  const slots: ({ kind: "plain"; bullet: TailoredBullet } | { kind: "project"; project: string })[] = [];
  for (const bullet of bullets) {
    if (bullet.project) {
      if (!projectBullets.has(bullet.project)) {
        projectBullets.set(bullet.project, []);
        slots.push({ kind: "project", project: bullet.project });
      }
      projectBullets.get(bullet.project)!.push(bullet);
    } else {
      slots.push({ kind: "plain", bullet });
    }
  }

  const blocks: DocumentBlock[] = [];
  let plainIndex = 0;
  let projectIndex = 0;
  for (const slot of slots) {
    if (slot.kind === "plain") {
      blocks.push({
        id: `${entryId}-bullet-${plainIndex}`,
        text: slot.bullet.text,
        included: true,
        evidence_id: slot.bullet.evidence_id ?? undefined,
      });
      plainIndex += 1;
    } else {
      const projectUrl = projectUrls[slot.project];
      blocks.push({
        id: `${entryId}-project-${projectIndex}`,
        text: slot.project,
        included: true,
        kind: "subheading",
        runs: projectUrl ? [{ text: slot.project, italic: true, link: projectUrl }] : undefined,
      });
      (projectBullets.get(slot.project) ?? []).forEach((bullet, bulletIndex) => {
        blocks.push({
          id: `${entryId}-project-${projectIndex}-bullet-${bulletIndex}`,
          text: bullet.text,
          included: true,
          evidence_id: bullet.evidence_id ?? undefined,
        });
      });
      projectIndex += 1;
    }
  }
  return blocks;
}

function buildExperienceSection(cv: AssembledCV, titles: Record<string, string>): DocumentSection {
  const entries = (cv.experience ?? []).map((entry, index) => {
    const id = entry.experience_id ?? `experience-${index}`;
    return {
      id,
      text: summarizeAssembledExperience(entry),
      included: true,
      locked: entry.is_gap,
      bullets: buildExperienceBullets(id, entry.bullets ?? [], entry.project_urls ?? {}),
      runs: experienceHeadingRuns(entry),
    };
  });
  return { key: "experience", title: titles.experience, included: true, entries };
}

interface CategorizedItem {
  id: string;
  name: string;
  category?: string | null;
  proficiency?: string | null;
}

// Post-31 — one already-rendered run of consecutive same-category items
// (or one run of consecutive uncategorized items), the input shape
// buildCompactSkillEntries turns into a single compact DocumentEntry.
// `pageBreakBefore` carries exactly one flag into that entry: a
// category's own subheading entry's flag (mirrors
// PrintSectionBlock.tsx's `group.pageBreakBefore`/app/cv_markdown.py's
// `group.category_page_break_before`), or an uncategorized run's *first*
// member's own flag (mirrors that same component's/module's identical
// "only the first member has anywhere left to attach to" rule — Post-30
// polish, see docs/development_plan.md). A category with zero members
// (every one of them excluded, or — for buildCategoryGroupedSection's
// own fresh-from-AssembledCV caller — genuinely impossible, since
// nothing's excludable yet at generation time) is still a real group:
// `itemTexts: []`, rendered as just the bold label, no trailing colon.
interface SkillGroup {
  category: string | null;
  pageBreakBefore: boolean;
  itemTexts: string[];
}

// Builds one compact DocumentEntry per group — mirrors
// PrintSectionBlock.tsx's `groupEntriesByCategory`/`renderFlatGroup`
// exactly (`"; "` within a category, `" · "` across an uncategorized
// run, no bullet marker either way) and app/cv_markdown.py's identical
// backend convention, just moved from render time into the document
// model itself. A category group's bold label uses `runs` (Phase 25's
// existing rich-text mechanism — see DocumentBlock.runs's own docstring)
// rather than inventing a second formatting channel; a plain
// uncategorized-run entry needs no `runs` at all. `idPrefix` keeps
// generated ids stable-shaped and collision-free across a document
// (`skills-0`, `technologies-0`, ...) without the caller inventing one —
// these ids are new synthetic ones, not reused from whatever the
// group's own members used to have, since collapsing N old entries into
// one has no single "right" id to inherit.
function buildCompactSkillEntries(idPrefix: string, groups: SkillGroup[]): DocumentEntry[] {
  return groups
    .filter((group) => group.category != null || group.itemTexts.length > 0)
    .map((group, index) => {
      const id = `${idPrefix}-${index}`;
      if (group.category != null) {
        const joined = group.itemTexts.join("; ");
        return {
          id,
          text: joined ? `${group.category}: ${joined}` : group.category,
          included: true,
          // Post-31 — see DocumentBlock.kind's own docstring: marks this
          // entry as already a final, pre-joined line, so a renderer
          // never tries to group/join it with a sibling again.
          kind: "compact",
          page_break_before: group.pageBreakBefore,
          // Bold covers just the category name, not the ": " separator —
          // matching the legacy grouped-rendering convention exactly
          // (PrintSectionBlock.tsx's own `<strong>{category}</strong>: `
          // JSX). Real bug, caught by app/graph_writeback.py's own
          // `_CATEGORY_LINE_RE`: an earlier version bolded "Category: "
          // as one run, which _serialize_runs (app/cv_markdown.py) then
          // re-emits as `**Category: **members` — the colon *inside*
          // the closing `**`, which that regex (built around the
          // legacy `**Category**: members` shape) doesn't match, so a
          // compact category line's members silently stopped being
          // detected as "Add skill" write-back proposals.
          runs: joined
            ? [
                { text: group.category, bold: true },
                { text: `: ${joined}`, bold: false },
              ]
            : [{ text: group.category, bold: true }],
        };
      }
      return {
        id,
        text: group.itemTexts.join(" · "),
        included: true,
        kind: "compact",
        page_break_before: group.pageBreakBefore,
      };
    });
}

// Mirrors app/cv_markdown.py's _render_grouped_by_category exactly:
// cv.skills/cv.technologies are already grouped and ranked by category
// (app/cv_assembler.py's _rank_by_category), so this just starts a new
// SkillGroup whenever the category changes from the previous item
// (uncategorized items get `category: null`, still their own group,
// wherever that run naturally falls) — category is never inlined into
// an item's own text, only proficiency is. Nothing here is excludable
// yet (generation hasn't happened), so `pageBreakBefore` is always false
// and every group always has at least one item.
function buildCategoryGroupedSection(
  cv: AssembledCV,
  key: "skills" | "technologies",
  titles: Record<string, string>,
): DocumentSection {
  const items = (cv[key] ?? []) as CategorizedItem[];
  const groups: SkillGroup[] = [];

  for (const item of items) {
    const category = item.category ?? null;
    const text = item.proficiency ? `${item.name} (${item.proficiency})` : item.name;
    const last = groups[groups.length - 1];
    if (last && last.category === category) {
      last.itemTexts.push(text);
    } else {
      groups.push({ category, pageBreakBefore: false, itemTexts: [text] });
    }
  }

  return { key, title: titles[key], included: true, entries: buildCompactSkillEntries(key, groups) };
}

// Post-31 — a one-time, load-time migration for a draft saved before
// Skills/Technologies collapsed into compact paragraphs (see this
// section's own docstring above `SkillGroup`): the old shape stored one
// DocumentEntry per skill, plus a `kind: "subheading"` entry per category
// name; the new shape stores one already-compact DocumentEntry per
// category (or per run of uncategorized skills) instead. Reuses
// buildCompactSkillEntries so a migrated document renders byte-for-byte
// the same compact line every export already produced from the old
// shape — this only changes what's *stored*, never what's shown.
//
// `needsSkillsCompaction` decides whether there's anything to collapse
// at all: any included entry that isn't already `kind: "compact"` (see
// DocumentBlock.kind's own docstring) — an explicit marker, not a count-
// based guess, so this stays correct without needing a separate schema-
// version flag anywhere (this codebase has none — see domain/models.py's
// own history of adding fields with plain optional-default back-compat
// instead). An empty/all-excluded section has nothing to collapse
// either. Deliberately checked *before* re-deriving groups, not just
// diffed after the fact — an already-migrated section would otherwise
// get needless new synthetic ids from buildCompactSkillEntries even
// though nothing about it actually needed to change.
function needsSkillsCompaction(entries: DocumentEntry[]): boolean {
  return entries.filter((entry) => entry.included).some((entry) => entry.kind !== "compact");
}

// Derives one SkillGroup per included category header (or per run of
// included, header-less entries) from the *old* shape — mirrors
// PrintSectionBlock.tsx's own `groupEntriesByCategory` exactly, right
// down to filtering to `included` entries first: an excluded header is
// treated as if it were never there at all (its own members are already
// separately excluded too, by toggleEntryIncluded's cascade rule above),
// so whatever follows it just starts (or continues) a plain, header-less
// group instead of erroring or skipping content.
function deriveSkillGroupsFromLegacyEntries(entries: DocumentEntry[]): SkillGroup[] {
  const groups: SkillGroup[] = [];
  let current: SkillGroup | null = null;
  for (const entry of entries.filter((entry) => entry.included)) {
    if (entry.kind === "subheading") {
      current = { category: entry.text, pageBreakBefore: entry.page_break_before ?? false, itemTexts: [] };
      groups.push(current);
      continue;
    }
    if (current == null) {
      current = { category: null, pageBreakBefore: entry.page_break_before ?? false, itemTexts: [] };
      groups.push(current);
    }
    current.itemTexts.push(entry.text);
  }
  return groups;
}

// The section-level half of the migration — returns `section` itself,
// unchanged (same reference), when there's nothing to collapse, so a
// caller can cheaply tell "did this change" via `!==` without a deep
// comparison.
export function collapseSkillsSectionIfNeeded(section: DocumentSection): DocumentSection {
  if ((section.key !== "skills" && section.key !== "technologies") || !needsSkillsCompaction(section.entries)) {
    return section;
  }
  const groups = deriveSkillGroupsFromLegacyEntries(section.entries);
  return { ...section, entries: buildCompactSkillEntries(section.key, groups) };
}

// Document-level entry point for the migration — the one a draft-load
// call site actually calls. Compare the result to the document it was
// given (`!==` per section is enough, since collapseSkillsSectionIfNeeded
// only ever returns a new object when it actually changed something) to
// decide whether the migrated document is worth persisting back.
export function collapseSkillsAndTechnologiesIfNeeded(document: DocumentModel): DocumentModel {
  return { sections: document.sections.map(collapseSkillsSectionIfNeeded) };
}

// Post-4.10 fixes round 3 — the flat list of skill/technology *names*
// currently visible in the document's Skills/Technologies section, read
// back out of whichever shape it's actually in (compact, post-Post-31, or
// the pre-migration one-entry-per-skill shape, handled defensively in
// case this ever runs before collapseSkillsAndTechnologiesIfNeeded gets a
// chance to migrate an old draft). Only `included` entries count — an
// excluded skill line shouldn't un-flag its own gap on the next recheck.
//
// Feeds a "recheck" job's `document_skills`/`document_technologies`
// (api/routes/jobs.py) so the Matching stage sees what this *draft*
// currently lists, not just the stored Candidate profile's own Skills/
// Technologies — reported directly: adding or deleting a skill line
// straight in the editor had no effect on a subsequent re-check, since
// that call always fell back to the profile.
//
// Reverses buildCompactSkillEntries' own joining exactly: a category
// entry's `runs` carry `[{category, bold:true}]` (no members) or
// `[{category, bold:true}, {": "+joined, bold:false}]`, joined with
// "; "; an uncategorized run has no `runs` and is joined with " · "
// instead (see that function's own docstring for why the separator
// differs). `(proficiency)` is stripped from each name the same way
// _real_skill_names never included it — this is grounding text for an LLM
// prompt, not data that round-trips anywhere, so recovering the name only
// approximately (a name that itself contains parentheses) is an
// acceptable trade rather than inventing a second storage shape just for
// this.
export function collectDocumentSkillNames(document: DocumentModel, sectionKey: "skills" | "technologies"): string[] {
  const section = document.sections.find((s) => s.key === sectionKey);
  if (section == null) {
    return [];
  }

  const stripProficiency = (text: string) => text.replace(/\s*\([^)]*\)\s*$/, "").trim();
  const names: string[] = [];
  for (const entry of section.entries) {
    if (!entry.included || entry.kind === "subheading") {
      continue;
    }
    if (entry.kind === "compact") {
      if (entry.runs != null) {
        if (entry.runs.length < 2) {
          continue; // A category header with no members.
        }
        const joined = entry.runs[1].text.replace(/^:\s*/, "");
        joined.split("; ").forEach((name) => names.push(stripProficiency(name)));
      } else {
        entry.text.split(" · ").forEach((name) => names.push(stripProficiency(name)));
      }
    } else {
      names.push(stripProficiency(entry.text));
    }
  }
  return names.filter((name) => name !== "");
}

function buildSummarySection(cv: AssembledCV, titles: Record<string, string>): DocumentSection {
  return {
    key: "summary",
    title: titles.summary,
    included: true,
    entries: [{ id: "summary", text: cv.summary ?? "", included: true }],
  };
}

function buildListSection(cv: AssembledCV, key: string, titles: Record<string, string>): DocumentSection {
  const summarize = summarizerFor(key);
  const items = ((cv as unknown as Record<string, { id: string }[] | undefined>)[key] ?? []) as {
    id: string;
  }[];
  const entries: DocumentEntry[] = items.map((item) => ({
    id: item.id,
    text: summarize ? summarize(item) : "",
    included: true,
  }));
  return { key, title: titles[key], included: true, entries };
}

export function buildDocumentFromAssembledCv(cv: AssembledCV): DocumentModel {
  // Version 4, Phase 4.3: resolved once here (cv.language), not read off
  // a module-level constant — see lib/sections.ts's sectionTitlesFor.
  const titles = sectionTitlesFor(cv.language);
  const sections = SECTION_KEYS.map((key) => {
    if (key === "summary") return buildSummarySection(cv, titles);
    if (key === "experience") return buildExperienceSection(cv, titles);
    if (key === "skills" || key === "technologies") return buildCategoryGroupedSection(cv, key, titles);
    return buildListSection(cv, key, titles);
  });
  return { sections };
}

// --- Pure edit helpers — no component/DOM knowledge, unit-testable in
// isolation. All return a new DocumentModel; none mutate their input. ---

function mapSection(document: DocumentModel, sectionKey: string, fn: (section: DocumentSection) => DocumentSection): DocumentModel {
  return {
    sections: document.sections.map((section) => (section.key === sectionKey ? fn(section) : section)),
  };
}

export function toggleSectionIncluded(document: DocumentModel, sectionKey: string): DocumentModel {
  return mapSection(document, sectionKey, (section) => ({ ...section, included: !section.included }));
}

// Phase 30 — manual pagination control (see DocumentSection.page_break_before's
// own docstring). Same shape as toggleSectionIncluded/toggleEntryIncluded —
// a plain flip, no cascade, no interaction with `included`/`locked`.
export function toggleSectionPageBreak(document: DocumentModel, sectionKey: string): DocumentModel {
  return mapSection(document, sectionKey, (section) => ({ ...section, page_break_before: !section.page_break_before }));
}

export function toggleEntryPageBreak(document: DocumentModel, sectionKey: string, entryId: string): DocumentModel {
  return mapSection(document, sectionKey, (section) => ({
    ...section,
    entries: section.entries.map((entry) =>
      entry.id === entryId ? { ...entry, page_break_before: !entry.page_break_before } : entry,
    ),
  }));
}

// Unchecking a category header (Skills/Technologies' `kind ===
// "subheading"` entries — see buildCategoryGroupedSection) also unchecks
// every member below it, down to the next header or the section's end.
// Reported directly: without this, excluding just the header entry still
// left its members `included: true`, but PrintSectionBlock.tsx's
// grouping only starts a new category on an *included* subheading (it
// filters to included entries before grouping) — so those members would
// silently render under whatever category preceded the excluded one, or
// as ungrouped bullets, on export. Deliberately one-directional:
// re-checking a header does NOT re-check its members back on, so a
// member the user separately, deliberately excluded stays excluded —
// only the header's own checkbox cascades, and only when turning it off.
//
// `target.locked` (a career-Gap entry) no longer blocks this. Reported
// directly: not auto-dropping a Gap during generation was only ever
// meant to guarantee it stays *visible by default*, never to forbid the
// user from excluding one by hand afterward — that's their call, same as
// any other entry (EntryNodeView.tsx's own checkbox stopped disabling
// itself for the same reason). `locked` still means something elsewhere
// — commands.ts's backspace-merge guard, EntryHeadingNodeView's italic
// styling, and the subheading-cascade a few lines below (a *different*
// locked concept, Skills/Technologies members, deliberately untouched
// here) — only this one always-block-the-toggle behavior is gone.
export function toggleEntryIncluded(document: DocumentModel, sectionKey: string, entryId: string): DocumentModel {
  return mapSection(document, sectionKey, (section) => {
    const index = section.entries.findIndex((entry) => entry.id === entryId);
    const target = index === -1 ? undefined : section.entries[index];
    if (target == null) {
      return section;
    }
    const nowIncluded = !target.included;
    const entries = section.entries.map((entry, i) => (i === index ? { ...entry, included: nowIncluded } : entry));
    if (target.kind === "subheading" && !nowIncluded) {
      for (let i = index + 1; i < entries.length && entries[i].kind !== "subheading"; i++) {
        if (!entries[i].locked) {
          entries[i] = { ...entries[i], included: false };
        }
      }
    }
    return { ...section, entries };
  });
}

export function toggleBulletIncluded(
  document: DocumentModel,
  sectionKey: string,
  entryId: string,
  bulletId: string,
): DocumentModel {
  return mapSection(document, sectionKey, (section) => ({
    ...section,
    entries: section.entries.map((entry) =>
      entry.id === entryId
        ? {
            ...entry,
            bullets: entry.bullets?.map((bullet) =>
              bullet.id === bulletId ? { ...bullet, included: !bullet.included } : bullet,
            ),
          }
        : entry,
    ),
  }));
}

// reorderEntries/reorderBullets (dnd-kit-index-array reordering) and
// their shared moveItem helper lived here through Phase 26 — deleted in
// Phase 27, superseded by real ProseMirror node drags (schema.ts's
// `draggable: true` + lib/tiptap/plugins.ts's dragScopeGuardPlugin):
// unlike every other mutation here, a drag is a live, continuous native
// interaction with no discrete "fromIndex/toIndex" call site to make —
// ProseMirror performs the move directly and DocumentEditor.tsx's
// existing `onUpdate` reads the result back, the same way keystrokes
// already work. Nothing called these two functions once Phase 26's own
// dnd-kit `DndContext` was removed; see git history for the prior
// implementation if it's ever needed for reference.

export function updateEntryText(document: DocumentModel, sectionKey: string, entryId: string, text: string): DocumentModel {
  return mapSection(document, sectionKey, (section) => ({
    ...section,
    entries: section.entries.map((entry) => (entry.id === entryId ? { ...entry, text } : entry)),
  }));
}

export function updateBulletText(
  document: DocumentModel,
  sectionKey: string,
  entryId: string,
  bulletId: string,
  text: string,
): DocumentModel {
  return mapSection(document, sectionKey, (section) => ({
    ...section,
    entries: section.entries.map((entry) =>
      entry.id === entryId
        ? { ...entry, bullets: entry.bullets?.map((bullet) => (bullet.id === bulletId ? { ...bullet, text } : bullet)) }
        : entry,
    ),
  }));
}

// Appends a brand-new bullet to one Experience entry — the one document
// mutation this editor didn't have before (only toggle/reorder/edit-
// existing-text did). Two real callers: a blank manually-typed bullet
// (evidence_id omitted) for hand-addressing a Gap the AI didn't cover, and
// an Unused-Evidence item's exact text (evidence_id set, so it can still
// be looked up in lib/bulletProvenanceIndex.ts later) via "Add to Role" in
// UnusedEvidencePanel.tsx. Always untailored, verbatim text — inventing a
// tailored rewrite for it would need a real plan/rewrite pass behind it.
export function addBullet(
  document: DocumentModel,
  sectionKey: string,
  entryId: string,
  text: string,
  evidenceId?: string,
): DocumentModel {
  const newBullet: DocumentBlock = {
    id: `${entryId}-manual-${crypto.randomUUID()}`,
    text,
    included: true,
    evidence_id: evidenceId,
  };
  return mapSection(document, sectionKey, (section) => ({
    ...section,
    entries: section.entries.map((entry) =>
      entry.id === entryId ? { ...entry, bullets: [...(entry.bullets ?? []), newBullet] } : entry,
    ),
  }));
}
