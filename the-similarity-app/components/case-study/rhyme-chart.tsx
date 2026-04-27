"use client";

/**
 * RhymeChart — purpose-built SVG chart for the SPY 2026 vs 2007 case study.
 *
 * Why a hand-rolled chart instead of the workstation's `LineChart`:
 *   The workstation chart is an analyst-shaped surface — interactive
 *   crosshair, multi-pane layout, lightweight-charts under the hood, etc.
 *   This page is presentation-shaped: two static lines, one optional
 *   continuation, an optional cone overlay, and a single peak marker.
 *   A ~250-line dedicated SVG component is faster to ship, faster to
 *   render (no chart-library bundle on this route), and lets the
 *   reveal animations stay declarative (just toggling `visible` props
 *   and CSS opacity, not driving an imperative chart API).
 *
 * Coordinate model:
 *   - Y axis is the normalized price (rebased to 100 at the window
 *     start). Bounds are computed once across all VISIBLE series so the
 *     present and analog charts share a y-scale when the consumer wants
 *     them visually comparable. The consumer passes `yDomain` to lock
 *     the bounds; otherwise the chart auto-fits to its own series.
 *   - X axis is the bar index, spanning the longest visible series.
 *     We do NOT use calendar dates on x — bar index keeps the two
 *     windows visually aligned even though they have different lengths.
 *
 * Animation lifecycle:
 *   - `pathLength` on each <path> animates from 0 to 1 when the series
 *     becomes visible. We don't actually use SVG path-length animation
 *     (which requires `getTotalLength` at runtime); instead we use a
 *     `clip-path: inset(...)` reveal driven by CSS keyframes. This is
 *     identical visually but works without any layout reads.
 *   - The continuation and cone are gated by `showContinuation` /
 *     `showCone` props so the page can stage the reveal independently
 *     of the main two series.
 *
 * Mutability boundary:
 *   - The component is pure-presentational. All inputs come in via
 *     props; no internal state, no refs that read the DOM. The only
 *     "state" is the CSS animation timeline, which the browser owns.
 */

import type { CSSProperties } from "react";

/** A single point on the case-study chart. Matches data.ts CaseStudyPoint
 *  but kept loose so any normalized series can be passed in. */
export interface RhymePoint {
  date: string;
  norm: number;
}

/** Optional forecast-cone overlay. Each element is one bar, with the
 *  P10/P50/P75 percentiles of the projected normalized path. The cone
 *  is rendered as two stacked translucent fills (P10..P75 and P25..P75)
 *  plus a P50 median line. */
export interface ConeBar {
  /** Bar index, anchored at the END of the present series (so 0 = the
   *  bar immediately after the present window). */
  t: number;
  p10: number;
  p25: number;
  p50: number;
  p75: number;
}

export interface RhymeChartProps {
  /** Primary series — always rendered. */
  primary: RhymePoint[];
  /** Optional secondary series (the analog). Rendered as a thinner
   *  line in the accent color when present. */
  secondary?: RhymePoint[];
  /** Optional continuation that extends `secondary` past its end.
   *  Hidden until `showContinuation` flips true. */
  continuation?: RhymePoint[];
  /** Optional projection cone. Rendered anchored at the right edge of
   *  the primary series. */
  cone?: ConeBar[];
  /** Stage flags — toggled by the page's IntersectionObserver. */
  showSecondary?: boolean;
  showContinuation?: boolean;
  showCone?: boolean;
  /** Locked y-axis bounds. When omitted, the chart auto-fits to all
   *  visible series. */
  yDomain?: [number, number];
  /** Optional caption rendered at the top-left of the chart frame. */
  caption?: string;
  /** Optional subtitle (e.g. date range). Renders smaller, beneath. */
  subtitle?: string;
  /** Optional className passthrough so the page can size the wrapper. */
  className?: string;
  /** Optional style passthrough. */
  style?: CSSProperties;
  /** Marker for a notable point on the secondary series (e.g. the
   *  2007-10-09 peak). The chart draws a small ring + label. */
  secondaryMarker?: { idx: number; label: string };
}

/* ----------------------------------------------------------------------
 *  Layout constants. Coordinates are in the SVG's intrinsic 1000x520
 *  viewBox; the wrapper scales the SVG to fit its container width while
 *  preserving aspect ratio. 1000 is wide enough that line-width 2 looks
 *  like a clean ~1px stroke at a 600px render and still readable on
 *  4k displays.
 * ---------------------------------------------------------------------- */
const VIEW_W = 1000;
const VIEW_H = 520;
const PAD_T = 56; // top padding leaves room for caption + grid label
const PAD_R = 40;
const PAD_B = 32; // bottom padding for x-axis labels (sparse)
const PAD_L = 56; // left padding for y-axis labels

/** Build a smoothly-rendered SVG path string from a series.
 *
 *  Uses simple line-to segments (no smoothing) — for ~180 daily bars at
 *  1000px render width the line is already smooth at the pixel level,
 *  and avoiding a Bezier smoother keeps the visual identical to the
 *  workstation's line chart (which doesn't smooth either). */
function pathFor(
  values: number[],
  xStart: number,
  xEnd: number,
  scaleY: (v: number) => number,
): string {
  if (values.length < 2) return "";
  const stepX = (xEnd - xStart) / (values.length - 1);
  const segs: string[] = [];
  for (let i = 0; i < values.length; i++) {
    const x = xStart + i * stepX;
    const y = scaleY(values[i]);
    segs.push(`${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`);
  }
  return segs.join(" ");
}

/** Build a closed area-fill path between two y-curves over the same x
 *  range. Used by the cone (P10..P75 outer band, P25..P75 inner band).
 *  Curves must have the same length; the function does not validate
 *  this beyond returning empty when either side is too short. */
function areaPath(
  upper: number[],
  lower: number[],
  xStart: number,
  xEnd: number,
  scaleY: (v: number) => number,
): string {
  if (upper.length < 2 || upper.length !== lower.length) return "";
  const stepX = (xEnd - xStart) / (upper.length - 1);
  const top: string[] = [];
  for (let i = 0; i < upper.length; i++) {
    const x = xStart + i * stepX;
    const y = scaleY(upper[i]);
    top.push(`${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`);
  }
  const bottom: string[] = [];
  for (let i = lower.length - 1; i >= 0; i--) {
    const x = xStart + i * stepX;
    const y = scaleY(lower[i]);
    bottom.push(`L${x.toFixed(2)},${y.toFixed(2)}`);
  }
  return `${top.join(" ")} ${bottom.join(" ")} Z`;
}

export function RhymeChart({
  primary,
  secondary,
  continuation,
  cone,
  showSecondary = true,
  showContinuation = false,
  showCone = false,
  yDomain,
  caption,
  subtitle,
  className,
  style,
  secondaryMarker,
}: RhymeChartProps) {
  // --------- y-domain calc ------------------------------------------------
  // The domain spans every series that is currently visible OR will be
  // visible by the time the page is fully scrolled. Locking it up front
  // (rather than recomputing as series fade in) prevents the y-axis from
  // jumping mid-reveal — which would re-scale every line and break the
  // visual rhyme.
  const yMin = (() => {
    if (yDomain) return yDomain[0];
    let min = Infinity;
    for (const p of primary) min = Math.min(min, p.norm);
    if (secondary) for (const p of secondary) min = Math.min(min, p.norm);
    if (continuation) for (const p of continuation) min = Math.min(min, p.norm);
    if (cone) for (const c of cone) min = Math.min(min, c.p10);
    return Number.isFinite(min) ? min : 0;
  })();
  const yMax = (() => {
    if (yDomain) return yDomain[1];
    let max = -Infinity;
    for (const p of primary) max = Math.max(max, p.norm);
    if (secondary) for (const p of secondary) max = Math.max(max, p.norm);
    if (continuation) for (const p of continuation) max = Math.max(max, p.norm);
    if (cone) for (const c of cone) max = Math.max(max, c.p75);
    return Number.isFinite(max) ? max : 100;
  })();

  // Pad the domain by ~5% so lines don't kiss the frame edge. Symmetric
  // padding keeps the visual mid-point predictable.
  const yRange = yMax - yMin;
  const yPad = yRange === 0 ? 1 : yRange * 0.08;
  const yLo = yMin - yPad;
  const yHi = yMax + yPad;

  const scaleY = (v: number) => {
    const t = (v - yLo) / (yHi - yLo);
    return PAD_T + (1 - t) * (VIEW_H - PAD_T - PAD_B);
  };

  // --------- x-domain calc ------------------------------------------------
  // The x-extent spans the longest series. The primary always anchors
  // the left half; secondary lines up alongside it from x=PAD_L; the
  // continuation extends past secondary's right edge.
  const primaryLen = primary.length;
  const secondaryLen = secondary?.length ?? 0;
  const continuationLen = continuation?.length ?? 0;
  const coneLen = cone?.length ?? 0;

  // Total x slots = max(primary, secondary + continuation, primary + cone).
  const totalSlots = Math.max(
    primaryLen,
    secondaryLen + continuationLen,
    primaryLen + coneLen,
  );
  const slotsForScale = Math.max(totalSlots - 1, 1);
  const xStart = PAD_L;
  const xEnd = VIEW_W - PAD_R;
  const slotW = (xEnd - xStart) / slotsForScale;

  // --------- gridlines ----------------------------------------------------
  // Pick 4 horizontal gridlines at "round" normalized levels (90, 100,
  // 110, etc) that fall within the domain. Round-y labels read better
  // than "108.34" on a presentation chart.
  const gridLevels: number[] = [];
  const step = (() => {
    const span = yHi - yLo;
    if (span > 50) return 20;
    if (span > 25) return 10;
    if (span > 12) return 5;
    return 2;
  })();
  const startLvl = Math.ceil(yLo / step) * step;
  for (let v = startLvl; v <= yHi; v += step) {
    gridLevels.push(Number(v.toFixed(2)));
  }

  // --------- path strings -------------------------------------------------
  const primaryValues = primary.map(p => p.norm);
  const primaryPath = pathFor(
    primaryValues,
    xStart,
    xStart + (primaryLen - 1) * slotW,
    scaleY,
  );

  const secondaryValues = (secondary ?? []).map(p => p.norm);
  const secondaryPath = pathFor(
    secondaryValues,
    xStart,
    xStart + (secondaryLen - 1) * slotW,
    scaleY,
  );

  const continuationValues = (continuation ?? []).map(p => p.norm);
  const continuationXStart = xStart + (secondaryLen - 1) * slotW;
  // Prepend secondary's last point so the continuation starts where
  // secondary ends. Without this the line would either disconnect or
  // would visually re-anchor at norm=100.
  const stitchedContinuation = (() => {
    if (!secondary || !continuation || continuation.length === 0) return [];
    const last = secondary[secondary.length - 1].norm;
    return [last, ...continuationValues];
  })();
  const continuationPath = pathFor(
    stitchedContinuation,
    continuationXStart,
    continuationXStart + continuationLen * slotW,
    scaleY,
  );

  // Cone overlay: anchored at the right edge of the present series.
  // The cone's t=0 sits at the present's last bar so the median line
  // visually emerges from the line tip.
  const conePath75 = (cone ?? []).map(c => c.p75);
  const conePath10 = (cone ?? []).map(c => c.p10);
  const conePath25 = (cone ?? []).map(c => c.p25);
  const conePath50 = (cone ?? []).map(c => c.p50);
  const coneXStart = xStart + (primaryLen - 1) * slotW;
  const coneXEnd = coneXStart + coneLen * slotW;
  // Stitch the present's last bar to the cone's first column so the
  // p50 line visually emerges from the line tip without a gap.
  const stitchedP50 = (() => {
    if (!cone || cone.length === 0 || primary.length === 0) return [];
    return [primary[primary.length - 1].norm, ...conePath50];
  })();
  const coneOuter =
    cone && cone.length >= 2
      ? areaPath(conePath75, conePath10, coneXStart, coneXEnd, scaleY)
      : "";
  const coneInner =
    cone && cone.length >= 2
      ? areaPath(conePath75, conePath25, coneXStart, coneXEnd, scaleY)
      : "";
  const coneMedian = pathFor(
    stitchedP50,
    coneXStart - slotW,
    coneXEnd,
    scaleY,
  );

  // Marker on the secondary (peak point) — a small ring + label.
  const marker = (() => {
    if (!secondary || !secondaryMarker) return null;
    const i = Math.max(0, Math.min(secondary.length - 1, secondaryMarker.idx));
    const x = xStart + i * slotW;
    const y = scaleY(secondary[i].norm);
    return { x, y, label: secondaryMarker.label };
  })();

  // X-axis date ticks — show first / middle / last of the primary,
  // plus the analog peak date if a marker is set. Sparse on purpose.
  const tickDates: { x: number; label: string }[] = [];
  if (primary.length > 0) {
    tickDates.push({ x: xStart, label: primary[0].date });
    const mid = Math.floor(primary.length / 2);
    tickDates.push({
      x: xStart + mid * slotW,
      label: primary[mid].date,
    });
    tickDates.push({
      x: xStart + (primaryLen - 1) * slotW,
      label: primary[primary.length - 1].date,
    });
  }

  return (
    <div className={`rhyme-chart ${className ?? ""}`} style={style}>
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={caption ?? "Case study chart"}
        className="rhyme-chart__svg"
      >
        {/* Caption + subtitle. Painted in SVG so they scale with the
            chart and don't need a separate HTML overlay element. */}
        {caption && (
          <text
            x={PAD_L}
            y={28}
            className="rhyme-chart__caption"
          >
            {caption}
          </text>
        )}
        {subtitle && (
          <text
            x={PAD_L}
            y={46}
            className="rhyme-chart__subtitle"
          >
            {subtitle}
          </text>
        )}

        {/* Gridlines — drawn beneath everything else. */}
        {gridLevels.map((lvl, i) => (
          <g key={`grid-${i}`}>
            <line
              x1={PAD_L}
              x2={VIEW_W - PAD_R}
              y1={scaleY(lvl)}
              y2={scaleY(lvl)}
              className="rhyme-chart__grid"
            />
            <text
              x={PAD_L - 8}
              y={scaleY(lvl) + 4}
              textAnchor="end"
              className="rhyme-chart__yaxis"
            >
              {lvl}
            </text>
          </g>
        ))}

        {/* Sparse x-axis tick labels. Date-formatted yyyy-mm to keep them
            short (the page caption already names the year). */}
        {tickDates.map((t, i) => (
          <text
            key={`xtick-${i}`}
            x={t.x}
            y={VIEW_H - 10}
            textAnchor={i === 0 ? "start" : i === tickDates.length - 1 ? "end" : "middle"}
            className="rhyme-chart__xaxis"
          >
            {t.label.slice(0, 7)}
          </text>
        ))}

        {/* Forecast cone (rendered first so lines paint on top). */}
        {cone && showCone && (
          <g className="rhyme-chart__cone">
            <path d={coneOuter} className="rhyme-chart__cone-outer" />
            <path d={coneInner} className="rhyme-chart__cone-inner" />
            <path
              d={coneMedian}
              fill="none"
              className="rhyme-chart__cone-median"
            />
          </g>
        )}

        {/* Secondary line (analog match). Drawn before primary so the
            primary line paints over it where they overlap. */}
        {secondary && (
          <g
            className={`rhyme-chart__line rhyme-chart__line--secondary ${
              showSecondary ? "is-visible" : ""
            }`}
          >
            <path d={secondaryPath} />
          </g>
        )}

        {/* Continuation (analog rolldown). */}
        {continuation && (
          <g
            className={`rhyme-chart__line rhyme-chart__line--continuation ${
              showContinuation ? "is-visible" : ""
            }`}
          >
            <path d={continuationPath} />
          </g>
        )}

        {/* Primary line (the "you are here" series). Always visible. */}
        <g className="rhyme-chart__line rhyme-chart__line--primary is-visible">
          <path d={primaryPath} />
        </g>

        {/* Optional marker on the secondary. */}
        {marker && showSecondary && (
          <g className="rhyme-chart__marker">
            <circle cx={marker.x} cy={marker.y} r="5" />
            <circle
              cx={marker.x}
              cy={marker.y}
              r="9"
              className="rhyme-chart__marker-ring"
            />
            <text
              x={marker.x + 12}
              y={marker.y - 8}
              className="rhyme-chart__marker-label"
            >
              {marker.label}
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
