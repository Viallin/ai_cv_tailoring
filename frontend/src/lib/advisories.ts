import type { DocumentModel } from "@/lib/structuredDocument";

// Phase 20 — deterministic heuristics over the live, edited DocumentModel.
// "Deterministic" is the operative word: no LLM call, no similarity
// scoring, just plain arithmetic over what's already on screen, so these
// recompute instantly on every edit. LLM-assisted advice ("this bullet is
// vague") is an explicit optional stretch in docs/development_plan.md's
// Phase 20 scope, not built here.

export interface AdvisoryChip {
  id: string;
  message: string;
}

// Phase 31 (follow-up) — reported directly, two separate complaints in
// one: the page-count chip was flatly wrong (claimed "~2 pages" for a
// real 4-page document) and the chip row itself reads as stray, unlabeled
// floating text with no visual connection to the page above it. The
// count's own wrongness had a real, findable cause: it used a crude
// chars-per-line/lines-per-page arithmetic estimate (removed below) that
// predates Phase 29's `lib/tiptap/pageBreaks.ts` — a genuine DOM-
// measurement-based page-break system that already exists and is
// visibly more accurate (it's what draws the "↓ Page N" markers in the
// editor itself) — the two were never reconciled once the better one
// existed. Rather than wire this component up to that DOM-dependent
// measurement (a real option, but a bigger change — pageBreaks.ts needs
// the actual rendered page element, not just the DocumentModel this
// component receives), confirmed directly with the user that the count
// isn't worth having at all: removed outright, along with
// findEmptySections below (same conversation) — an included-but-empty
// section is exactly what export already silently skips
// (app/cv_markdown.py's own `if lines: sections[key] = ...`), so
// flagging it added noise without changing what to do about it. Only
// the bullet-count-outlier checks below survived — the ones that
// actually point at something worth fixing.

// ----- bullets-per-role outliers --------------------------------------------

// Experience-only: a career-gap entry (`locked: true`, see structuredDocument
// .ts::buildExperienceSection) has no achievements by design and is never
// flagged. A plain, explainable threshold, not a statistical model —
// matching "deterministic heuristics" over anything ML-flavored.
export function findBulletCountOutliers(document: DocumentModel): AdvisoryChip[] {
  const experience = document.sections.find((section) => section.key === "experience");
  if (experience == null || !experience.included) {
    return [];
  }

  const roles = experience.entries.filter((entry) => entry.included && !entry.locked);
  const bulletCounts = roles.map(
    (entry) => (entry.bullets ?? []).filter((bullet) => bullet.included && bullet.kind !== "subheading").length,
  );
  if (bulletCounts.length === 0) {
    return [];
  }
  const average = bulletCounts.reduce((sum, count) => sum + count, 0) / bulletCounts.length;

  const chips: AdvisoryChip[] = [];
  roles.forEach((entry, index) => {
    const count = bulletCounts[index];
    if (count === 0) {
      chips.push({ id: `outlier-empty-${entry.id}`, message: `"${entry.text}" has no achievements listed.` });
    } else if (count >= 6 && count > average * 1.8) {
      chips.push({
        id: `outlier-many-${entry.id}`,
        message: `"${entry.text}" has ${count} bullets — notably more than the other roles.`,
      });
    }
  });
  return chips;
}

// ----- combined --------------------------------------------------------------

export function buildAdvisoryChips(document: DocumentModel): AdvisoryChip[] {
  return findBulletCountOutliers(document);
}
