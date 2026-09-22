import { useState } from "react";

import { BulletRowsEditor, type BulletRow } from "@/components/BulletRowsEditor";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { LINK_CLASSNAME } from "@/lib/linkify";

export interface LocalProject {
  id: string;
  name: string;
  period: string;
  url: string;
}

export interface ExperienceFormValues {
  position: string;
  company: string;
  companyUrl: string;
  period: string;
  location: string;
  isGap: boolean;
  responsibilities: BulletRow[];
  achievements: BulletRow[];
  projects: LocalProject[];
}

export function emptyExperienceFormValues(): ExperienceFormValues {
  return {
    position: "",
    company: "",
    companyUrl: "",
    period: "",
    location: "",
    isGap: false,
    responsibilities: [],
    achievements: [],
    projects: [],
  };
}

function newLocalProjectId(): string {
  // Becomes the real persisted ExperienceProject.id once this form is
  // saved — same "the client-generated id just is the id, no server-side
  // reassignment" scheme as ui/graph_explorer.py's `_new_local_id()`.
  return `local-${crypto.randomUUID()}`;
}

function bulletTextsFor(rows: BulletRow[], projectId: string | null): string[] {
  return rows
    .filter((row) => row.projectId === projectId)
    .map((row) => row.text.trim())
    .filter(Boolean);
}

// Full-overwrite request body for PUT (create uses the same shape minus
// `projects` — see ExperienceSection.tsx's two-write handling for a new
// entry, mirroring ui/graph_explorer.py's `_add_experience`).
//
// A project with a blank/whitespace-only name is dropped here rather than
// sent — its own bullet rows fall back to role-level (`projectId: null`
// wasn't set on them, but since that project's id is now absent from
// `projects`, its rows are excluded from every project's own list *and*
// from the role-level list too, since they're still tagged with that
// project's id). To avoid silently losing that content, treat "no name at
// save time" exactly like "deleted": reassign its rows to role-level
// first. See `toExperienceRequestBody` below.
export function toExperienceRequestBody(values: ExperienceFormValues) {
  const namedProjectIds = new Set(
    values.projects.filter((project) => project.name.trim()).map((project) => project.id),
  );
  const normalizedProjectId = (projectId: string | null) =>
    projectId != null && namedProjectIds.has(projectId) ? projectId : null;

  const achievementsFor = (projectId: string | null) =>
    bulletTextsFor(
      values.achievements.map((row) => ({ ...row, projectId: normalizedProjectId(row.projectId) })),
      projectId,
    );
  const responsibilitiesFor = (projectId: string | null) =>
    bulletTextsFor(
      values.responsibilities.map((row) => ({ ...row, projectId: normalizedProjectId(row.projectId) })),
      projectId,
    );

  return {
    position: values.position.trim(),
    company: values.company.trim() || null,
    company_url: values.companyUrl.trim() || null,
    period: values.period.trim() || null,
    location: values.location.trim() || null,
    is_gap: values.isGap,
    responsibilities: responsibilitiesFor(null),
    achievements: achievementsFor(null),
    projects: values.projects
      .filter((project) => project.name.trim())
      .map((project) => ({
        id: project.id,
        name: project.name.trim(),
        period: project.period.trim() || null,
        achievements: achievementsFor(project.id),
        responsibilities: responsibilitiesFor(project.id),
        url: project.url.trim() || null,
      })),
  };
}

interface ExperienceFormProps {
  values: ExperienceFormValues;
  onChange: (values: ExperienceFormValues) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}

// Experience's own dedicated edit form. Achievements/Responsibilities are
// one flat list per role (BulletRowsEditor), each bullet optionally tagged
// to one of this role's Projects via a dropdown — replacing the previous
// design where project-scoped bullets lived in that Project's own nested,
// separately-saved form (ExperienceProjectsManager) and were invisible
// from the role's own Achievements/Responsibilities editor unless you
// clicked that Project's "Edit". Ports ui/graph_explorer.py's
// `_ExperienceFormDialog`/`_BulletRowsEditor` design (single unified list
// + dropdown, one combined save) — confirmed with the user as worth the
// tradeoff against the previous per-project-atomic-save architecture: a
// Project here is in-memory state only (name/period, no independent
// mutations of its own) until this form's own Save button fires one
// combined request (see ExperienceSection.tsx's handleSave).
export function ExperienceForm({ values, onChange, onSave, onCancel, saving }: ExperienceFormProps) {
  const [editingProjectId, setEditingProjectId] = useState<string | null>(null);

  const projectOptions = values.projects.map((project) => ({ id: project.id, name: project.name }));

  const handleAddProject = () => {
    const id = newLocalProjectId();
    onChange({ ...values, projects: [...values.projects, { id, name: "", period: "", url: "" }] });
    setEditingProjectId(id);
  };

  const handleProjectFieldChange = (id: string, patch: Partial<LocalProject>) => {
    onChange({
      ...values,
      projects: values.projects.map((project) => (project.id === id ? { ...project, ...patch } : project)),
    });
  };

  const handleDeleteProject = (id: string) => {
    // Unlink, don't drop: a bullet tagged to a deleted project falls back
    // to role-level rather than losing its text (same principle
    // ui/graph_explorer.py's `refresh_project_options()` documents).
    onChange({
      ...values,
      projects: values.projects.filter((project) => project.id !== id),
      achievements: values.achievements.map((row) => (row.projectId === id ? { ...row, projectId: null } : row)),
      responsibilities: values.responsibilities.map((row) =>
        row.projectId === id ? { ...row, projectId: null } : row,
      ),
    });
    if (editingProjectId === id) {
      setEditingProjectId(null);
    }
  };

  return (
    <div className="space-y-3 rounded-lg border p-2">
      <div className="space-y-1">
        <label htmlFor="experience-position" className="text-xs font-medium text-muted-foreground">
          Position
        </label>
        <Input
          id="experience-position"
          value={values.position}
          onChange={(event) => onChange({ ...values, position: event.target.value })}
          disabled={saving}
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="experience-company" className="text-xs font-medium text-muted-foreground">
          Company
        </label>
        <Input
          id="experience-company"
          value={values.company}
          onChange={(event) => onChange({ ...values, company: event.target.value })}
          disabled={saving}
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="experience-company-url" className="text-xs font-medium text-muted-foreground">
          Company website
        </label>
        <Input
          id="experience-company-url"
          value={values.companyUrl}
          onChange={(event) => onChange({ ...values, companyUrl: event.target.value })}
          placeholder="https://..."
          disabled={saving}
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="experience-period" className="text-xs font-medium text-muted-foreground">
          Period
        </label>
        <Input
          id="experience-period"
          value={values.period}
          onChange={(event) => onChange({ ...values, period: event.target.value })}
          disabled={saving}
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="experience-location" className="text-xs font-medium text-muted-foreground">
          Location
        </label>
        <Input
          id="experience-location"
          value={values.location}
          onChange={(event) => onChange({ ...values, location: event.target.value })}
          disabled={saving}
        />
      </div>
      <label className="flex items-center gap-1.5 text-sm">
        <Checkbox
          checked={values.isGap}
          onCheckedChange={(checked) => onChange({ ...values, isGap: checked === true })}
          disabled={saving}
        />
        This is a career gap
      </label>

      <ProjectsManager
        projects={values.projects}
        achievements={values.achievements}
        editingProjectId={editingProjectId}
        onEdit={setEditingProjectId}
        onDoneEditing={() => setEditingProjectId(null)}
        onFieldChange={handleProjectFieldChange}
        onDelete={handleDeleteProject}
        onAdd={handleAddProject}
        disabled={saving}
      />

      <BulletRowsEditor
        label="Achievements"
        rows={values.achievements}
        projects={projectOptions}
        onChange={(achievements) => onChange({ ...values, achievements })}
        disabled={saving}
      />
      <BulletRowsEditor
        label="Responsibilities"
        rows={values.responsibilities}
        projects={projectOptions}
        onChange={(responsibilities) => onChange({ ...values, responsibilities })}
        disabled={saving}
      />

      <div className="flex gap-2">
        <Button size="sm" onClick={onSave} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </Button>
        <Button size="sm" variant="ghost" onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// The project name as real, clickable <a> when the project has a url
// (Post-4.10 follow-up), plain text otherwise — same convention
// ExperienceSection.tsx's ExperienceSummaryLine uses for a hyperlinked
// company name; see that component's own comment for why lib/linkify.tsx's
// text-scanning helpers don't apply here.
function ProjectSummaryLine({ project }: { project: LocalProject }) {
  const name = project.name.trim() || "Untitled project";
  const period = project.period.trim() ? ` (${project.period.trim()})` : "";
  return (
    <span>
      {project.url ? (
        <a href={project.url} target="_blank" rel="noopener noreferrer" className={LINK_CLASSNAME}>
          {name}
        </a>
      ) : (
        name
      )}
      {period}
    </span>
  );
}

function ProjectsManager({
  projects,
  achievements,
  editingProjectId,
  onEdit,
  onDoneEditing,
  onFieldChange,
  onDelete,
  onAdd,
  disabled,
}: {
  projects: LocalProject[];
  achievements: BulletRow[];
  editingProjectId: string | null;
  onEdit: (id: string) => void;
  onDoneEditing: () => void;
  onFieldChange: (id: string, patch: Partial<LocalProject>) => void;
  onDelete: (id: string) => void;
  onAdd: () => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-2 border-l-2 pl-3">
      <span className="text-xs font-medium text-muted-foreground">Projects</span>
      {projects.map((project) => {
        const achievementCount = achievements.filter((row) => row.projectId === project.id).length;
        return editingProjectId === project.id ? (
          <div key={project.id} className="space-y-2 rounded-lg border p-2">
            <div className="space-y-1">
              <label
                htmlFor={`project-name-${project.id}`}
                className="text-xs font-medium text-muted-foreground"
              >
                Name
              </label>
              <Input
                id={`project-name-${project.id}`}
                value={project.name}
                onChange={(event) => onFieldChange(project.id, { name: event.target.value })}
                disabled={disabled}
              />
            </div>
            <div className="space-y-1">
              <label
                htmlFor={`project-period-${project.id}`}
                className="text-xs font-medium text-muted-foreground"
              >
                Period
              </label>
              <Input
                id={`project-period-${project.id}`}
                value={project.period}
                onChange={(event) => onFieldChange(project.id, { period: event.target.value })}
                disabled={disabled}
              />
            </div>
            <div className="space-y-1">
              <label
                htmlFor={`project-url-${project.id}`}
                className="text-xs font-medium text-muted-foreground"
              >
                Project website
              </label>
              <Input
                id={`project-url-${project.id}`}
                value={project.url}
                onChange={(event) => onFieldChange(project.id, { url: event.target.value })}
                placeholder="https://..."
                disabled={disabled}
              />
            </div>
            <Button type="button" size="sm" variant="ghost" onClick={onDoneEditing} disabled={disabled}>
              Done
            </Button>
          </div>
        ) : (
          <div key={project.id} className="flex items-center justify-between gap-2 text-sm">
            <span>
              <ProjectSummaryLine project={project} /> — {achievementCount} achievement
              {achievementCount === 1 ? "" : "s"}
            </span>
            <div className="flex shrink-0 gap-1">
              <Button variant="ghost" size="sm" onClick={() => onEdit(project.id)} disabled={disabled}>
                Edit
              </Button>
              <Button variant="destructive" size="sm" onClick={() => onDelete(project.id)} disabled={disabled}>
                Delete
              </Button>
            </div>
          </div>
        );
      })}
      <Button type="button" variant="outline" size="sm" onClick={onAdd} disabled={disabled}>
        + Add Project
      </Button>
    </div>
  );
}
