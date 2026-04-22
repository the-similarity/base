import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import {
  AnalogDetailDrawer,
  regimeLabelFor,
} from "../components/workstation/analog-detail-drawer";
import type { AnalogMatch, LensScores } from "../lib/data";

afterEach(cleanup);

/*
 * Tests for AnalogDetailDrawer.
 *
 * Scope:
 *   - regimeLabelFor: the pure heuristic that labels dates. Known-regime
 *     dates land on their curated label; off-list dates fall back to
 *     "Q{n} YYYY"; bad inputs return "" (so the caller can skip render).
 *   - Component: drawer renders rank badge + date range + composite when
 *     open + analog supplied. Pin toggle + close wire to props.
 *     data-open reflects the open prop (drives the CSS transform).
 *     "Find similar analogs" calls onUseAsQuery with the analog.
 */

const ZERO_LENSES: LensScores = {
  lens1: 0.9,
  lens2: 0.8,
  lens3: 0.75, // top-3 cutoff should include lens1, lens2, lens3
  lens4: 0.1,
  lens5: 0.2,
  lens6: 0.15,
  lens7: 0.05,
  lens8: 0.0,
  lens9: 0.3,
};

function makeAnalog(overrides: Partial<AnalogMatch> = {}): AnalogMatch {
  return {
    id: "A1",
    rank: 1,
    startIdx: 100,
    // Date inside the curated COVID regime window so the context strip
    // renders that label (asserted below).
    date: new Date("2020-03-20"),
    endDate: new Date("2020-11-08"),
    label: "Summer 2020",
    composite: 0.72,
    lenses: ZERO_LENSES,
    priceWindow: Array.from({ length: 40 }, (_, i) => 90 + i),
    after: Array.from({ length: 60 }, (_, i) => 130 + i * 0.5),
    afterReturn: 0.08,
    note: "strong shape alignment",
    ...overrides,
  };
}

describe("regimeLabelFor", () => {
  it("labels known regime dates with the curated label", () => {
    const covid = new Date("2020-03-20");
    expect(regimeLabelFor(covid)).toMatch(/COVID/);
  });

  it("labels 2008 GFC dates", () => {
    const gfc = new Date("2008-10-15");
    expect(regimeLabelFor(gfc)).toMatch(/Financial Crisis/);
  });

  it("falls back to Q{n} YYYY for off-list dates", () => {
    // April 2013 — well outside any curated regime.
    const off = new Date("2013-04-15");
    expect(regimeLabelFor(off)).toBe("Q2 2013");
  });

  it("returns '' for invalid dates so callers can skip rendering", () => {
    expect(regimeLabelFor(new Date("not-a-date"))).toBe("");
  });
});

describe("AnalogDetailDrawer", () => {
  it("renders with data-open=false when closed", () => {
    const { container } = render(
      <AnalogDetailDrawer
        analog={null}
        open={false}
        pinned={false}
        onClose={() => {}}
        onTogglePin={() => {}}
        onUseAsQuery={() => {}}
      />,
    );
    const aside = container.querySelector(".adrawer");
    expect(aside?.getAttribute("data-open")).toBe("false");
  });

  it("renders rank badge, date range, and composite when open with an analog", () => {
    render(
      <AnalogDetailDrawer
        analog={makeAnalog()}
        open={true}
        pinned={false}
        onClose={() => {}}
        onTogglePin={() => {}}
        onUseAsQuery={() => {}}
      />,
    );
    // Rank badge.
    expect(screen.getByText("#1")).toBeDefined();
    // Composite formatted to 2dp.
    expect(screen.getByText("0.72")).toBeDefined();
    // Context strip labels covid-era dates.
    expect(screen.getByText(/COVID/)).toBeDefined();
  });

  it("fires onTogglePin with the analog id when the pin toggle is clicked", () => {
    const onTogglePin = vi.fn();
    render(
      <AnalogDetailDrawer
        analog={makeAnalog({ id: "custom-id" })}
        open={true}
        pinned={false}
        onClose={() => {}}
        onTogglePin={onTogglePin}
        onUseAsQuery={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Pin this analog$/i }));
    expect(onTogglePin).toHaveBeenCalledWith("custom-id");
  });

  it("fires onClose when the close button is clicked", () => {
    const onClose = vi.fn();
    render(
      <AnalogDetailDrawer
        analog={makeAnalog()}
        open={true}
        pinned={false}
        onClose={onClose}
        onTogglePin={() => {}}
        onUseAsQuery={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /close analog detail drawer/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("fires onUseAsQuery with the analog when 'Find similar analogs' is clicked", () => {
    const onUseAsQuery = vi.fn();
    const a = makeAnalog();
    render(
      <AnalogDetailDrawer
        analog={a}
        open={true}
        pinned={false}
        onClose={() => {}}
        onTogglePin={() => {}}
        onUseAsQuery={onUseAsQuery}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /find similar analogs/i }));
    expect(onUseAsQuery).toHaveBeenCalledWith(a);
  });

  it("renders 9 lens rows when open with an analog", () => {
    const { container } = render(
      <AnalogDetailDrawer
        analog={makeAnalog()}
        open={true}
        pinned={false}
        onClose={() => {}}
        onTogglePin={() => {}}
        onUseAsQuery={() => {}}
      />,
    );
    expect(container.querySelectorAll(".adrawer__lens-row").length).toBe(9);
    // Top-3 marker: the three rows with top score should have data-top=true.
    const topRows = container.querySelectorAll('.adrawer__lens-row[data-top="true"]');
    expect(topRows.length).toBe(3);
  });

  it("reflects the pinned prop in the toggle label", () => {
    render(
      <AnalogDetailDrawer
        analog={makeAnalog()}
        open={true}
        pinned={true}
        onClose={() => {}}
        onTogglePin={() => {}}
        onUseAsQuery={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /^Unpin this analog$/i })).toBeDefined();
  });
});
