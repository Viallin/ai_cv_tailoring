// Phase 16a — templates are CSS custom-property sets applied to A4Page's
// `data-template` attribute, not alternate component trees. Scope
// confirmed with the user: typography/spacing only (fonts, bullet style,
// section spacing) — the document stays single-column, so this can't
// regress ATS-readability the way a structural/multi-column template
// could. Exact values are a visual call, not worth over-specifying here;
// eyeball and adjust once rendered.

export interface CvTemplate {
  id: string;
  label: string;
  cssVars: Record<string, string>;
  // Plain bullet character, mirrors app/cv_templates.py's DocxTemplate.
  // Used as a literal text prefix by the print renderers (PrintSectionBlock/
  // PrintExperienceSection) rather than a CSS ::before pseudo-element — a
  // literal character is what a naive text extractor (ATS parsers, PDF
  // copy-paste) actually sees, matching cv_pdf.py's own existing choice to
  // use a literal "-  " prefix rather than relying on layout-only markers.
  bulletChar: string;
}

const TEMPLATE_CSS_VAR_KEYS = ["--cv-heading-font", "--cv-body-font", "--cv-section-spacing", "--cv-heading-weight"] as const;

export const CV_TEMPLATES: CvTemplate[] = [
  {
    id: "classic",
    label: "Classic",
    cssVars: {
      "--cv-heading-font": "Georgia, 'Times New Roman', serif",
      "--cv-body-font": "Georgia, 'Times New Roman', serif",
      "--cv-section-spacing": "1.5rem",
      "--cv-heading-weight": "700",
    },
    bulletChar: "–", // en dash — matches app/cv_templates.py's "classic" entry
  },
  {
    id: "modern",
    label: "Modern",
    cssVars: {
      "--cv-heading-font": "'Geist Variable', system-ui, sans-serif",
      "--cv-body-font": "'Geist Variable', system-ui, sans-serif",
      "--cv-section-spacing": "1rem",
      "--cv-heading-weight": "600",
    },
    bulletChar: "•", // bullet — matches app/cv_templates.py's "modern" entry
  },
];

export function isValidTemplate(template: CvTemplate): boolean {
  return TEMPLATE_CSS_VAR_KEYS.every((key) => key in template.cssVars);
}

export const NO_TEMPLATE_ID = "none";

// Deliberately not one of CV_TEMPLATES (and so exempt from
// cvTemplates.test.ts's "every template has every required CSS var key"
// check) — its whole point is supplying *no* CSS vars, so .cv-a4-page and
// its children fall through to their own `var(--cv-body-font, inherit)`
// -style defaults in index.css. That's the plain, ATS-safe look: no
// template styling applied at all, not "styling that happens to look
// plain." bulletChar "-" matches app/cv_pdf.py's own literal "-  " prefix
// for the untemplated PDF/DOCX export.
export const PLAIN_TEMPLATE: CvTemplate = {
  id: NO_TEMPLATE_ID,
  label: "None (ATS-safe)",
  cssVars: {},
  bulletChar: "-",
};

// The one Template picker's full option list (DraftScreen's Export card) —
// same set drives both the on-screen preview (DocumentEditor) and the
// exported file (ExportButton), so there's exactly one place a person
// chooses a template instead of two independent, unsynced ones.
export const TEMPLATE_CHOICES: CvTemplate[] = [PLAIN_TEMPLATE, ...CV_TEMPLATES];

export const DEFAULT_TEMPLATE_ID = CV_TEMPLATES[0].id;
