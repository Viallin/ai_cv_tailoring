import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { AssembledExperienceEntry, BulletProvenanceReport } from "@/api/models";
import { UnusedEvidencePanel } from "./UnusedEvidencePanel";

describe("UnusedEvidencePanel", () => {
  it("renders nothing before a provenance report exists", () => {
    const { container } = render(<UnusedEvidencePanel provenance={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows a fallback message when every Evidence item made it in", () => {
    const provenance: BulletProvenanceReport = { bullets: [], unused_evidence: [] };

    render(<UnusedEvidencePanel provenance={provenance} />);

    expect(screen.getByText("Every Evidence item made it into this CV.")).toBeInTheDocument();
  });

  it("lists each unused Evidence item's text and source_context", () => {
    const provenance: BulletProvenanceReport = {
      bullets: [],
      unused_evidence: [
        { id: "ev-2", text: "Organized a hackathon", source_context: "Acme Corp", locked: false },
        { id: "ev-3", text: "Volunteered as a mentor", locked: false },
      ],
    };

    render(<UnusedEvidencePanel provenance={provenance} />);

    expect(screen.getByText("Organized a hackathon")).toBeInTheDocument();
    expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText("Volunteered as a mentor")).toBeInTheDocument();
    expect(screen.getByText("Didn't make the cut for this vacancy — add manually?")).toBeInTheDocument();
  });

  const EXPERIENCE: AssembledExperienceEntry[] = [
    { experience_id: "exp-1", position: "Engineer", company: "Acme", is_gap: false, bullets: [] },
  ];

  it("shows an Add to Role button only for an item whose experience_id matches a known role", () => {
    const provenance: BulletProvenanceReport = {
      bullets: [],
      unused_evidence: [
        { id: "ev-1", text: "Role-linked item", experience_id: "exp-1", locked: false },
        { id: "ev-2", text: "No role link at all", locked: false },
        {
          id: "ev-3",
          text: "Role id doesn't match any current entry",
          experience_id: "exp-does-not-exist",
          locked: false,
        },
      ],
    };

    render(<UnusedEvidencePanel provenance={provenance} experience={EXPERIENCE} onAddToRole={vi.fn()} />);

    // Only ev-1 has an experience_id matching a real, known entry.
    expect(screen.getAllByRole("button", { name: /^Add to / })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Add to Engineer — Acme" })).toBeInTheDocument();
  });

  it("clicking Add to Role calls onAddToRole with the evidence item and its experience_id", async () => {
    const user = userEvent.setup();
    const onAddToRole = vi.fn();
    const provenance: BulletProvenanceReport = {
      bullets: [],
      unused_evidence: [{ id: "ev-1", text: "Role-linked item", experience_id: "exp-1", locked: false }],
    };

    render(<UnusedEvidencePanel provenance={provenance} experience={EXPERIENCE} onAddToRole={onAddToRole} />);
    await user.click(screen.getByRole("button", { name: "Add to Engineer — Acme" }));

    expect(onAddToRole).toHaveBeenCalledWith(
      { id: "ev-1", text: "Role-linked item", experience_id: "exp-1", locked: false },
      "exp-1",
    );
  });

  it("has no Add to Role button when onAddToRole isn't provided, even for a role-linked item", () => {
    const provenance: BulletProvenanceReport = {
      bullets: [],
      unused_evidence: [{ id: "ev-1", text: "Role-linked item", experience_id: "exp-1", locked: false }],
    };

    render(<UnusedEvidencePanel provenance={provenance} experience={EXPERIENCE} />);

    expect(screen.queryByRole("button", { name: /^Add to / })).not.toBeInTheDocument();
  });

  it("hides an item whose id is in usedEvidenceIds, so it can't be added twice", () => {
    // Regression: clicking "Add to Role" inserted a bullet but never
    // removed the item from this list, so repeated clicks kept appending
    // duplicate bullets for the same Evidence.
    const provenance: BulletProvenanceReport = {
      bullets: [],
      unused_evidence: [
        { id: "ev-1", text: "Already added", experience_id: "exp-1", locked: false },
        { id: "ev-2", text: "Still unused", experience_id: "exp-1", locked: false },
      ],
    };

    render(
      <UnusedEvidencePanel
        provenance={provenance}
        experience={EXPERIENCE}
        onAddToRole={vi.fn()}
        usedEvidenceIds={new Set(["ev-1"])}
      />,
    );

    expect(screen.queryByText("Already added")).not.toBeInTheDocument();
    expect(screen.getByText("Still unused")).toBeInTheDocument();
  });

  it("shows the fallback message once usedEvidenceIds covers every remaining item", () => {
    const provenance: BulletProvenanceReport = {
      bullets: [],
      unused_evidence: [{ id: "ev-1", text: "Already added", experience_id: "exp-1", locked: false }],
    };

    render(
      <UnusedEvidencePanel
        provenance={provenance}
        experience={EXPERIENCE}
        onAddToRole={vi.fn()}
        usedEvidenceIds={new Set(["ev-1"])}
      />,
    );

    expect(screen.getByText("Every Evidence item made it into this CV.")).toBeInTheDocument();
  });
});
