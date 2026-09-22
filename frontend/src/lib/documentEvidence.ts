import type { DocumentModel } from "./structuredDocument";

// Phase 18: the Evidence ids no longer backing anything in the current
// document — a bullet whose own toggle, its role entry's toggle, or the
// whole Experience section's toggle is off. Only Experience bullets ever
// carry an evidence_id (see structuredDocument.ts's DocumentBlock
// docstring), so every other section is irrelevant here. Fed straight
// into a "recheck" job's excluded_evidence_ids (api/routes/jobs.py) —
// see app/pipeline.py::run_gap_recheck's docstring for what this can't
// represent (a hand-typed bullet, or Evidence never tied to a bullet at
// all — both stay "active" by default, a known, documented limit).
export function collectExcludedEvidenceIds(document: DocumentModel): string[] {
  const experience = document.sections.find((section) => section.key === "experience");
  if (experience == null) {
    return [];
  }

  const excluded: string[] = [];
  for (const entry of experience.entries) {
    const entryExcluded = !experience.included || !entry.included;
    for (const bullet of entry.bullets ?? []) {
      if (bullet.evidence_id == null) {
        continue;
      }
      if (entryExcluded || !bullet.included) {
        excluded.push(bullet.evidence_id);
      }
    }
  }
  return excluded;
}

// Every Evidence id already backing a bullet somewhere in the document —
// unlike collectExcludedEvidenceIds above, this doesn't care about
// included/locked state at all, since the point is just "does a bullet
// for this Evidence already exist" (UnusedEvidencePanel.tsx's "Add to
// Role" uses this to hide an item once added, so a second click can't
// insert a duplicate bullet for the same Evidence — reported directly,
// from a real draft where repeated clicks kept appending the same
// bullet). A bullet added this way stays counted even if later excluded
// or the role itself is excluded — re-adding a duplicate is exactly what
// this prevents; the user can still edit/remove it directly in the
// Experience section instead.
// Post-4.10 fixes round 3 — the evidence_id -> current text of every
// Experience bullet still tied to an Evidence item, regardless of
// included state (mirrors collectUsedEvidenceIds' own "don't care about
// included" reasoning — an excluded bullet's edited text is harmless to
// send, since api/routes/jobs.py's run_gap_recheck drops it from the
// active-evidence list before this override would ever apply to it).
// Fed into a "recheck" job's `edited_bullet_text` (api/routes/jobs.py) so
// the Matching stage sees what the bullet actually says in the document
// right now, not the stale text still stored on the profile's Evidence
// item — reported directly: rewriting a bullet by hand to cover a gap
// didn't change anything on the next re-check, because that call had
// never been told about the edit at all.
export function collectEditedBulletText(document: DocumentModel): Record<string, string> {
  const experience = document.sections.find((section) => section.key === "experience");
  if (experience == null) {
    return {};
  }

  const edited: Record<string, string> = {};
  for (const entry of experience.entries) {
    for (const bullet of entry.bullets ?? []) {
      if (bullet.evidence_id != null) {
        edited[bullet.evidence_id] = bullet.text;
      }
    }
  }
  return edited;
}

// The text of every hand-typed Experience bullet (no evidence_id — a
// manually added line, see structuredDocument.ts's addBullet) that's
// still actually included. Unlike collectEditedBulletText above, this one
// *does* care about included state: there's no id-keyed override to skip
// server-side the way an excluded evidence-linked bullet gets dropped, so
// an excluded hand-typed bullet has to be left out here instead, or its
// content would keep counting toward the recheck after being toggled off.
// Fed into a "recheck" job's `manual_bullet_text` — each becomes its own
// synthetic Evidence item for that one matching call (run_gap_recheck's
// own docstring).
export function collectManualBulletText(document: DocumentModel): string[] {
  const experience = document.sections.find((section) => section.key === "experience");
  if (experience == null) {
    return [];
  }

  const manual: string[] = [];
  for (const entry of experience.entries) {
    const entryExcluded = !experience.included || !entry.included;
    if (entryExcluded) {
      continue;
    }
    for (const bullet of entry.bullets ?? []) {
      if (bullet.evidence_id == null && bullet.included && bullet.text.trim() !== "") {
        manual.push(bullet.text);
      }
    }
  }
  return manual;
}

export function collectUsedEvidenceIds(document: DocumentModel): string[] {
  const experience = document.sections.find((section) => section.key === "experience");
  if (experience == null) {
    return [];
  }

  const used: string[] = [];
  for (const entry of experience.entries) {
    for (const bullet of entry.bullets ?? []) {
      if (bullet.evidence_id != null) {
        used.push(bullet.evidence_id);
      }
    }
  }
  return used;
}
