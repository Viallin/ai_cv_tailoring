import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DocumentModel } from "@/lib/structuredDocument";
import { ExcludedContentPanel } from "./ExcludedContentPanel";

describe("ExcludedContentPanel", () => {
  it("renders nothing before a document exists", () => {
    const { container } = render(<ExcludedContentPanel document={null} onRestore={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a fallback message when nothing is excluded", () => {
    const document: DocumentModel = {
      sections: [
        {
          key: "education",
          title: "Education",
          included: true,
          entries: [{ id: "edu-1", text: "State University", included: true }],
        },
      ],
    };

    render(<ExcludedContentPanel document={document} onRestore={vi.fn()} />);
    expect(screen.getByText("Nothing excluded from this CV.")).toBeInTheDocument();
  });

  it("lists each excluded item's section and text", () => {
    const document: DocumentModel = {
      sections: [
        {
          key: "education",
          title: "Education",
          included: true,
          entries: [
            { id: "edu-1", text: "State University", included: true },
            { id: "edu-2", text: "Community College", included: false },
          ],
        },
      ],
    };

    render(<ExcludedContentPanel document={document} onRestore={vi.fn()} />);
    expect(screen.getByText("Community College")).toBeInTheDocument();
    expect(screen.getByText("Education")).toBeInTheDocument();
    expect(screen.queryByText("State University")).not.toBeInTheDocument();
  });

  it("clicking Restore calls onRestore with that item", async () => {
    const user = userEvent.setup();
    const onRestore = vi.fn();
    const document: DocumentModel = {
      sections: [
        {
          key: "education",
          title: "Education",
          included: true,
          entries: [{ id: "edu-2", text: "Community College", included: false }],
        },
      ],
    };

    render(<ExcludedContentPanel document={document} onRestore={onRestore} />);
    await user.click(screen.getByRole("button", { name: "Restore" }));

    expect(onRestore).toHaveBeenCalledWith({
      sectionKey: "education",
      sectionTitle: "Education",
      entryId: "edu-2",
      text: "Community College",
    });
  });

  it("lists an excluded bullet with its bulletId, distinct from an excluded entry", async () => {
    const user = userEvent.setup();
    const onRestore = vi.fn();
    const document: DocumentModel = {
      sections: [
        {
          key: "experience",
          title: "Experience",
          included: true,
          entries: [
            {
              id: "exp-1",
              text: "Engineer — Acme",
              included: true,
              bullets: [{ id: "exp-1-bullet-0", text: "Owned the backend", included: false }],
            },
          ],
        },
      ],
    };

    render(<ExcludedContentPanel document={document} onRestore={onRestore} />);
    expect(screen.getByText("Owned the backend")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Restore" }));

    expect(onRestore).toHaveBeenCalledWith({
      sectionKey: "experience",
      sectionTitle: "Experience",
      entryId: "exp-1",
      bulletId: "exp-1-bullet-0",
      text: "Owned the backend",
    });
  });
});
