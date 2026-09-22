import type { JSONContent } from "@tiptap/core";

import type { DocumentBlock, DocumentEntry, DocumentModel, DocumentSection, TextRun } from "@/lib/structuredDocument";

// Phase 26 — DocumentModel ⇄ Tiptap JSON doc. A total, lossless bijection
// with no per-section/per-kind special-casing: every optional
// DocumentBlock field maps 1:1 to a same-named node attr on `entry`/
// `bullet` (see lib/tiptap/schema.ts), and every section's entries map
// the same way regardless of which section they're in. The one real
// gotcha: a ProseMirror text node can never hold `text: ""`, so empty
// text maps to `content: []`, not a zero-length text node.
//
// `entry.content = "entryHeading bullet*"` (schema.ts) is why entries
// round-trip through a wrapper `entryHeading` node that plain
// DocumentBlock/DocumentEntry never had — entryToJSON/entryFromJSON are
// the only two functions here that know about it; everything above them
// (sectionToJSON/DocumentModel) is unaffected.

function textContent(text: string): JSONContent[] {
  return text.length > 0 ? [{ type: "text", text }] : [];
}

// Reads every text child rather than assuming exactly one — ProseMirror
// can legitimately produce adjacent text nodes (undo steps, paste) even
// in this mark-less schema.
function textFromContent(content: JSONContent[] | undefined): string {
  return (content ?? [])
    .filter((node) => node.type === "text")
    .map((node) => node.text ?? "")
    .join("");
}

// Phase 31 — marks are this phase's source of truth for a block's rich
// formatting; `runs[]` is derived from them, never stored as its own
// node attr (that was the pre-Phase-31 shape, and it's why a
// Skills/Technologies category's bold label — the one existing runs
// producer, buildCompactSkillEntries — rendered bold in every export but
// invisibly plain on screen: the attr and the actual text content were
// two disconnected things). contentFromRuns/runsFromContent are the two
// halves of that bijection, used by both entryHeading and bullet content
// below — no per-section special-casing, same rule this file's own
// top-of-file comment already states for every other field.
function marksFromRun(run: TextRun): JSONContent["marks"] {
  const marks: NonNullable<JSONContent["marks"]> = [];
  if (run.bold) marks.push({ type: "bold" });
  if (run.italic) marks.push({ type: "italic" });
  if (run.underline) marks.push({ type: "underline" });
  if (run.link) marks.push({ type: "link", attrs: { href: run.link } });
  return marks.length > 0 ? marks : undefined;
}

// Outbound: a run with empty text is dropped rather than emitting a
// zero-length ProseMirror text node (invalid — same constraint
// textContent's own docstring already documents for the runs-less case).
function contentFromRuns(runs: TextRun[] | undefined, text: string): JSONContent[] {
  if (!runs || runs.length === 0) return textContent(text);
  return runs
    .filter((run) => run.text.length > 0)
    .map((run) => {
      const marks = marksFromRun(run);
      return marks ? { type: "text", text: run.text, marks } : { type: "text", text: run.text };
    });
}

interface MarkFlags {
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  link?: string;
}

function flagsFromMarks(marks: JSONContent["marks"] | undefined): MarkFlags {
  const flags: MarkFlags = {};
  for (const mark of marks ?? []) {
    if (mark.type === "bold") flags.bold = true;
    else if (mark.type === "italic") flags.italic = true;
    else if (mark.type === "underline") flags.underline = true;
    else if (mark.type === "link") flags.link = (mark.attrs?.href as string | undefined) ?? "";
  }
  return flags;
}

function sameFlags(a: MarkFlags, b: MarkFlags): boolean {
  return a.bold === b.bold && a.italic === b.italic && a.underline === b.underline && a.link === b.link;
}

// Inbound: undefined (not `[]`) when nothing in `content` carries a mark
// — keeps every block this phase's UI never touches (still the vast
// majority: anything the user hasn't selected-and-formatted) structurally
// identical to a pre-Phase-31 DocumentBlock, matching outAttrs/inAttrs's
// own "absent stays absent" rule. Adjacent text nodes sharing an
// identical mark set merge into one run — ProseMirror can legitimately
// produce more than one (undo steps, paste), same reasoning
// textFromContent's own comment gives for the mark-less case.
function runsFromContent(content: JSONContent[] | undefined): TextRun[] | undefined {
  const nodes = (content ?? []).filter((node) => node.type === "text" && (node.text?.length ?? 0) > 0);
  if (nodes.length === 0 || !nodes.some((node) => (node.marks?.length ?? 0) > 0)) return undefined;

  const runs: TextRun[] = [];
  for (const node of nodes) {
    const flags = flagsFromMarks(node.marks);
    const previous = runs[runs.length - 1];
    if (previous && sameFlags(previous, flags)) {
      previous.text += node.text ?? "";
    } else {
      runs.push({ text: node.text ?? "", ...flags });
    }
  }
  return runs;
}

// Outbound: DocumentBlock's optional fields have no single "absent" JSON
// representation (JSONContent attrs must be present, `undefined` isn't
// valid JSON) — every one collapses to `null` when unset. `runs` is
// deliberately not here — see contentFromRuns/runsFromContent above.
function outAttrs(block: DocumentBlock) {
  return {
    locked: block.locked ?? null,
    kind: block.kind ?? null,
    evidence_id: block.evidence_id ?? null,
    alignment: block.alignment ?? null,
  };
}

// Inbound: collapses both `null` and `undefined` attrs to `undefined` —
// no existing code path distinguishes e.g. `locked: false` from absent,
// so this keeps reconstructed DocumentBlocks structurally identical to
// what structuredDocument.ts's own builders produce (they never set a
// field to `null`, only omit it or set a real value).
function inAttrs(attrs: Record<string, unknown> | undefined) {
  const a = attrs ?? {};
  return {
    locked: (a.locked as boolean | null | undefined) ?? undefined,
    kind: (a.kind as DocumentBlock["kind"] | null | undefined) ?? undefined,
    evidence_id: (a.evidence_id as string | null | undefined) ?? undefined,
    alignment: (a.alignment as DocumentBlock["alignment"] | null | undefined) ?? undefined,
  };
}

function bulletToJSON(bullet: DocumentBlock): JSONContent {
  return {
    type: "bullet",
    attrs: { id: bullet.id, included: bullet.included, ...outAttrs(bullet) },
    content: contentFromRuns(bullet.runs, bullet.text),
  };
}

function bulletFromJSON(json: JSONContent): DocumentBlock {
  return {
    id: json.attrs?.id as string,
    text: textFromContent(json.content),
    included: (json.attrs?.included as boolean) ?? true,
    ...inAttrs(json.attrs),
    runs: runsFromContent(json.content),
  };
}

function entryToJSON(entry: DocumentEntry): JSONContent {
  return {
    type: "entry",
    attrs: {
      id: entry.id,
      included: entry.included,
      // Phase 30 — entry-only (see DocumentEntry.page_break_before's own
      // docstring), so not part of the shared outAttrs/inAttrs pair
      // bulletToJSON also uses. `?? null`, not `?? false` — same
      // "absent collapses to null, not the field's own falsy value"
      // convention outAttrs/inAttrs already use for locked/kind/etc.,
      // so a round-trip through this layer doesn't turn "never set"
      // into "explicitly set to false".
      page_break_before: entry.page_break_before ?? null,
      ...outAttrs(entry),
    },
    content: [
      { type: "entryHeading", content: contentFromRuns(entry.runs, entry.text) },
      ...(entry.bullets ?? []).map(bulletToJSON),
    ],
  };
}

function entryFromJSON(json: JSONContent): DocumentEntry {
  const [heading, ...bullets] = json.content ?? [];
  const entry: DocumentEntry = {
    id: json.attrs?.id as string,
    text: textFromContent(heading?.content),
    included: (json.attrs?.included as boolean) ?? true,
    page_break_before: (json.attrs?.page_break_before as boolean | null | undefined) ?? undefined,
    ...inAttrs(json.attrs),
    runs: runsFromContent(heading?.content),
  };
  // Omitted (not `[]`) when there are none — matches every non-Experience
  // builder in structuredDocument.ts, which never sets this key at all.
  if (bullets.length > 0) {
    entry.bullets = bullets.map(bulletFromJSON);
  }
  return entry;
}

function sectionToJSON(section: DocumentSection): JSONContent {
  return {
    type: "section",
    attrs: {
      key: section.key,
      title: section.title,
      included: section.included,
      // Phase 30 — see DocumentSection.page_break_before's own docstring
      // and entryToJSON's own comment on why `?? null`, not `?? false`.
      page_break_before: section.page_break_before ?? null,
    },
    content: section.entries.map(entryToJSON),
  };
}

function sectionFromJSON(json: JSONContent): DocumentSection {
  return {
    key: json.attrs?.key as string,
    title: json.attrs?.title as string,
    included: (json.attrs?.included as boolean) ?? true,
    page_break_before: (json.attrs?.page_break_before as boolean | null | undefined) ?? undefined,
    entries: (json.content ?? []).map(entryFromJSON),
  };
}

export function documentModelToTiptapJSON(model: DocumentModel): JSONContent {
  return { type: "doc", content: model.sections.map(sectionToJSON) };
}

export function tiptapJSONToDocumentModel(json: JSONContent): DocumentModel {
  return { sections: (json.content ?? []).map(sectionFromJSON) };
}
