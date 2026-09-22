import type { BulletProvenance, BulletProvenanceReport } from "@/api/models";

// Mirrors evidenceIndex.ts's buildEvidenceById exactly — a Map keyed by
// evidence_id, so DocumentExperienceSection can look up a bullet block's
// provenance in O(1) via its DocumentBlock.evidence_id.
export function buildProvenanceByEvidenceId(
  report: BulletProvenanceReport | null,
): Map<string, BulletProvenance> {
  return new Map((report?.bullets ?? []).map((item) => [item.evidence_id, item]));
}
