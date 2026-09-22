import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { IngestPanel } from "./IngestPanel";

function renderPanel(overrides: Partial<Parameters<typeof IngestPanel>[0]> = {}) {
  const props = {
    resumeText: "",
    onResumeTextChange: vi.fn(),
    onIngestClick: vi.fn(),
    onFileSelected: vi.fn(),
    hintText: "Ingesting always creates a new candidate profile.",
    busy: false,
    ingestBusy: false,
    uploadBusy: false,
    ...overrides,
  };
  const { container } = render(<IngestPanel {...props} />);
  // The drop zone is the whole panel's outer wrapper — it has no
  // distinguishing accessible role of its own (it's a plain container,
  // not a control), so tests that need to dispatch drag/drop events at it
  // grab it structurally rather than by role/label like everything else
  // here.
  const dropZone = container.firstElementChild as HTMLElement;
  return { ...props, dropZone };
}

describe("IngestPanel", () => {
  it("renders the paste box, the Ingest Resume button, and the hint text", () => {
    renderPanel({ hintText: "Some hint." });

    expect(screen.getByPlaceholderText("Paste your resume text here...")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ingest Resume" })).toBeInTheDocument();
    expect(screen.getByText("Some hint.")).toBeInTheDocument();
  });

  it("clicking Ingest Resume calls onIngestClick, not onFileSelected", async () => {
    const user = userEvent.setup();
    const props = renderPanel();

    await user.click(screen.getByRole("button", { name: "Ingest Resume" }));

    expect(props.onIngestClick).toHaveBeenCalledTimes(1);
    expect(props.onFileSelected).not.toHaveBeenCalled();
  });

  it("picking a file via the hidden input calls onFileSelected with that file", async () => {
    const user = userEvent.setup();
    const props = renderPanel();
    const file = new File(["resume text"], "resume.pdf", { type: "application/pdf" });

    const input = screen.getByLabelText("Upload resume file");
    await user.upload(input, file);

    expect(props.onFileSelected).toHaveBeenCalledWith(file);
    expect(props.onIngestClick).not.toHaveBeenCalled();
  });

  it("dropping a file onto the panel calls onFileSelected with that file", () => {
    // The regression this guards: before this handler existed, the panel
    // had no dragover/drop wiring at all — a drop fell through to the
    // browser's own default handling instead of reaching React at all.
    const props = renderPanel();
    const file = new File(["resume text"], "resume.pdf", { type: "application/pdf" });

    fireEvent.drop(props.dropZone, { dataTransfer: { files: [file] } });

    expect(props.onFileSelected).toHaveBeenCalledWith(file);
  });

  it("dragover on the panel prevents the browser's default (open-the-file) behavior", () => {
    const props = renderPanel();

    const event = fireEvent.dragOver(props.dropZone, { dataTransfer: { files: [] } });

    // fireEvent's boolean return value is the *pre-preventDefault*
    // dispatchEvent result — true only means the handler didn't call
    // preventDefault. false here means it did, i.e. the drop is no longer
    // left to the browser's own default file-open handling.
    expect(event).toBe(false);
  });

  it("ignores a drop while busy", () => {
    const props = renderPanel({ busy: true });
    const file = new File(["resume text"], "resume.pdf");

    fireEvent.drop(props.dropZone, { dataTransfer: { files: [file] } });

    expect(props.onFileSelected).not.toHaveBeenCalled();
  });

  it("does not call onFileSelected for a drop with no files", () => {
    const props = renderPanel();

    fireEvent.drop(props.dropZone, { dataTransfer: { files: [] } });

    expect(props.onFileSelected).not.toHaveBeenCalled();
  });

  it("does not call onFileSelected for a file extension outside the input's accept list", async () => {
    // userEvent.upload itself enforces the input's `accept` attribute — a
    // file whose extension isn't in ACCEPTED_FILE_TYPES never reaches
    // onChange at all, the same way a real OS file picker filters its
    // dialog. Real (server-side) rejection of an accepted-but-unparseable
    // file is exercised separately in CandidateHomeScreen.test.tsx.
    const user = userEvent.setup();
    const props = renderPanel();
    const file = new File(["x"], "resume.odt");

    await user.upload(screen.getByLabelText("Upload resume file"), file);

    expect(props.onFileSelected).not.toHaveBeenCalled();
  });

  it("disables the textarea, both buttons, and the file input while busy", () => {
    renderPanel({ busy: true });

    expect(screen.getByPlaceholderText("Paste your resume text here...")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ingest Resume" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Upload a file" })).toBeDisabled();
    expect(screen.getByLabelText("Upload resume file")).toBeDisabled();
  });

  it("shows the busy state on the Ingest Resume button itself, not the Upload button", () => {
    // Same "status lives on the button you pushed" convention as
    // GenerateButton.tsx/ReevaluateSkillLinksButton.tsx — found live: a
    // status paragraph pinned to the top of CandidateHomeScreen read as
    // disconnected from whichever button was actually pressed.
    renderPanel({ busy: true, ingestBusy: true });

    expect(screen.getByRole("button", { name: "Ingesting…" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload a file" })).toBeInTheDocument();
  });

  it("shows the busy state on the Upload a file button itself, not the Ingest button", () => {
    renderPanel({ busy: true, uploadBusy: true });

    expect(screen.getByRole("button", { name: "Ingest Resume" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ingesting…" })).toBeInTheDocument();
  });
});
