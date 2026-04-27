/**
 * Lumen — pure-SVG chart primitives.
 *
 * No third-party chart library. Everything is hand-rolled SVG paths so the
 * page can layer multiple chart types in tight cards without bringing in
 * recharts/visx/d3. Each component is self-contained and stateless; pass
 * fresh data each render and React will reconcile via the path `d` strings.
 *
 * Performance: paths are built once per render with O(n) string ops where
 * n = data.length (≤ 60 for the dashboard). For lists of sparklines the
 * caller renders many <Sparkline> instances — keep `data` references stable
 * across renders to let React's reconciler skip re-paints.
 *
 * Accessibility note: charts are decorative rather than primary content
 * here. Tooltips on the heatmap use the native <title> attribute so screen
 * readers can read totals; line/area charts have no ARIA wrap because the
 * neighboring KPI text states the same numbers.
 */
import type { Transaction } from "./data";

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
// AreaChart — full-width line + gradient fill with grid + Y axis labels.
// =====================================================================

export interface AreaChartDatum {
  m: string;
  v: number;
}

export interface AreaChartProps {
  data: AreaChartDatum[];
  height?: number;
  accent?: string;
  formatY?: (v: number) => string;
  labels?: boolean;
  // Caller-supplied gradient id avoids collisions when multiple AreaCharts
  // render on the same screen — each must own a unique <linearGradient> id.
  gradientId?: string;
}

export function AreaChart({
  data,
  height = 220,
  accent = "#0a6b48",
  formatY = (v: number) => String(v),
  labels = true,
  gradientId = "areaG",
}: AreaChartProps) {
  if (!data?.length) return null;
  const W = 800;
  const H = height;
  const P = { l: 50, r: 14, t: 18, b: 24 };
  const min = Math.min(...data.map((d) => d.v));
  const max = Math.max(...data.map((d) => d.v));
  const pad = (max - min) * 0.12 || 1;
  // Clamp yMin to 0 so net-worth/portfolio charts don't dip below the axis
  // when the series happens to start near zero.
  const yMin = Math.max(0, min - pad);
  const yMax = max + pad;
  const xStep = (W - P.l - P.r) / (data.length - 1);
  const yScale = (v: number) =>
    P.t + (1 - (v - yMin) / (yMax - yMin)) * (H - P.t - P.b);
  const pts: [number, number][] = data.map((d, i) => [
    P.l + i * xStep,
    yScale(d.v),
  ]);
  let path = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [px, py] = pts[i - 1];
    const [x, y] = pts[i];
    const cx = (px + x) / 2;
    path += ` C ${cx} ${py}, ${cx} ${y}, ${x} ${y}`;
  }
  const fillPath =
    path + ` L ${pts[pts.length - 1][0]} ${H - P.b} L ${pts[0][0]} ${H - P.b} Z`;
  const ticks = 4;
  const ys = Array.from(
    { length: ticks + 1 },
    (_, i) => yMin + (i / ticks) * (yMax - yMin)
  );

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      style={{ width: "100%", height: H, overflow: "visible" }}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={accent} stopOpacity="0.22" />
          <stop offset="100%" stopColor={accent} stopOpacity="0" />
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
          {labels && (
            <text
              x={P.l - 8}
              y={yScale(y) + 3}
              fontSize="10"
              fill="#8a8a86"
              textAnchor="end"
              fontFamily="JetBrains Mono"
            >
              {formatY(y)}
            </text>
          )}
        </g>
      ))}
      <path d={fillPath} fill={`url(#${gradientId})`} />
      <path
        d={path}
        fill="none"
        stroke={accent}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        cx={pts[pts.length - 1][0]}
        cy={pts[pts.length - 1][1]}
        r="4"
        fill={accent}
        stroke="#fff"
        strokeWidth="2"
      />
      {labels &&
        data.map((d, i) =>
          i % 2 === 0 || i === data.length - 1 ? (
            <text
              key={i}
              x={pts[i][0]}
              y={H - 8}
              fontSize="10"
              fill="#8a8a86"
              textAnchor="middle"
            >
              {d.m}
            </text>
          ) : null
        )}
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
  // Optional caller key — donut renders any extra fields opaquely.
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
  // Each slice is a stroked circle whose visible arc is drawn via a
  // dasharray "[arc] [gap]". Stacking them with strokeDashoffset bumps each
  // subsequent arc forward by the prior cumulative length.
  //
  // We compute the per-slice fractions, then a prefix-sum of those
  // fractions to derive each slice's "start fraction" (i.e. how far
  // around the ring it begins). Both passes return new arrays — no
  // in-render mutation of an outer variable, so React Compiler is happy.
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
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill="none"
        stroke="#ececea"
        strokeWidth={thickness}
      />
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
}

export function Ring({
  pct,
  size = 84,
  thickness = 6,
  color = "#0a6b48",
  track = "rgba(0,0,0,0.08)",
}: RingProps) {
  const r = size / 2 - thickness / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(1, pct));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={track}
        strokeWidth={thickness}
      />
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

// =====================================================================
// FlowBars — stacked monthly in/out bars (HTML+CSS, not SVG, so the
// painterly background can show through small column gaps consistently).
// =====================================================================

export interface FlowBarsDatum {
  m: string;
  in: number;
  out: number;
}

export interface FlowBarsProps {
  data: FlowBarsDatum[];
  height?: number;
}

export function FlowBars({ data, height = 180 }: FlowBarsProps) {
  const max = Math.max(...data.map((d) => Math.max(d.in, d.out)));
  return (
    <div className="flow-bars" style={{ height }}>
      {data.map((d, i) => (
        <div key={i} className="flow-col">
          <div className="stack">
            <div
              className="b-in"
              style={{ height: `${(d.in / max) * 100}%` }}
              title={`In: $${d.in}`}
            />
            <div
              className="b-out"
              style={{ height: `${(d.out / max) * 100}%`, marginTop: 1 }}
              title={`Out: $${d.out}`}
            />
          </div>
          <div className="lab">{d.m.split(" ")[0]}</div>
        </div>
      ))}
    </div>
  );
}

// =====================================================================
// SpendHeatmap — last 49 days × emerald intensity grid (7 columns).
// =====================================================================

export interface SpendHeatmapProps {
  tx: Transaction[];
}

export function SpendHeatmap({ tx }: SpendHeatmapProps) {
  // Anchor on the same fixed "today" used by data.ts so the heatmap aligns
  // with the demo TX. The 49-day window matches the 7-week heatmap shown
  // in the dashboard.
  const today = new Date("2026-04-27T00:00:00Z");
  const days: Date[] = [];
  for (let i = 48; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    days.push(d);
  }
  const totalsByKey: Record<string, number> = {};
  tx.forEach((t) => {
    if (t.amount < 0) {
      const k = t.date.toISOString().slice(0, 10);
      totalsByKey[k] = (totalsByKey[k] || 0) + Math.abs(t.amount);
    }
  });
  const max = Math.max(...Object.values(totalsByKey), 1);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
      {days.map((d) => {
        const k = d.toISOString().slice(0, 10);
        const v = totalsByKey[k] || 0;
        // Pow 0.6 compresses high-spend days so a single $400 outlier
        // doesn't flatten the rest of the grid into pale green.
        const intensity = Math.pow(v / max, 0.6);
        const bg =
          v === 0
            ? "rgba(0,0,0,0.04)"
            : `rgba(10,107,72,${0.15 + intensity * 0.7})`;
        return (
          <div
            key={k}
            title={`${d.toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            })}: ${v ? "$" + v.toFixed(0) : "No spending"}`}
            style={{ aspectRatio: "1", borderRadius: 3, background: bg }}
          />
        );
      })}
    </div>
  );
}
