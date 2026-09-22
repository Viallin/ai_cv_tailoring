import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { MatchResult, Vacancy } from "@/api/models";
import { JobDescriptionSummary } from "./JobDescriptionSummary";

const vacancy: Vacancy = {
  title: "Senior Game Designer",
  company: "Voodoo",
  raw_text: "...",
  requirements: [
    { text: "5+ years of experience in mobile midcore games.", keywords: [], priority: "required" },
    { text: "Proven track record in gameplay design and balancing.", keywords: [], priority: "required" },
  ],
  keywords: ["Game Design", "Feature Engineering", "A/B Testing"],
};

describe("JobDescriptionSummary", () => {
  it("renders nothing for an untailored vacancy with no requirements or keywords", () => {
    const { container } = render(
      <JobDescriptionSummary vacancy={{ raw_text: "" }} matchResult={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the 'Vacancy details' label, the vacancy title/company, and the Hard Skills row open by default", () => {
    render(<JobDescriptionSummary vacancy={vacancy} matchResult={null} />);

    expect(screen.getByText("Vacancy details")).toBeInTheDocument();
    expect(screen.getByText("Senior Game Designer · Voodoo")).toBeInTheDocument();
    expect(screen.getByText("Game Design")).toBeInTheDocument();
  });

  it("starts with Requirements collapsed", () => {
    render(<JobDescriptionSummary vacancy={vacancy} matchResult={null} />);

    expect(screen.getByRole("button", { name: "Requirements" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("5+ years of experience in mobile midcore games.")).not.toBeInTheDocument();
  });

  it("highlights only the keywords the match result doesn't flag as missing", () => {
    const matchResult: MatchResult = {
      matches: [],
      gaps: [],
      missing_keywords: ["A/B Testing"],
    };
    render(<JobDescriptionSummary vacancy={vacancy} matchResult={matchResult} />);

    expect(screen.getByText("Game Design")).toHaveClass("text-[#1d4ed8]");
    expect(screen.getByText("A/B Testing")).toHaveClass("text-muted-foreground");
  });

  it("toggles Requirements and Hard Skills independently", async () => {
    const user = userEvent.setup();
    render(<JobDescriptionSummary vacancy={vacancy} matchResult={null} />);

    // Requirements: closed -> open, Hard Skills untouched (still visible).
    await user.click(screen.getByRole("button", { name: "Requirements" }));
    expect(screen.getByText("5+ years of experience in mobile midcore games.")).toBeInTheDocument();
    expect(screen.getByText("Game Design")).toBeInTheDocument();

    // Hard Skills: open -> closed, Requirements untouched (still open).
    await user.click(screen.getByRole("button", { name: "Hard Skills" }));
    expect(screen.queryByText("Game Design")).not.toBeInTheDocument();
    expect(screen.getByText("5+ years of experience in mobile midcore games.")).toBeInTheDocument();
  });
});
