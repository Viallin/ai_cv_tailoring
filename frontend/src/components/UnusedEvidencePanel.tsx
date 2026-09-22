import type { AssembledExperienceEntry, BulletProvenanceReport, Evidence } from "@/api/models";
import { Button } from "@/components/ui/button";
import { summarizeAssembledExperience } from "@/lib/structuredDocument";

interface UnusedEvidencePanelProps {
  provenance: BulletProvenanceReport | null;
  // Phase 18b — for resolving an Evidence item's experience_id to a role
  // label ("Add to <Role>"). Omit (or pass []) when there's no assembled
  // CV yet; every button then simply doesn't render.
  experience?: AssembledExperienceEntry[];
  // Omitted entirely before a CV has been generated, same convention as
  // GapsPanel's onDismiss — no add affordance makes sense with nothing to
  // add to yet.
  onAddToRole?: (evidence: Evidence, experienceId: string) => void;
  // Evidence ids already backing a bullet somewhere in the current
  // document (lib/documentEvidence.ts::collectUsedEvidenceIds) — filtered
  // out of the list below so clicking "Add to Role" once removes that
  // item, instead of staying clickable and inserting a duplicate bullet
  // on every click. Omit (or pass an empty Set) to show the full list,
  // e.g. before the document has finished its first render.
  usedEvidenceIds?: Set<string>;
}

// Read-only except for one action — Phase 17: surfaces the Evidence items
// that never made it into a bullet in the assembled CV (plan-removed, or
// never linked to a role at all — see app/bullet_provenance.py's
// unused_evidence docstring), as an informational "didn't make the cut"
// nudge. Phase 18b added "Add to Role": only for items with an
// experience_id matching a real role (the only case with an unambiguous
// target bullet list) — inserts the evidence's exact text as a new,
// untailored bullet (structuredDocument.ts::addBullet), never a rewritten
// one, since there's no rewrite-plan reasoning behind a manually-added
// bullet. An Evidence item with no role link (e.g. extracted from the
// candidate's own summary or a standalone Key Project) gets no button —
// there's no single sensible bullet list to add it to.
export function UnusedEvidencePanel({
  provenance,
  experience = [],
  onAddToRole,
  usedEvidenceIds,
}: UnusedEvidencePanelProps) {
  if (provenance == null) {
    return null;
  }

  const unused = (provenance.unused_evidence ?? []).filter((item) => !usedEvidenceIds?.has(item.id));
  if (unused.length === 0) {
    return <p className="text-sm text-muted-foreground">Every Evidence item made it into this CV.</p>;
  }

  const roleById = new Map(experience.filter((entry) => entry.experience_id).map((entry) => [entry.experience_id!, entry]));

  return (
    <div className="space-y-2 text-sm">
      <p className="text-muted-foreground">Didn't make the cut for this vacancy — add manually?</p>
      {unused.map((item) => {
        const role = item.experience_id ? roleById.get(item.experience_id) : undefined;
        return (
          <div key={item.id} className="space-y-1.5 rounded-lg border bg-muted/40 p-3">
            <p>{item.text}</p>
            {item.source_context && <p className="text-xs text-muted-foreground">{item.source_context}</p>}
            {role && onAddToRole && (
              // Long role labels ("Add to Senior Engineer — Some Long
              // Company Name (Jan 2020 – Mar 2024)") shouldn't force the
              // card wider than its column or get clipped — Button's base
              // styles are whitespace-nowrap/shrink-0 (right, for normal
              // short-label buttons elsewhere), so this instance opts back
              // into wrapping: full-width, auto height, text wraps onto as
              // many lines as it needs instead of overflowing sideways.
              <Button
                type="button"
                variant="outline"
                size="xs"
                className="h-auto w-full min-w-0 justify-start whitespace-normal break-words text-left"
                onClick={() => onAddToRole(item, role.experience_id!)}
              >
                Add to {summarizeAssembledExperience(role)}
              </Button>
            )}
          </div>
        );
      })}
    </div>
  );
}
