import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { AssembledCV } from "@/api/models";
import { CvPrintHeader } from "./CvPrintHeader";

function makeCv(overrides: Partial<AssembledCV> = {}): AssembledCV {
  return { name: "Ada Lovelace", language: "en", summary: "A summary.", ...overrides };
}

describe("CvPrintHeader", () => {
  it("renders name and headline as plain text when onHeadlineChange is omitted", () => {
    render(<CvPrintHeader cv={makeCv({ headline: "Senior Engineer" })} />);

    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
    expect(screen.getByText("Senior Engineer")).toBeInTheDocument();
    expect(screen.queryByLabelText("Role title")).not.toBeInTheDocument();
  });

  it("renders no headline paragraph when there is none and onHeadlineChange is omitted", () => {
    const { container } = render(<CvPrintHeader cv={makeCv()} />);

    expect(container.querySelectorAll("p")).toHaveLength(0);
  });

  it("renders the headline as an editable input, right in the header, when onHeadlineChange is passed", async () => {
    const user = userEvent.setup();
    const onHeadlineChange = vi.fn();
    render(<CvPrintHeader cv={makeCv({ headline: "Senior Engineer" })} onHeadlineChange={onHeadlineChange} />);

    const field = screen.getByLabelText("Role title");
    expect(field).toHaveValue("Senior Engineer");
    expect(screen.queryByText("Senior Engineer", { selector: "p" })).not.toBeInTheDocument();

    await user.type(field, "!");
    expect(onHeadlineChange).toHaveBeenLastCalledWith("Senior Engineer!");
  });

  it("still renders the (empty, placeholder-only) input when editable and there is no headline yet", () => {
    render(<CvPrintHeader cv={makeCv()} onHeadlineChange={vi.fn()} />);

    const field = screen.getByLabelText("Role title");
    expect(field).toHaveValue("");
    expect(field).toHaveAttribute("placeholder", "Add a role title…");
  });

  it("no longer renders contacts — they moved into their own section", () => {
    render(
      <CvPrintHeader
        cv={makeCv({ contacts: [{ id: "c1", label: "Email", value: "ada@example.com" }] })}
      />,
    );

    expect(screen.queryByText(/ada@example\.com/)).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
