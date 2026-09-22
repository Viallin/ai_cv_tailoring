import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AdvisoryChips } from "./AdvisoryChips";

// Phase 31 (follow-up) — this component is now purely presentational
// (a plain list of items for an already-computed `chips` array); the
// "should this render at all" and "what counts as worth flagging"
// decisions moved to DraftScreen.tsx (buildAdvisoryChips) and
// lib/advisories.test.ts respectively, so this file only needs to
// confirm the render itself.
describe("AdvisoryChips", () => {
  it("renders one list item per chip, in order, matching its rail siblings' own item-box shape", () => {
    render(
      <AdvisoryChips
        chips={[
          { id: "a", message: "First thing worth a look." },
          { id: "b", message: "Second thing worth a look." },
        ]}
      />,
    );

    const first = screen.getByText("First thing worth a look.");
    expect(first.tagName).toBe("LI");
    // Same class string GapsPanel/ExcludedContentPanel/UnusedEvidencePanel
    // use for their own item boxes — the whole point of this follow-up.
    expect(first).toHaveClass("rounded-lg", "border", "bg-muted/40", "p-3");
    expect(screen.getByText("Second thing worth a look.")).toBeInTheDocument();
  });

  it("renders an empty list for an empty chips array", () => {
    const { container } = render(<AdvisoryChips chips={[]} />);
    expect(container.querySelectorAll("li")).toHaveLength(0);
  });
});
