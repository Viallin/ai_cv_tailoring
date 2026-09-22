// Thin named aliases over the openapi-typescript-generated schema
// (./types.ts, regenerated via `npm run gen:types` — see README) so the
// rest of the app imports clean names instead of reaching into
// components["schemas"][...] everywhere.

import type { components } from "./types";

export type Candidate = components["schemas"]["Candidate"];
export type AssembledCV = components["schemas"]["AssembledCV"];
export type MatchResult = components["schemas"]["MatchResult"];
export type Gap = components["schemas"]["Gap"];
// A JD keyword the candidate's Evidence supports but that isn't named
// explicitly in their Skills/Technologies lists — see
// domain.models.SkillToSurface's docstring for why this is distinct from
// both `Gap` and `MatchResult.missing_keywords`.
export type SkillToSurface = components["schemas"]["SkillToSurface"];
export type Requirement = components["schemas"]["Requirement"];
export type Vacancy = components["schemas"]["Vacancy"];
export type CandidateProfileSummary = components["schemas"]["CandidateProfileSummary"];
export type JobStatus = components["schemas"]["JobStatus"];
export type JobErrorBody = components["schemas"]["JobErrorBody"];
export type IngestJobResult = components["schemas"]["IngestJobResult"];
export type GenerateJobResult = components["schemas"]["GenerateJobResult"];

// Phase 18 — Gap.status (above) is a client-applied flag, never set by the
// Matching stage itself (see domain/models.py's Gap docstring); the
// dismiss-across-a-recheck logic lives in lib/dismissedGaps.ts, client-side
// only. RecheckJobResult is what a "recheck" job (api/routes/jobs.py)
// returns — just a fresh MatchResult, no assembled_cv/provenance.
export type RecheckJobResult = components["schemas"]["RecheckJobResult"];

// The on-demand "Re-evaluate Skill Dependencies" action's job result —
// just the counts of Skills/Technologies updated, not the full candidate
// (the frontend refetches the candidate on success instead).
export type RelinkSkillEvidenceJobResult = components["schemas"]["RelinkSkillEvidenceJobResult"];

// Phase 15b-i — the 11 "simple" entity types plus Evidence, for the new
// profile view.
export type Education = components["schemas"]["Education"];
export type Skill = components["schemas"]["Skill"];
export type Technology = components["schemas"]["Technology"];
export type Language = components["schemas"]["Language"];
export type Certification = components["schemas"]["Certification"];
export type Award = components["schemas"]["Award"];
export type ContactItem = components["schemas"]["ContactItem"];
export type Project = components["schemas"]["Project"];
export type Publication = components["schemas"]["Publication"];
export type PortfolioLink = components["schemas"]["PortfolioLink"];
export type VolunteerExperience = components["schemas"]["VolunteerExperience"];
export type Evidence = components["schemas"]["Evidence"];

// Phase 15b-ii — Experience has nested Projects and role/project-level
// bullet lists, which is why it isn't one of the 11 "simple" entities above.
export type Experience = components["schemas"]["Experience"];
export type ExperienceProject = components["schemas"]["ExperienceProject"];

// Phase 16a — AssembledCV's own Experience/bullet shapes (the LLM-tailored
// output), distinct from the profile-editing Experience/ExperienceProject
// above.
export type AssembledExperienceEntry = components["schemas"]["AssembledExperienceEntry"];
export type TailoredBullet = components["schemas"]["TailoredBullet"];

// Phase 17a — TailoredBullet.evidence_id (above) links a bullet back to a
// BulletProvenance; BulletProvenanceReport is what GenerateJobResult now
// carries alongside assembled_cv/match_result.
export type BulletProvenance = components["schemas"]["BulletProvenance"];
export type BulletProvenanceReport = components["schemas"]["BulletProvenanceReport"];
// The tailored summary's own before/after — BulletProvenanceReport.summary,
// same before/after/revert affordance as a bullet's BulletProvenance, but
// for the one CV field with no evidence_id/action of its own to key off.
export type SummaryProvenance = components["schemas"]["SummaryProvenance"];
// Per-stage + total wall-clock duration of one generation run
// (GenerateJobResult.timing, persisted onto CVDraft.timing alongside it) —
// asked for directly, so "how long does this actually take" has a real
// answer from stored data instead of a guess from created_at/updated_at
// (which also counts however long the person then spent editing).
export type GenerationTiming = components["schemas"]["GenerationTiming"];

// Phase 16b — the backend's own mirror of structuredDocument.ts's
// DocumentModel types (see domain/models.py's PrintDocument* docstrings),
// used for the /export request payload — the backend re-serializes what
// the frontend sent rather than echoing it byte-for-byte.
export type PrintDocument = components["schemas"]["PrintDocument"];
export type PrintDocumentSection = components["schemas"]["PrintDocumentSection"];
export type PrintDocumentEntry = components["schemas"]["PrintDocumentEntry"];
export type PrintDocumentBlock = components["schemas"]["PrintDocumentBlock"];
// Phase 25 — one inline-styled span within a PrintDocumentBlock.runs.
export type TextRun = components["schemas"]["TextRun"];

// No standalone `EmploymentType` schema exists in the generated types —
// FastAPI/Pydantic inline the literal union everywhere it's used rather
// than naming it, so there's nothing to alias from `components["schemas"]`.
// Hand-declared here instead, matching domain.models.EmploymentType
// exactly; low drift risk since this is a fixed, rarely-changing set.
// Phase 19 — write-back's preview/apply request/response shapes
// (api/routes/writeback.py). `key` is a stable index into whichever
// ordered proposal list /preview just returned, re-sent to /apply to
// select which ones to write back.
export type WritebackProposalOut = components["schemas"]["WritebackProposalOut"];
export type WritebackApplyResult = components["schemas"]["WritebackApplyResult"];

// Phase 20 — a persisted generate-and-refine session
// (api/routes/cv_drafts.py). CVDraftSummary is the lightweight listing
// shape (GET .../drafts); CVDraft is the full record (GET .../drafts/{id}).
export type CVDraft = components["schemas"]["CVDraft"];
export type CVDraftSummary = components["schemas"]["CVDraftSummary"];

// On-screen page-break-prediction fix (follow-up to Version 4, Phase
// 4.9) — POST /export/page-breaks's response shape, see
// app/cv_pdf.py::compute_page_breaks's own docstring for the full story.
export type PageBreakPosition = components["schemas"]["PageBreakPositionOut"];

export type EmploymentType =
  | "Full-time"
  | "Part-time"
  | "Contract"
  | "Freelance"
  | "Internship"
  | "Temporary";
