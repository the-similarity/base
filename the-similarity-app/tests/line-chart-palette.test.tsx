/**
 * Tests for the multi-analog palette + hover preview + rank-badge
 * rendering in the SVG LineChart (Fast view).
 *
 * What we assert:
 *   1. With N analogs and no pins, each rendered analog <path> has a
 *      distinct `data-rank` attribute 0..N-1 AND carries its own inline
 *      stroke color (— the palette CSS var, NOT the single
 *      --c-analog token). This is the "is it only showing top 1?"
 *      regression guard.
 *   2. Hovered analog (via `hoveredAnalogId` prop) is rendered with a
 *      heavier stroke-width inline style. No other analog is.
 *   3. Rank badges (`<g class="analog-badge" data-rank="N">`) render
 *      one per visible analog when no pins are set, and are SUPPRESSED
 *      when any pin is active (pin mode replaces palette emphasis).
 *   4. With a pin set, palette inline styles DO NOT apply — the path
 *      falls back to the .strong/.context className only.
 *
 * These tests are the contract between the card strip and the chart.
 * If they fail, the visual distinction between analogs is broken and
 * the product regresses to the "single smear" problem.
 */
import { describe, it, expect, beforeAll } from "vitest";
import { render } from "@testing-library/react";
import { LineChart, type AnalogOverlay } from "../components/workstation/line-chart";
import type { DataPoint } from "../lib/data";

// jsdom (the vitest environment) does not ship a ResizeObserver. The
// LineChart component observes its wrapping <div> to reflow the SVG
// viewBox on container-width changes; for the test we stub a no-op so
// the mount does not throw. The observer never needs to fire — the
// component falls back to the default 800px width which is fine for
// attribute assertions.
beforeAll(() => {
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
});

/** Synthesize a deterministic daily price series for the fixture. */
function makeSeries(n = 200): DataPoint[] {
  const out: DataPoint[] = [];
  const t0 = new Date(2026, 0, 1).getTime();
  let prev = 100;
  for (let i = 0; i < n; i++) {
    const p = 100 + Math.sin(i / 10) * 5 + i * 0.02;
    const t = t0 + i * 86400000;
    const r = i === 0 ? 0 : Math.log(p / prev);
    out.push({
      t,
      d: new Date(t),
      p,
      r,
    });
    prev = p;
  }
  return out;
}

/**
 * Build a synthetic analog overlay anchored at the query end. `priceWindow`
 * ends at the series' price at `qEnd`, and `after` extends forward by
 * `afterFactor` bumps so each analog diverges slightly.
 */
function makeOverlay(
  series: DataPoint[],
  qEnd: number,
  id: string,
  afterFactor: number,
  pinned = false,
): AnalogOverlay {
  const priceWindow = series.slice(qEnd - 30, qEnd + 1).map(d => d.p);
  const last = priceWindow[priceWindow.length - 1];
  const after = Array.from({ length: 30 }, (_, k) => last * (1 + afterFactor * (k + 1) / 30));
  return {
    id,
    priceWindow,
    after,
    pinned,
    composite: 0.9,
  };
}

describe("LineChart multi-analog palette", () => {
  const series = makeSeries();
  const windowState = { start: 120, len: 40 };
  const qEnd = windowState.start + windowState.len - 1;

  it("renders each analog with a distinct data-rank and its own inline stroke", () => {
    const analogs: AnalogOverlay[] = [
      makeOverlay(series, qEnd, "a", 0.05),
      makeOverlay(series, qEnd, "b", 0.10),
      makeOverlay(series, qEnd, "c", 0.15),
      makeOverlay(series, qEnd, "d", -0.05),
    ];
    const { container } = render(
      <LineChart
        series={series}
        viewStart={0}
        viewEnd={series.length}
        window={windowState}
        onWindowChange={() => {}}
        analogsOverlay={analogs}
      />,
    );
    const analogPaths = container.querySelectorAll("path.analog");
    expect(analogPaths.length).toBe(4);
    // data-rank is 0..3, unique.
    const ranks = Array.from(analogPaths).map(p => p.getAttribute("data-rank"));
    expect(new Set(ranks).size).toBe(4);
    // Each path must have an inline stroke referencing a distinct
    // palette variable. The raw `style` attribute carries
    // stroke: var(--c-analog-N) for N=1..4. The CSSStyleDeclaration
    // only resolves computed values in jsdom, so we check the raw
    // attribute text instead.
    const strokes = Array.from(analogPaths).map(p => p.getAttribute("style") || "");
    expect(strokes[0]).toContain("--c-analog-1");
    expect(strokes[1]).toContain("--c-analog-2");
    expect(strokes[2]).toContain("--c-analog-3");
    expect(strokes[3]).toContain("--c-analog-4");
  });

  it("renders one rank badge per analog when no pins are active", () => {
    const analogs: AnalogOverlay[] = [
      makeOverlay(series, qEnd, "a", 0.05),
      makeOverlay(series, qEnd, "b", 0.10),
      makeOverlay(series, qEnd, "c", 0.15),
    ];
    const { container } = render(
      <LineChart
        series={series}
        viewStart={0}
        viewEnd={series.length}
        window={windowState}
        onWindowChange={() => {}}
        analogsOverlay={analogs}
      />,
    );
    const badges = container.querySelectorAll("g.analog-badge");
    expect(badges.length).toBe(3);
    // Each badge has a numeral 1..3.
    const labels = Array.from(badges).map(g => g.querySelector("text")?.textContent);
    expect(labels).toEqual(["1", "2", "3"]);
  });

  it("suppresses rank badges when at least one analog is pinned", () => {
    const analogs: AnalogOverlay[] = [
      makeOverlay(series, qEnd, "a", 0.05, true),
      makeOverlay(series, qEnd, "b", 0.10),
      makeOverlay(series, qEnd, "c", 0.15),
    ];
    const { container } = render(
      <LineChart
        series={series}
        viewStart={0}
        viewEnd={series.length}
        window={windowState}
        onWindowChange={() => {}}
        analogsOverlay={analogs}
      />,
    );
    const badges = container.querySelectorAll("g.analog-badge");
    expect(badges.length).toBe(0);
  });

  it("palette inline stroke does NOT apply when a pin is active", () => {
    const analogs: AnalogOverlay[] = [
      makeOverlay(series, qEnd, "a", 0.05, true),
      makeOverlay(series, qEnd, "b", 0.10),
    ];
    const { container } = render(
      <LineChart
        series={series}
        viewStart={0}
        viewEnd={series.length}
        window={windowState}
        onWindowChange={() => {}}
        analogsOverlay={analogs}
      />,
    );
    const paths = container.querySelectorAll("path.analog");
    // The pinned path gets .strong, the unpinned path gets .context.
    // Neither should carry an inline --c-analog-N stroke because pin
    // mode defers to the CSS classes.
    for (const p of Array.from(paths)) {
      const style = p.getAttribute("style") || "";
      expect(style).not.toContain("--c-analog-");
    }
    // Sanity: class names are wired as expected.
    expect(paths[0].getAttribute("class")).toContain("strong");
    expect(paths[1].getAttribute("class")).toContain("context");
  });

  it("hovered analog gets a heavier stroke-width than its siblings", () => {
    const analogs: AnalogOverlay[] = [
      makeOverlay(series, qEnd, "a", 0.05),
      makeOverlay(series, qEnd, "hovered", 0.10),
      makeOverlay(series, qEnd, "c", 0.15),
    ];
    const { container } = render(
      <LineChart
        series={series}
        viewStart={0}
        viewEnd={series.length}
        window={windowState}
        onWindowChange={() => {}}
        analogsOverlay={analogs}
        hoveredAnalogId="hovered"
      />,
    );
    const paths = container.querySelectorAll("path.analog");
    // Extract the stroke-width inline style value for each path.
    const widths = Array.from(paths).map(p => {
      const style = p.getAttribute("style") || "";
      const m = style.match(/stroke-width:\s*([\d.]+)/);
      return m ? parseFloat(m[1]) : NaN;
    });
    // The hovered analog (id="hovered", index 1) must have the largest
    // stroke-width (2.0 by contract); siblings at index 0 and 2 are on
    // the ramp (1.5 and 1.1 respectively).
    expect(widths[1]).toBeGreaterThan(widths[0]);
    expect(widths[1]).toBeGreaterThan(widths[2]);
    expect(widths[1]).toBeCloseTo(2.0, 5);
  });
});
