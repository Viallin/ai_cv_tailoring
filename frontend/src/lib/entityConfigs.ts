// Config table for the 11 "simple" entity types EntitySection.tsx renders
// generically — the React equivalent of ui/graph_explorer.py's
// _ENTITY_SPECS/_TITLES/_SUMMARIZERS/_singular(), ported field-for-field
// (see that file for the source of truth). Experience isn't here — its
// nested Projects/Evidence-backed bullets are Phase 15b-ii.
//
// `sectionKey` reuses the same section names the CV export already uses
// (lib/sections.ts's sectionTitlesFor(), itself mirroring
// app/cv_locales.py's section-title tables) rather than inventing new
// ones, so a section is called the same thing whether you're editing the
// profile or looking at the generated CV. Version 4, Phase 4.3: this
// used to be a pre-resolved `title: string` (always English) — now just
// the lookup key, resolved by the one consumer (ProfileView.tsx, which
// has the candidate's own `language` in scope) via
// `sectionTitlesFor(candidate.language)[config.sectionKey]`, since this
// table is built once at module load, before any candidate is known.
// `singularLabel` is only for the "+ Add {singularLabel}" button text
// (Graph Explorer's `_TITLES`, e.g. "Technology" not "Technologies") —
// deliberately still English-only; Version 4's scope is localizing CV
// output, not the editing UI's own chrome.

import type { Candidate } from "@/api/models";

export interface FieldSpec {
  name: string;
  label: string;
  multiline?: boolean;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- summarize
// must accept whichever entity shape its own EntityConfig is for; a shared
// union of all 11 shapes would be less readable than Python's equivalent
// untyped `Callable[[Any], str]` for no real safety benefit here.
export interface EntityConfig<T = any> {
  pathSegment: string;
  listField: keyof Candidate;
  sectionKey: string;
  singularLabel: string;
  fields: FieldSpec[];
  summarize: (item: T) => string;
  // Phase 15b-ii: pure data accessor (not a renderer — mirrors summarize's
  // own "config returns data, EntitySection owns JSX" split) returning an
  // item's linked Evidence ids. Only skills/technologies set this; every
  // other entity leaves it undefined and EntitySection renders nothing
  // extra for them.
  evidenceIds?: (item: T) => string[];
  // Phase 21: only skills/technologies set this. Enables the
  // Experience-style "category header" row type in EntitySection —
  // `category` becomes derived from the nearest preceding header row
  // instead of a directly editable field, so it's deliberately absent
  // from `fields` above for these two configs.
  categoryHeaders?: true;
}

function joinNonEmpty(parts: (string | null | undefined)[], sep: string): string {
  return parts.filter((part): part is string => Boolean(part)).join(sep);
}

export const ENTITY_CONFIGS: EntityConfig[] = [
  {
    pathSegment: "education",
    listField: "education",
    sectionKey: "education",
    singularLabel: "Education",
    fields: [
      { name: "institution", label: "Institution" },
      { name: "degree", label: "Degree" },
      { name: "field", label: "Field" },
      { name: "period", label: "Period" },
    ],
    summarize: (item) => {
      const details = joinNonEmpty([item.degree, item.field], ", ");
      const period = item.period ? ` (${item.period})` : "";
      return `${item.institution}${details ? ` — ${details}` : ""}${period}`;
    },
  },
  {
    pathSegment: "skills",
    listField: "skills",
    sectionKey: "skills",
    singularLabel: "Skill",
    fields: [
      { name: "name", label: "Name" },
      { name: "proficiency", label: "Proficiency (e.g. Beginner/Intermediate/Advanced/Expert)" },
    ],
    summarize: (item) => {
      const details = joinNonEmpty([item.category, item.proficiency], ", ");
      return `${item.name}${details ? ` (${details})` : ""}`;
    },
    evidenceIds: (item) => item.evidence_ids ?? [],
    categoryHeaders: true,
  },
  {
    pathSegment: "technologies",
    listField: "technologies",
    sectionKey: "technologies",
    singularLabel: "Technology",
    fields: [
      { name: "name", label: "Name" },
      { name: "proficiency", label: "Proficiency (e.g. Beginner/Intermediate/Advanced/Expert)" },
    ],
    summarize: (item) => {
      const details = joinNonEmpty([item.category, item.proficiency], ", ");
      return `${item.name}${details ? ` (${details})` : ""}`;
    },
    evidenceIds: (item) => item.evidence_ids ?? [],
    categoryHeaders: true,
  },
  {
    pathSegment: "languages",
    listField: "languages",
    sectionKey: "languages",
    singularLabel: "Language",
    fields: [
      { name: "name", label: "Name" },
      { name: "proficiency", label: "Proficiency" },
    ],
    summarize: (item) => `${item.name}${item.proficiency ? ` (${item.proficiency})` : ""}`,
  },
  {
    pathSegment: "certifications",
    listField: "certifications",
    sectionKey: "certifications",
    singularLabel: "Certification",
    fields: [
      { name: "name", label: "Name" },
      { name: "issuer", label: "Issuer" },
      { name: "date", label: "Date" },
    ],
    summarize: (item) => {
      const details = joinNonEmpty([item.issuer, item.date], ", ");
      return `${item.name}${details ? ` — ${details}` : ""}`;
    },
  },
  {
    pathSegment: "awards",
    listField: "awards",
    sectionKey: "awards",
    singularLabel: "Award",
    fields: [
      { name: "name", label: "Name" },
      { name: "issuer", label: "Issuer" },
      { name: "date", label: "Date" },
    ],
    summarize: (item) => {
      const details = joinNonEmpty([item.issuer, item.date], ", ");
      return `${item.name}${details ? ` — ${details}` : ""}`;
    },
  },
  {
    pathSegment: "contacts",
    listField: "contacts",
    sectionKey: "contacts",
    singularLabel: "Contact",
    fields: [
      { name: "label", label: "Label" },
      { name: "value", label: "Value" },
    ],
    summarize: (item) => `${item.label}: ${item.value}`,
  },
  {
    pathSegment: "projects",
    listField: "projects",
    sectionKey: "projects",
    singularLabel: "Key Project",
    fields: [
      { name: "name", label: "Name" },
      { name: "description", label: "Description", multiline: true },
      { name: "url", label: "URL" },
    ],
    summarize: (item) => `${item.name}${item.description ? ` — ${item.description}` : ""}`,
  },
  {
    pathSegment: "publications",
    listField: "publications",
    sectionKey: "publications",
    singularLabel: "Publication",
    fields: [
      { name: "title", label: "Title" },
      { name: "venue", label: "Venue" },
      { name: "date", label: "Date" },
      { name: "url", label: "URL" },
    ],
    summarize: (item) => {
      const details = joinNonEmpty([item.venue, item.date], ", ");
      return `${item.title}${details ? ` — ${details}` : ""}`;
    },
  },
  {
    pathSegment: "portfolio-links",
    listField: "portfolio_links",
    sectionKey: "portfolio_links",
    singularLabel: "Portfolio Link",
    fields: [
      { name: "url", label: "URL" },
      { name: "description", label: "Description" },
    ],
    summarize: (item) => (item.description ? `${item.description} — ${item.url}` : item.url),
  },
  {
    pathSegment: "volunteer-experience",
    listField: "volunteer_experience",
    sectionKey: "volunteer_experience",
    singularLabel: "Volunteer Experience",
    fields: [
      { name: "organization", label: "Organization" },
      { name: "role", label: "Role" },
      { name: "period", label: "Period" },
      { name: "description", label: "Description", multiline: true },
    ],
    summarize: (item) => {
      const header = `${item.role} — ${item.organization}`;
      return item.period ? `${header} (${item.period})` : header;
    },
  },
];
