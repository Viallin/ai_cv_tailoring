import { useMemo } from "react";

import { useCandidate } from "@/api/candidates";
import { useEvidence } from "@/api/evidence";
import { EntitySection, type EntityItem } from "@/components/EntitySection";
import { ExperienceSection } from "@/components/ExperienceSection";
import { ProfileExportPanel } from "@/components/ProfileExportPanel";
import { ProfileHeader } from "@/components/ProfileHeader";
import { ReevaluateSkillLinksButton } from "@/components/ReevaluateSkillLinksButton";
import { ENTITY_CONFIGS } from "@/lib/entityConfigs";
import { buildEvidenceById } from "@/lib/evidenceIndex";
import { sectionTitlesFor } from "@/lib/sections";

interface ProfileViewProps {
  candidateId: string | null;
}

// Orchestrates ProfileHeader + ExperienceSection + one EntitySection per
// lib/entityConfigs.ts entry — the profile-editing equivalent of
// CvWorkflowView. Evidence is fetched separately (it isn't embedded in the
// Candidate object) and indexed once here, then threaded down to
// EntitySection's per-row "backed by" summary (skills/technologies).
export function ProfileView({ candidateId }: ProfileViewProps) {
  const { data: candidate, isLoading } = useCandidate(candidateId);
  const { data: evidence } = useEvidence(candidateId);

  const evidenceById = useMemo(() => buildEvidenceById(evidence ?? []), [evidence]);

  if (candidateId == null) {
    return <p className="text-sm text-muted-foreground">Select a candidate to view their profile.</p>;
  }
  if (isLoading || candidate == null) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  // Version 4, Phase 4.3: resolved once here (not read off each
  // EntityConfig directly — ENTITY_CONFIGS is built once at module load,
  // before any candidate/language is known) and passed down as a plain
  // string prop to every section that needs a localized heading.
  const sectionTitles = sectionTitlesFor(candidate.language);

  return (
    // Post-4.10 nav redesign, round 3 — the standalone CV export
    // page/tab is gone; ProfileExportPanel is a sticky rail here instead
    // (same lg:sticky pattern DraftScreen.tsx's own action rail uses),
    // so "Export CV" and "Your drafts" are always in view next to the
    // profile rather than one click away behind a button that didn't
    // say drafts lived there. Stacks to a single column below `lg`,
    // exactly like DraftScreen's own CV/rail split.
    <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
      <div className="min-w-0 flex-1 space-y-6">
        <ProfileHeader candidateId={candidateId} candidate={candidate} />
        <ExperienceSection
          candidateId={candidateId}
          experience={candidate.experience ?? []}
          evidence={evidence ?? []}
          language={candidate.language}
        />
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">
            Skill/Technology "backed by" links are explainability only — re-evaluate them any time.
          </p>
          <ReevaluateSkillLinksButton candidateId={candidateId} />
        </div>
        {ENTITY_CONFIGS.map((config) => (
          <EntitySection
            key={config.pathSegment}
            candidateId={candidateId}
            config={config}
            title={sectionTitles[config.sectionKey]}
            // listField is always one of the 11 array entity fields by
            // construction of entityConfigs.ts — keyof Candidate is too
            // broad for TS to narrow that statically, hence the cast.
            items={((candidate[config.listField] as unknown as EntityItem[]) ?? [])}
            evidenceById={evidenceById}
            experience={candidate.experience ?? []}
          />
        ))}
      </div>

      <ProfileExportPanel
        candidateId={candidateId}
        language={candidate.language}
        className="w-full shrink-0 lg:sticky lg:top-14 lg:w-80 lg:max-h-[calc(100vh-4rem)] lg:overflow-y-auto"
      />
    </div>
  );
}
