import { useRelinkSkillEvidenceJob } from "@/api/jobs";
import { Button } from "@/components/ui/button";

interface ReevaluateSkillLinksButtonProps {
  candidateId: string;
}

// The on-demand "Re-evaluate Skill Dependencies" action — re-derives every
// Skill's/Technology's evidence_ids from the profile's current data via one
// scoped LLM call (app/pipeline.py::run_skill_evidence_relink), replacing
// each item's links wholesale. Confirmed as an on-demand action, not
// automatic per-edit (too frequent/costly) — see docs/development_plan.md's
// Phase 21 addendum. No success toast: the refreshed "Supported by
// achievements: N" counts under Skills/Technologies (EntitySection.tsx)
// are the visible proof — same minimalism as DraftScreen.tsx's "Re-check
// Gaps" button, which this mirrors exactly.
export function ReevaluateSkillLinksButton({ candidateId }: ReevaluateSkillLinksButtonProps) {
  const relinkJob = useRelinkSkillEvidenceJob();
  const busy = relinkJob.isSubmitting || relinkJob.isRunning;

  return (
    <Button variant="outline" size="xs" onClick={() => relinkJob.relink(candidateId)} disabled={busy}>
      {busy ? "Re-evaluating…" : "Re-evaluate Skill Dependencies"}
    </Button>
  );
}
