import { Lock, Unlock } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useEntityMutations } from "@/api/entities";
import type { Evidence, Experience, ExperienceProject } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { LINK_CLASSNAME } from "@/lib/linkify";
import { cn } from "@/lib/utils";

interface ExperienceEvidencePanelProps {
  candidateId: string;
  experience: Experience;
  evidence: Evidence[];
}

function showError(error: unknown): void {
  const category = error instanceof ApiError ? error.category : "Error";
  const message = error instanceof ApiError ? error.message : "Could not update the locked bullet.";
  toast.error(category, { description: message });
}

// Read/edit "Responsibilities & Achievements" panel. Renders nothing when
// this role has no linked Evidence, which is true for most manually-added
// (non-ingested) Experience entries — an empty panel would be pure noise.
//
// Phase 19 — this is the canonical place to lock/unlock an Evidence
// item's wording (not the A4 CV editor, which was tried first and moved
// here: `locked`/`locked_text` are durable Candidate-Profile facts, not
// per-generate CV state, and this panel already renders off a live query
// (ProfileView's useEvidence, via ExperienceSection), so a lock toggle
// here is reflected correctly for every future generate with no
// per-generate staleness to manage — unlike the A4 editor, where a
// bullet's on-screen identity is positional, not evidence-keyed).
//
// Used to also show "(backs: SkillName, ...)" per bullet (the reverse of
// EntitySection's own "backed by" summary) — reported as hard to read
// inline, dropped in the same pass that collapsed EntitySection's own
// list behind a summary + popover instead.
export function ExperienceEvidencePanel({
  candidateId,
  experience,
  evidence,
}: ExperienceEvidencePanelProps) {
  const { update } = useEntityMutations<Evidence>(candidateId, "evidence");
  const roleEvidence = evidence.filter((item) => item.experience_id === experience.id);
  if (roleEvidence.length === 0) {
    return null;
  }

  const handleLock = (item: Evidence) => {
    update.mutate({ itemId: item.id, body: { locked: true, locked_text: item.text } }, { onError: showError });
  };

  const handleUnlock = (item: Evidence) => {
    update.mutate({ itemId: item.id, body: { locked: false } }, { onError: showError });
  };

  const roleLevel = roleEvidence.filter((item) => item.experience_project_id == null);
  const byProjectId = new Map<string, Evidence[]>();
  for (const item of roleEvidence) {
    if (item.experience_project_id == null) {
      continue;
    }
    const group = byProjectId.get(item.experience_project_id);
    if (group) {
      group.push(item);
    } else {
      byProjectId.set(item.experience_project_id, [item]);
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-dashed p-2 text-xs">
      <span className="font-medium text-muted-foreground">Responsibilities & Achievements</span>
      {roleLevel.length > 0 && (
        <EvidenceGroup heading={null} items={roleLevel} onLock={handleLock} onUnlock={handleUnlock} />
      )}
      {[...byProjectId.entries()].map(([projectId, items]) => {
        const project = experience.projects?.find((p) => p.id === projectId);
        return (
          <EvidenceGroup
            key={projectId}
            heading={project ? <ProjectHeading project={project} /> : "Project"}
            items={items}
            onLock={handleLock}
            onUnlock={handleUnlock}
          />
        );
      })}
    </div>
  );
}

// Same "name becomes a real, clickable <a> when the project has a url"
// treatment as ExperienceForm.tsx's ProjectSummaryLine — this panel is the
// read-only counterpart of that same Projects list (Profile's "preview"
// state vs. the edit form), so a project's link belongs here too, not
// just in the form.
function ProjectHeading({ project }: { project: ExperienceProject }) {
  return project.url ? (
    <a href={project.url} target="_blank" rel="noopener noreferrer" className={LINK_CLASSNAME}>
      {project.name}
    </a>
  ) : (
    <>{project.name}</>
  );
}

function EvidenceGroup({
  heading,
  items,
  onLock,
  onUnlock,
}: {
  heading: ReactNode;
  items: Evidence[];
  onLock: (item: Evidence) => void;
  onUnlock: (item: Evidence) => void;
}) {
  return (
    <div className="space-y-1">
      {heading && <span className="font-medium text-muted-foreground">{heading}</span>}
      <ul className="ml-1 space-y-0.5 border-l-2 pl-2 text-muted-foreground">
        {items.map((item) => (
          <li key={item.id} className="flex items-start gap-1">
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-xs"
                  className={cn("shrink-0", item.locked && "text-primary")}
                  aria-label={
                    item.locked
                      ? "Locked — reused verbatim for every future vacancy"
                      : "Lock this wording for every future vacancy"
                  }
                >
                  {item.locked ? <Lock /> : <Unlock />}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-72 space-y-2 text-sm">
                {item.locked ? (
                  <>
                    <p className="text-xs font-medium text-muted-foreground uppercase">Locked</p>
                    <p>
                      Reused verbatim for every future vacancy — Rewrite Planning/Bullet Rewriting skip
                      it entirely.
                    </p>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={() => onUnlock(item)}
                    >
                      Unlock
                    </Button>
                  </>
                ) : (
                  <>
                    <p>
                      Lock this item's current wording so every future generate reuses it verbatim
                      instead of re-tailoring it.
                    </p>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="w-full"
                      onClick={() => onLock(item)}
                    >
                      Lock this wording
                    </Button>
                  </>
                )}
              </PopoverContent>
            </Popover>
            <span>{item.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
