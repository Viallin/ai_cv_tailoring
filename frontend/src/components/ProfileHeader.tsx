import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { useDeleteCandidate, useUpdateCandidateProfile } from "@/api/candidates";
import { ApiError } from "@/api/client";
import type { Candidate, EmploymentType } from "@/api/models";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { languageLabel } from "@/lib/sections";

const EMPLOYMENT_TYPES: EmploymentType[] = [
  "Full-time",
  "Part-time",
  "Contract",
  "Freelance",
  "Internship",
  "Temporary",
];

interface ProfileHeaderProps {
  candidateId: string;
  candidate: Candidate;
}

// Profile-level fields (everything not in one of the 11 entity lists) —
// the React equivalent of ui/graph_explorer.py's name/headline/summary
// fields + employment-type checkboxes + "Save Profile Info" button.
//
// Read-only-by-default, click-Edit-to-edit — the same convention every
// other Profile Explorer section (EntitySection.tsx, ExperienceSection.tsx)
// already uses. This used to be the one section always shown as an open
// form, inconsistent with the rest and easy to misread as "these fields
// aren't saved yet." No "+ Add"/Delete here (a singleton record, not a
// list), so Edit lives in the CardHeader instead of trailing the rows the
// way "+ Add X" does elsewhere.
export function ProfileHeader({ candidateId, candidate }: ProfileHeaderProps) {
  const navigate = useNavigate();
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState(candidate.name);
  const [headline, setHeadline] = useState(candidate.headline ?? "");
  const [summary, setSummary] = useState(candidate.summary ?? "");
  const [employmentTypes, setEmploymentTypes] = useState<EmploymentType[]>(
    candidate.employment_types_sought ?? [],
  );

  const resetFormFromCandidate = () => {
    setName(candidate.name);
    setHeadline(candidate.headline ?? "");
    setSummary(candidate.summary ?? "");
    setEmploymentTypes(candidate.employment_types_sought ?? []);
  };

  // Re-sync local state whenever a different (or freshly refetched)
  // candidate object arrives — otherwise switching candidates would leave
  // the previous one's edits showing in these fields. Also drops back out
  // of edit mode, so switching candidates never leaves a stale form open.
  useEffect(() => {
    resetFormFromCandidate();
    setIsEditing(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- resetFormFromCandidate closes over candidate, which is already a dep
  }, [candidateId, candidate]);

  const update = useUpdateCandidateProfile(candidateId);
  const deleteCandidate = useDeleteCandidate();

  // Version 4, Phase 4.6 (4.2) — grey button + window.confirm, matching
  // CandidateTable.tsx's own delete convention (and the codebase's
  // existing one, e.g. EntitySection.tsx's handleRemove) rather than a new
  // dialog primitive. Navigates back to the start screen on success —
  // there's no "current" profile to fall back to once this one is gone.
  const handleDeleteClick = () => {
    if (!window.confirm(`Delete "${candidate.name}"? This can't be undone.`)) {
      return;
    }
    deleteCandidate.mutate(candidateId, {
      onSuccess: () => navigate("/"),
      onError: (error) => {
        const category = error instanceof ApiError ? error.category : "Error";
        const message = error instanceof ApiError ? error.message : "Something went wrong.";
        toast.error(category, { description: message });
      },
    });
  };

  const toggleEmploymentType = (type: EmploymentType, checked: boolean) => {
    setEmploymentTypes((previous) => (checked ? [...previous, type] : previous.filter((t) => t !== type)));
  };

  const startEdit = () => {
    resetFormFromCandidate();
    setIsEditing(true);
  };

  const cancelEdit = () => {
    resetFormFromCandidate();
    setIsEditing(false);
  };

  const handleSave = () => {
    update.mutate(
      {
        name: name.trim(),
        headline: headline.trim() === "" ? null : headline.trim(),
        summary: summary.trim() === "" ? null : summary.trim(),
        employment_types_sought: employmentTypes,
      },
      {
        onSuccess: () => setIsEditing(false),
        onError: (error) => {
          const category = error instanceof ApiError ? error.category : "Error";
          const message = error instanceof ApiError ? error.message : "Something went wrong.";
          toast.error(category, { description: message });
        },
      },
    );
  };

  if (!isEditing) {
    const seeking = candidate.employment_types_sought ?? [];
    return (
      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardAction className="flex gap-1">
            <Button variant="ghost" size="sm" onClick={startEdit}>
              Edit
            </Button>
            <Button variant="secondary" size="sm" onClick={handleDeleteClick} disabled={deleteCandidate.isPending}>
              Delete
            </Button>
          </CardAction>
        </CardHeader>
        <CardContent className="space-y-1 text-sm">
          <p className="text-base font-medium">{candidate.name}</p>
          {/* Version 4, Phase 4.3: read-only, no edit control — language is
              immutable per-profile (docs/development_plan.md's Version 4
              section: a different target language means creating a new
              profile, not editing this one in place). */}
          <p className="text-xs text-muted-foreground">Language: {languageLabel(candidate.language)}</p>
          {candidate.headline && <p className="text-muted-foreground">{candidate.headline}</p>}
          {candidate.summary && <p className="whitespace-pre-wrap">{candidate.summary}</p>}
          {seeking.length > 0 && <p className="text-muted-foreground">Seeking: {seeking.join(", ")}</p>}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <label htmlFor="profile-name" className="text-xs font-medium text-muted-foreground">
            Name
          </label>
          <Input id="profile-name" value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <div className="space-y-1">
          <label htmlFor="profile-headline" className="text-xs font-medium text-muted-foreground">
            Headline
          </label>
          <Input
            id="profile-headline"
            value={headline}
            onChange={(event) => setHeadline(event.target.value)}
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="profile-summary" className="text-xs font-medium text-muted-foreground">
            Summary
          </label>
          <Textarea
            id="profile-summary"
            value={summary}
            onChange={(event) => setSummary(event.target.value)}
            rows={4}
          />
        </div>
        <div className="space-y-1">
          <span className="text-xs font-medium text-muted-foreground">Seeking</span>
          <div className="flex flex-wrap gap-3">
            {EMPLOYMENT_TYPES.map((type) => (
              <label key={type} className="flex items-center gap-1.5 text-sm">
                <Checkbox
                  checked={employmentTypes.includes(type)}
                  onCheckedChange={(checked) => toggleEmploymentType(type, checked === true)}
                />
                {type}
              </label>
            ))}
          </div>
        </div>
        <div className="flex gap-2">
          <Button onClick={handleSave} disabled={update.isPending}>
            {update.isPending ? "Saving…" : "Save"}
          </Button>
          <Button variant="ghost" onClick={cancelEdit} disabled={update.isPending}>
            Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
