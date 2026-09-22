import { ChevronDown } from "lucide-react";
import { useState, type ReactNode } from "react";

import type { MatchResult, Vacancy } from "@/api/models";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { isKeywordCovered } from "@/lib/vacancySummary";
import { cn } from "@/lib/utils";

interface JobDescriptionSummaryProps {
  vacancy: Vacancy;
  matchResult: MatchResult | null;
}

// Sits above the CV editor on the draft screen (DraftScreen.tsx). Reported
// directly: with only GapsPanel in the action rail, the draft screen
// showed what's *missing* against this vacancy but nowhere showed the
// vacancy itself, or which of its named skills the tailored CV already
// covers — gap analysis only ever told half the story. Modeled on a
// JD-summary layout from Jobgether (screenshot supplied directly) — a
// Requirements list plus a Hard Skills chip row, the chips split by
// whether the candidate covers each one. The "Vacancy details" label
// above the Card mirrors the "Vacancy title" label already sitting above
// its own Input higher up this screen, so the two read as one family of
// fields rather than one styled differently from the other.
//
// Deliberately narrower than that reference layout: Vacancy has no
// qualifications/responsibilities split (02_jd_parser_v1.md extracts one
// flat, atomized `requirements` list — a Requirement is scored as a
// single pass/fail unit regardless of whether the JD phrased it as a
// qualification or a duty) and no hard/soft-skill or language distinction
// (`keywords` is one flat list covering "skills, tools, technologies,
// certifications" together, with no language extraction at all).
// Reproducing the reference's four-way split would mean teaching the JD
// parser LLM a new classification it doesn't make today — real backend/
// prompt work that would only benefit newly-generated drafts, not every
// existing one. Chose the frontend-only cut instead, confirmed directly:
// one Requirements list, one Hard Skills row, highlighted using data the
// Matching stage already computes (see isKeywordCovered's own docstring)
// — available immediately, for every draft, with no LLM prompt risk.
export function JobDescriptionSummary({ vacancy, matchResult }: JobDescriptionSummaryProps) {
  // Two independent toggles, not one whole-card one (tried first — see
  // this component's own git history — then reported directly as the
  // wrong grain): Requirements is the long list nobody needs open on
  // every visit, so it starts collapsed; Hard Skills is the compact,
  // worth-a-glance row people actually want to see right away, so it
  // starts open.
  const [requirementsExpanded, setRequirementsExpanded] = useState(false);
  const [skillsExpanded, setSkillsExpanded] = useState(true);
  const requirements = vacancy.requirements ?? [];
  const keywords = vacancy.keywords ?? [];

  // Nothing to show at all — an untailored draft's Vacancy is the empty
  // UNTAILORED_VACANCY placeholder (raw_text: "", no requirements or
  // keywords) — hidden entirely rather than rendered as an empty card,
  // same "no empty-state Card" precedent AdvisoryChips/UnusedEvidencePanel
  // already use elsewhere on this screen.
  if (requirements.length === 0 && keywords.length === 0) {
    return null;
  }

  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">Vacancy details</p>
      <Card>
        <CardHeader>
          <CardTitle>
            {vacancy.title || "Job description"}
            {vacancy.company ? ` · ${vacancy.company}` : ""}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {requirements.length > 0 && (
            <CollapsibleSection
              label="Requirements"
              expanded={requirementsExpanded}
              onToggle={() => setRequirementsExpanded((current) => !current)}
            >
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {requirements.map((requirement, index) => (
                  <li key={index}>{requirement.text}</li>
                ))}
              </ul>
            </CollapsibleSection>
          )}
          {keywords.length > 0 && (
            <CollapsibleSection
              label="Hard Skills"
              expanded={skillsExpanded}
              onToggle={() => setSkillsExpanded((current) => !current)}
            >
              <div className="flex flex-wrap gap-1.5">
                {keywords.map((keyword) => {
                  const covered = isKeywordCovered(keyword, matchResult);
                  return (
                    <span
                      key={keyword}
                      className={cn(
                        "rounded-full px-2.5 py-1 text-xs font-medium",
                        // Hardcoded blue, not text-primary/bg-primary — verified live
                        // against this app's actual theme (index.css): --primary is
                        // zero-chroma grayscale in both light and dark mode, so a
                        // "covered" chip styled off it rendered visually
                        // indistinguishable from an uncovered one, the exact opposite
                        // of "highlighting." Same fix GapsPanel.tsx already applies to
                        // its HIGH/MED severity tags, for the same reason.
                        covered
                          ? "border border-[#3b82f6]/40 bg-[#3b82f6]/10 text-[#1d4ed8]"
                          : "bg-muted text-muted-foreground",
                      )}
                    >
                      {keyword}
                    </span>
                  );
                })}
              </div>
              <p className="mt-1.5 text-xs text-muted-foreground">
                Highlighted skills are already backed by your evidence for this vacancy.
              </p>
            </CollapsibleSection>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// One disclosure row (chevron + uppercase label, chevron on the left per
// the Jobgether reference) plus its collapsible body — Requirements and
// Hard Skills above are just two instances of this with independent
// state, rather than two hand-duplicated toggle blocks.
function CollapsibleSection({
  label,
  expanded,
  onToggle,
  children,
}: {
  label: string;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase"
      >
        <ChevronDown className={cn("size-3.5 shrink-0 transition-transform", !expanded && "-rotate-90")} />
        {label}
      </button>
      {expanded && children}
    </div>
  );
}
