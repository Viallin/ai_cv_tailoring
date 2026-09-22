import { Navigate, Route, BrowserRouter as Router, Routes, useParams } from "react-router-dom";

import { CandidateHomeScreen } from "@/components/CandidateHomeScreen";
import { CandidateWorkflowLayout } from "@/components/CandidateWorkflowLayout";
import { DraftScreen } from "@/components/DraftScreen";
import { ProfileView } from "@/components/ProfileView";

// Phase 20 — the routed flow (docs/development_plan.md): distinct
// screens instead of one dense window. `/` is candidate picker/ingest;
// everything scoped to one candidate nests under `/candidates/:candidateId`
// (CandidateWorkflowLayout owns the shared header/nav for those, per its
// own docstring). Replaces the Phase 15b-i `useState<"workflow"|"profile">`
// view toggle entirely — candidate identity and the active screen are
// both real, bookmarkable URL state now, not React state.
function ProfileRoute() {
  const { candidateId } = useParams<{ candidateId: string }>();
  return <ProfileView candidateId={candidateId ?? null} />;
}

// Post-4.10 nav redesign, round 3 — the standalone "CV export" screen is
// gone (its two export paths + drafts list now live in
// ProfileExportPanel.tsx, a sticky rail next to the profile itself), so
// this route no longer renders a screen of its own. Kept only so an old
// /export bookmark or link still lands somewhere real instead of a dead
// route — redirects straight into the profile that now holds the same
// content.
function ExportRedirect() {
  const { candidateId } = useParams<{ candidateId: string }>();
  return <Navigate to={`/candidates/${candidateId}/profile`} replace />;
}

function App() {
  return (
    <Router>
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-4 p-6">
        <h1 className="text-2xl font-semibold">AI CV Builder</h1>
        <Routes>
          <Route path="/" element={<CandidateHomeScreen />} />
          <Route path="/candidates/:candidateId" element={<CandidateWorkflowLayout />}>
            <Route index element={<Navigate to="profile" replace />} />
            <Route path="profile" element={<ProfileRoute />} />
            <Route path="export" element={<ExportRedirect />} />
            <Route path="drafts/:draftId" element={<DraftScreen />} />
          </Route>
        </Routes>
      </div>
    </Router>
  );
}

export default App;
