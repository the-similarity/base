/**
 * Tests for components/workstation/notebook-panel.tsx — left-rail
 * editable notebook entries.
 *
 * Coverage:
 *   1. Empty state renders prompt copy.
 *   2. Save button is disabled until text is non-empty.
 *   3. Entering + clicking Save fires onAdd with trimmed text and clears.
 *   4. Enter (no shift) submits; Shift+Enter does not.
 *   5. Click on row body fires onRestore with the full entry.
 *   6. Click on × fires onDelete with the entry id, NOT onRestore.
 *   7. Show-more toggle reveals entries beyond the 5-entry collapsed view.
 */

import { describe, it, expect, vi } from "vitest";
import { render, fireEvent, screen } from "@testing-library/react";
import { NotebookPanel } from "../components/workstation/notebook-panel";
import type { NotebookEntry } from "../lib/notebook";

function makeEntry(id: string, text: string, idx = 0): NotebookEntry {
  return {
    id,
    ts: `2026-04-${String(10 + idx).padStart(2, "0")}T00:00:00.000Z`,
    text,
    dataset: "stocks/spy/1d",
    windowStart: 1000 + idx,
    windowEnd: 1120 + idx,
  };
}

describe("NotebookPanel — empty state", () => {
  it("renders the empty-state copy when there are no entries", () => {
    render(
      <NotebookPanel
        entries={[]}
        onAdd={() => {}}
        onDelete={() => {}}
        onRestore={() => {}}
      />,
    );
    expect(
      screen.getByText(/no entries yet/i),
    ).toBeInTheDocument();
  });

  it("disables Save until text has non-whitespace content", () => {
    render(
      <NotebookPanel
        entries={[]}
        onAdd={() => {}}
        onDelete={() => {}}
        onRestore={() => {}}
      />,
    );
    const button = screen.getByRole("button", { name: /save notebook entry/i });
    expect(button).toBeDisabled();

    const textarea = screen.getByLabelText("New notebook entry");
    fireEvent.change(textarea, { target: { value: "   " } });
    expect(button).toBeDisabled();

    fireEvent.change(textarea, { target: { value: "real text" } });
    expect(button).not.toBeDisabled();
  });
});

describe("NotebookPanel — submission", () => {
  it("clicking Save fires onAdd with trimmed text and clears the textarea", () => {
    const onAdd = vi.fn();
    render(
      <NotebookPanel
        entries={[]}
        onAdd={onAdd}
        onDelete={() => {}}
        onRestore={() => {}}
      />,
    );
    const textarea = screen.getByLabelText("New notebook entry") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "  hello world  " } });
    fireEvent.click(screen.getByRole("button", { name: /save notebook entry/i }));

    expect(onAdd).toHaveBeenCalledWith("hello world");
    expect(textarea.value).toBe("");
  });

  it("Enter (no shift) submits", () => {
    const onAdd = vi.fn();
    render(
      <NotebookPanel
        entries={[]}
        onAdd={onAdd}
        onDelete={() => {}}
        onRestore={() => {}}
      />,
    );
    const textarea = screen.getByLabelText("New notebook entry");
    fireEvent.change(textarea, { target: { value: "via enter" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    expect(onAdd).toHaveBeenCalledWith("via enter");
  });

  it("Shift+Enter does NOT submit (lets the user newline)", () => {
    const onAdd = vi.fn();
    render(
      <NotebookPanel
        entries={[]}
        onAdd={onAdd}
        onDelete={() => {}}
        onRestore={() => {}}
      />,
    );
    const textarea = screen.getByLabelText("New notebook entry");
    fireEvent.change(textarea, { target: { value: "two\nlines" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(onAdd).not.toHaveBeenCalled();
  });
});

describe("NotebookPanel — row interactions", () => {
  it("clicking the row body fires onRestore with the full entry", () => {
    const entries = [makeEntry("nb-1", "thought one")];
    const onRestore = vi.fn();
    render(
      <NotebookPanel
        entries={entries}
        onAdd={() => {}}
        onDelete={() => {}}
        onRestore={onRestore}
      />,
    );
    const row = screen.getByText("thought one").closest('[role="button"]');
    if (!row) throw new Error("row not found");
    fireEvent.click(row);
    expect(onRestore).toHaveBeenCalledWith(entries[0]);
  });

  it("clicking × fires onDelete and NOT onRestore", () => {
    const entries = [makeEntry("nb-1", "to delete")];
    const onRestore = vi.fn();
    const onDelete = vi.fn();
    render(
      <NotebookPanel
        entries={entries}
        onAdd={() => {}}
        onDelete={onDelete}
        onRestore={onRestore}
      />,
    );
    fireEvent.click(screen.getByLabelText("Delete entry"));
    expect(onDelete).toHaveBeenCalledWith("nb-1");
    expect(onRestore).not.toHaveBeenCalled();
  });

  it("collapses to 5 entries by default; show-more reveals the rest", () => {
    const many: NotebookEntry[] = Array.from({ length: 8 }, (_, i) =>
      makeEntry(`nb-${i}`, `entry ${i}`, i),
    );
    render(
      <NotebookPanel
        entries={many}
        onAdd={() => {}}
        onDelete={() => {}}
        onRestore={() => {}}
      />,
    );
    // 5 visible initially.
    expect(screen.getByText("entry 0")).toBeInTheDocument();
    expect(screen.getByText("entry 4")).toBeInTheDocument();
    expect(screen.queryByText("entry 5")).not.toBeInTheDocument();

    // Toggle on.
    fireEvent.click(screen.getByText(/show 3 more/));
    expect(screen.getByText("entry 5")).toBeInTheDocument();
    expect(screen.getByText("entry 7")).toBeInTheDocument();

    // Toggle off.
    fireEvent.click(screen.getByText(/show fewer/));
    expect(screen.queryByText("entry 5")).not.toBeInTheDocument();
  });
});
