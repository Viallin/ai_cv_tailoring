import { Button } from "@/components/ui/button";
import { collectExcludedContent, type ExcludedContentItem } from "@/lib/excludedContent";
import type { DocumentModel } from "@/lib/structuredDocument";

interface ExcludedContentPanelProps {
  document: DocumentModel | null;
  onRestore: (item: ExcludedContentItem) => void;
}

// Phase 24 — everything the user has unchecked lands here instead of
// staying struck-through in place on the A4 page (DocumentSectionBlock.tsx/
// DocumentExperienceSection.tsx now skip rendering an excluded row
// entirely). Distinct from UnusedEvidencePanel: that one only ever lists
// Evidence the AI never put into the document at generation time; this
// one tracks content that *was* in the document and got manually
// excluded afterward — most of it has no Evidence record to fall back on
// (Skills/Education/Contacts/etc. were never Evidence-linked), so it
// reads straight off the live DocumentModel's own text via
// lib/excludedContent.ts.
export function ExcludedContentPanel({ document, onRestore }: ExcludedContentPanelProps) {
  if (document == null) {
    return null;
  }

  const items = collectExcludedContent(document);
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">Nothing excluded from this CV.</p>;
  }

  return (
    <ul className="space-y-2 text-sm">
      {items.map((item) => (
        <li
          key={`${item.sectionKey}-${item.entryId}-${item.bulletId ?? ""}`}
          className="flex items-start justify-between gap-2 rounded-lg border bg-muted/40 p-3"
        >
          <div className="space-y-0.5">
            <p className="text-xs font-medium text-muted-foreground uppercase">{item.sectionTitle}</p>
            <p>{item.text}</p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="xs"
            className="shrink-0"
            onClick={() => onRestore(item)}
          >
            Restore
          </Button>
        </li>
      ))}
    </ul>
  );
}
