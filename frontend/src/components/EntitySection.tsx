import { closestCenter, DndContext, PointerSensor, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, useSortable, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { CircleHelp, GripVertical, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useEntityMutations } from "@/api/entities";
import type { Evidence, Experience } from "@/api/models";
import type { EntityConfig } from "@/lib/entityConfigs";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { describeEvidenceSource } from "@/lib/evidenceIndex";
import { linkifyContactLine, linkifyText } from "@/lib/linkify";
import { cn } from "@/lib/utils";

export type EntityItem = { id: string } & Record<string, unknown>;

interface EntitySectionProps {
  candidateId: string;
  config: EntityConfig;
  // Version 4, Phase 4.3: resolved by the caller (ProfileView.tsx, via
  // sectionTitlesFor(candidate.language)[config.sectionKey]) rather than
  // read off config directly — ENTITY_CONFIGS is built once at module
  // load, before any candidate (and so its language) is known.
  title: string;
  items: EntityItem[];
  disabled?: boolean;
  // Phase 15b-ii: only consulted when config.evidenceIds is set (skills/
  // technologies) — harmless to pass for every other entity.
  evidenceById?: Map<string, Evidence>;
  // Only consulted alongside evidenceById, to group the "backed by" popover
  // by which role/project each Evidence item came from.
  experience?: Experience[];
}

type FormValues = Record<string, string>;

function emptyFormValues(config: EntityConfig): FormValues {
  return Object.fromEntries(config.fields.map((field) => [field.name, ""]));
}

function itemToFormValues(config: EntityConfig, item: EntityItem): FormValues {
  return Object.fromEntries(
    config.fields.map((field) => {
      const value = item[field.name];
      return [field.name, value == null ? "" : String(value)];
    }),
  );
}

function hasChanges(config: EntityConfig, item: EntityItem, values: FormValues): boolean {
  const original = itemToFormValues(config, item);
  return config.fields.some((field) => (values[field.name] ?? "") !== (original[field.name] ?? ""));
}

// The first field in every config is the required "name"-like field
// (institution/name/label/title/organization), matching every add_X()
// method's own required first parameter — everything after it is
// optional, submitted as null (not "") when left blank.
function toRequestBody(config: EntityConfig, values: FormValues): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  config.fields.forEach((field, index) => {
    const raw = (values[field.name] ?? "").trim();
    body[field.name] = index === 0 ? raw : raw === "" ? null : raw;
  });
  return body;
}

function showError(error: unknown): void {
  const category = error instanceof ApiError ? error.category : "Error";
  const message = error instanceof ApiError ? error.message : "Something went wrong.";
  toast.error(category, { description: message });
}

// Extracted as a plain, directly-testable function of (items, fromId,
// toId) — same reasoning BulletRowsEditor.tsx's reorderBulletRows
// documents: jsdom has no real pointer/drag geometry to simulate an
// actual drag gesture through, so this is exercised directly in tests
// rather than through a simulated DndContext drag. Returns `items`
// unchanged if either id isn't found, rather than throwing — dnd-kit can
// in principle fire a drag-end after the item list has already changed
// out from under it (e.g. a concurrent delete).
export function reorderEntityItems(items: EntityItem[], fromId: string, toId: string): EntityItem[] {
  const fromIndex = items.findIndex((item) => item.id === fromId);
  const toIndex = items.findIndex((item) => item.id === toId);
  if (fromIndex === -1 || toIndex === -1) {
    return items;
  }
  const next = [...items];
  const [moved] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, moved);
  return next;
}

// Phase 21: for config.categoryHeaders entities (skills/technologies),
// "category" is derived from position, not a directly editable field — a
// header is a normal item (is_category_header: true) whose `name` is the
// category label, sitting in the same flat list as the skills it groups.
function isCategoryHeader(item: EntityItem): boolean {
  return item.is_category_header === true;
}

export interface HeaderGroup {
  header: EntityItem | null;
  members: EntityItem[];
}

// Walks the flat list once, starting a new group on every header row — the
// `header: null` group collects any items before the first header (no
// category). Shared by the grouped read-only view and deriveCategories
// below, so both agree on exactly the same grouping.
export function groupItemsByHeader(items: EntityItem[]): HeaderGroup[] {
  const groups: HeaderGroup[] = [{ header: null, members: [] }];
  for (const item of items) {
    if (isCategoryHeader(item)) {
      groups.push({ header: item, members: [] });
    } else {
      groups[groups.length - 1].members.push(item);
    }
  }
  return groups.filter((group) => group.header !== null || group.members.length > 0);
}

// Every non-header item's effective category: the nearest preceding
// header's label, or null if none precedes it.
export function deriveCategories(items: EntityItem[]): Map<string, string | null> {
  const map = new Map<string, string | null>();
  for (const group of groupItemsByHeader(items)) {
    const category = group.header ? String(group.header.name ?? "") : null;
    for (const member of group.members) {
      map.set(member.id, category);
    }
  }
  return map;
}

// True the first time a categoryHeaders section is opened against data
// that predates this feature: real category values already exist, but no
// header row has ever been created to back them yet. Never true once any
// header exists, even an empty one — that's what makes the migration
// below one-shot.
function needsCategoryHeaderBootstrap(items: EntityItem[]): boolean {
  return !items.some(isCategoryHeader) && items.some((item) => (item.category as string | null) != null);
}

// Module-level, not a component-instance ref: a real StrictMode double-
// mount (or a fast-refresh remount) creates a brand-new EntitySection
// instance with its own fresh useRef before the first instance's create/
// reorder calls have landed and invalidated the query — a per-instance
// ref guard doesn't see that and the migration ran twice in practice,
// creating duplicate header rows. Keyed by candidate+entity so it still
// only blocks the same logical migration, and survives remounts within
// the same page load (only a hard page reload clears it, at which point
// a real header already exists if the first attempt succeeded, so
// needsCategoryHeaderBootstrap itself goes false).
const bootstrappedSections = new Set<string>();

// Contacts gets its own summary rendering rather than the generic
// `linkifyText(config.summarize(item))` every other entity uses: a
// Contact's `value` is very often a bare-domain link (LinkedIn/portfolio/
// GitHub, e.g. "linkedin.com/in/..." with no http(s)/www prefix at all —
// confirmed directly, from a real ingested resume), and safely detecting
// that requires checking a whole, known `value` field rather than
// scanning arbitrary summary text — see linkify.tsx's own comment on
// `contactValueHref` for why a general bare-domain scan would misfire on
// things like "ASP.NET"/"Node.js" elsewhere in the app. Every other
// entity keeps the general (http(s)/www/email-substring) linkifyText
// treatment, which is a safe no-op for text with no link in it.
function renderItemSummary(config: EntityConfig, item: EntityItem): ReactNode {
  if (config.pathSegment === "contacts") {
    return linkifyContactLine(String(item.label ?? ""), String(item.value ?? ""));
  }
  return linkifyText(config.summarize(item));
}

// Generic read/bulk-edit/add/delete/reorder list, config-driven — the
// React equivalent of ui/graph_explorer.py's _EntityListSection. One
// component serves all 11 simple entity types via lib/entityConfigs.ts,
// the same "factory, not hand-duplication" choice entity_crud.py already
// made on the backend (now including its own generic `reorder_entities`,
// used here too).
//
// Edit is section-wide, not per-row: one "Edit" toggle turns every row's
// text into editable fields at once (Save writes only the rows that
// actually changed), rather than needing to click Edit/Save on each row
// in turn. Reported directly as a real friction point when a row-at-a-
// time flow meant editing several skills took several separate Edit/Save
// round trips. Delete (per row) and "+ Add X" are deliberately NOT part
// of this edit mode — both stay immediately available regardless of
// whether the section is in bulk-edit mode, since neither needs the rest
// of the list to be editable first.
//
// Drag-reorder (dnd-kit, same DndContext/SortableContext/useSortable
// shape as BulletRowsEditor.tsx's identical Experience-bullets feature)
// is scoped to edit mode only — reported directly as the natural
// follow-up once bullet reordering shipped for Experience: unlike
// BulletRowsEditor's rows (in-memory form state, only ever persisted as
// part of one atomic Experience save), every item here is already
// individually persisted, so a drop fires CandidateService.
// reorder_entities immediately via a new `POST .../reorder` route —
// there's no encompassing "save the whole list" step to defer it to,
// matching Delete's own "acts immediately, independent of edit mode"
// precedent.
export function EntitySection({
  candidateId,
  config,
  title,
  items,
  disabled,
  evidenceById,
  experience = [],
}: EntitySectionProps) {
  const { create, update, remove, reorder } = useEntityMutations<EntityItem>(candidateId, config.pathSegment);
  const [editingAll, setEditingAll] = useState(false);
  const [formValuesById, setFormValuesById] = useState<Record<string, FormValues>>({});
  const [saving, setSaving] = useState(false);
  const [addingNew, setAddingNew] = useState(false);
  const [newFormValues, setNewFormValues] = useState<FormValues>(emptyFormValues(config));
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  // Phase 21 — one-shot migration: the first time a categoryHeaders
  // section (skills/technologies) is opened against data that predates
  // this feature, synthesize one header per distinct existing category
  // value (first-appearance order, mirroring app/cv_assembler.py's
  // _rank_by_category grouping exactly, so the migrated structure matches
  // what the exported CV already shows) and reorder the list into
  // contiguous runs behind them. Guarded by the module-level
  // bootstrappedSections set (see its own comment) — this must not
  // re-start on the re-renders that happen while its own awaits are in
  // flight, and a plain per-instance ref isn't enough to guarantee that.
  useEffect(() => {
    const bootstrapKey = `${candidateId}:${config.pathSegment}`;
    if (!config.categoryHeaders || bootstrappedSections.has(bootstrapKey) || !needsCategoryHeaderBootstrap(items)) {
      return;
    }
    bootstrappedSections.add(bootstrapKey);

    async function bootstrapCategoryHeaders() {
      const nameField = config.fields[0].name;
      const groups = new Map<string | null, EntityItem[]>();
      for (const item of items) {
        const key = (item.category as string | null) ?? null;
        const group = groups.get(key);
        if (group) {
          group.push(item);
        } else {
          groups.set(key, [item]);
        }
      }
      try {
        const orderedIds: string[] = [];
        for (const [category, members] of groups) {
          if (category !== null) {
            const header = await create.mutateAsync({ [nameField]: category, is_category_header: true });
            orderedIds.push(header.id);
          }
          orderedIds.push(...members.map((member) => member.id));
        }
        await reorder.mutateAsync(orderedIds);
      } catch (error) {
        showError(error);
      }
    }

    void bootstrapCategoryHeaders();
    // create/reorder deliberately excluded: useMutation()'s returned
    // object is not referentially stable (it's a fresh object on every
    // idle/pending/success transition), so including it here would
    // re-trigger this effect purely from calling mutateAsync — see the
    // recompute effect below's comment for the real bug that caused live.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, config, candidateId]);

  // Phase 21 — ongoing maintenance: after any structural change (reorder,
  // add, delete, or a header's label saved), every skill's derived
  // category (nearest preceding header, or null) may have shifted. Skips
  // entirely while a bootstrap migration is still needed, so the two never
  // race each other on first mount.
  //
  // A real runaway-loop bug was found live here: `update` (useMutation()'s
  // returned object) is NOT referentially stable — it's a fresh object on
  // every idle/pending/success transition — so depending on it (as the
  // first version of this effect did) re-triggered the effect purely from
  // *calling* mutateAsync, independent of whether `items` had actually
  // changed. Against a real profile that meant: PUT succeeds -> the
  // mutation's own state change re-fires this effect before the
  // invalidate-triggered refetch lands -> `items` is still stale -> the
  // "diff" looks unchanged -> another PUT, forever (hundreds of identical
  // PUTs to the same two skills, confirmed live). Fixed by depending only
  // on `items`/`config` (candidateId/create/reorder are the bootstrap
  // effect's own concern) — `update.mutateAsync` is still read via
  // closure, just never used to decide whether to re-run. `persistingRef`
  // stays as a second, independent guard against overlapping runs (e.g. if
  // `items` itself updates again before a run's sequential loop
  // finishes) — belt and braces, not a substitute for the dependency fix.
  const persistingRef = useRef(false);
  useEffect(() => {
    if (!config.categoryHeaders || needsCategoryHeaderBootstrap(items) || persistingRef.current) {
      return;
    }
    const derived = deriveCategories(items);
    const changed = items.filter((item) => {
      if (isCategoryHeader(item)) {
        return false;
      }
      const nextCategory = derived.get(item.id) ?? null;
      const currentCategory = (item.category as string | null) ?? null;
      return nextCategory !== currentCategory;
    });
    if (changed.length === 0) {
      return;
    }
    persistingRef.current = true;

    async function persistDerivedCategories() {
      try {
        for (const item of changed) {
          await update.mutateAsync({ itemId: item.id, body: { category: derived.get(item.id) ?? null } });
        }
      } catch (error) {
        showError(error);
      } finally {
        persistingRef.current = false;
      }
    }

    void persistDerivedCategories();
    // update deliberately excluded — see comment above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items, config]);

  const handleAddCategory = () => {
    const nameField = config.fields[0].name;
    create.mutate(
      { [nameField]: "New Category", is_category_header: true },
      { onError: showError },
    );
  };

  const startEditAll = () => {
    setFormValuesById(Object.fromEntries(items.map((item) => [item.id, itemToFormValues(config, item)])));
    setEditingAll(true);
  };

  const cancelEditAll = () => {
    setEditingAll(false);
    setFormValuesById({});
  };

  const handleFieldChange = (itemId: string, name: string, value: string) => {
    setFormValuesById((previous) => ({
      ...previous,
      [itemId]: { ...previous[itemId], [name]: value },
    }));
  };

  const handleSaveAll = async () => {
    const changed = items.filter((item) => {
      const values = formValuesById[item.id];
      return values && hasChanges(config, item, values);
    });
    if (changed.length === 0) {
      setEditingAll(false);
      setFormValuesById({});
      return;
    }
    setSaving(true);
    try {
      // Sequential, deliberately not Promise.all: every entity here lives
      // inside the same whole-Candidate JSON blob row (CandidateRow.data),
      // and each PUT is its own independent read-mutate-write round trip
      // (CandidateService.update_X -> _require_existing()/_save()) with no
      // locking between requests. Firing them concurrently let a later
      // request's read (taken before an earlier request's write had
      // landed) clobber that earlier write when it saved the whole blob
      // back — a real, reported silent-data-loss bug: editing several rows
      // at once and saving could leave only one edit actually persisted.
      // Awaiting one at a time makes each write fully land before the next
      // request reads, closing the race.
      for (const item of changed) {
        await update.mutateAsync({ itemId: item.id, body: toRequestBody(config, formValuesById[item.id]) });
      }
      setEditingAll(false);
      setFormValuesById({});
    } catch (error) {
      showError(error);
    } finally {
      setSaving(false);
    }
  };

  const startAdd = () => {
    setAddingNew(true);
    setNewFormValues(emptyFormValues(config));
  };

  const cancelAdd = () => {
    setAddingNew(false);
    setNewFormValues(emptyFormValues(config));
  };

  const handleAddFieldChange = (name: string, value: string) => {
    setNewFormValues((previous) => ({ ...previous, [name]: value }));
  };

  const handleSaveNew = () => {
    create.mutate(toRequestBody(config, newFormValues), { onSuccess: cancelAdd, onError: showError });
  };

  const handleRemove = (item: EntityItem) => {
    if (!window.confirm(`Remove "${config.summarize(item)}"?`)) {
      return;
    }
    remove.mutate(item.id, { onError: showError });
  };

  // Delete acts immediately regardless of edit mode (see this component's
  // own docstring), but a per-row click previously had *no* visual
  // feedback at all while its request was in flight — the button stayed
  // fully interactive, showing nothing different, for however long the
  // round trip took. Reported directly: a real delete (confirmed gone
  // server-side moments later) looked like it "didn't work" because
  // nothing on screen changed right away. `remove` is one shared
  // mutation for the whole section (not one per row), so `.variables`
  // holds whichever item id the *most recent* call was for — exactly
  // right here since a person can only clear one confirm() dialog at a
  // time, so only one delete is ever really in flight at once.
  const isDeleting = (item: EntityItem) => remove.isPending && remove.variables === item.id;

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (over == null || active.id === over.id) {
      return;
    }
    const next = reorderEntityItems(items, String(active.id), String(over.id));
    if (next === items) {
      return;
    }
    reorder.mutate(
      next.map((item) => item.id),
      { onError: showError },
    );
  };

  const rowsDisabled = disabled || saving;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardAction>
          {editingAll ? (
            <div className="flex gap-2">
              <Button size="sm" onClick={handleSaveAll} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </Button>
              <Button size="sm" variant="ghost" onClick={cancelEditAll} disabled={saving}>
                Cancel
              </Button>
            </div>
          ) : (
            items.length > 0 && (
              <Button variant="ghost" size="sm" onClick={startEditAll} disabled={disabled}>
                Edit
              </Button>
            )
          )}
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-2">
        {editingAll ? (
          <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={items.map((item) => item.id)} strategy={verticalListSortingStrategy}>
              {items.map((item) => (
                <SortableEntityRow
                  key={item.id}
                  id={item.id}
                  item={item}
                  config={config}
                  title={title}
                  values={formValuesById[item.id] ?? itemToFormValues(config, item)}
                  onChange={(name, value) => handleFieldChange(item.id, name, value)}
                  onRemove={() => handleRemove(item)}
                  disabled={rowsDisabled}
                  deleting={isDeleting(item)}
                />
              ))}
            </SortableContext>
          </DndContext>
        ) : config.categoryHeaders ? (
          groupItemsByHeader(items).map((group, index) => (
            <div key={group.header?.id ?? `uncategorized-${index}`} className="space-y-1">
              {group.header && (
                <div className="flex items-center justify-between gap-2 pt-1">
                  <span className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    {String(group.header.name)}
                  </span>
                  <Button
                    variant="destructive"
                    size="sm"
                    className="shrink-0"
                    onClick={() => handleRemove(group.header!)}
                    disabled={rowsDisabled || isDeleting(group.header)}
                  >
                    {isDeleting(group.header) ? "Deleting…" : "Delete"}
                  </Button>
                </div>
              )}
              {group.members.map((item) => (
                <div key={item.id} className="flex items-center justify-between gap-2 text-sm">
                  <span className="flex-1">
                    {String(item.name)}
                    {item.proficiency ? ` (${String(item.proficiency)})` : ""}
                  </span>
                  {config.evidenceIds && evidenceById && (
                    <EvidenceBackedBySummary
                      ids={config.evidenceIds(item)}
                      evidenceById={evidenceById}
                      experience={experience}
                    />
                  )}
                  <Button
                    variant="destructive"
                    size="sm"
                    className="shrink-0"
                    onClick={() => handleRemove(item)}
                    disabled={rowsDisabled || isDeleting(item)}
                  >
                    {isDeleting(item) ? "Deleting…" : "Delete"}
                  </Button>
                </div>
              ))}
            </div>
          ))
        ) : (
          items.map((item) => (
            <div key={item.id} className="flex items-center justify-between gap-2 text-sm">
              <span className="flex-1">{renderItemSummary(config, item)}</span>
              {config.evidenceIds && evidenceById && (
                <EvidenceBackedBySummary
                  ids={config.evidenceIds(item)}
                  evidenceById={evidenceById}
                  experience={experience}
                />
              )}
              <Button
                variant="destructive"
                size="sm"
                className="shrink-0"
                onClick={() => handleRemove(item)}
                disabled={rowsDisabled || isDeleting(item)}
              >
                {isDeleting(item) ? "Deleting…" : "Delete"}
              </Button>
            </div>
          ))
        )}

        {editingAll && config.categoryHeaders && (
          <Button variant="outline" size="sm" onClick={handleAddCategory} disabled={disabled}>
            + Add Category
          </Button>
        )}

        {addingNew ? (
          <EntityForm
            config={config}
            values={newFormValues}
            onChange={handleAddFieldChange}
            onSave={handleSaveNew}
            onCancel={cancelAdd}
            saving={create.isPending}
          />
        ) : (
          <Button variant="outline" size="sm" onClick={startAdd} disabled={disabled}>
            + Add {config.singularLabel}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

// One draggable row in bulk-edit mode: a grip handle, the row's editable
// fields, and its (always-immediate, edit-mode-independent) Delete
// button. Only ever rendered while editingAll is true — the plain
// read-only row above handles every other case, so there's no
// conditional-hook concern here despite useSortable needing a stable
// mount.
function SortableEntityRow({
  id,
  item,
  config,
  title,
  values,
  onChange,
  onRemove,
  disabled,
  deleting,
}: {
  id: string;
  item: EntityItem;
  config: EntityConfig;
  title: string;
  values: FormValues;
  onChange: (name: string, value: string) => void;
  onRemove: () => void;
  disabled?: boolean;
  deleting?: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id });
  const style = { transform: CSS.Transform.toString(transform), transition };
  const isHeader = isCategoryHeader(item);
  const nameField = config.fields[0].name;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "space-y-1 rounded-lg border p-2 text-sm",
        isHeader ? "bg-muted" : "bg-card",
        isDragging && "opacity-50",
      )}
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          className="mt-1.5 shrink-0 cursor-grab text-muted-foreground"
          aria-label={`Drag to reorder ${title.toLowerCase()}`}
          disabled={disabled}
          {...attributes}
          {...listeners}
        >
          <GripVertical className="size-4" />
        </button>
        {isHeader ? (
          <Input
            className="flex-1 font-semibold tracking-wide uppercase"
            aria-label="Category label"
            value={values[nameField] ?? ""}
            onChange={(event) => onChange(nameField, event.target.value)}
            disabled={disabled}
          />
        ) : (
          <EntityFieldsOnly config={config} itemId={item.id} values={values} onChange={onChange} disabled={disabled} />
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          className="mt-0.5 shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
          aria-label={deleting ? "Deleting…" : "Delete"}
          onClick={onRemove}
          disabled={disabled || deleting}
        >
          <Trash2 className={cn("size-4", deleting && "animate-pulse")} />
        </Button>
      </div>
    </div>
  );
}

// Read-only "why does this skill exist" summary — a count plus a "?"
// popover trigger, rendered as its own column in the row (not a new line
// under it — reported as taking up too much vertical space when every
// row shows its own count) under a skills/technologies row when its
// evidence_ids is non-empty. Used to always render the full backing-
// evidence text inline; reported as clutter (hard to read with several
// skills each showing their own list at once), so it's collapsed behind
// the popover instead — same information, opened on demand. Read-only
// view only — SortableEntityRow (bulk-edit mode) deliberately never
// renders this at all, reported directly as unwanted during editing.
//
// The popover groups items by describeEvidenceSource (company, position,
// project) into one heading per source with real bullets underneath,
// rather than repeating each item's own source_context individually —
// reported as showing the same "Company, Project: <bullet text again>"
// restatement twice per line (source_context is usually just that
// restatement — same duplication ExperienceEvidencePanel.tsx's own
// grouped view already avoids by never rendering source_context at all).
function EvidenceBackedBySummary({
  ids,
  evidenceById,
  experience,
}: {
  ids: string[];
  evidenceById: Map<string, Evidence>;
  experience: Experience[];
}) {
  const items = ids.map((id) => evidenceById.get(id)).filter((item): item is Evidence => item != null);
  if (items.length === 0) {
    return null;
  }
  const groups = new Map<string, Evidence[]>();
  for (const item of items) {
    const heading = describeEvidenceSource(item, experience) ?? "";
    const group = groups.get(heading);
    if (group) {
      group.push(item);
    } else {
      groups.set(heading, [item]);
    }
  }
  return (
    <div className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
      <span>Supported by achievements: {items.length}</span>
      <Popover>
        <PopoverTrigger asChild>
          <Button type="button" variant="ghost" size="icon-xs" aria-label="Show supporting achievements">
            <CircleHelp />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-80 space-y-2 text-xs">
          {[...groups.entries()].map(([heading, groupItems]) => (
            <div key={heading || "(no linked role)"} className="space-y-1">
              {heading && <p className="font-medium text-foreground">{heading}</p>}
              <ul className="list-disc space-y-0.5 pl-4">
                {groupItems.map((item) => (
                  <li key={item.id}>{item.text}</li>
                ))}
              </ul>
            </div>
          ))}
        </PopoverContent>
      </Popover>
    </div>
  );
}

interface EntityFieldsProps {
  config: EntityConfig;
  itemId: string;
  values: FormValues;
  onChange: (name: string, value: string) => void;
  disabled?: boolean;
}

// Just the input fields, no Save/Cancel of their own — used by the
// section-wide bulk-edit mode above, where one Save/Cancel pair (in the
// CardHeader) applies to every row at once instead of each row owning
// its own. `itemId` (the entity's own id, not a form field) keeps every
// row's DOM ids/label associations unique — FormValues itself is keyed by
// config.fields' names only (never "id"), so reusing it here would have
// given every row's inputs the exact same id.
function EntityFieldsOnly({ config, itemId, values, onChange, disabled }: EntityFieldsProps) {
  return (
    <div className="flex-1 space-y-2">
      {config.fields.map((field) => (
        <div key={field.name} className="space-y-1">
          <label
            htmlFor={`${config.pathSegment}-${itemId}-${field.name}`}
            className="text-xs font-medium text-muted-foreground"
          >
            {field.label}
          </label>
          {field.multiline ? (
            <Textarea
              id={`${config.pathSegment}-${itemId}-${field.name}`}
              value={values[field.name] ?? ""}
              onChange={(event) => onChange(field.name, event.target.value)}
              disabled={disabled}
              rows={3}
            />
          ) : (
            <Input
              id={`${config.pathSegment}-${itemId}-${field.name}`}
              value={values[field.name] ?? ""}
              onChange={(event) => onChange(field.name, event.target.value)}
              disabled={disabled}
            />
          )}
        </div>
      ))}
    </div>
  );
}

interface EntityFormProps {
  config: EntityConfig;
  values: FormValues;
  onChange: (name: string, value: string) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}

// The "+ Add X" form — a standalone flow, independent of the section-wide
// bulk-edit mode above, so it keeps its own Save/Cancel.
function EntityForm({ config, values, onChange, onSave, onCancel, saving }: EntityFormProps) {
  return (
    <div className="space-y-2 rounded-lg border p-2">
      {config.fields.map((field) => (
        <div key={field.name} className="space-y-1">
          <label htmlFor={`${config.pathSegment}-new-${field.name}`} className="text-xs font-medium text-muted-foreground">
            {field.label}
          </label>
          {field.multiline ? (
            <Textarea
              id={`${config.pathSegment}-new-${field.name}`}
              value={values[field.name] ?? ""}
              onChange={(event) => onChange(field.name, event.target.value)}
              rows={3}
            />
          ) : (
            <Input
              id={`${config.pathSegment}-new-${field.name}`}
              value={values[field.name] ?? ""}
              onChange={(event) => onChange(field.name, event.target.value)}
            />
          )}
        </div>
      ))}
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
