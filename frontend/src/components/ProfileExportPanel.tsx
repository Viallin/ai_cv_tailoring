import { Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useExportUntailored } from "@/api/candidates";
import { ApiError } from "@/api/client";
import { useCvDrafts } from "@/api/cvDrafts";
import { useEntityMutations } from "@/api/entities";
import type { CVDraft, CVDraftSummary } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TailorToJobDialog } from "@/components/TailorToJobDialog";
import { draftLabel, languageLabel } from "@/lib/sections";
import { buildDocumentFromAssembledCv } from "@/lib/structuredDocument";
import { cn } from "@/lib/utils";

interface ProfileExportPanelProps {
  candidateId: string;
  language: string;
  className?: string;
}

const UNTAILORED_VACANCY = { raw_text: "", title: null, company: null };

// Post-4.10 nav redesign, round 3 — replaces the standalone "CV export"
// page/tab entirely. Reported directly: the old "Export CV" button gave
// no hint that "Your drafts" lived behind it, so people who'd already
// generated a CV for this profile had no obvious way back to it — this
// sticky rail (the same lg:sticky pattern DraftScreen.tsx's own action
// rail already uses) puts both export paths and the drafts list
// permanently in view next to the profile itself, not one click away
// behind an unlabeled button.
export function ProfileExportPanel({ candidateId, language, className }: ProfileExportPanelProps) {
  const navigate = useNavigate();
  const exportUntailored = useExportUntailored(candidateId);
  const { data: drafts } = useCvDrafts(candidateId);
  const { create: createDraft, remove: removeDraft } = useEntityMutations<CVDraft>(candidateId, "drafts");

  const exporting = exportUntailored.isPending || createDraft.isPending;

  const handleExportAsIsClick = () => {
    exportUntailored.mutate(undefined, {
      onSuccess: (assembledCv) => {
        createDraft.mutate(
          {
            vacancy: UNTAILORED_VACANCY,
            assembled_cv: assembledCv,
            document: buildDocumentFromAssembledCv(assembledCv),
          },
          {
            onSuccess: (draft) => navigate(`/candidates/${candidateId}/drafts/${draft.id}`),
            onError: () => toast.error("Error", { description: "Exported, but couldn't save the draft — try again." }),
          },
        );
      },
      onError: () => toast.error("Error", { description: "Couldn't export the CV — try again." }),
    });
  };

  const handleDeleteDraftClick = (draft: CVDraftSummary) => {
    if (!window.confirm(`Delete the draft "${draftLabel(draft)}"? This can't be undone.`)) {
      return;
    }
    removeDraft.mutate(draft.id, {
      onError: (error) => {
        const category = error instanceof ApiError ? error.category : "Error";
        const message = error instanceof ApiError ? error.message : "Something went wrong.";
        toast.error(category, { description: message });
      },
    });
  };

  return (
    <div className={cn("space-y-4", className)}>
      <Card>
        <CardHeader>
          <CardTitle>Export CV</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs text-muted-foreground">
            CVs are generated in this profile's language ({languageLabel(language)}). To generate in a
            different language, create a new candidate profile in that language.
          </p>
          <Button type="button" className="w-full" onClick={handleExportAsIsClick} disabled={exporting}>
            {exporting ? "Preparing…" : "Export without tailoring"}
          </Button>
          <TailorToJobDialog candidateId={candidateId} language={language} />
        </CardContent>
      </Card>

      {drafts && drafts.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Your drafts</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1">
              {drafts.map((draft) => (
                <li key={draft.id} className="flex items-start gap-1">
                  <Button
                    type="button"
                    variant="outline"
                    className="h-auto flex-1 flex-col items-start gap-0.5 px-2.5 py-2 text-left whitespace-normal"
                    onClick={() => navigate(`/candidates/${candidateId}/drafts/${draft.id}`)}
                  >
                    <span className="text-sm font-medium">{draftLabel(draft)}</span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(draft.updated_at).toLocaleString()}
                    </span>
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
                    aria-label={`Delete draft: ${draftLabel(draft)}`}
                    onClick={() => handleDeleteDraftClick(draft)}
                    disabled={removeDraft.isPending}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
