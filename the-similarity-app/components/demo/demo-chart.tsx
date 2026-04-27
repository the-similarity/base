"use client";

/**
 * DemoChart — a polished, interactive demo of the workstation's chart.
 *
 * Reuses the REAL engine fallback (`SERIES` + `findAnalogs` + `buildCone`
 * from `lib/data.ts`) that the workstation uses when the API is offline.
 * The 7,500-bar synthetic SPY-style series is the source of truth; the
 * same 9-lens `findAnalogs` algorithm picks the historical analog live
 * on every window change.
 *
 * Interactivity:
 *   - The query window is draggable (grab anywhere inside the window box)
 *     and resizable (left/right handles). Interaction is wired through
 *     the underlying LineChart's built-in pointer handlers.
 *   - As the user moves or resizes the window, the analog match and
 *     forecast cone re-run against the actual engine and re-render.
 *     `useDeferredValue` keeps the window box itself tracking the mouse
 *     at full speed while React schedules the expensive analog
 *     recompute at lower priority — drag stays silky and the overlay
 *     catches up as soon as the user pauses or slows.
 *
 * No search button. No "computing" / engine-status UI. No lens bars or
 * drawer. The component just needs a height.
 */

import { useDeferredValue, useMemo, useState } from "react";
import {
  SERIES,
  findAnalogs,
  type AnalogMatch,
  type DataPoint,
} from "../../lib/data";
import { LineChart, type AnalogOverlay } from "../workstation/line-chart";

/*
 * Date-aligned copy of SERIES.
 *
 * The module-level SERIES starts at 1995-01-03 and runs 7,500 daily bars,
 * which means the last bar lands around mid-2015 - a detail that reads as
 * a calendar bug when the chart labels its final bar "TODAY" on an
 * investor landing in 2026. We produce a shallow copy that shifts every
 * .d / .t field so the final bar sits on today's date; prices and log
 * returns are untouched. findAnalogs still operates against the original
 * SERIES (by-index, date-independent) so scoring is unaffected.
 *
 * Computed once per module load. Uses a fixed `todayAtLoad` anchor so
 * the displayed dates don't tick during a session.
 */
const DAY_MS = 86400000;
const todayAtLoad = new Date();
const DISPLAY_SERIES: DataPoint[] = SERIES.map((pt, i) => {
  const d = new Date(
    todayAtLoad.getTime() - (SERIES.length - 1 - i) * DAY_MS,
  );
  return { ...pt, d, t: d.getTime() };
});

/*
 * Module-level window-length sweep to pick a STRONG starting pose.
 *
 * The initial window ends at the last real bar in SERIES so the forecast
 * region projects into genuine empty future space — the "this is now,
 * what happens next?" narrative. We try a handful of window widths and
 * keep the one whose top-1 match composite is highest; that first
 * impression sets the tone before the user touches anything.
 *
 * Cost: five findAnalogs calls at module load, deterministic, cached.
 */
const WINDOW_OPTIONS = [30, 40, 50, 60, 80];
const MIN_WINDOW = 20;
const MAX_WINDOW = 100;
// Fixed horizon allowance for the camera — SERIES.length + HORIZON_PAD
// gives the cone and analog forward paths room to draw into synthesized
// future space regardless of the window length the user picks.
const HORIZON_PAD = 100;

function pickBestInitial(): {
  queryStart: number;
  windowLen: number;
  analogs: AnalogMatch[];
} {
  const N = SERIES.length;
  let bestLen = 60;
  let bestStart = N - bestLen;
  let bestComposite = -Infinity;
  let bestAnalogs: AnalogMatch[] = [];
  for (const windowLen of WINDOW_OPTIONS) {
    const horizon = windowLen;
    const queryStart = N - windowLen;
    if (queryStart - windowLen - horizon <= 200) continue;
    const a = findAnalogs(queryStart, windowLen, { k: 1, horizon });
    if (a[0] && a[0].composite > bestComposite) {
      bestComposite = a[0].composite;
      bestStart = queryStart;
      bestLen = windowLen;
      bestAnalogs = a;
    }
  }
  return { queryStart: bestStart, windowLen: bestLen, analogs: bestAnalogs };
}

const INITIAL = pickBestInitial();

/*
 * Fixed left edge of the camera. Runway for the user to drag the window
 * left without it clipping against the chart edge. Kept static so early
 * history doesn't reflow horizontally while the user interacts.
 */
const VIEW_START = Math.max(0, INITIAL.queryStart - Math.floor(INITIAL.windowLen * 3.5));

export interface DemoChartProps {
  /** Height of the chart body in px. Default 360 for the standalone /demo
   *  page. Home-page embed uses a smaller height. */
  height?: number;
  /** Optional subtitle override. */
  sub?: string;
  /** Optional title override. */
  title?: string;
}

/**
 * Renders a chart-card (same structure as the workstation) around the
 * real LineChart component. Users can drag and resize the query window
 * to make the engine re-run against a different slice of history.
 */
export function DemoChart({ height = 360, title, sub }: DemoChartProps) {
  // Query window state. LineChart's internal drag handlers clamp:
  //   - start ≥ viewStart + 1
  //   - start + len ≤ series.length
  //   - len ≥ 20 (the chart enforces MIN_WINDOW as 20 internally)
  // so we don't need additional guards here; we just accept whatever
  // LineChart hands back through onWindowChange.
  const [win, setWin] = useState<{ start: number; len: number }>({
    start: INITIAL.queryStart,
    len: INITIAL.windowLen,
  });

  /*
   * Defer the analog + cone recompute so it runs at LOWER priority than
   * the window box rerender. During a fast drag, React keeps `win`
   * updating at 60fps (the SVG window rect follows the cursor) while
   * `deferredWin` lags behind — once the user pauses or slows, React
   * flushes the deferred update and `findAnalogs` runs against the
   * latest position. End result: the window glides under the cursor,
   * the overlay snaps into place a beat later. No jank, no thrashing.
   */
  const deferredWin = useDeferredValue(win);

  const { overlays, matchScore } = useMemo(() => {
    // Horizon tracks window length so the forecast spans the same forward
    // distance the window reached back - standard workstation convention.
    const horizon = deferredWin.len;
    // findAnalogs requires queryStart - windowLen - horizon > 200; if the
    // user has dragged the window far enough left that there's no room to
    // score against, we drop the overlay rather than crashing.
    if (deferredWin.start - deferredWin.len - horizon <= 200) {
      return { overlays: [] as AnalogOverlay[], matchScore: 0 };
    }
    const analogs = findAnalogs(deferredWin.start, deferredWin.len, {
      k: 1,
      horizon,
    });
    const overlaysOut: AnalogOverlay[] = analogs.map((a, i) => ({
      id: a.id,
      priceWindow: a.priceWindow,
      after: a.after,
      pinned: false,
      composite: a.composite,
      rank: i,
    }));
    return {
      overlays: overlaysOut,
      matchScore: analogs[0]?.composite ?? 0,
    };
  }, [deferredWin.start, deferredWin.len]);

  // Staleness signal: true while the user's live `win` has diverged from
  // the `deferredWin` the overlay was last computed for. Drives a tiny
  // subtitle hint so the viewer knows the match is catching up, not
  // missing. Tab is cleared the moment the deferred state syncs back.
  const syncing = win.start !== deferredWin.start || win.len !== deferredWin.len;

  const resolvedTitle = title ?? "SPY · daily";
  const resolvedSub =
    sub ??
    (syncing
      ? `${SERIES.length.toLocaleString()} bars · matching…`
      : `${SERIES.length.toLocaleString()} bars · match ${matchScore.toFixed(2)} · drag to explore`);

  return (
    <div className="chart-card demo-chart">
      <div className="chart-card__head">
        <div className="chart-card__title">
          <span className="t">{resolvedTitle}</span>
          <span className="sub">{resolvedSub}</span>
        </div>
        <div className="chart-card__legend">
          <span className="legend-dot"><i />Query</span>
          <span className="legend-dot analog"><i />Analog</span>
        </div>
      </div>
      <div className="chart-card__body" style={{ position: "relative" }}>
        <LineChart
          series={DISPLAY_SERIES}
          viewStart={VIEW_START}
          // Right edge of the camera tracks the deferred window length
          // plus a small breathing buffer. Keeps the gap between "today"
          // and the right edge tight regardless of how the user resizes
          // the window, instead of a fixed pad that left the tail empty
          // for small windows.
          viewEnd={SERIES.length + deferredWin.len + 4}
          window={win}
          // Real window-change handler - drives the full interaction. The
          // chart's built-in drag + resize handlers call this on every
          // pointer-move tick while the user is dragging.
          onWindowChange={(next) => {
            // Clamp the window length defensively - the chart enforces a
            // min of 20 internally but making the bound explicit here
            // protects us against future chart refactors.
            const len = Math.max(MIN_WINDOW, Math.min(MAX_WINDOW, next.len));
            setWin({ start: next.start, len });
          }}
          analogsOverlay={overlays}
          // Forecast horizon tracks the deferred window length so the
          // rendered forward region matches the overlay we computed. If
          // we used the live `win.len` here, a fast drag would render
          // further than the overlay array actually extends, producing a
          // transient visual gap.
          forecastHorizon={deferredWin.len}
          height={height}
          // Cone + median hidden per design - the analog line itself is
          // the story post-query ("what rhymed last time did X"), not
          // the P10-P90 envelope.
          showCone={false}
          showMedian={false}
          showWindow
        />
      </div>
    </div>
  );
}
