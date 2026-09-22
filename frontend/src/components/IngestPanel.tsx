import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

// Version 4, Phase 4.5: matches app/resume_reader.py's read_resume_text
// dispatch (PDF/DOCX/RTF/TXT/MD) exactly — kept as one constant so the two
// never drift silently.
const ACCEPTED_FILE_TYPES = ".txt,.md,.pdf,.docx,.rtf";

interface IngestPanelProps {
  resumeText: string;
  onResumeTextChange: (value: string) => void;
  onIngestClick: () => void;
  onFileSelected: (file: File) => void;
  hintText: string;
  // Disables the whole panel (textarea, both buttons, the hidden file
  // input, drag-drop) — true while either ingest path below is running,
  // or while an unrelated action elsewhere on the same screen (creating an
  // empty profile) is, so this panel can't start a conflicting ingest
  // mid-navigation. Doesn't by itself say *which* action is running — see
  // ingestBusy/uploadBusy for that.
  busy: boolean;
  // Same "put the busy state on the button itself" convention as
  // GenerateButton.tsx/ReevaluateSkillLinksButton.tsx, applied to this
  // panel's two actions individually rather than one shared status
  // message — found live: a status paragraph pinned to the top of
  // CandidateHomeScreen, well above this panel (and further still from
  // wherever a drag-and-drop actually landed), read as disconnected from
  // the button just pressed. `ingestBusy`/`uploadBusy` swap only the
  // relevant button's own label, right where the person's attention
  // already is.
  ingestBusy: boolean;
  uploadBusy: boolean;
}

// Two ways to provide a resume, side by side but mutually exclusive in
// effect: paste text and click "Ingest Resume", or pick a file and it's
// sent as-is — nothing here merges the two into one request.
export function IngestPanel({
  resumeText,
  onResumeTextChange,
  onIngestClick,
  onFileSelected,
  hintText,
  busy,
  ingestBusy,
  uploadBusy,
}: IngestPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Purely a visual affordance while a file is dragged over the panel —
  // see handleDrop's own comment for why dropping itself needs no client-
  // side gate.
  const [isDraggingOver, setIsDraggingOver] = useState(false);

  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Reset so selecting the same file again (e.g. after a failed ingest)
    // still fires onChange.
    event.target.value = "";
    if (file) {
      onFileSelected(file);
    }
  };

  // Found live: this panel never had drag-and-drop at all, only the
  // click-to-browse button below — with no `dragover`/`drop` handlers
  // anywhere, dropping a file here fell through to the browser's own
  // default handling: navigating the tab to the dropped file, unbounded by
  // ACCEPTED_FILE_TYPES. preventDefault on both dragover and drop opts
  // this element back into the standard HTML5 drag-and-drop API so the
  // browser stops treating a drop here as "open this file", the same as
  // any other drop-to-upload control.
  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    if (busy) return;
    event.preventDefault();
    setIsDraggingOver(true);
  };

  const handleDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDraggingOver(false);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDraggingOver(false);
    if (busy) return;
    const file = event.dataTransfer.files?.[0];
    // No client-side extension check against ACCEPTED_FILE_TYPES here,
    // deliberately: the hidden file input below doesn't do one either (it
    // relies entirely on the OS picker's own `accept` filtering, which a
    // drop has no equivalent of) — an unsupported drop reaches the same
    // server-side ParsingError -> toast path a manually-renamed bad
    // extension would if it slipped past the picker.
    if (file) {
      onFileSelected(file);
    }
  };

  return (
    <div
      className={cn(
        "space-y-1 rounded-md outline-2 outline-offset-4 outline-dashed transition-colors",
        isDraggingOver ? "outline-primary" : "outline-transparent",
      )}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <label htmlFor="resume-text" className="text-sm font-medium">
        Resume
      </label>
      <Textarea
        id="resume-text"
        value={resumeText}
        onChange={(event) => onResumeTextChange(event.target.value)}
        placeholder="Paste your resume text here..."
        disabled={busy}
        rows={8}
      />
      <div className="flex items-center gap-2">
        <Button onClick={onIngestClick} disabled={busy}>
          {ingestBusy ? "Ingesting…" : "Ingest Resume"}
        </Button>
        <span className="text-xs text-muted-foreground">or</span>
        <Button
          type="button"
          variant="outline"
          onClick={() => fileInputRef.current?.click()}
          disabled={busy}
        >
          {uploadBusy ? "Ingesting…" : "Upload a file"}
        </Button>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_FILE_TYPES}
          onChange={handleFileInputChange}
          disabled={busy}
          aria-label="Upload resume file"
          className="hidden"
        />
      </div>
      <p className="text-xs text-muted-foreground">{hintText}</p>
    </div>
  );
}
