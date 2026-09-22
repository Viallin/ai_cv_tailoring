import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useExportCv, type ExportFormat } from "@/api/export";
import type { AssembledCV } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { NO_TEMPLATE_ID, TEMPLATE_CHOICES } from "@/lib/cvTemplates";
import type { DocumentModel } from "@/lib/structuredDocument";

interface ExportButtonProps {
  assembledCv: AssembledCV | null;
  // Named cvDocument, not document — a plain `document` prop would shadow
  // the global window.document inside this component's scope.
  cvDocument: DocumentModel | null;
  disabled?: boolean;
  // Controlled by DraftScreen and also handed to DocumentEditor's
  // `templateId` prop — the *same* Template picker now drives both the
  // on-screen preview and the export, instead of each component keeping
  // its own independent, unsynced default (previously "Preview template"
  // above the CV vs. this component's own Template select). See
  // cvTemplates.ts's TEMPLATE_CHOICES docstring.
  templateId: string;
  onTemplateIdChange: (id: string) => void;
  // Post-29 fix — lifted the same way templateId already was (see that
  // prop's own comment): PageBreakGuide needs to know which export
  // format is currently selected too, so DraftScreen now owns this
  // instead of it being this component's own local state.
  format: ExportFormat;
  onFormatChange: (format: ExportFormat) => void;
}

// One button + a format Select + the shared Template Select, not three
// separate buttons — the web equivalent of ui/main_window.py's single
// "Export CV" button plus its save-dialog's format filter (there's no
// native save-file dialog with a format filter available to a browser
// download, so the format choice moves into an explicit control next to
// the button instead). Phase 16c: this is now the ONLY export control
// (the A4 Preview tab's own duplicate "Export Templated" button was
// merged in here). The Template select itself no longer owns its choice
// locally — "none" (ATS-safe) still converts to `undefined` before
// hitting the export API (and a Markdown export always ignores template
// styling, format === "md" disables the select entirely), but which
// template is selected now lives in DraftScreen so DocumentEditor's
// preview matches exactly what Export CV will produce.
export function ExportButton({
  assembledCv,
  cvDocument,
  disabled,
  templateId,
  onTemplateIdChange,
  format,
  onFormatChange,
}: ExportButtonProps) {
  const exportCv = useExportCv();

  const handleClick = () => {
    if (assembledCv == null || cvDocument == null) {
      return;
    }
    const exportTemplateId = format === "md" || templateId === NO_TEMPLATE_ID ? undefined : templateId;
    exportCv.mutate(
      { assembledCv, document: cvDocument, format, templateId: exportTemplateId },
      {
        onError: (error) => {
          const category = error instanceof ApiError ? error.category : "Error";
          const message = error instanceof ApiError ? error.message : "Export failed.";
          toast.error(category, { description: message });
        },
      },
    );
  };

  const disableExport = disabled || assembledCv == null || cvDocument == null || exportCv.isPending;

  return (
    // Each control its own labeled row, all sharing one width, rather than
    // the previous single wrapping inline row of differently-sized
    // controls — reads as a small form instead of a loose button cluster.
    <div className="space-y-3">
      <div className="space-y-1">
        <label htmlFor="cv-template" className="text-xs font-medium text-muted-foreground">
          Preview template
        </label>
        <Select value={templateId} onValueChange={onTemplateIdChange} disabled={disabled || format === "md"}>
          <SelectTrigger id="cv-template" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TEMPLATE_CHOICES.map((t) => (
              <SelectItem key={t.id} value={t.id}>
                {t.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1">
        <label htmlFor="cv-format" className="text-xs font-medium text-muted-foreground">
          Format
        </label>
        <Select value={format} onValueChange={(value) => onFormatChange(value as ExportFormat)} disabled={disabled}>
          <SelectTrigger id="cv-format" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="pdf">.pdf</SelectItem>
            <SelectItem value="docx">.docx</SelectItem>
            <SelectItem value="md">.md</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <Button className="w-full" onClick={handleClick} disabled={disableExport}>
        {exportCv.isPending ? "Exporting…" : "Export CV"}
      </Button>
    </div>
  );
}
