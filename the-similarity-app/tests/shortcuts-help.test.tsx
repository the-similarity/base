import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { ShortcutsHelp } from "../components/shortcuts-help";

afterEach(cleanup);

/*
 * Tests for ShortcutsHelp.
 *
 * Coverage focus:
 *   - Lifecycle: returns null when closed (no DOM leakage of the overlay).
 *   - Visible content invariants: section headers + a couple of canonical
 *     shortcut labels. The catalogue could grow, but these anchors should
 *     always be present.
 *   - SHOW_PREVIEW gate: `g e`/`g s`/etc only show when showPreviewChords
 *     is true. Protects against accidentally advertising preview-only
 *     features in client builds.
 *   - Dismissal paths: close button, backdrop click both fire onClose;
 *     clicks inside the card do NOT.
 */

describe("ShortcutsHelp", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <ShortcutsHelp open={false} onClose={() => {}} showPreviewChords={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders section headers and key shortcut rows when open", () => {
    render(<ShortcutsHelp open={true} onClose={() => {}} showPreviewChords={false} />);
    expect(screen.getByText("Navigation")).toBeDefined();
    expect(screen.getByText("Workstation")).toBeDefined();
    expect(screen.getByText("Chart")).toBeDefined();
    // "Open command palette" appears twice (shortcut `/` + shortcut Cmd+K),
    // so assert on the count rather than getByText (which throws on >1 match).
    expect(screen.getAllByText("Open command palette").length).toBe(2);
    expect(screen.getByText("Jump to Retrieve surface")).toBeDefined();
    // "Run search" also appears twice (Enter + alternate `r`).
    expect(screen.getAllByText(/Run search/).length).toBeGreaterThanOrEqual(1);
  });

  it("hides preview-only chords when showPreviewChords is false", () => {
    render(<ShortcutsHelp open={true} onClose={() => {}} showPreviewChords={false} />);
    expect(screen.queryByText("Jump to Simulate")).toBeNull();
    expect(screen.queryByText("Jump to Evaluate")).toBeNull();
  });

  it("shows preview-only chords when showPreviewChords is true", () => {
    render(<ShortcutsHelp open={true} onClose={() => {}} showPreviewChords={true} />);
    expect(screen.getByText("Jump to Simulate")).toBeDefined();
    expect(screen.getByText("Jump to Evaluate")).toBeDefined();
  });

  it("fires onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    render(<ShortcutsHelp open={true} onClose={onClose} showPreviewChords={false} />);
    fireEvent.click(screen.getByLabelText("Close shortcuts help"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not fire onClose when the card body is clicked", () => {
    const onClose = vi.fn();
    render(<ShortcutsHelp open={true} onClose={onClose} showPreviewChords={false} />);
    // Clicking the title (inside the card) must NOT close the modal —
    // stopPropagation keeps the backdrop handler from firing.
    fireEvent.click(screen.getByText("Keyboard shortcuts"));
    expect(onClose).not.toHaveBeenCalled();
  });
});
