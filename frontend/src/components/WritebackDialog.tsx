import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import type { AssembledCV, WritebackProposalOut } from "@/api/models";
import { useWritebackApply, useWritebackPreview } from "@/api/writeback";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import type { DocumentModel } from "@/lib/structuredDocument";

interface WritebackDialogProps {
  candidateId: string | null;
  assembledCv: AssembledCV | null;
  cvDocument: DocumentModel | null;
  disabled?: boolean;
  // Passed straight to the trigger Button — lets DraftScreen's Export
  // card line this up with ExportButton's now full-width stacked
  // controls (see that component's docstring) without this component
  // needing to know about that layout itself.
  className?: string;
}

// Phase 19: the web equivalent of ui/main_window.py's "Save edits to
// profile" button + "Save to profile?" confirm dialog
// (docs/phase_8_wireframes_spec.md) — one checkbox per proposed write,
// pre-checked when enabled, disabled+warning-colored when not (e.g. the
// block-count-mismatch case, app/graph_writeback.py:build_experience_
// proposals). Preview/apply are both stateless (api/routes/writeback.py):
// this always resends the *current* assembledCv/cvDocument, same
// "edited text is never re-parsed from somewhere else" convention
// ExportButton already follows.
export function WritebackDialog({ candidateId, assembledCv, cvDocument, disabled, className }: WritebackDialogProps) {
  const [open, setOpen] = useState(false);
  const [proposals, setProposals] = useState<WritebackProposalOut[] | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const preview = useWritebackPreview();
  const apply = useWritebackApply();

  const canOpen = !disabled && candidateId != null && assembledCv != null && cvDocument != null;

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen || candidateId == null || assembledCv == null || cvDocument == null) {
      return;
    }
    setProposals(null);
    preview.mutate(
      { candidateId, assembledCv, document: cvDocument },
      {
        onSuccess: (result) => {
          setProposals(result);
          setSelectedKeys(new Set(result.filter((p) => p.enabled).map((p) => p.key)));
        },
        onError: (error) => {
          const category = error instanceof ApiError ? error.category : "Error";
          const message = error instanceof ApiError ? error.message : "Could not preview write-back.";
          toast.error(category, { description: message });
          setOpen(false);
        },
      },
    );
  };

  const handleToggle = (key: string) => {
    setSelectedKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleSave = () => {
    if (candidateId == null || assembledCv == null || cvDocument == null) {
      return;
    }
    apply.mutate(
      { candidateId, assembledCv, document: cvDocument, selectedKeys: [...selectedKeys] },
      {
        onSuccess: (result) => {
          toast.success(
            result.applied_keys.length > 0
              ? `Saved ${result.applied_keys.length} edit(s) to the profile.`
              : "Nothing selected to save.",
          );
          setOpen(false);
        },
        onError: (error) => {
          const category = error instanceof ApiError ? error.category : "Error";
          const message = error instanceof ApiError ? error.message : "Could not save to profile.";
          toast.error(category, { description: message });
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button type="button" variant="outline" className={className} disabled={!canOpen}>
          Save to Profile
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Save to profile?</DialogTitle>
        </DialogHeader>

        {preview.isPending && <p className="text-sm text-muted-foreground">Checking what changed…</p>}

        {proposals && proposals.length === 0 && (
          <p className="text-sm text-muted-foreground">No edits to save back to the profile.</p>
        )}

        {proposals && proposals.length > 0 && (
          <ul className="space-y-3">
            {proposals.map((proposal) => (
              <li key={proposal.key} className="flex items-start gap-2">
                <Checkbox
                  id={`writeback-${proposal.key}`}
                  checked={selectedKeys.has(proposal.key)}
                  disabled={!proposal.enabled}
                  onCheckedChange={() => handleToggle(proposal.key)}
                  className="mt-0.5"
                />
                <Label
                  htmlFor={`writeback-${proposal.key}`}
                  className={!proposal.enabled ? "text-destructive" : undefined}
                >
                  {proposal.label}
                </Label>
              </li>
            ))}
          </ul>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleSave}
            disabled={!proposals || proposals.length === 0 || apply.isPending}
          >
            {apply.isPending ? "Saving…" : "Save selected"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
