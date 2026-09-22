import type { Evidence, Experience } from "@/api/models";

export function buildEvidenceById(evidence: Evidence[]): Map<string, Evidence> {
  return new Map(evidence.map((item) => [item.id, item]));
}

// "Company, Position, Project" for one Evidence item, resolved from its
// experience_id/experience_project_id against the candidate's own
// Experience list — used to group an Evidence item's origin as one
// heading instead of repeating source_context (usually just a "Company,
// Project: <bullet text again>" restatement of the bullet itself) per
// item. Returns null when the item has no experience_id at all (a
// standalone/summary-level Evidence item) — nothing to resolve.
export function describeEvidenceSource(evidence: Evidence, experience: Experience[]): string | null {
  if (evidence.experience_id == null) {
    return null;
  }
  const role = experience.find((entry) => entry.id === evidence.experience_id);
  if (role == null) {
    return null;
  }
  const project =
    evidence.experience_project_id != null
      ? role.projects?.find((p) => p.id === evidence.experience_project_id)
      : undefined;
  return [role.company, role.position, project?.name].filter(Boolean).join(", ");
}
