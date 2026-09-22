import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useCandidates, useDeleteCandidate } from "@/api/candidates";
import { ApiError } from "@/api/client";
import type { CandidateProfileSummary } from "@/api/models";
import { Button } from "@/components/ui/button";
import { languageLabel } from "@/lib/sections";

interface CandidateTableProps {
  disabled?: boolean;
}

// Version 4, Phase 4.6 (3.1) — replaces the dropdown (CandidatePicker) as
// the start screen's primary way to open an existing profile; a table
// scales better once "a few non-technical friends" each have several
// profiles, and surfaces Role/Language without an extra click.
// CandidatePicker itself is untouched — still used by
// CandidateWorkflowLayout's compact header dropdown, where a table
// wouldn't fit.
export function CandidateTable({ disabled }: CandidateTableProps) {
  const navigate = useNavigate();
  const { data: candidates, isLoading } = useCandidates();
  const deleteCandidate = useDeleteCandidate();

  const handleOpen = (candidate: CandidateProfileSummary) => {
    navigate(`/candidates/${candidate.id}/profile`);
  };

  // Grey (not red/destructive) button + window.confirm — matches the
  // codebase's existing delete convention (e.g. EntitySection.tsx's
  // handleRemove, ExportScreen.tsx's handleDeleteDraftClick), no new
  // dialog primitive introduced for this.
  const handleDelete = (candidate: CandidateProfileSummary) => {
    if (!window.confirm(`Delete "${candidate.name}"? This can't be undone.`)) {
      return;
    }
    deleteCandidate.mutate(candidate.id, {
      onError: (error) => {
        const category = error instanceof ApiError ? error.category : "Error";
        const message = error instanceof ApiError ? error.message : "Something went wrong.";
        toast.error(category, { description: message });
      },
    });
  };

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!candidates || candidates.length === 0) {
    return null;
  }

  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-left text-xs text-muted-foreground">
            <th className="px-3 py-2 font-medium">Name</th>
            <th className="px-3 py-2 font-medium">Role</th>
            <th className="px-3 py-2 font-medium">Language</th>
            <th className="px-3 py-2 font-medium">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => (
            <tr key={candidate.id} className="border-b last:border-0">
              <td className="px-3 py-2 font-medium">{candidate.name}</td>
              <td className="px-3 py-2 text-muted-foreground">{candidate.headline ?? "—"}</td>
              <td className="px-3 py-2 text-muted-foreground">{languageLabel(candidate.language)}</td>
              <td className="px-3 py-2">
                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => handleOpen(candidate)}
                    disabled={disabled}
                  >
                    Open
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => handleDelete(candidate)}
                    disabled={disabled || deleteCandidate.isPending}
                  >
                    Delete
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
