import { Textarea } from "@/components/ui/textarea";

interface VacancyPanelProps {
  vacancyText: string;
  onVacancyTextChange: (value: string) => void;
  busy: boolean;
}

export function VacancyPanel({ vacancyText, onVacancyTextChange, busy }: VacancyPanelProps) {
  return (
    <div className="space-y-1">
      <label htmlFor="vacancy-text" className="text-sm font-medium">
        Job Description
      </label>
      {/* field-sizing-fixed overrides the Textarea base component's own
          field-sizing-content — that grows the box to fit whatever's
          pasted in with no limit, which inside TailorToJobDialog.tsx's
          modal pushed the Tailor button off the bottom of the screen for
          a real, multi-paragraph vacancy post (reported directly). Fixed
          height + its own scrollbar instead, same as any other textarea
          that doesn't want to grow the page around it. */}
      <Textarea
        id="vacancy-text"
        value={vacancyText}
        onChange={(event) => onVacancyTextChange(event.target.value)}
        placeholder="Paste the job description here..."
        disabled={busy}
        className="field-sizing-fixed h-64 resize-none overflow-y-auto"
      />
    </div>
  );
}
