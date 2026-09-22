import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useEntityMutations } from "@/api/entities";
import { useGenerateJob } from "@/api/jobs";
import type { CVDraft } from "@/api/models";
import { GenerateButton } from "@/components/GenerateButton";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { VacancyPanel } from "@/components/VacancyPanel";
import { languageLabel } from "@/lib/sections";
import { buildDocumentFromAssembledCv } from "@/lib/structuredDocument";

interface TailorToJobDialogProps {
  candidateId: string;
  language: string;
}

// Post-4.10 nav redesign, round 3 — was ExportScreen.tsx's "Tailor to a
// job description" card (JD textarea inline, next to "Export without
// tailoring"), now a modal reached from ProfileExportPanel.tsx's own
// button. Reported directly: an always-visible JD box sitting in a narrow
// sidebar next to a profile someone might still be editing raised "what
// happens if I edit the profile while this is tailoring?" — a real
// question with no good inline answer. A modal sidesteps it entirely: the
// profile is inert (visually dimmed behind the overlay, and edits made
// during tailoring — reasonable a click away is disabled below) while
// this is open, so tailoring always reads against one snapshot of the
// profile rather than something that might be shifting under it.
//
// Closing is blocked for the whole generation — no X button, Escape, or
// outside click — rather than letting someone navigate away mid-run and
// lose track of it; there's nowhere to resume it from yet if they do (a
// pending-draft state that survives a closed dialog is a real follow-up,
// not built here).
export function TailorToJobDialog({ candidateId, language }: TailorToJobDialogProps) {
  const [open, setOpen] = useState(false);
  const [vacancyText, setVacancyText] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const navigate = useNavigate();
  const generateJob = useGenerateJob();
  const { create: createDraft } = useEntityMutations<CVDraft>(candidateId, "drafts");

  const busy = generateJob.isSubmitting || generateJob.isRunning || createDraft.isPending;

  const handleOpenChange = (next: boolean) => {
    if (!next && busy) {
      // Blocks Escape/outside-click too (both route through this same
      // callback) — the Cancel button in the footer is separately
      // disabled below, so there's genuinely no way to close this mid-run.
      return;
    }
    setOpen(next);
  };

  const handleGenerateClick = () => {
    const trimmed = vacancyText.trim();
    if (!trimmed) {
      setStatusMessage("Paste a job description first.");
      return;
    }
    setStatusMessage("Generating... this calls the LLM a few times and can take a bit.");
    generateJob.generate(candidateId, trimmed);
  };

  useEffect(() => {
    if (generateJob.result == null) {
      return;
    }
    const { vacancy, assembled_cv: assembledCv, match_result: matchResult, provenance, timing } = generateJob.result;
    createDraft.mutate(
      {
        vacancy,
        assembled_cv: assembledCv,
        document: buildDocumentFromAssembledCv(assembledCv),
        match_result: matchResult,
        provenance,
        timing,
      },
      {
        onSuccess: (draft) => {
          setOpen(false);
          navigate(`/candidates/${candidateId}/drafts/${draft.id}`, { state: { matchResult, provenance } });
        },
        onError: () => setStatusMessage("Generated, but couldn't save the draft — try again."),
      },
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires once per fresh generate result; createDraft/navigate/candidateId are stable or read at that moment
  }, [generateJob.result]);

  useEffect(() => {
    if (generateJob.error) {
      toast.error(generateJob.error.category, { description: generateJob.error.message });
      setStatusMessage(`Generation failed: ${generateJob.error.message}`);
    }
  }, [generateJob.error]);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" className="w-full">
          Tailor CV to a Job Description
        </Button>
      </DialogTrigger>
      <DialogContent
        className="sm:max-w-2xl"
        showCloseButton={!busy}
        onEscapeKeyDown={(event) => busy && event.preventDefault()}
        onInteractOutside={(event) => busy && event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Tailor CV to a job description</DialogTitle>
        </DialogHeader>

        <p className="text-sm text-muted-foreground">
          CVs are generated in this profile's language ({languageLabel(language)}). Tailoring calls the AI a
          few times and can take a minute or two.
        </p>

        <VacancyPanel vacancyText={vacancyText} onVacancyTextChange={setVacancyText} busy={busy} />

        {statusMessage && <p className="text-sm text-muted-foreground">{statusMessage}</p>}
        {busy && (
          <p className="text-sm font-medium">Hang tight — please don't close this window while it's working.</p>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setOpen(false)} disabled={busy}>
            Cancel
          </Button>
          <GenerateButton
            onClick={handleGenerateClick}
            disabled={busy}
            busy={busy}
            progress={generateJob.progress}
          />
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
