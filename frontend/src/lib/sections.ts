import type { CVDraftSummary } from "@/api/models";

// Mirrors app/cv_locales.py exactly — order matters (both display order
// and the canonical key set). Keep these two in sync by hand; there's no
// schema for it since it's a constant, not a request/response shape
// openapi-typescript would pick up.
export const SECTION_TITLES_EN: Record<string, string> = {
  contacts: "Contacts",
  summary: "Summary",
  projects: "Key Projects",
  portfolio_links: "Portfolio",
  publications: "Publications & Talks",
  experience: "Experience",
  volunteer_experience: "Volunteer Experience",
  education: "Education",
  skills: "Skills",
  technologies: "Tools & Technologies",
  languages: "Languages",
  certifications: "Certifications",
  awards: "Awards & Honors",
};

// First target language (Version 4, Phase 4.2/4.3) — see
// app/cv_locales.py:SECTION_TITLES_RU's own comment on the labeling
// convention (native-Russian-CV style, not literal word-for-word).
export const SECTION_TITLES_RU: Record<string, string> = {
  contacts: "Контакты",
  summary: "О себе",
  projects: "Ключевые проекты",
  portfolio_links: "Портфолио",
  publications: "Публикации и выступления",
  experience: "Опыт работы",
  volunteer_experience: "Волонтёрский опыт",
  education: "Образование",
  skills: "Навыки",
  technologies: "Инструменты и технологии",
  languages: "Языки",
  certifications: "Сертификаты",
  awards: "Награды",
};

const SECTION_TITLES_BY_LOCALE: Record<string, Record<string, string>> = {
  en: SECTION_TITLES_EN,
  ru: SECTION_TITLES_RU,
};

// Falls back to English for any language this table doesn't recognize —
// mirrors app/cv_locales.py:section_titles_for's own reasoning: a
// candidate's `language` is a plain, open string (LLM-detected or
// user-typed), not limited to what this table happens to support labels
// for yet.
export function sectionTitlesFor(language: string): Record<string, string> {
  return SECTION_TITLES_BY_LOCALE[language] ?? SECTION_TITLES_EN;
}

// Human-readable language names for UI display (ProfileHeader.tsx,
// ExportScreen.tsx, the create-candidate language picker) — a frontend-
// only concern, no backend equivalent (the backend only ever stores/reads
// the raw ISO code). Falls back to the raw code itself for anything not
// listed, so an unexpected code (a language detected but not yet in this
// UI-label table) still displays as *something* rather than blank/undefined.
const LANGUAGE_LABELS: Record<string, string> = {
  en: "English",
  ru: "Russian",
};

export function languageLabel(language: string): string {
  return LANGUAGE_LABELS[language] ?? language;
}

// Shared by ExportScreen.tsx's "Your drafts" list and
// CandidateWorkflowLayout.tsx's breadcrumb (the trailing crumb when a
// draft is open) — one label format for a draft everywhere it's named in
// the UI, not two definitions drifting apart.
export function draftLabel(draft: CVDraftSummary): string {
  const title = draft.vacancy_title ?? "Untitled vacancy";
  return draft.vacancy_company ? `${title} — ${draft.vacancy_company}` : title;
}

// Version 4, Phase 4.6 (3.2.2) — the empty-profile creation form's language
// dropdown offers exactly the languages this table (and app/cv_locales.py)
// actually has header labels for; an LLM-detected code from ingestion can
// still be anything (languageLabel above falls back to the raw code for
// those), but a human explicitly picking a language for a brand-new empty
// profile should only be offered ones the app can actually localize.
export const SUPPORTED_LANGUAGES = Object.keys(LANGUAGE_LABELS);

// Backward-compat aliases — kept because entityConfigs.ts previously
// imported these directly; new code should prefer sectionTitlesFor() /
// SECTION_TITLES_EN explicitly instead of the bare, English-only name.
export const SECTION_TITLES = SECTION_TITLES_EN;
export const SECTION_KEYS = Object.keys(SECTION_TITLES_EN);
