import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { MatchResult } from "@/api/models";
import { GapsPanel } from "./GapsPanel";

// Pins ui/main_window.py's _gaps_html branching exactly — see that
// function's docstring for the spec each assertion below ports.
describe("GapsPanel", () => {
  it("shows the fallback message when there are no gaps or missing keywords", () => {
    render(<GapsPanel matchResult={{ matches: [], gaps: [], missing_keywords: [] }} />);

    expect(screen.getByText("No notable gaps found for this vacancy.")).toBeInTheDocument();
  });

  it("sorts high before medium and shows a suggested action", () => {
    const matchResult: MatchResult = {
      matches: [],
      gaps: [
        { requirement_text: "Docker", description: "No Docker experience found.", severity: "medium", status: "open" },
        {
          requirement_text: "AWS",
          description: "No cloud experience found.",
          severity: "high",
          suggested_action: "Add a bullet naming any AWS work.",
          status: "open",
        },
      ],
      missing_keywords: [],
    };

    render(<GapsPanel matchResult={matchResult} />);

    const tags = screen.getAllByText(/^(HIGH|MED)$/);
    expect(tags.map((el) => el.textContent)).toEqual(["HIGH", "MED"]);
    expect(screen.getByText(/Add a bullet naming any AWS work\./)).toBeInTheDocument();
  });

  it("never shows low-severity gaps individually", () => {
    const matchResult: MatchResult = {
      matches: [],
      gaps: [{ requirement_text: "Rust", description: "No Rust experience.", severity: "low", status: "open" }],
      missing_keywords: [],
    };

    render(<GapsPanel matchResult={matchResult} />);

    expect(screen.queryByText(/No Rust experience/)).not.toBeInTheDocument();
    expect(screen.getByText("+ 1 more, low priority · collapsed")).toBeInTheDocument();
  });

  it("collapses multiple low-severity gaps into one count line", () => {
    const matchResult: MatchResult = {
      matches: [],
      gaps: [
        { requirement_text: "A", description: "a", severity: "low", status: "open" },
        { requirement_text: "B", description: "b", severity: "low", status: "open" },
      ],
      missing_keywords: [],
    };

    render(<GapsPanel matchResult={matchResult} />);

    expect(screen.getByText("+ 2 more, low priority · collapsed")).toBeInTheDocument();
  });

  it("shows a trailing missing-keywords line", () => {
    render(<GapsPanel matchResult={{ matches: [], gaps: [], missing_keywords: ["AWS", "Docker"] }} />);

    expect(screen.getByText("Missing keywords: AWS, Docker")).toBeInTheDocument();
  });

  it("shows a trailing skills-to-add line, distinct from missing keywords", () => {
    const matchResult: MatchResult = {
      matches: [],
      gaps: [],
      missing_keywords: [],
      skills_to_add: [
        { keyword: "A/B Testing", evidence_ids: ["ev-4"] },
        { keyword: "Roadmapping", evidence_ids: ["ev-9"] },
      ],
    };

    render(<GapsPanel matchResult={matchResult} />);

    expect(
      screen.getByText("Already backed by your experience — add to your Skills list: A/B Testing, Roadmapping"),
    ).toBeInTheDocument();
  });

  it("shows skills_to_add even when there are no gaps or missing keywords", () => {
    const matchResult: MatchResult = {
      matches: [],
      gaps: [],
      missing_keywords: [],
      skills_to_add: [{ keyword: "A/B Testing", evidence_ids: [] }],
    };

    render(<GapsPanel matchResult={matchResult} />);

    expect(screen.queryByText("No notable gaps found for this vacancy.")).not.toBeInTheDocument();
  });

  it("renders nothing before a MatchResult exists", () => {
    const { container } = render(<GapsPanel matchResult={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("has no Dismiss button when onDismiss isn't provided", () => {
    const matchResult: MatchResult = {
      matches: [],
      gaps: [{ requirement_text: "AWS", description: "No cloud experience found.", severity: "high", status: "open" }],
      missing_keywords: [],
    };

    render(<GapsPanel matchResult={matchResult} />);

    expect(screen.queryByRole("button", { name: "Dismiss" })).not.toBeInTheDocument();
  });

  it("clicking Dismiss calls onDismiss with that gap's requirement_text", async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();
    const matchResult: MatchResult = {
      matches: [],
      gaps: [
        {
          requirement_text: "AWS certification",
          description: "No cloud experience found.",
          severity: "high",
          status: "open",
        },
      ],
      missing_keywords: [],
    };

    render(<GapsPanel matchResult={matchResult} onDismiss={onDismiss} />);
    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(onDismiss).toHaveBeenCalledWith("AWS certification");
  });

  it("a skipped gap doesn't show individually, and is counted in a dismissed line instead", () => {
    const matchResult: MatchResult = {
      matches: [],
      gaps: [
        { requirement_text: "AWS", description: "No cloud experience found.", severity: "high", status: "skipped" },
        { requirement_text: "Docker", description: "No Docker experience found.", severity: "medium", status: "open" },
      ],
      missing_keywords: [],
    };

    render(<GapsPanel matchResult={matchResult} onDismiss={vi.fn()} />);

    expect(screen.queryByText(/No cloud experience found/)).not.toBeInTheDocument();
    expect(screen.getByText(/No Docker experience found/)).toBeInTheDocument();
    expect(screen.getByText("+ 1 dismissed")).toBeInTheDocument();
  });

  it("a skipped low-severity gap doesn't get double-counted in both lines", () => {
    const matchResult: MatchResult = {
      matches: [],
      gaps: [{ requirement_text: "Rust", description: "No Rust experience.", severity: "low", status: "skipped" }],
      missing_keywords: [],
    };

    render(<GapsPanel matchResult={matchResult} onDismiss={vi.fn()} />);

    expect(screen.queryByText(/dismissed/)).not.toBeInTheDocument();
    expect(screen.getByText("+ 1 more, low priority · collapsed")).toBeInTheDocument();
  });
});
