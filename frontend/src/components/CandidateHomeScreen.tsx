import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useCandidates, useCreateCandidate } from "@/api/candidates";
import { ApiError } from "@/api/client";
import { useIngestJob, useIngestUploadJob } from "@/api/jobs";
import { CandidateTable } from "@/components/CandidateTable";
import { CreateProfilePanel } from "@/components/CreateProfilePanel";
import { IngestPanel } from "@/components/IngestPanel";

// Phase 20 — screen 1 of the routed flow: "Candidate picker/ingest."
// Ingest moved here verbatim from CvWorkflowView's left column (it used
// to share a screen with the JD/CV export step; the phase's own screen
// breakdown puts it on its own, first screen instead). Both actions land
// on the same next step — the candidate's profile — since that's screen
// 2 in the flow (profile + cross-links), ahead of JD/CV export.
export function CandidateHomeScreen() {
  const navigate = useNavigate();
  const { data: candidates } = useCandidates();
  const ingestJob = useIngestJob();
  const ingestUploadJob = useIngestUploadJob();
  const createCandidate = useCreateCandidate();
  const [resumeText, setResumeText] = useState("");
  const [statusMessage, setStatusMessage] = useState("");

  // Split out so IngestPanel can put each action's busy state on its own
  // button (ingestBusy/uploadBusy) — same "status lives on the button you
  // pushed" convention as GenerateButton.tsx/ReevaluateSkillLinksButton.tsx
  // — while `busy` still disables the whole panel/table for either one
  // (or an unrelated create-empty-profile) in flight.
  const ingestBusy = ingestJob.isSubmitting || ingestJob.isRunning;
  const uploadBusy = ingestUploadJob.isSubmitting || ingestUploadJob.isRunning;
  const busy = ingestBusy || uploadBusy || createCandidate.isPending;

  // Version 4, Phase 4.6 (3.2.2) — the empty-profile creation path: no
  // resume text to ingest, so this is a plain POST /candidates (via
  // useCreateCandidate), not a job — navigates straight to the new
  // profile on success, same destination as a successful ingest.
  const handleCreateProfileClick = (name: string, language: string) => {
    const trimmedName = name.trim();
    if (!trimmedName) {
      setStatusMessage("Enter a name first.");
      return;
    }
    createCandidate.mutate(
      { name: trimmedName, language },
      {
        onSuccess: (result) => navigate(`/candidates/${result.id}/profile`),
        onError: (error) => {
          const category = error instanceof ApiError ? error.category : "Error";
          const message = error instanceof ApiError ? error.message : "Something went wrong.";
          toast.error(category, { description: message });
          setStatusMessage(`Couldn't create the profile: ${message}`);
        },
      },
    );
  };

  const handleIngestClick = () => {
    const trimmed = resumeText.trim();
    if (!trimmed) {
      setStatusMessage("Paste a resume first.");
      return;
    }
    // No "Ingesting..." status message here — IngestPanel's own "Ingest
    // Resume" button shows that (ingestBusy below), right where the click
    // happened, instead of a separate paragraph elsewhere on the screen.
    ingestJob.ingest(trimmed);
  };

  // Version 4, Phase 4.5: the file-upload path — separate from the
  // paste-and-click path above, its own job (useIngestUploadJob), its own
  // result/error effects below, so a failed upload never clobbers pasted
  // text still sitting in the textarea, and vice versa.
  const handleFileSelected = (file: File) => {
    ingestUploadJob.ingest(file);
  };

  useEffect(() => {
    if (ingestJob.result) {
      navigate(`/candidates/${ingestJob.result.candidate_id}/profile`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- navigate is a stable function from the router
  }, [ingestJob.result]);

  useEffect(() => {
    if (ingestJob.error) {
      toast.error(ingestJob.error.category, { description: ingestJob.error.message });
      setStatusMessage(`Ingestion failed: ${ingestJob.error.message}`);
    }
  }, [ingestJob.error]);

  useEffect(() => {
    if (ingestUploadJob.result) {
      navigate(`/candidates/${ingestUploadJob.result.candidate_id}/profile`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- navigate is a stable function from the router
  }, [ingestUploadJob.result]);

  useEffect(() => {
    if (ingestUploadJob.error) {
      toast.error(ingestUploadJob.error.category, { description: ingestUploadJob.error.message });
      setStatusMessage(`Ingestion failed: ${ingestUploadJob.error.message}`);
    }
  }, [ingestUploadJob.error]);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {statusMessage && <p className="text-sm text-muted-foreground">{statusMessage}</p>}

      <div>
        <h2 className="mb-2 text-lg font-medium">Open an existing profile</h2>
        <CandidateTable disabled={busy} />
        {candidates?.length === 0 && (
          <p className="mt-1 text-xs text-muted-foreground">
            No profiles yet — ingest a resume or create a blank one below to get started.
          </p>
        )}
      </div>

      <div>
        <h2 className="mb-2 text-lg font-medium">Or start from a resume</h2>
        <IngestPanel
          resumeText={resumeText}
          onResumeTextChange={setResumeText}
          onIngestClick={handleIngestClick}
          onFileSelected={handleFileSelected}
          hintText="Ingesting always creates a new candidate profile. Accepts .txt, .md, .pdf, .docx, or .rtf files — drag one onto this panel or use the upload button."
          busy={busy}
          ingestBusy={ingestBusy}
          uploadBusy={uploadBusy}
        />
      </div>

      <div>
        <h2 className="mb-2 text-lg font-medium">Or create an empty profile</h2>
        <CreateProfilePanel onCreateClick={handleCreateProfileClick} busy={busy} />
      </div>
    </div>
  );
}
