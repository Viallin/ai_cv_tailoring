import { closestCenter, DndContext, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export interface BulletRow {
  // Client-side only, generated on flatten/add (see ExperienceSection.tsx's
  // experienceToValues and this file's own `add`) — never sent to the
  // backend (ExperienceForm.tsx's toExperienceRequestBody never reads it).
  // Exists purely to give dnd-kit a stable identity to track across
  // reorders; an array index can't serve that role since it's exactly
  // what changes when a row moves.
  id: string;
  text: string;
  // null = role-level; otherwise a LocalProject.id from the same
  // ExperienceForm's in-memory Projects list.
  projectId: string | null;
}

interface ProjectOption {
  id: string;
  name: string;
}

interface BulletRowsEditorProps {
  label: string;
  rows: BulletRow[];
  projects: ProjectOption[];
  onChange: (rows: BulletRow[]) => void;
  disabled?: boolean;
}

const NONE_VALUE = "none";

function newBulletId(): string {
  return `bullet-${crypto.randomUUID()}`;
}

// Extracted as a plain, directly-testable function of (rows, fromId,
// toId) — jsdom has no real pointer/drag geometry to simulate an actual
// drag gesture through (the same limitation the A4 CV editor's own
// drag-reorder hits — see lib/tiptap/plugins.test.ts's own note on
// testing native ProseMirror node drags instead), so this is exercised
// directly in tests rather than through a simulated DndContext drag.
// Returns `rows` unchanged if either id isn't found, rather than
// throwing — dnd-kit can in principle fire a drag-end after the item
// list has already changed out from under it.
export function reorderBulletRows(rows: BulletRow[], fromId: string, toId: string): BulletRow[] {
  const fromIndex = rows.findIndex((row) => row.id === fromId);
  const toIndex = rows.findIndex((row) => row.id === toId);
  if (fromIndex === -1 || toIndex === -1) {
    return rows;
  }
  const next = [...rows];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}

// One flat, freely-editable, drag-reorderable list of bullet rows, each
// pairable with one of the role's current Projects via a dropdown
// ("(none)" = role-level) — the React port of ui/graph_explorer.py's
// `_BulletRowsEditor`. Replaces BulletListEditor for Experience
// specifically: previously, role-level and project-level bullets lived in
// two separate forms (the role's own Achievements/Responsibilities editor,
// and each Project's own nested form), so a role whose achievements were
// entirely project-scoped showed an empty top-level Achievements list —
// the real content was one more "Edit" click away on a Project row. This
// single list makes every bullet visible and reassignable in one place.
// Confirmed with the user: worth the tradeoff against the previous
// per-project-atomic-save architecture (see ExperienceForm.tsx's
// docstring).
//
// Drag-reorder (dnd-kit, already a dependency for the A4 CV editor's own
// bullet reordering — DocumentExperienceSection.tsx, same
// DndContext/SortableContext/useSortable shape mirrored here) was missing
// entirely until reported directly: there was no way to reorder bullets
// in the Profile Explorer at all, in any Experience role. Reordering the
// flat `rows` array is sufficient on its own — toExperienceRequestBody's
// per-project/role-level split already preserves each group's relative
// order via a plain `.filter()`, so moving a row here is exactly moving
// it in the exported order too.
export function BulletRowsEditor({ label, rows, projects, onChange, disabled }: BulletRowsEditorProps) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  const updateAt = (index: number, patch: Partial<BulletRow>) => {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };

  const removeAt = (index: number) => {
    onChange(rows.filter((_, i) => i !== index));
  };

  const add = () => {
    onChange([...rows, { id: newBulletId(), text: "", projectId: null }]);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over == null || active.id === over.id) {
      return;
    }
    onChange(reorderBulletRows(rows, String(active.id), String(over.id)));
  };

  return (
    <div className="space-y-1">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={rows.map((row) => row.id)} strategy={verticalListSortingStrategy}>
          <div className="space-y-1">
            {rows.map((row, index) => (
              <BulletRowItem
                key={row.id}
                id={row.id}
                index={index}
                label={label}
                row={row}
                projects={projects}
                onTextChange={(text) => updateAt(index, { text })}
                onProjectChange={(projectId) => updateAt(index, { projectId })}
                onRemove={() => removeAt(index)}
                disabled={disabled}
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
      <Button type="button" variant="outline" size="sm" onClick={add} disabled={disabled}>
        + Add {label.replace(/s$/, "")}
      </Button>
    </div>
  );
}

function BulletRowItem({
  id,
  index,
  label,
  row,
  projects,
  onTextChange,
  onProjectChange,
  onRemove,
  disabled,
}: {
  id: string;
  index: number;
  label: string;
  row: BulletRow;
  projects: ProjectOption[];
  onTextChange: (text: string) => void;
  onProjectChange: (projectId: string | null) => void;
  onRemove: () => void;
  disabled?: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = { transform: CSS.Transform.toString(transform), transition };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn("flex items-start gap-2 rounded-lg border bg-card p-2", isDragging && "opacity-50")}
    >
      <button
        type="button"
        className="mt-1.5 shrink-0 cursor-grab text-muted-foreground"
        aria-label={`Drag to reorder ${label.toLowerCase()} ${index + 1}`}
        disabled={disabled}
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-4" />
      </button>
      <Textarea
        aria-label={`${label} ${index + 1}`}
        value={row.text}
        onChange={(event) => onTextChange(event.target.value)}
        rows={2}
        disabled={disabled}
      />
      <Select
        value={row.projectId ?? NONE_VALUE}
        onValueChange={(value) => onProjectChange(value === NONE_VALUE ? null : value)}
        disabled={disabled}
      >
        <SelectTrigger aria-label={`${label} ${index + 1} project`} className="w-36 shrink-0">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={NONE_VALUE}>(none)</SelectItem>
          {projects.map((project) => (
            <SelectItem key={project.id} value={project.id}>
              {project.name.trim() || "Untitled project"}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="mt-0.5 shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
        aria-label="Remove"
        onClick={onRemove}
        disabled={disabled}
      >
        <Trash2 className="size-4" />
      </Button>
    </div>
  );
}
