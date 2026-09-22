import type { DocumentModel } from "./structuredDocument";

// Phase 24 — one entry describing a manually-excluded piece of the
// document (an entry, or a single bullet within an Experience entry).
// `bulletId` is only set for the bullet case; an excluded top-level entry
// (e.g. a whole Experience role, or a Skills/Education/etc. row) is
// represented once, without recursing into whatever's nested inside it —
// see collectExcludedContent's docstring for why.
export interface ExcludedContentItem {
  sectionKey: string;
  sectionTitle: string;
  entryId: string;
  bulletId?: string;
  text: string;
}

// Everything the user has unchecked (entry- or bullet-level, any
// section) — the data DocumentSectionBlock.tsx/DocumentExperienceSection.tsx
// now skip rendering entirely instead of showing struck-through in place.
// Reads straight off the live DocumentModel's own text rather than an
// Evidence record: unlike lib/documentEvidence.ts's collectExcludedEvidenceIds
// (Evidence-only, Experience-only), most sections have no Evidence behind
// their entries at all (Skills/Education/Contacts/etc. were never
// Evidence-linked), so this has to work for every section generically.
//
// Two deliberate scoping choices, both mirroring what's already visible/
// recoverable elsewhere in the UI rather than re-deriving it here:
// * A fully-excluded *section* (`section.included === false`) is skipped
//   entirely — its own checkbox stays visible right next to its heading
//   (DocumentSectionBlock.tsx/DocumentExperienceSection.tsx always render
//   the header regardless of `included`), so it already has a working
//   restore path and doesn't need a stash entry too.
// * An excluded top-level entry is listed once, not walked into — its
//   nested bullets (if any) keep whatever `included` value they already
//   had and simply reappear alongside it once the entry itself is
//   restored (toggleEntryIncluded doesn't touch them, so nothing is
//   lost); listing every nested bullet separately while the parent is
//   already gone would just be noise with no independent restore target
//   (the row that would host that checkbox isn't rendered either).
export function collectExcludedContent(document: DocumentModel): ExcludedContentItem[] {
  const items: ExcludedContentItem[] = [];
  for (const section of document.sections) {
    if (!section.included) {
      continue;
    }
    for (const entry of section.entries) {
      if (!entry.included) {
        items.push({ sectionKey: section.key, sectionTitle: section.title, entryId: entry.id, text: entry.text });
        continue;
      }
      for (const bullet of entry.bullets ?? []) {
        if (!bullet.included) {
          items.push({
            sectionKey: section.key,
            sectionTitle: section.title,
            entryId: entry.id,
            bulletId: bullet.id,
            text: bullet.text,
          });
        }
      }
    }
  }
  return items;
}
