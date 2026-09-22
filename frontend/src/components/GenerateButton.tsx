import { Button } from "@/components/ui/button";

interface GenerateButtonProps {
  onClick: () => void;
  // Matches ui/main_window.py exactly: generate_button.setEnabled(candidate
  // is not None) — enabled purely on "a candidate is loaded", regardless of
  // JD text. Empty-JD-text is a click-time check (onClick shows a status
  // message), not a second reactive disabled condition.
  disabled: boolean;
  busy: boolean;
  // Live progress through app/pipeline.py's six-stage chain
  // (useGenerateJob's own `progress`) — reported directly: a bare
  // "Generating…" for the several minutes a real generation can take
  // gives no sign whether it's almost done or stuck. Optional/omittable
  // so a caller with no generate job at all (there isn't one today, but
  // nothing stops a future caller reusing this button for something else)
  // still gets the plain busy label.
  progress?: { stage: string; stageNumber: number; stageCount: number };
}

export function GenerateButton({ onClick, disabled, busy, progress }: GenerateButtonProps) {
  const label = busy
    ? progress
      ? `Step ${progress.stageNumber}/${progress.stageCount}: ${progress.stage}…`
      : "Generating…"
    : "Tailor CV to Job Description";
  return (
    <Button onClick={onClick} disabled={disabled}>
      {label}
    </Button>
  );
}
