import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CreateProfilePanel } from "./CreateProfilePanel";

function renderPanel(overrides: Partial<Parameters<typeof CreateProfilePanel>[0]> = {}) {
  const props = { onCreateClick: vi.fn(), busy: false, ...overrides };
  render(<CreateProfilePanel {...props} />);
  return props;
}

describe("CreateProfilePanel", () => {
  it("renders the name field, a language dropdown defaulted to English, and the Create Profile button", () => {
    renderPanel();

    expect(screen.getByLabelText("Name")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Language" })).toHaveTextContent("English");
    expect(screen.getByRole("button", { name: "Create Profile" })).toBeInTheDocument();
  });

  it("clicking Create Profile calls onCreateClick with the typed name and default language", async () => {
    const user = userEvent.setup();
    const props = renderPanel();

    await user.type(screen.getByLabelText("Name"), "Grace Hopper");
    await user.click(screen.getByRole("button", { name: "Create Profile" }));

    expect(props.onCreateClick).toHaveBeenCalledWith("Grace Hopper", "en");
  });

  it("disables the name field, language dropdown, and button while busy", () => {
    renderPanel({ busy: true });

    expect(screen.getByLabelText("Name")).toBeDisabled();
    expect(screen.getByRole("combobox", { name: "Language" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Create Profile" })).toBeDisabled();
  });
});
