import { ChevronRight, Home } from "lucide-react";
import { Link, Outlet, useNavigate, useParams } from "react-router-dom";

import { useCvDrafts } from "@/api/cvDrafts";
import { CandidatePicker, NEW_CANDIDATE_OPTION } from "@/components/CandidatePicker";
import { draftLabel } from "@/lib/sections";
import { cn } from "@/lib/utils";

// Phase 20 — the shared layout for every screen scoped to one candidate
// (profile, a specific draft). Deliberately thin: just candidate identity
// (from the URL, not React state — see App.tsx) and a small nav.
// Generate-result state (assembledCv/vacancy/matchResult/cvDocument) does
// NOT live here — it's persisted through CVDraft instead (confirmed with
// the user; see docs/development_plan.md's Phase 20 scoping note), so
// there's nothing to lift into this layout beyond the candidate id itself.
//
// Post-4.10 friend feedback, round 1: "no obvious way back" — fixed with a
// sticky breadcrumb trail (Home / profile / draft), every crumb but the
// current one a link one level up.
//
// Post-4.10 friend feedback, round 2: the persistent Profile/CV export
// tabs sitting below the breadcrumb duplicated it, and the profile picker
// below *that* repeated the candidate's name a third time. Tabs are gone
// entirely — the breadcrumb alone is the nav now — and the picker moved
// into the breadcrumb itself as the "current profile" crumb.
//
// Post-4.10 friend feedback, round 3 — the standalone "CV export" screen
// is gone too (ProfileExportPanel.tsx folds it into a rail on the profile
// itself), so there's no "CV export" crumb to show any more: a draft's
// breadcrumb goes straight from the profile crumb to the draft's own
// title. `draftId` resolves here even though this component's own route
// is just "/candidates/:candidateId" — useParams merges params from the
// whole matched branch, including the nested "drafts/:draftId" route.
export function CandidateWorkflowLayout() {
  const { candidateId, draftId } = useParams<{ candidateId: string; draftId?: string }>();
  const navigate = useNavigate();
  // Cheap even when not on a draft screen — same query key
  // ProfileExportPanel.tsx's "Your drafts" list already uses, so this
  // just subscribes to whatever's cached rather than forcing an extra
  // fetch in the common case.
  const { data: drafts } = useCvDrafts(candidateId ?? null);
  const currentDraft = draftId ? drafts?.find((d) => d.id === draftId) : undefined;

  const crumbLinkClass = "text-muted-foreground hover:text-foreground hover:underline";

  return (
    <div className="space-y-4">
      <nav
        aria-label="Breadcrumb"
        className="sticky top-0 z-10 -mx-6 flex flex-wrap items-center gap-1.5 bg-background px-6 py-3 text-sm"
      >
        <Link to="/" className={cn("flex items-center gap-1", crumbLinkClass)}>
          <Home className="size-3.5" />
          Home
        </Link>
        <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
        <CandidatePicker
          selectedId={candidateId ?? null}
          onSelect={(id) => navigate(id === NEW_CANDIDATE_OPTION ? "/" : `/candidates/${id}/profile`)}
        />
        {draftId && (
          <>
            <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="font-medium">{currentDraft ? draftLabel(currentDraft) : "…"}</span>
          </>
        )}
      </nav>

      <Outlet />
    </div>
  );
}
