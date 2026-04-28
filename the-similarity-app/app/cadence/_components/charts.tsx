/**
 * Cadence — pure-SVG chart primitives.
 *
 * No third-party chart library. Everything is hand-rolled SVG paths so the
 * page can layer multiple chart types in tight cards without bringing in
 * recharts/visx/d3. Each component is self-contained and stateless; pass
 * fresh data each render and React will reconcile via the path `d` strings.
 *
 * Performance: paths are built once per render with O(n) string ops where
 * n = data.length (≤ 365). For lists of sparklines the caller renders
 * many <Sparkline> instances — keep `data` references stable across
 * renders to let React's reconciler skip re-paints.
 *
 * Accessibility note: charts are decorative rather than primary content
 * here. Tooltips on the heatmap use the native <title> attribute so screen
 * readers can read totals; line/area charts have no ARIA wrap because the
 * neighboring KPI text states the same numbers.
 *
 * Components:
 *   - Sparkline       — small inline trend line, optional fill + dot
 *   - DayTrajectory   — today's HR over 24h with overlay (used by /today)
 *   - ForecastCone    — line + p10/p90 fan area for /rhymes
 *   - LabTrend        — 5-point lab trendline with optimal range band (/labs)
 *   - Ring            — single progress arc (used by Today recovery hero)
 *
 * RhymeHeatmap, TagDonut, ThreadRibbon, ChannelMini, PolarCycle, and the
 * inner Donut primitive were removed in the slop cut along with the
 * screens / sections that consumed them.
 */

import { type ReactNode } from "react";

import type { ForecastPoint } from "../engine";

// =====================================================================
// Sparkline — small inline trend line, optionally filled, with end dot.
// =====================================================================

export interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  stroke?: string;
  fill?: boolean;
  smooth?: boolean;
  dot?: boolean;
}

export function Sparkline({
  data,
  width = 120,
  height = 36,
  stroke = "currentColor",
  fill = true,
  smooth = true,
  dot = true,
}: SparklineProps) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const stepX = width / (data.length - 1);
  // Compute pixel coords with a 2px top/bottom inset so the stroke doesn't
  // clip at the SVG edge.
  const pts: [number, number][] = data.map((v, i) => [
    i * stepX,
    height - 2 - ((v - min) / range) * (height - 4),
  ]);
  let d = "";
  if (smooth) {
    // Mid-segment Bezier control points yield a soft monotone-ish curve
    // without overshooting the data range.
    d = `M ${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length; i++) {
      const [px, py] = pts[i - 1];
      const [x, y] = pts[i];
      const cx = (px + x) / 2;
      d += ` C ${cx} ${py}, ${cx} ${y}, ${x} ${y}`;
    }
  } else {
    d = "M " + pts.map((p) => p.join(" ")).join(" L ");
  }
  // Closed polygon back along the baseline so the area below the curve
  // can be filled.
  const fillD =
    d + ` L ${pts[pts.length - 1][0]} ${height} L ${pts[0][0]} ${height} Z`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      {fill && <path className="cadence-fill" d={fillD} fill={stroke} fillOpacity="0.10" />}
      <path
        className="cadence-line"
        d={d}
        stroke={stroke}
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {dot && (
        <circle
          cx={pts[pts.length - 1][0]}
          cy={pts[pts.length - 1][1]}
          r="2.5"
          fill={stroke}
        />
      )}
    </svg>
  );
}

// =====================================================================
// DayTrajectory — today's HR series with up to 3 compare overlays.
// =====================================================================
//
// The Today screen's hero chart. Renders the primary series (today's HR
// across 24h) as a filled area, plus optional dashed overlay lines for
// "yesterday", "rhyming day", and "baseline". Y axis spans 40-110 bpm.

export interface OverlaySeries {
  key: string;
  label: string;
  data: number[];
  color: string;
  dashed?: boolean;
}

export interface DayTrajectoryProps {
  primary: number[];
  primaryLabel: string;
  primaryColor: string;
  overlays?: OverlaySeries[];
  height?: number;
  yMin?: number;
  yMax?: number;
}

export function DayTrajectory({
  primary,
  primaryLabel,
  primaryColor,
  overlays = [],
  height = 220,
  yMin = 45,
  yMax = 110,
}: DayTrajectoryProps) {
  const W = 800;
  const H = height;
  const P = { l: 38, r: 12, t: 16, b: 24 };
  const xStep = (W - P.l - P.r) / (primary.length - 1);
  const yScale = (v: number) =>
    P.t + (1 - (v - yMin) / (yMax - yMin)) * (H - P.t - P.b);
  const ptsFor = (arr: number[]): [number, number][] =>
    arr.map((v, i) => [P.l + i * xStep, yScale(v)]);
  const buildPath = (pts: [number, number][]): string => {
    let d = `M ${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length; i++) {
      const [px, py] = pts[i - 1];
      const [x, y] = pts[i];
      const cx = (px + x) / 2;
      d += ` C ${cx} ${py}, ${cx} ${y}, ${x} ${y}`;
    }
    return d;
  };
  const ppts = ptsFor(primary);
  const ppath = buildPath(ppts);
  const fillPath =
    ppath + ` L ${ppts[ppts.length - 1][0]} ${H - P.b} L ${ppts[0][0]} ${H - P.b} Z`;
  const ticks = 4;
  const ys = Array.from(
    { length: ticks + 1 },
    (_, i) => yMin + (i / ticks) * (yMax - yMin)
  );

  // X ticks at every 3 hours so the axis isn't crowded.
  const xticks = primary.map((_, h) => h).filter((h) => h % 3 === 0);

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      style={{ width: "100%", height: H, overflow: "visible" }}
    >
      <defs>
        <linearGradient id="cadence-traj-grad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={primaryColor} stopOpacity="0.22" />
          <stop offset="100%" stopColor={primaryColor} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* horizontal grid */}
      {ys.map((y, i) => (
        <g key={i}>
          <line
            x1={P.l}
            x2={W - P.r}
            y1={yScale(y)}
            y2={yScale(y)}
            stroke="#ececea"
            strokeDasharray={i === 0 ? "0" : "2,4"}
          />
          <text
            x={P.l - 6}
            y={yScale(y) + 3}
            fontSize="10"
            fill="#8a8a86"
            textAnchor="end"
            fontFamily="JetBrains Mono"
          >
            {Math.round(y)}
          </text>
        </g>
      ))}
      {/* x ticks */}
      {xticks.map((h) => (
        <text
          key={h}
          x={P.l + h * xStep}
          y={H - 8}
          fontSize="10"
          fill="#8a8a86"
          textAnchor="middle"
          fontFamily="JetBrains Mono"
        >
          {h.toString().padStart(2, "0")}
        </text>
      ))}
      {/* overlays first so primary stays on top */}
      {overlays.map((o) => {
        const opts = ptsFor(o.data);
        const op = buildPath(opts);
        return (
          <path
            key={o.key}
            d={op}
            fill="none"
            stroke={o.color}
            strokeWidth="1.25"
            strokeOpacity="0.7"
            strokeDasharray={o.dashed ? "4 3" : undefined}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        );
      })}
      {/* primary fill + line */}
      <path d={fillPath} fill="url(#cadence-traj-grad)" />
      <path
        d={ppath}
        fill="none"
        stroke={primaryColor}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx={ppts[ppts.length - 1][0]}
        cy={ppts[ppts.length - 1][1]}
        r="4"
        fill={primaryColor}
        stroke="#fff"
        strokeWidth="2"
      />
      {/* primary label tucked top-left */}
      <text
        x={P.l + 4}
        y={P.t + 12}
        fontSize="11"
        fill={primaryColor}
        fontFamily="Inter"
        fontWeight="600"
      >
        {primaryLabel}
      </text>
    </svg>
  );
}

// =====================================================================
// ForecastCone — line (median) + p10/p90 fan area for /rhymes.
// =====================================================================

export interface ForecastConeProps {
  cone: ForecastPoint[];
  height?: number;
  color?: string;
  yMin?: number;
  yMax?: number;
  /** Optional anchor point at day 0 (today's value). */
  anchor?: number;
}

export function ForecastCone({
  cone,
  height = 200,
  color = "#5b8a72",
  yMin = 30,
  yMax = 90,
  anchor,
}: ForecastConeProps) {
  if (!cone.length) return null;
  const W = 800;
  const H = height;
  const P = { l: 38, r: 14, t: 18, b: 28 };

  // x indices: include anchor at day 0 if provided
  const allDays = anchor !== undefined ? [0, ...cone.map((p) => p.day)] : cone.map((p) => p.day);
  const allMedian = anchor !== undefined ? [anchor, ...cone.map((p) => p.median)] : cone.map((p) => p.median);
  const allP10 = anchor !== undefined ? [anchor, ...cone.map((p) => p.p10)] : cone.map((p) => p.p10);
  const allP90 = anchor !== undefined ? [anchor, ...cone.map((p) => p.p90)] : cone.map((p) => p.p90);

  const xMin = allDays[0];
  const xMax = allDays[allDays.length - 1];
  const xScale = (d: number) => P.l + ((d - xMin) / (xMax - xMin)) * (W - P.l - P.r);
  const yScale = (v: number) => P.t + (1 - (v - yMin) / (yMax - yMin)) * (H - P.t - P.b);

  const buildPath = (vs: number[]): string => {
    const pts = vs.map((v, i) => [xScale(allDays[i]), yScale(v)] as [number, number]);
    let d = `M ${pts[0][0]} ${pts[0][1]}`;
    for (let i = 1; i < pts.length; i++) {
      const [px, py] = pts[i - 1];
      const [x, y] = pts[i];
      const cx = (px + x) / 2;
      d += ` C ${cx} ${py}, ${cx} ${y}, ${x} ${y}`;
    }
    return d;
  };
  const medianPath = buildPath(allMedian);
  const p90Path = buildPath(allP90);
  const p10Path = buildPath(allP10);
  // Cone fill: p90 forward + p10 backward
  const conePath = (() => {
    const top = allP90.map((v, i) => [xScale(allDays[i]), yScale(v)] as [number, number]);
    const bot = allP10.map((v, i) => [xScale(allDays[i]), yScale(v)] as [number, number]).reverse();
    let d = `M ${top[0][0]} ${top[0][1]}`;
    for (let i = 1; i < top.length; i++) d += ` L ${top[i][0]} ${top[i][1]}`;
    for (const [x, y] of bot) d += ` L ${x} ${y}`;
    return d + " Z";
  })();
  const yticks = 4;
  const ys = Array.from({ length: yticks + 1 }, (_, i) => yMin + (i / yticks) * (yMax - yMin));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: H }}>
      {/* Y grid */}
      {ys.map((y, i) => (
        <g key={i}>
          <line x1={P.l} x2={W - P.r} y1={yScale(y)} y2={yScale(y)} stroke="#ececea" strokeDasharray={i === 0 ? "0" : "2,4"} />
          <text x={P.l - 6} y={yScale(y) + 3} fontSize="10" fill="#8a8a86" textAnchor="end" fontFamily="JetBrains Mono">
            {Math.round(y)}
          </text>
        </g>
      ))}
      {/* X ticks every 2 days */}
      {allDays.map((d, i) =>
        d % 2 === 0 ? (
          <text key={i} x={xScale(d)} y={H - 10} fontSize="10" fill="#8a8a86" textAnchor="middle" fontFamily="JetBrains Mono">
            {d === 0 ? "now" : `+${d}d`}
          </text>
        ) : null
      )}
      {/* Cone */}
      <path d={conePath} fill={color} fillOpacity="0.14" />
      <path d={p90Path} fill="none" stroke={color} strokeOpacity="0.4" strokeWidth="1" strokeDasharray="3 3" />
      <path d={p10Path} fill="none" stroke={color} strokeOpacity="0.4" strokeWidth="1" strokeDasharray="3 3" />
      {/* Median */}
      <path d={medianPath} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
      {/* Anchor dot */}
      {anchor !== undefined && (
        <circle cx={xScale(0)} cy={yScale(anchor)} r="4" fill={color} stroke="#fff" strokeWidth="2" />
      )}
    </svg>
  );
}

// =====================================================================
// LabTrend — 5-point trendline with optimal range band.
// =====================================================================

export interface LabTrendProps {
  values: number[];
  optimalLow: number;
  optimalHigh: number;
  color?: string;
  height?: number;
}

export function LabTrend({
  values,
  optimalLow,
  optimalHigh,
  color = "#5b8a72",
  height = 50,
}: LabTrendProps) {
  if (!values.length) return null;
  const W = 120;
  const H = height;
  const min = Math.min(...values, optimalLow);
  const max = Math.max(...values, optimalHigh);
  const range = max - min || 1;
  const yScale = (v: number) => 4 + (1 - (v - min) / range) * (H - 8);
  const xStep = (W - 8) / (values.length - 1);
  const pts = values.map((v, i) => [4 + i * xStep, yScale(v)] as [number, number]);
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    d += ` L ${pts[i][0]} ${pts[i][1]}`;
  }
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
      {/* optimal band */}
      <rect
        x={0}
        y={yScale(optimalHigh)}
        width={W}
        height={yScale(optimalLow) - yScale(optimalHigh)}
        fill={color}
        fillOpacity="0.08"
      />
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      {pts.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r="2" fill={color} />
      ))}
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="3" fill={color} stroke="#fff" strokeWidth="1.5" />
    </svg>
  );
}

// =====================================================================
// Ring — single progress arc (used by Today recovery hero).
// =====================================================================

export interface RingProps {
  pct: number;
  size?: number;
  thickness?: number;
  color?: string;
  track?: string;
  children?: ReactNode;
}

export function Ring({
  pct,
  size = 84,
  thickness = 6,
  color = "#5b8a72",
  track = "rgba(0,0,0,0.08)",
}: RingProps) {
  const r = size / 2 - thickness / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(1, pct));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={thickness} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={thickness}
        strokeDasharray={c}
        strokeDashoffset={off}
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
}
