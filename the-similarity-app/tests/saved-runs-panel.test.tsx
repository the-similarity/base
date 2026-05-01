/**
 * Tests for components/workstation/saved-runs-panel.tsx — left-rail
 * browser of saved goodruns.
 *
 * Coverage:
 *   1. Empty state copy renders when records is [].
 *   2. Each row shows a date, symbol (uppercased), and composite.
 *   3. Click on row body fires onRestore with the full record.
 *   4. Click × fires onDelete with the id, NOT onRestore.
 *   5. Show-more reveals records beyond the 5-row collapsed view.
 *   6. Composite formatting handles null / NaN gracefully.
 */

import { describe, it, expect, vi } from "vitest";
import { render, fireEvent, screen } from "@testing-library/react";
import { SavedRunsPanel } from "../components/workstation/saved-runs-panel";
import type { GoodrunRecord } from "../lib/goodruns";

function makeRecord(id: string, overrides: Partial<GoodrunRecord> = {}): GoodrunRecord {
  return {
    id,
    saved_at: "2026-04-30T00:00:00.000Z",
    dataset: "stocks/spy/1d",
    horizon: 60,
    match_id: `${id}-m`,
    query: { start_idx: 0, end_idx: 1, start_date: null, end_date: null, values: [] },
    match: { start_idx: 0, end_idx: 1, start_date: null, end_date: null, values: [] },
    match_after_values: [],
    lens_breakdown: {} as GoodrunRecord["lens_breakdown"],
    composite: 0.84,
    note: null,
    ...overrides,
  };
}

describe("SavedRunsPanel — empty state", () => {
  it("renders empty-state copy when there are no records", () => {
    render(
      <SavedRunsPanel records={[]} onRestore={() => {}} onDelete={() => {}} />,
    );
    expect(screen.getByText(/save a run from the analog detail drawer/i)).toBeInTheDocument();
  });
});

describe("SavedRunsPanel — row rendering", () => {
  it("renders each row's symbol uppercased and composite to 2 decimals", () => {
    const records = [
      makeRecord("a", { dataset: "stocks/aapl/1d", composite: 0.871234 }),
      makeRecord("b", { dataset: "crypto/btc/1h", composite: 0.5 }),
    ];
    render(
      <SavedRunsPanel
        records={records}
        onRestore={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.getByText("0.87")).toBeInTheDocument();
    expect(screen.getByText("0.50")).toBeInTheDocument();
  });

  it("renders '—' when composite is null or non-finite", () => {
    render(
      <SavedRunsPanel
        records={[
          makeRecord("a", { composite: null }),
          makeRecord("b", { composite: Number.NaN }),
        ]}
        onRestore={() => {}}
        onDelete={() => {}}
      />,
    );
    // Two rows × one '—' each = at least two on the screen.
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });
});

describe("SavedRunsPanel — interactions", () => {
  it("clicking a row body fires onRestore with the full record", () => {
    const records = [makeRecord("rec-1")];
    const onRestore = vi.fn();
    render(
      <SavedRunsPanel
        records={records}
        onRestore={onRestore}
        onDelete={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("SPY").closest('[role="button"]')!);
    expect(onRestore).toHaveBeenCalledWith(records[0]);
  });

  it("clicking × fires onDelete and NOT onRestore", () => {
    const records = [makeRecord("rec-1")];
    const onRestore = vi.fn();
    const onDelete = vi.fn();
    render(
      <SavedRunsPanel
        records={records}
        onRestore={onRestore}
        onDelete={onDelete}
      />,
    );
    fireEvent.click(screen.getByLabelText("Forget saved run"));
    expect(onDelete).toHaveBeenCalledWith("rec-1");
    expect(onRestore).not.toHaveBeenCalled();
  });
});

describe("SavedRunsPanel — collapsed/expanded", () => {
  it("shows only 5 rows by default; show-more reveals the rest", () => {
    const records = Array.from({ length: 8 }, (_, i) =>
      makeRecord(`r-${i}`, { dataset: `stocks/sym${i}/1d` }),
    );
    render(
      <SavedRunsPanel
        records={records}
        onRestore={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("SYM0")).toBeInTheDocument();
    expect(screen.getByText("SYM4")).toBeInTheDocument();
    expect(screen.queryByText("SYM5")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(/show 3 more/));
    expect(screen.getByText("SYM5")).toBeInTheDocument();
    expect(screen.getByText("SYM7")).toBeInTheDocument();

    fireEvent.click(screen.getByText(/show fewer/));
    expect(screen.queryByText("SYM5")).not.toBeInTheDocument();
  });
});
