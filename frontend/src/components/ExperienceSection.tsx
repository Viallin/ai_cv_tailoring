import { useState } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useEntityMutations } from "@/api/entities";
import type { Evidence, Experience } from "@/api/models";
import type { BulletRow } from "@/components/BulletRowsEditor";
import {
  emptyExperienceFormValues,
  ExperienceForm,
  toExperienceRequestBody,
  type ExperienceFormValues,
} from "@/components/ExperienceForm";
import { ExperienceEvidencePanel } from "@/components/ExperienceEvidencePanel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LINK_CLASSNAME } from "@/lib/linkify";
import { sectionTitlesFor } from "@/lib/sections";

interface ExperienceSectionProps {
  candidateId: string;
  experience: Experience[];
  evidence: Evidence[];
  disabled?: boolean;
  // Version 4, Phase 4.3 — the candidate's own profile language
  // (ProfileView.tsx passes candidate.language), used to localize the
  // section heading.
  language: string;
}

// Flattens role-level bullets plus every nested Project's own bullets into
// one list per (Achievements/Responsibilities) BulletRowsEditor, tagging
// each row with the Project id it came from (null = role-level) — the
// reverse of ExperienceForm.tsx's toExperienceRequestBody, which regroups
// them back by project at save time. Role-level rows first, then each
// project's rows in the project's own order, matching
// ui/graph_explorer.py's `_ExperienceFormDialog.__init__` exactly.
function experienceToValues(entry: Experience): ExperienceFormValues {
  const projects = (entry.projects ?? []).map((project) => ({
    id: project.id,
    name: project.name,
    period: project.period ?? "",
    url: project.url ?? "",
  }));

  const flatten = (roleLevel: string[] | undefined, listField: "achievements" | "responsibilities"): BulletRow[] => [
    ...(roleLevel ?? []).map((text) => ({ id: crypto.randomUUID(), text, projectId: null })),
    ...(entry.projects ?? []).flatMap((project) =>
      (project[listField] ?? []).map((text) => ({ id: crypto.randomUUID(), text, projectId: project.id })),
    ),
  ];

  return {
    position: entry.position,
    company: entry.company ?? "",
    companyUrl: entry.company_url ?? "",
    period: entry.period ?? "",
    location: entry.location ?? "",
    isGap: entry.is_gap,
    responsibilities: flatten(entry.responsibilities, "responsibilities"),
    achievements: flatten(entry.achievements, "achievements"),
    projects,
  };
}

// Matches ui/graph_explorer.py's _summarize_experience exactly. Stays a
// plain string for handleRemove's window.confirm() message, which can't
// render JSX — ExperienceSummaryLine below is the on-screen counterpart
// that can.
function summarizeExperience(entry: Experience): string {
  const company = entry.company ? ` — ${entry.company}` : "";
  const periodAndLocation = [entry.period, entry.location].filter(Boolean).join(", ");
  const period = periodAndLocation ? ` (${periodAndLocation})` : "";
  const gap = entry.is_gap ? " [GAP]" : "";
  return `${entry.position}${company}${period}${gap}`;
}

// The on-screen row: same text summarizeExperience produces, but the
// company name becomes a real, clickable <a> when company_url is set
// (Post-4.10 follow-up) — same bare <a href target="_blank" rel="noopener
// noreferrer"> convention lib/linkify.tsx already uses for Contacts/
// Portfolio Links/Key Projects. Those go through linkifyText, which scans
// already-rendered text for a URL *substring* — not applicable here, since
// company_url is a separate field, never part of the display text itself,
// so the link has to be built directly around just the company name.
function ExperienceSummaryLine({ entry }: { entry: Experience }) {
  const periodAndLocation = [entry.period, entry.location].filter(Boolean).join(", ");
  const period = periodAndLocation ? ` (${periodAndLocation})` : "";
  const gap = entry.is_gap ? " [GAP]" : "";
  return (
    <span>
      {entry.position}
      {entry.company && (
        <>
          {" — "}
          {entry.company_url ? (
            <a href={entry.company_url} target="_blank" rel="noopener noreferrer" className={LINK_CLASSNAME}>
              {entry.company}
            </a>
          ) : (
            entry.company
          )}
        </>
      )}
      {period}
      {gap}
    </span>
  );
}

function showError(error: unknown): void {
  const category = error instanceof ApiError ? error.category : "Error";
  const message = error instanceof ApiError ? error.message : "Something went wrong.";
  toast.error(category, { description: message });
}

// Experience's own dedicated component tree — not one of EntitySection's
// generic 11, since it has nested Projects and role/project-level bullet
// lists that FieldSpec/toRequestBody can't express. Structurally the
// direct analogue of EntitySection (owns the mutations + editingId state,
// delegates the form itself to a child component).
export function ExperienceSection({
  candidateId,
  experience,
  evidence,
  disabled,
  language,
}: ExperienceSectionProps) {
  const { create, update, remove } = useEntityMutations<Experience>(candidateId, "experience");
  const [editingId, setEditingId] = useState<string | null>(null); // null = none, "new" = add form
  const [values, setValues] = useState<ExperienceFormValues>(emptyExperienceFormValues());

  const startEdit = (entry: Experience) => {
    setEditingId(entry.id);
    setValues(experienceToValues(entry));
  };

  const startAdd = () => {
    setEditingId("new");
    setValues(emptyExperienceFormValues());
  };

  const cancelEdit = () => {
    setEditingId(null);
    setValues(emptyExperienceFormValues());
  };

  const handleSave = () => {
    const { projects, ...body } = toExperienceRequestBody(values);
    if (editingId === "new") {
      // add_experience has no `projects` param (a brand-new Experience has
      // no id yet to attach ExperienceProjects to) — mirrors
      // ui/graph_explorer.py's `_add_experience`: create first, then a
      // follow-up projects-only PUT once the entry has a real id. Two
      // writes, but no backend signature change needed.
      create.mutate(body, {
        onSuccess: (created) => {
          if (projects.length === 0) {
            cancelEdit();
            return;
          }
          update.mutate(
            { itemId: created.id, body: { projects } },
            { onSuccess: cancelEdit, onError: showError },
          );
        },
        onError: showError,
      });
    } else if (editingId != null) {
      update.mutate({ itemId: editingId, body: { ...body, projects } }, { onSuccess: cancelEdit, onError: showError });
    }
  };

  const handleRemove = (entry: Experience) => {
    if (!window.confirm(`Remove "${summarizeExperience(entry)}"?`)) {
      return;
    }
    remove.mutate(entry.id, { onError: showError });
  };

  const saving = create.isPending || update.isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{sectionTitlesFor(language).experience}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {experience.map((entry) =>
          editingId === entry.id ? (
            <ExperienceForm
              key={entry.id}
              values={values}
              onChange={setValues}
              onSave={handleSave}
              onCancel={cancelEdit}
              saving={saving}
            />
          ) : (
            <div key={entry.id} className="space-y-1 text-sm">
              <div className="flex items-center justify-between gap-2">
                <ExperienceSummaryLine entry={entry} />
                <div className="flex shrink-0 gap-1">
                  <Button variant="ghost" size="sm" onClick={() => startEdit(entry)} disabled={disabled}>
                    Edit
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => handleRemove(entry)}
                    disabled={disabled}
                  >
                    Delete
                  </Button>
                </div>
              </div>
              <ExperienceEvidencePanel candidateId={candidateId} experience={entry} evidence={evidence} />
            </div>
          ),
        )}

        {editingId === "new" ? (
          <ExperienceForm values={values} onChange={setValues} onSave={handleSave} onCancel={cancelEdit} saving={saving} />
        ) : (
          <Button variant="outline" size="sm" onClick={startAdd} disabled={disabled}>
            + Add Experience
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
