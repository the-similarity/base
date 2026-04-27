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
 *   - DayTrajectory   — today's HR over 24h with up to 3 compare overlays
 *   - ChannelMini     — small-multiples row used by /flow
 *   - RhymeHeatmap    — 7-day × 12-hour intensity grid (Today screen)
 *   - TagDonut        — context donut (travel/illness/training/normal)
 *   - ThreadRibbon    — 30-day thin-bar history strip
 *   - ForecastCone    — line + p10/p90 fan area for /rhymes
 *   - PolarCycle      — polar bar/area chart for /cycles
 *   - LabTrend        — 5-point lab trendline with optimal range band
 *   - Donut           — concentric arcs sized by stroke-dasharray
 *   - Ring            — single progress arc for goal cards
 */

import type { ReactNode } from "react";

import type { DaySummary } from "./data";
import { BASELINE, TAG_META } from "./data";
import type { ChannelSeries } from "./data";
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
      {fill && <path className="fill" d={fillD} fill={stroke} fillOpacity="0.10" />}
      <path
        className="line"
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
// ChannelMini — small-multiple row used by /flow.
// =====================================================================
//
// Compact 24h sparkline for a single channel with label, current value,
// and a faint baseline reference line. Designed to stack vertically.

export interface ChannelMiniProps {
  channel: ChannelSeries;
  height?: number;
}

export function ChannelMini({ channel, height = 88 }: ChannelMiniProps) {
  const W = 800;
  const H = height;
  const P = { l: 50, r: 12, t: 12, b: 18 };
  const [yMin, yMax] = channel.range;
  const xStep = (W - P.l - P.r) / (channel.series.length - 1);
  const yScale = (v: number) =>
    P.t + (1 - (v - yMin) / (yMax - yMin)) * (H - P.t - P.b);
  const pts: [number, number][] = channel.series.map((v, i) => [
    P.l + i * xStep,
    yScale(v),
  ]);
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [px, py] = pts[i - 1];
    const [x, y] = pts[i];
    const cx = (px + x) / 2;
    d += ` C ${cx} ${py}, ${cx} ${y}, ${x} ${y}`;
  }
  const fillD =
    d + ` L ${pts[pts.length - 1][0]} ${H - P.b} L ${pts[0][0]} ${H - P.b} Z`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ width: "100%", height: H }}>
      <defs>
        <linearGradient id={`chan-${channel.key}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={channel.color} stopOpacity="0.18" />
          <stop offset="100%" stopColor={channel.color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* baseline tick line at midpoint */}
      <line
        x1={P.l}
        x2={W - P.r}
        y1={yScale((yMin + yMax) / 2)}
        y2={yScale((yMin + yMax) / 2)}
        stroke="#ececea"
        strokeDasharray="2 4"
      />
      <text x={P.l - 6} y={yScale(yMax) + 3} fontSize="9" fill="#a8a8a3" textAnchor="end" fontFamily="JetBrains Mono">{yMax}</text>
      <text x={P.l - 6} y={yScale(yMin) + 3} fontSize="9" fill="#a8a8a3" textAnchor="end" fontFamily="JetBrains Mono">{yMin}</text>
      <path d={fillD} fill={`url(#chan-${channel.key})`} />
      <path d={d} fill="none" stroke={channel.color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// =====================================================================
// RhymeHeatmap — 7-day × 12-hour intensity grid (Today screen).
// =====================================================================
//
// Shows the user's last 7 days as rows × 12 two-hour bins as columns.
// Cell intensity = energy level (0-100). Sage-tinted palette so it reads
// as biological.

export interface RhymeHeatmapProps {
  days: DaySummary[]; // last 7 days, most recent first
}

export function RhymeHeatmap({ days }: RhymeHeatmapProps) {
  // 12 columns: 0-2, 2-4, …, 22-24
  const cols = 12;
  // Synthesize hourly intensity per day from the day's energy + a smooth
  // morning-low / evening-high curve. Demo-only — real version would use
  // hourly steps + HR.
  return (
    <div style={{ display: "grid", gridTemplateColumns: `60px repeat(${cols}, 1fr)`, gap: 4, alignItems: "center" }}>
      {/* header row: 2-hour labels */}
      <div />
      {Array.from({ length: cols }, (_, c) => (
        <div key={c} style={{ fontSize: 9, fontFamily: "JetBrains Mono", color: "#a8a8a3", textAlign: "center" }}>
          {String(c * 2).padStart(2, "0")}
        </div>
      ))}
      {days.map((d, di) => {
        const dow = d.date.toLocaleDateString("en-US", { weekday: "short" });
        return (
          <>
            <div key={`lbl-${di}`} style={{ fontSize: 11, color: "#7a7a75", fontWeight: 500 }}>
              {dow}
            </div>
            {Array.from({ length: cols }, (_, c) => {
              const h = c * 2;
              // Intensity model: low overnight, peak mid-afternoon
              const tod = Math.cos(((h - 14) / 24) * Math.PI * 2) * 0.5 + 0.5;
              const intensity = Math.pow((d.energy / 100) * tod, 0.7);
              const bg = `rgba(91,138,114,${0.10 + intensity * 0.7})`;
              return (
                <div
                  key={`${di}-${c}`}
                  title={`${dow} ${String(h).padStart(2, "0")}:00 — energy ${Math.round(d.energy * tod)}/100`}
                  style={{
                    aspectRatio: "1",
                    borderRadius: 3,
                    background: bg,
                    minHeight: 18,
                  }}
                />
              );
            })}
          </>
        );
      })}
    </div>
  );
}

// =====================================================================
// TagDonut — distribution of tagged contexts across last 30 days.
// =====================================================================

export interface TagDonutProps {
  days: DaySummary[]; // last 30 days
  size?: number;
  thickness?: number;
}

export function TagDonut({ days, size = 160, thickness = 22 }: TagDonutProps) {
  const counts: Record<string, number> = {};
  for (const d of days) {
    const t = d.tag ?? "normal";
    counts[t] = (counts[t] || 0) + 1;
  }
  const slices = Object.entries(counts)
    .map(([t, n]) => ({
      label: TAG_META[t as keyof typeof TAG_META]?.label ?? t,
      color: TAG_META[t as keyof typeof TAG_META]?.color ?? "#7a7a75",
      value: n,
      cat: t,
    }))
    .sort((a, b) => b.value - a.value);
  return <Donut slices={slices} size={size} thickness={thickness} />;
}

// =====================================================================
// ThreadRibbon — last 30 days as a horizontal strip of colored bars.
// =====================================================================
//
// Each bar = one day. Height encodes recovery (0-100), color encodes the
// day's tag. Hover tooltip via <title>.

export interface ThreadRibbonProps {
  days: DaySummary[]; // last 30 days, most recent first
  height?: number;
}

export function ThreadRibbon({ days, height = 50 }: ThreadRibbonProps) {
  // Reverse so the most-recent is on the right (timeline reads left=old → right=new)
  const order = [...days].reverse();
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height }}>
      {order.map((d, i) => {
        const h = (d.recovery / 100) * height;
        const color = d.tag ? TAG_META[d.tag].color : "#5b8a72";
        const dow = d.date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
        return (
          <div
            key={i}
            title={`${dow} — recovery ${d.recovery}, HRV ${d.hrv}ms, RHR ${d.rhr}${d.tag ? ` · ${TAG_META[d.tag].label}` : ""}`}
            style={{
              flex: 1,
              minWidth: 4,
              height: Math.max(4, h),
              borderRadius: 2,
              background: color,
              opacity: 0.8,
            }}
          />
        );
      })}
    </div>
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
// PolarCycle — polar bar chart for /cycles (recurring patterns).
// =====================================================================

export interface PolarCycleProps {
  /** Categorical labels around the perimeter (e.g. ["Mon","Tue",...]). */
  labels: string[];
  /** Values, one per label, scaled to 0-1. */
  values: number[];
  size?: number;
  color?: string;
}

export function PolarCycle({
  labels,
  values,
  size = 220,
  color = "#5b8a72",
}: PolarCycleProps) {
  const cx = size / 2;
  const cy = size / 2;
  const rOuter = size / 2 - 24;
  const rInner = rOuter * 0.4;
  const n = labels.length;
  const angle = (i: number) => (i / n) * Math.PI * 2 - Math.PI / 2;
  const sweep = (Math.PI * 2) / n;

  // Build sector paths. Each sector spans from angle(i) - sweep/2 to + sweep/2,
  // with outer radius = rInner + (rOuter - rInner) * value.
  const sectors = values.map((v, i) => {
    const a = angle(i);
    const a0 = a - sweep / 2 + 0.02;
    const a1 = a + sweep / 2 - 0.02;
    const r = rInner + (rOuter - rInner) * Math.max(0, Math.min(1, v));
    const x0 = cx + r * Math.cos(a0);
    const y0 = cy + r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1);
    const y1 = cy + r * Math.sin(a1);
    const ix0 = cx + rInner * Math.cos(a0);
    const iy0 = cy + rInner * Math.sin(a0);
    const ix1 = cx + rInner * Math.cos(a1);
    const iy1 = cy + rInner * Math.sin(a1);
    const large = a1 - a0 > Math.PI ? 1 : 0;
    return `M ${ix0} ${iy0} L ${x0} ${y0} A ${r} ${r} 0 ${large} 1 ${x1} ${y1} L ${ix1} ${iy1} A ${rInner} ${rInner} 0 ${large} 0 ${ix0} ${iy0} Z`;
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {/* track */}
      <circle cx={cx} cy={cy} r={rInner} fill="none" stroke="#ececea" strokeWidth="1" />
      <circle cx={cx} cy={cy} r={rOuter} fill="none" stroke="#ececea" strokeWidth="1" strokeDasharray="2 4" />
      {sectors.map((d, i) => (
        <path key={i} d={d} fill={color} fillOpacity={0.22 + values[i] * 0.55} stroke={color} strokeOpacity="0.4" />
      ))}
      {labels.map((l, i) => {
        const a = angle(i);
        const r = rOuter + 14;
        const x = cx + r * Math.cos(a);
        const y = cy + r * Math.sin(a);
        return (
          <text key={i} x={x} y={y + 3} fontSize="10" fill="#7a7a75" textAnchor="middle" fontFamily="Inter" fontWeight="500">
            {l}
          </text>
        );
      })}
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
// Donut — concentric arcs sized by stroke-dasharray; rotated -90° so
// slices start at the top.
// =====================================================================

export interface DonutSlice {
  value: number;
  color: string;
  label?: string;
  cat?: string;
}

export interface DonutProps {
  slices: DonutSlice[];
  size?: number;
  thickness?: number;
}

export function Donut({ slices, size = 200, thickness = 24 }: DonutProps) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  const r = size / 2 - thickness / 2;
  const cx = size / 2;
  const cy = size / 2;
  const len = 2 * Math.PI * r;
  const fractions = slices.map((s) => (total > 0 ? s.value / total : 0));
  const startFractions = fractions.map((_, i) =>
    fractions.slice(0, i).reduce((sum, f) => sum + f, 0)
  );
  const arcs = slices.map((s, i) => ({
    color: s.color,
    dash: fractions[i] * len,
    offset: -startFractions[i] * len,
  }));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="#ececea" strokeWidth={thickness} />
      {arcs.map((a, i) => (
        <circle
          key={i}
          cx={cx}
          cy={cy}
          r={r}
          fill="none"
          stroke={a.color}
          strokeWidth={thickness}
          strokeDasharray={`${a.dash} ${len - a.dash}`}
          strokeDashoffset={a.offset}
          transform={`rotate(-90 ${cx} ${cy})`}
          strokeLinecap="butt"
        />
      ))}
    </svg>
  );
}

// =====================================================================
// Ring — single progress arc for goal cards.
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
