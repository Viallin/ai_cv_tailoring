import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { ApiError } from "@/api/client";
import { useCvDraft } from "@/api/cvDrafts";
import { useEntityMutations } from "@/api/entities";
import type { ExportFormat } from "@/api/export";
import { useGenerateJob, useRecheckGapsJob } from "@/api/jobs";
import type { BulletProvenanceReport, CVDraft, Evidence, MatchResult } from "@/api/models";
import { AdvisoryChips } from "@/components/AdvisoryChips";
import { DocumentEditor, type DocumentEditorHandle } from "@/components/DocumentEditor";
import { ExcludedContentPanel } from "@/components/ExcludedContentPanel";
import { ExportButton } from "@/components/ExportButton";
import { GapsPanel } from "@/components/GapsPanel";
import { JobDescriptionSummary } from "@/components/JobDescriptionSummary";
import { UnusedEvidencePanel } from "@/components/UnusedEvidencePanel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { WritebackDialog } from "@/components/WritebackDialog";
import { buildAdvisoryChips } from "@/lib/advisories";
import { DEFAULT_TEMPLATE_ID } from "@/lib/cvTemplates";
import { applyDismissed } from "@/lib/dismissedGaps";
import {
  collectEditedBulletText,
  collectExcludedEvidenceIds,
  collectManualBulletText,
  collectUsedEvidenceIds,
} from "@/lib/documentEvidence";
import type { ExcludedContentItem } from "@/lib/excludedContent";
import {
  buildDocumentFromAssembledCv,
  collapseSkillsAndTechnologiesIfNeeded,
  collectDocumentSkillNames,
  type DocumentModel,
} from "@/lib/structuredDocument";
import { useDebouncedEffect } from "@/lib/useDebouncedEffect";

// Phase 20 — screen 4: "preview/edit/export." Loads a persisted CVDraft by
// id (ExportScreen always navigates here right after creating one) and
// autosaves edits back to that same row ~1.5s after the last change —
// see CandidateService.update_cv_draft's docstring for why this is a
// plain partial PUT, not a new mechanism. Vacancy title and Role title
// (assembled_cv.headline) are two further editable fields that aren't
// part of `document` — each on the same debounce, but its own effect (a
// PUT that only touches `vacancy` or `assembled_cv` respectively, never
// `document`), since all three can legitimately change independently.
//
// `match_result`/`provenance` are read from the persisted `draft` itself
// (Phase 20b) — a reopen (refresh, "Your drafts," a direct link) shows
// Gaps and the AI-edit Sparkles highlighting exactly like the original
// landing did, not just the document. `location.state` still carries the
// same two values through the *initial* navigation from ExportScreen —
// kept only so this screen has them the instant it mounts, before its own
// GET for `draft` resolves, not as the source of truth; `draft` (once
// loaded) always wins.
interface DraftLocationState {
  provenance?: BulletProvenanceReport;
  matchResult?: MatchResult;
}

const AUTOSAVE_DEBOUNCE_MS = 1500;

export function DraftScreen() {
  const { candidateId, draftId } = useParams<{ candidateId: string; draftId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const initialState = (location.state ?? {}) as DraftLocationState;

  const { create: createDraft, update: updateDraft, remove: removeDraft } = useEntityMutations<CVDraft>(
    candidateId ?? "",
    "drafts",
  );
  // Disabled once the delete mutation starts (not just once it settles) —
  // see useCvDraft's own comment for the race this avoids.
  const { data: draft, isLoading } = useCvDraft(candidateId ?? null, draftId ?? null, !removeDraft.isPending);
  const recheckJob = useRecheckGapsJob();
  // Regenerate / Regenerate as New (below) share this one job — a person
  // can only sensibly have one regeneration in flight at a time, same
  // reasoning as ExportScreen.tsx's single `generateJob`. Which mode is
  // active also drives the two buttons' own busy label/disabled state, so
  // it stays set for the *whole* click-to-settled span (the LLM call via
  // `generateJob`, then the save mutate below) rather than being cleared
  // the moment the LLM call itself finishes.
  const generateJob = useGenerateJob();
  const [regenerateMode, setRegenerateMode] = useState<"replace" | "new" | null>(null);
  // Bumped only on a successful in-place Regenerate, never on a routine
  // autosave — forces DocumentEditor to remount (via its `key` prop
  // below) so it re-seeds from the freshly-regenerated `initialDocument`
  // instead of keeping whatever it already seeded once at mount (see that
  // component's own "consulted only once" comment on its `initialDocument`
  // prop — without this, a same-draft regenerate would save the new
  // content but leave the old content on screen until a manual reload).
  const [regenVersion, setRegenVersion] = useState(0);

  const provenance = draft?.provenance ?? initialState.provenance ?? null;
  const [cvDocument, setCvDocument] = useState<DocumentModel | null>(null);
  const [matchResult, setMatchResult] = useState<MatchResult | null>(initialState.matchResult ?? null);
  const [dismissedRequirements, setDismissedRequirements] = useState<Set<string>>(new Set());
  const [vacancyTitle, setVacancyTitle] = useState("");
  // Same autosave shape as vacancyTitle above, but for
  // assembled_cv.headline — the role title shown on the CV itself
  // ("Senior/Lead Game Designer, Product Manager" etc.), not the
  // vacancy's own title. Unlike vacancyTitle, there's no dedicated form
  // field for this one: CvPrintHeader.tsx renders it as an inline input
  // right where the headline appears in the on-screen preview (see that
  // component's own docstring for why — a first version with a separate
  // field was reported as unintuitive), and calls setHeadline directly
  // via DocumentEditor's onHeadlineChange prop. Used to be genuinely
  // uneditable (candidate.headline, copied in verbatim by
  // cv_assembler.py for every draft alike) — reported directly: a person
  // tailoring for one vacancy wants a trimmed-down title ("Senior Game
  // Designer" only, no "Product Manager") without changing the global
  // profile headline every *other* draft still relies on. Since
  // assembled_cv is already a per-draft snapshot (not shared with
  // Candidate.headline after the initial generate), patching it here
  // only ever touches this one draft.
  const [headline, setHeadline] = useState("");
  // The one Template choice, driving both DocumentEditor's on-screen
  // preview and ExportButton's export — see cvTemplates.ts's
  // TEMPLATE_CHOICES docstring for why this replaced two independent,
  // unsynced pickers.
  const [templateId, setTemplateId] = useState(DEFAULT_TEMPLATE_ID);
  // Post-29 fix — same "one lifted choice drives both the preview and the
  // export" reasoning as templateId above, now extended to the format
  // picker too: PageBreakGuide's dashed lines are a real approximation of
  // PDF pagination specifically (calibrated against `.cv-a4-page`'s own
  // `@media print` CSS) and mean nothing for a `.docx` (paginated later,
  // by whatever opens it — Word/LibreOffice/Google Docs — using a
  // completely different, independent layout engine; see that file's own
  // docstring) or a plain `.md` (never paginated at all). Previously
  // `format` was ExportButton's own local state, invisible to
  // DocumentEditor — this makes it the second field both components read
  // off the same source, so the on-screen guide can react to *which*
  // export format is actually selected instead of always assuming PDF.
  const [format, setFormat] = useState<ExportFormat>("pdf");
  const documentEditorRef = useRef<DocumentEditorHandle>(null);
  const hasSeededVacancyTitle = useRef(false);
  const hasSeededHeadline = useRef(false);

  useEffect(() => {
    // Only seeds when nothing has set matchResult yet (a reopen with no
    // location.state, and no Re-check run in this session) — never
    // overwrites a fresher Re-check result once the person has run one.
    if (draft?.match_result && matchResult == null) {
      setMatchResult(applyDismissed(draft.match_result, dismissedRequirements));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires once per loaded draft; dismissedRequirements/matchResult read at that moment, not triggers
  }, [draft]);

  useEffect(() => {
    // Ref-guarded "consult once per mount" — the same pattern
    // DocumentEditor.tsx's initialDocument seeding uses — so a later
    // `draft` refetch (e.g. the title-autosave PUT resolving) never
    // clobbers whatever the person is mid-typing.
    if (draft != null && !hasSeededVacancyTitle.current) {
      hasSeededVacancyTitle.current = true;
      setVacancyTitle(draft.vacancy.title ?? "");
    }
  }, [draft]);

  useEffect(() => {
    // Same ref-guarded "consult once per mount" as the vacancy-title seed
    // above.
    if (draft != null && !hasSeededHeadline.current) {
      hasSeededHeadline.current = true;
      setHeadline(draft.assembled_cv.headline ?? "");
    }
  }, [draft]);

  useDebouncedEffect(
    () => {
      if (draftId == null || cvDocument == null || draft == null) {
        return;
      }
      // Diff against the persisted document, not just "did cvDocument
      // change" — DocumentEditor.tsx's initial seed (handing back
      // exactly what `initialDocument` gave it) is content-identical to
      // what's already persisted, so this naturally no-ops for it.
      // Without this, useDebouncedEffect's own "skip only the absolute
      // first run" logic still treats cvDocument's null -> populated
      // transition as a real *second* run, scheduling a pointless
      // PUT-back of the unchanged document ~1.5s after every page load.
      // Reported directly, from a real, reproducible bug that phantom
      // PUT caused: its own refetch can land at the same moment as an
      // unrelated DELETE to the same draft (Delete Draft button below),
      // silently aborting the DELETE (net::ERR_ABORTED) — this fixes
      // that race at the root instead of working around it. (A ref-based
      // "was this the first callback run" guard was tried and rejected
      // here — it would wrongly swallow a genuine edit made within the
      // same debounce window as the seed; comparing content avoids that
      // entirely.)
      if (JSON.stringify(cvDocument) === JSON.stringify(draft.document)) {
        return;
      }
      updateDraft.mutate({ itemId: draftId, body: { document: cvDocument } });
    },
    [cvDocument],
    AUTOSAVE_DEBOUNCE_MS,
  );

  useDebouncedEffect(
    () => {
      // Skip until seeded (avoids an immediate, pointless PUT-back of the
      // same value on load) and skip when nothing actually changed (the
      // seed effect above, and this same PUT's own refetch landing,
      // would otherwise both re-trigger this).
      if (draftId == null || draft == null || !hasSeededVacancyTitle.current) {
        return;
      }
      const nextTitle = vacancyTitle.trim() === "" ? null : vacancyTitle.trim();
      if (nextTitle === (draft.vacancy.title ?? null)) {
        return;
      }
      updateDraft.mutate({ itemId: draftId, body: { vacancy: { ...draft.vacancy, title: nextTitle } } });
    },
    [vacancyTitle],
    AUTOSAVE_DEBOUNCE_MS,
  );

  useDebouncedEffect(
    () => {
      // Same skip conditions as the vacancy-title autosave above.
      if (draftId == null || draft == null || !hasSeededHeadline.current) {
        return;
      }
      const nextHeadline = headline.trim() === "" ? null : headline.trim();
      if (nextHeadline === (draft.assembled_cv.headline ?? null)) {
        return;
      }
      updateDraft.mutate({
        itemId: draftId,
        body: { assembled_cv: { ...draft.assembled_cv, headline: nextHeadline } },
      });
    },
    [headline],
    AUTOSAVE_DEBOUNCE_MS,
  );

  useEffect(() => {
    if (recheckJob.result) {
      setMatchResult(applyDismissed(recheckJob.result.match_result, dismissedRequirements));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- dismissedRequirements is read at the moment the result lands, not a trigger for re-running this
  }, [recheckJob.result]);

  // Regenerate / Regenerate as New — once the shared generateJob (the LLM
  // chain) finishes, save its result either back onto this same draft
  // (mirroring update_cv_draft's full-content PUT, same shape ExportScreen
  // uses for a first-time createDraft) or as a brand new one, depending on
  // which button was clicked. Mirrors ExportScreen.tsx's own
  // generateJob.result effect, plus the save step it doesn't need (that
  // screen only ever creates).
  useEffect(() => {
    if (generateJob.result == null || candidateId == null || draftId == null || regenerateMode == null) {
      return;
    }
    const {
      vacancy,
      assembled_cv: assembledCv,
      match_result: freshMatchResult,
      provenance: freshProvenance,
      timing: freshTiming,
    } = generateJob.result;
    const freshDocument = buildDocumentFromAssembledCv(assembledCv);

    if (regenerateMode === "new") {
      createDraft.mutate(
        {
          vacancy,
          assembled_cv: assembledCv,
          document: freshDocument,
          match_result: freshMatchResult,
          provenance: freshProvenance,
          timing: freshTiming,
        },
        {
          onSuccess: (newDraft) => {
            setRegenerateMode(null);
            navigate(`/candidates/${candidateId}/drafts/${newDraft.id}`, {
              state: { matchResult: freshMatchResult, provenance: freshProvenance },
            });
          },
          onError: () => {
            setRegenerateMode(null);
            toast.error("Couldn't save the new draft", {
              description: "Regeneration finished, but saving it as a new draft failed — try again.",
            });
          },
        },
      );
    } else {
      updateDraft.mutate(
        {
          itemId: draftId,
          body: {
            vacancy,
            assembled_cv: assembledCv,
            document: freshDocument,
            match_result: freshMatchResult,
            provenance: freshProvenance,
            timing: freshTiming,
          },
        },
        {
          onSuccess: () => {
            setRegenerateMode(null);
            // Same "replace local state, don't wait on the refetch" reasoning
            // as everywhere else in this file — the freshly-saved content is
            // already in hand, no need to wait on invalidate+refetch to show
            // it. dismissedRequirements resets too: those were dismissals
            // against the *old* Gaps, which no longer exist.
            setMatchResult(freshMatchResult);
            setDismissedRequirements(new Set());
            setVacancyTitle(vacancy.title ?? "");
            setHeadline(assembledCv.headline ?? "");
            setRegenVersion((v) => v + 1);
            toast.success("Draft regenerated.");
          },
          onError: () => {
            setRegenerateMode(null);
            toast.error("Couldn't save the regenerated draft", {
              description: "Regeneration finished, but saving the result to this draft failed — try again.",
            });
          },
        },
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fires once per fresh generate result; mutate/navigate are stable, regenerateMode/candidateId/draftId are read at the moment this fires
  }, [generateJob.result]);

  useEffect(() => {
    if (generateJob.error) {
      toast.error(generateJob.error.category, { description: generateJob.error.message });
      setRegenerateMode(null);
    }
  }, [generateJob.error]);

  // Post-31 — a one-time migration for a draft saved before Skills/
  // Technologies collapsed into compact paragraphs (see
  // structuredDocument.ts's own docstring on collapseSkillsAndTechnologiesIfNeeded):
  // applied to the fetched document *before* DocumentEditor ever sees it
  // as `initialDocument`, so an old draft seeds directly into the new
  // compact shape rather than the old one-row-per-skill shape. No
  // separate save-trigger needed — DocumentEditor's own `model` state
  // (and the `onModelChange` effect that mirrors it into `cvDocument`
  // below) updates from this same initial seed regardless of whether it
  // came from `applyModel`'s silent `emitUpdate: false` Tiptap call, so
  // the existing autosave effect above (diffing `cvDocument` against
  // `draft.document`) already persists the migrated shape back on its
  // own the moment it differs from what was loaded — exactly the same
  // path a real edit already goes through. A no-op (returns the exact
  // same object) for a document that's already in the compact shape, or
  // has no Skills/Technologies content at all, so this doesn't perturb
  // an already-migrated draft on every subsequent load.
  const initialDocument = useMemo(
    () => (draft ? collapseSkillsAndTechnologiesIfNeeded(draft.document as unknown as DocumentModel) : null),
    [draft],
  );

  // `draft.assembled_cv` with the live (possibly not-yet-autosaved)
  // `headline` edit layered on top — same reasoning as `cvDocument` being
  // the thing that's actually passed around instead of `draft.document`
  // directly: Export/Writeback should reflect what's on screen right now,
  // not lag ~1.5s behind until the debounced PUT above resolves and
  // refetches. Safe to hand a fresh object to DocumentEditor's
  // `assembledCv` prop on every keystroke — its own rebuild-from-
  // assembledCv effect only ever fires once a real `initialDocument` is
  // present (see that file's own comment), so this never blows away
  // in-progress document edits.
  const liveAssembledCv = useMemo(
    () => (draft ? { ...draft.assembled_cv, headline: headline.trim() === "" ? null : headline } : null),
    [draft, headline],
  );

  if (isLoading || draft == null) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const handleRecheckClick = () => {
    if (cvDocument == null || candidateId == null) {
      return;
    }
    recheckJob.recheck(candidateId, draft.vacancy.requirements ?? [], collectExcludedEvidenceIds(cvDocument), {
      editedBulletText: collectEditedBulletText(cvDocument),
      manualBulletText: collectManualBulletText(cvDocument),
      documentSkills: collectDocumentSkillNames(cvDocument, "skills"),
      documentTechnologies: collectDocumentSkillNames(cvDocument, "technologies"),
    });
  };

  const handleDismissGap = (requirementText: string) => {
    const next = new Set(dismissedRequirements).add(requirementText);
    setDismissedRequirements(next);
    setMatchResult((current) => (current ? applyDismissed(current, next) : current));
  };

  const handleAddToRole = (evidence: Evidence, experienceId: string) => {
    documentEditorRef.current?.addBulletFromEvidence(experienceId, evidence.text, evidence.id);
  };

  const handleRestoreContent = (item: ExcludedContentItem) => {
    documentEditorRef.current?.restoreContent(item.sectionKey, item.entryId, item.bulletId);
  };

  const handleRegenerateClick = () => {
    if (candidateId == null || draftId == null) {
      return;
    }
    const rawText = draft.vacancy.raw_text.trim();
    if (!rawText) {
      return;
    }
    const label = vacancyTitle.trim() || "Untitled vacancy";
    if (
      !window.confirm(
        `Regenerate "${label}"? This reruns tailoring for the same job description against your ` +
          "current profile, and replaces the summary, bullets, and skills currently in this draft " +
          "with the fresh result. This can't be undone — use \"Regenerate as New\" instead if you " +
          "want to keep this draft as-is.",
      )
    ) {
      return;
    }
    setRegenerateMode("replace");
    generateJob.generate(candidateId, rawText, draft.vacancy);
  };

  const handleRegenerateAsNewClick = () => {
    if (candidateId == null) {
      return;
    }
    const rawText = draft.vacancy.raw_text.trim();
    if (!rawText) {
      return;
    }
    setRegenerateMode("new");
    generateJob.generate(candidateId, rawText, draft.vacancy);
  };

  const handleDeleteClick = () => {
    if (candidateId == null || draftId == null) {
      return;
    }
    const label = vacancyTitle.trim() || "Untitled vacancy";
    if (!window.confirm(`Delete the draft "${label}"? This can't be undone.`)) {
      return;
    }
    removeDraft.mutate(draftId, {
      // Post-4.10 nav redesign, round 3 — "Your drafts" now lives in
      // ProfileExportPanel.tsx, a rail on the profile itself, not a
      // separate /export screen.
      onSuccess: () => navigate(`/candidates/${candidateId}/profile`),
      onError: (error) => {
        const category = error instanceof ApiError ? error.category : "Error";
        const message = error instanceof ApiError ? error.message : "Something went wrong.";
        toast.error(category, { description: message });
      },
    });
  };

  // Recomputed on every render off the live document, so it updates as
  // the user edits — the heuristics themselves are cheap plain
  // arithmetic (lib/advisories.ts), no memoization needed. Drives
  // whether the "Worth a look" Card below even renders at all.
  const advisoryChips = cvDocument ? buildAdvisoryChips(cvDocument) : [];

  // An untailored draft ("Export without tailoring", ExportScreen.tsx)
  // has no job description to regenerate against — its Vacancy is the
  // empty UNTAILORED_VACANCY placeholder (raw_text: ""). Both buttons
  // below are disabled in that case rather than hidden, so their absence
  // doesn't read as "this feature doesn't exist here."
  const hasVacancyText = draft.vacancy.raw_text.trim().length > 0;
  const regenerateDisabled = !hasVacancyText || regenerateMode != null;

  return (
    <div className="space-y-4">
      {/* Top bar — vacancy title + regenerate actions + Delete Draft,
          spanning the full width above the CV/action-rail split below
          (neither belongs to just one side of that split). */}
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-64 flex-1 space-y-1">
          <label htmlFor="draft-vacancy-title" className="text-xs font-medium text-muted-foreground">
            Vacancy title
          </label>
          {/* CVDraftSummary.vacancy_title — the same field "Your drafts"
              (ExportScreen.tsx) already lists each draft by — surfaced here,
              editable, since a draft otherwise carries no visible label of
              its own while you're actually working on it. Autosaves on the
              same ~1.5s debounce as the document; a blank value (e.g. an
              untailored draft's null title) saves back as null, not "". */}
          <Input
            id="draft-vacancy-title"
            value={vacancyTitle}
            onChange={(event) => setVacancyTitle(event.target.value)}
            placeholder="Untitled vacancy"
            className="text-lg font-semibold"
          />
        </div>
        {/* Re-tailors against the same job description (Vacancy.raw_text,
            already on this draft — never re-typed) and this candidate's
            *current* profile, so any edits made since this draft was
            generated are reflected. "Regenerate as New" is the safe,
            unconfirmed one (creates a fresh draft, this one is untouched);
            plain "Regenerate" overwrites this draft's content in place,
            hence the confirm dialog and the same destructive styling as
            Delete Draft. */}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleRegenerateAsNewClick}
          disabled={regenerateDisabled}
          title={
            regenerateMode === "new" && generateJob.progress
              ? `Step ${generateJob.progress.stageNumber}/${generateJob.progress.stageCount}: ${generateJob.progress.stage}`
              : hasVacancyText
                ? undefined
                : "This draft has no job description to regenerate from."
          }
        >
          {regenerateMode === "new"
            ? generateJob.progress
              ? `Step ${generateJob.progress.stageNumber}/${generateJob.progress.stageCount}…`
              : "Regenerating…"
            : "Regenerate as New"}
        </Button>
        <Button
          type="button"
          variant="destructive"
          size="sm"
          onClick={handleRegenerateClick}
          disabled={regenerateDisabled}
          title={
            regenerateMode === "replace" && generateJob.progress
              ? `Step ${generateJob.progress.stageNumber}/${generateJob.progress.stageCount}: ${generateJob.progress.stage}`
              : hasVacancyText
                ? undefined
                : "This draft has no job description to regenerate from."
          }
        >
          {regenerateMode === "replace"
            ? generateJob.progress
              ? `Step ${generateJob.progress.stageNumber}/${generateJob.progress.stageCount}…`
              : "Regenerating…"
            : "Regenerate"}
        </Button>
        <Button
          type="button"
          variant="destructive"
          size="sm"
          onClick={handleDeleteClick}
          disabled={removeDraft.isPending}
        >
          {removeDraft.isPending ? "Deleting…" : "Delete Draft"}
        </Button>
      </div>

      {/* CV left, action rail right — stacks to a single column below
          `lg`. The rail is sticky + independently scrollable at `lg` and
          up so Export/Gaps/Unused Evidence stay reachable next to a CV
          that's taller than the viewport. `top-14` (not `top-4`) — the
          rail must clear CandidateWorkflowLayout.tsx's own sticky
          breadcrumb bar above it (~52px), or it pins in behind it instead
          of below it. */}
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <div className="min-w-0 flex-1 space-y-3">
          <JobDescriptionSummary vacancy={draft.vacancy} matchResult={matchResult} />
          <DocumentEditor
            // Forces a full remount after a same-draft Regenerate (see
            // regenVersion's own comment) — draftId included too, so
            // navigating straight from one draft to another (no full page
            // reload) also seeds fresh rather than reusing whatever this
            // instance already seeded for the previous draft.
            key={`${draftId}-${regenVersion}`}
            ref={documentEditorRef}
            assembledCv={liveAssembledCv}
            // The persisted PrintDocument and the editor's own DocumentModel
            // are structural mirrors (see domain/models.py's PrintDocument*
            // docstrings) but not identical TS types: `kind` is a plain
            // string on the wire vs. a literal union here, and `locked` is
            // `boolean | null` vs. optional — differences JS doesn't care
            // about at runtime, so a deliberate cast bridges them (done
            // once, above, alongside the Post-31 migration pass — see
            // `initialDocument`'s own comment).
            initialDocument={initialDocument}
            provenance={provenance}
            onModelChange={setCvDocument}
            onHeadlineChange={setHeadline}
            templateId={templateId}
            exportFormat={format}
          />
        </div>

        <div className="w-full shrink-0 space-y-4 lg:sticky lg:top-14 lg:w-80 lg:max-h-[calc(100vh-4rem)] lg:overflow-y-auto">
          <Card>
            <CardHeader>
              <CardTitle>Export</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              <ExportButton
                assembledCv={liveAssembledCv}
                cvDocument={cvDocument}
                templateId={templateId}
                onTemplateIdChange={setTemplateId}
                format={format}
                onFormatChange={setFormat}
              />
              <WritebackDialog
                candidateId={candidateId ?? null}
                assembledCv={liveAssembledCv}
                cvDocument={cvDocument}
                className="w-full"
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
              <CardTitle>Gaps</CardTitle>
              <Button
                type="button"
                variant="outline"
                size="xs"
                onClick={handleRecheckClick}
                disabled={cvDocument == null || recheckJob.isSubmitting || recheckJob.isRunning}
              >
                {recheckJob.isSubmitting || recheckJob.isRunning ? "Re-checking…" : "Re-check Gaps"}
              </Button>
            </CardHeader>
            <CardContent>
              <GapsPanel matchResult={matchResult} onDismiss={handleDismissGap} />
            </CardContent>
          </Card>

          {/* Phase 31 (follow-up) — moved here from a bare, unlabeled row
              under the A4 page (reported directly: it read as stray
              floating text there, and would be "much more noticeable"
              in the action rail below Gaps). Only rendered at all when
              there's something to flag — no empty-state Card, unlike
              Gaps/Excluded from CV/Unused Evidence, since "nothing worth
              a second look" isn't information worth a permanent card on
              every draft the way "no gaps" or "nothing excluded" is. */}
          {advisoryChips.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Worth a look</CardTitle>
              </CardHeader>
              <CardContent>
                <AdvisoryChips chips={advisoryChips} />
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Excluded from CV</CardTitle>
            </CardHeader>
            <CardContent>
              <ExcludedContentPanel document={cvDocument} onRestore={handleRestoreContent} />
            </CardContent>
          </Card>

          {provenance && (
            <Card>
              <CardHeader>
                <CardTitle>Unused Evidence</CardTitle>
              </CardHeader>
              <CardContent>
                <UnusedEvidencePanel
                  provenance={provenance}
                  experience={draft.assembled_cv.experience ?? []}
                  onAddToRole={handleAddToRole}
                  usedEvidenceIds={new Set(cvDocument ? collectUsedEvidenceIds(cvDocument) : [])}
                />
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
