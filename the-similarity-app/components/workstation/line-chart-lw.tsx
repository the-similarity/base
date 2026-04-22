"use client";

/**
 * LineChartLW — lightweight-charts ("Pro") alternate view for the workstation chart.
 *
 * Drop-in replacement for {@link LineChart} (the SVG "Fast" view). Renders the
 * same data shape (`series`, `cone`, `analogsOverlay`, `win`, `viewStart`,
 * `viewEnd`, `forecastHorizon`, `showCone`, `showWindow`) via the
 * TradingView-grade `lightweight-charts` canvas engine. The Pro view is
 * read-only with respect to the query window: the `onWindowChange` prop is
 * accepted for interface parity but never invoked. A corner note tells the
 * user window editing remains in Fast view.
 *
 * Lifecycle and invariants:
 * - The chart instance is created once on mount via `createChart` and destroyed
 *   via `chart.remove()` on unmount. The entire series graph lives on the
 *   canvas; React does not own those pixels.
 * - A `ResizeObserver` resizes the chart via `chart.applyOptions({ width })`
 *   every time the container width changes. The observer is disconnected on
 *   unmount to avoid leaks when the Workstation unmounts or swaps modes.
 * - A `MutationObserver` on `<html data-theme>` re-reads CSS color tokens
 *   and calls `chart.applyOptions({ layout, grid, … })` so the canvas follows
 *   light/dark theme swaps without a full remount.
 * - All series (`priceSeriesRef`, `coneP10P90Ref`, `coneP25P75Ref`,
 *   `medianSeriesRef`, `analogSeriesRefs`) are held in refs because their
 *   identity is stable for the life of the chart; we mutate their data via
 *   `series.setData(...)`, never reconstruct.
 * - Analog overlays: each analog gets its own `LineSeries`. When the set of
 *   analogs changes (count or identity), previously-created analog series are
 *   removed from the chart and a fresh batch is created. This is deliberate —
 *   matching analogs pairwise by index is brittle once the composite sort order
 *   flips, and lightweight-charts has no cheap "rename series" primitive.
 *
 * Data conversion:
 * - DataPoint.d (Date) → UTCTimestamp: `Math.floor(date.getTime() / 1000)`.
 *   This is the lightweight-charts contract; millis are rejected.
 * - The visible range is clamped to `[viewStart, viewEnd]` via
 *   `timeScale().setVisibleRange(...)` after each data update.
 *
 * Accessibility:
 * - Root container exposes `role="img"` + `aria-label`. Keyboard users can
 *   still pan/zoom via the native lightweight-charts canvas wheel handling
 *   (mouse/trackpad), but there is no screen-reader friendly representation
 *   of the price data — for that the Fast SVG view has proper tick text.
 */

import { useEffect, useRef } from "react";
import {
  createChart,
  AreaSeries,
  LineSeries,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
  type LineData,
  type AreaData,
  type Time,
} from "lightweight-charts";
import { DataPoint, ConePoint } from "../../lib/data";
import type { AnalogOverlay } from "./line-chart";

/**
 * Props for {@link LineChartLW}. The shape mirrors the SVG LineChart's
 * LineChartProps so a single `sharedProps` spread in the parent works for
 * both modes. The `window` prop is renamed to `win` at destructure time in
 * the parent — here we accept it under the original name to stay 1:1.
 */
export interface LineChartLWProps {
  /** Full series array */
  series: DataPoint[];
  /** Start index of visible range */
  viewStart: number;
  /** End index of visible range */
  viewEnd: number;
  /** Query window position and length */
  window: { start: number; len: number };
  /** Kept for interface parity — Pro view never fires this. */
  onWindowChange: (w: { start: number; len: number }) => void;
  /** Analog overlays to draw on the chart */
  analogsOverlay?: AnalogOverlay[];
  /** Forecast cone quantile data */
  cone?: ConePoint[];
  /** Chart height in px */
  height?: number;
  /** Forecast horizon in trading days */
  forecastHorizon?: number;
  /** Hover crosshair index — unused by Pro (the chart owns its crosshair). */
  crosshairIdx?: number | null;
  /** Hover callback — unused by Pro view. */
  onHover?: (idx: number | null) => void;
  /** Whether to show the (read-only) query window band */
  showWindow?: boolean;
  /** Whether to show the forecast cone */
  showCone?: boolean;
  /**
   * The `id` of the analog currently hovered in the card strip — drives
   * a "preview" emphasis on the matching overlay line. Mirrors
   * `hoveredAnalogId` on the Fast view. Null when nothing is hovered. */
  hoveredAnalogId?: string | null;
}

/**
 * Read current CSS color tokens from the document root so the chart matches
 * the active theme. Called on mount and again whenever `data-theme` mutates.
 *
 * Why read CSS vars instead of hardcoding: the project uses a single
 * `--ink`/`--bg`/`--rule` palette that the theme toggle swaps at the :root
 * level, and lightweight-charts needs concrete color strings, not var()
 * lookups. We resolve them once and push into `chart.applyOptions(...)`.
 */
function readThemeTokens(): {
  bg: string;
  ink: string;
  ink3: string;
  ink4: string;
  rule: string;
  grid: string;
  query: string;
  analog: string;
  analogStrong: string;
  analogContext: string;
  coneFill: string;
  coneLine: string;
  accent: string;
  /** Six-slot rank palette — `palette[0]` is rank 1, etc. Mirrors the
   *  --c-analog-1..6 tokens introduced by Agent G; resolved at theme
   *  switch time so both light and dark forks pick up the right shade. */
  palette: [string, string, string, string, string, string];
} {
  // SSR guard — during static render there is no DOM. Fall back to light
  // tokens; the post-mount effect will re-read immediately on the client.
  if (typeof document === "undefined") {
    return {
      bg: "#f7f4ea",
      ink: "#14130f",
      ink3: "#6b6858",
      ink4: "#8c8a7c",
      rule: "#e6e2d6",
      grid: "#e6e2d6",
      query: "#14130f",
      analog: "#9a9a9a",
      analogStrong: "#5a2b2b",
      analogContext: "#8c8a7c",
      coneFill: "rgba(20,19,15,0.08)",
      coneLine: "#6b6858",
      accent: "#5a2b2b",
      palette: [
        "#5a2b2b", // oxblood (rank 1)
        "#8a6200", // amber
        "#1c5b3d", // green
        "#3a4a6b", // navy
        "#6b3a5a", // plum
        "#8a5a3a", // sienna
      ],
    };
  }
  const cs = getComputedStyle(document.documentElement);
  // Small helper: trim then fall back to a safe default if the var is empty.
  const v = (name: string, fallback: string) =>
    (cs.getPropertyValue(name).trim() || fallback);
  const ink4 = v("--ink-4", "#8c8a7c");
  const accent = v("--accent", "#5a2b2b");
  return {
    bg: v("--bg", "#f7f4ea"),
    ink: v("--ink", "#14130f"),
    ink3: v("--ink-3", "#6b6858"),
    ink4,
    rule: v("--rule", "#e6e2d6"),
    grid: v("--c-grid", v("--rule", "#e6e2d6")),
    query: v("--c-query", v("--ink", "#14130f")),
    analog: v("--c-analog", "#9a9a9a"),
    // "Strong" (pinned) analog in the Pro view uses the product accent
    // red — mirrors the SVG chart's .analog.strong which reads
    // var(--accent). Keeps the two renderers visually coherent when the
    // user toggles between Fast and Pro with pins active.
    analogStrong: accent,
    // "Context" (unpinned-while-any-pinned) uses the --ink-4 muted ink.
    analogContext: ink4,
    // The SVG chart uses a translucent cone fill. lightweight-charts AreaSeries
    // needs top/bottom colors — we derive a 20%-alpha and 6%-alpha of --ink.
    coneFill: v("--c-cone-fill", "rgba(20,19,15,0.08)"),
    coneLine: v("--c-cone-line", "#6b6858"),
    accent,
    palette: [
      v("--c-analog-1", "#5a2b2b"),
      v("--c-analog-2", "#8a6200"),
      v("--c-analog-3", "#1c5b3d"),
      v("--c-analog-4", "#3a4a6b"),
      v("--c-analog-5", "#6b3a5a"),
      v("--c-analog-6", "#8a5a3a"),
    ],
  };
}

/** Convert a DataPoint into lightweight-charts LineData. */
function toLineData(d: DataPoint): LineData<UTCTimestamp> {
  return {
    time: Math.floor(d.d.getTime() / 1000) as UTCTimestamp,
    value: d.p,
  };
}

/**
 * Convert a hex / named / rgb(a) color to an rgba() string with a
 * substituted alpha channel. Used to simulate "opacity" on
 * lightweight-charts LineSeries (the library has no line opacity knob —
 * colors must be baked with alpha).
 *
 * Supported inputs:
 *   - `#rgb`, `#rrggbb`, `#rrggbbaa` — standard hex forms.
 *   - `rgb(r,g,b)` / `rgba(r,g,b,a)` — the alpha is overwritten with
 *     the `alpha` parameter regardless of what was there.
 *   - any other value — returned verbatim; caller is responsible for
 *     providing a safe fallback when the CSS var was empty.
 *
 * The conversion is conservative: we parse only the forms the project
 * actually emits from CSS tokens (hex and rgb/rgba). Anything unknown
 * passes through — misconfigured colors fail visibly rather than
 * silently producing transparent lines.
 */
function hexToRgba(color: string, alpha: number): string {
  const hex = color.trim();
  // #rrggbb or #rrggbbaa
  if (/^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(hex)) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  // #rgb shorthand
  if (/^#[0-9a-fA-F]{3}$/.test(hex)) {
    const r = parseInt(hex[1] + hex[1], 16);
    const g = parseInt(hex[2] + hex[2], 16);
    const b = parseInt(hex[3] + hex[3], 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  // rgb(a) — swap the alpha channel.
  const rgbMatch = hex.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*[\d.]+\s*)?\)$/);
  if (rgbMatch) {
    return `rgba(${rgbMatch[1]}, ${rgbMatch[2]}, ${rgbMatch[3]}, ${alpha})`;
  }
  // Fallback: return verbatim. The caller controls token defaults so
  // this only triggers when a CSS var resolves to something unusual.
  return hex;
}

/**
 * Build cone area data aligned with the query-terminal bar. The cone
 * starts at `series[win.start + win.len - 1]` (same anchor as the SVG
 * view) and extends `forecastHorizon` bars forward using the dates of
 * subsequent bars in `series` when available. If `series` doesn't have
 * enough forward bars, we synthesize daily timestamps by offsetting the
 * anchor time by N days — lightweight-charts just needs monotonically
 * increasing timestamps.
 */
function buildConeData(
  series: DataPoint[],
  win: { start: number; len: number },
  cone: ConePoint[],
  forecastHorizon: number,
): {
  p10p90: AreaData<UTCTimestamp>[];
  p25p75: AreaData<UTCTimestamp>[];
  median: LineData<UTCTimestamp>[];
} {
  const anchorIdx = win.start + win.len - 1;
  const anchor = series[anchorIdx];
  if (!anchor) return { p10p90: [], p25p75: [], median: [] };
  const anchorTime = Math.floor(anchor.d.getTime() / 1000);

  const pts = cone.slice(0, forecastHorizon);
  const p10p90: AreaData<UTCTimestamp>[] = [];
  const p25p75: AreaData<UTCTimestamp>[] = [];
  const median: LineData<UTCTimestamp>[] = [];

  pts.forEach((q, i) => {
    // Prefer the real future bar's timestamp when series has it — this keeps
    // weekends/holidays aligned between the price line and the cone. Fall back
    // to synthetic +N*86400 seconds for any bars past the end of the series.
    const futureBar = series[anchorIdx + i];
    const t = (futureBar
      ? Math.floor(futureBar.d.getTime() / 1000)
      : anchorTime + i * 86400) as UTCTimestamp;
    // AreaData encodes a single `value`; to draw a band we create TWO area
    // series (top=p90, bottom=p10) and set the bottom's background to the
    // page bg so only the gap between them is visible. lightweight-charts v5
    // does not natively expose a band primitive.
    p10p90.push({ time: t, value: q.p90 });
    // We stash p10 as a separate record the consumer passes to a second
    // AreaSeries whose top color is transparent and bottom covers the
    // [minPrice, p10] region — see component below.
    // For the p25..p75 band we use the same pattern (p75 top, p25 bottom).
    p25p75.push({ time: t, value: q.p75 });
    median.push({ time: t, value: q.p50 });
  });

  // Note: we only need the TOP (p90, p75) series for rendering because we
  // express "band" as two stacked AreaSeries. The LOWER edge is drawn by
  // independent AreaSeries the caller will build below. Keeping this
  // helper pure — caller handles the lower edges.
  return { p10p90, p25p75, median };
}

/**
 * Build the lower edge of a quantile band. lightweight-charts AreaSeries
 * renders `value → baseline`, so to fake a filled BAND we draw the TOP at
 * `value=p90` and a SECOND AreaSeries at `value=p10` with the same color
 * as the chart background + transparent top. Stacked, the visible fill is
 * only the p10..p90 gap.
 */
function buildConeLowerEdge(
  series: DataPoint[],
  win: { start: number; len: number },
  cone: ConePoint[],
  forecastHorizon: number,
  key: "p10" | "p25",
): AreaData<UTCTimestamp>[] {
  const anchorIdx = win.start + win.len - 1;
  const anchor = series[anchorIdx];
  if (!anchor) return [];
  const anchorTime = Math.floor(anchor.d.getTime() / 1000);
  return cone.slice(0, forecastHorizon).map((q, i) => {
    const futureBar = series[anchorIdx + i];
    const t = (futureBar
      ? Math.floor(futureBar.d.getTime() / 1000)
      : anchorTime + i * 86400) as UTCTimestamp;
    return { time: t, value: q[key] };
  });
}

/**
 * Build LineData for a single analog overlay. Mirrors the scaling rule from
 * the SVG chart (`line-chart.tsx:219`): the analog's terminal bar is pinned
 * to the query's terminal price by `scale = qAnchorP / analogEnd`. We then
 * emit both the priceWindow and the `after[]` projection in a single
 * continuous series.
 */
function buildAnalogData(
  series: DataPoint[],
  win: { start: number; len: number },
  analog: AnalogOverlay,
  forecastHorizon: number,
): LineData<UTCTimestamp>[] {
  const anchorIdx = win.start + win.len - 1;
  const anchor = series[anchorIdx];
  if (!anchor) return [];
  const qAnchorP = anchor.p;
  const analogEnd = analog.priceWindow[analog.priceWindow.length - 1];
  if (!analogEnd) return [];
  const scale = qAnchorP / analogEnd;

  const combined = [
    ...analog.priceWindow,
    ...analog.after.slice(0, forecastHorizon),
  ];
  const startOffset = anchorIdx - (analog.priceWindow.length - 1);
  const anchorTime = Math.floor(anchor.d.getTime() / 1000);

  const out: LineData<UTCTimestamp>[] = [];
  for (let k = 0; k < combined.length; k++) {
    const idx = startOffset + k;
    // For bars inside `series` use the real date; for bars past the end
    // (forward window beyond the last bar) fabricate a daily cadence.
    let t: UTCTimestamp;
    if (idx >= 0 && idx < series.length) {
      t = Math.floor(series[idx].d.getTime() / 1000) as UTCTimestamp;
    } else if (idx >= series.length) {
      t = (anchorTime + (idx - anchorIdx) * 86400) as UTCTimestamp;
    } else {
      // idx < 0 — analog window extends before history starts. Skip.
      continue;
    }
    out.push({ time: t, value: combined[k] * scale });
  }
  // De-duplicate non-monotonic times (e.g. weekends) to satisfy the
  // lightweight-charts contract of strictly increasing timestamps.
  out.sort((a, b) => (a.time as number) - (b.time as number));
  const dedup: LineData<UTCTimestamp>[] = [];
  for (const p of out) {
    if (!dedup.length || (p.time as number) > (dedup[dedup.length - 1].time as number)) {
      dedup.push(p);
    }
  }
  return dedup;
}

export function LineChartLW({
  series,
  viewStart,
  viewEnd,
  window: win,
  analogsOverlay,
  cone,
  height = 380,
  forecastHorizon = 60,
  showWindow = true,
  showCone = true,
  hoveredAnalogId = null,
}: LineChartLWProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const priceSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const coneP90Ref = useRef<ISeriesApi<"Area"> | null>(null);
  const coneP10Ref = useRef<ISeriesApi<"Area"> | null>(null);
  const coneP75Ref = useRef<ISeriesApi<"Area"> | null>(null);
  const coneP25Ref = useRef<ISeriesApi<"Area"> | null>(null);
  const medianSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const analogSeriesRefs = useRef<ISeriesApi<"Line">[]>([]);
  // Window band implemented via two vertical price lines bracketing the
  // query range on a hidden "marker" series. The actual visual band is a
  // DOM overlay (absolutely positioned div) that syncs with the chart's
  // timeScale via coordinate lookups — see effect below.
  const windowOverlayRef = useRef<HTMLDivElement>(null);

  // ── Chart creation (once) ────────────────────────────────────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const tokens = readThemeTokens();

    const chart = createChart(el, {
      width: el.clientWidth || 800,
      height,
      layout: {
        background: { color: tokens.bg },
        textColor: tokens.ink3,
        fontFamily: "var(--mono), 'SF Mono', 'Fira Code', Consolas, monospace",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: tokens.grid },
        horzLines: { color: tokens.grid },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: tokens.ink3, width: 1, style: LineStyle.Dotted, labelVisible: true },
        horzLine: { color: tokens.ink3, width: 1, style: LineStyle.Dotted, labelVisible: true },
      },
      rightPriceScale: {
        borderColor: tokens.rule,
        textColor: tokens.ink3,
      },
      timeScale: {
        borderColor: tokens.rule,
        timeVisible: false,
        secondsVisible: false,
      },
      handleScroll: true,
      handleScale: true,
      autoSize: false,
    });
    chartRef.current = chart;

    // Cone area series — created BEFORE the price line so it renders behind.
    // The trick: for each band we create TWO AreaSeries. The "top" one draws
    // the upper quantile as a filled area down to the baseline (minPrice).
    // The "bottom" one overlays with the page-background color and a
    // transparent top, erasing the area below the lower quantile. What's
    // left visible is the band strip between the two quantiles.
    const p90 = chart.addSeries(AreaSeries, {
      topColor: tokens.coneFill,
      bottomColor: tokens.coneFill,
      lineColor: tokens.coneLine,
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const p10 = chart.addSeries(AreaSeries, {
      // Paint the sub-p10 region with the page background so it "erases"
      // the tail of the p90 fill below p10.
      topColor: tokens.bg,
      bottomColor: tokens.bg,
      lineColor: tokens.coneLine,
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    // Inner band (p25-p75) — slightly stronger fill.
    const p75 = chart.addSeries(AreaSeries, {
      topColor: tokens.coneFill,
      bottomColor: tokens.coneFill,
      lineColor: "transparent",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    const p25 = chart.addSeries(AreaSeries, {
      topColor: tokens.bg,
      bottomColor: tokens.bg,
      lineColor: "transparent",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    // P50 median line
    const median = chart.addSeries(LineSeries, {
      color: tokens.coneLine,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    // Main price line on top of everything cone-related.
    const price = chart.addSeries(LineSeries, {
      color: tokens.query,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 3,
    });

    coneP90Ref.current = p90;
    coneP10Ref.current = p10;
    coneP75Ref.current = p75;
    coneP25Ref.current = p25;
    medianSeriesRef.current = median;
    priceSeriesRef.current = price;

    // Resize observer — keeps the chart width pinned to its container.
    const ro = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (!rect || !chartRef.current) return;
      chartRef.current.applyOptions({ width: Math.max(100, Math.floor(rect.width)) });
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      priceSeriesRef.current = null;
      coneP90Ref.current = null;
      coneP10Ref.current = null;
      coneP75Ref.current = null;
      coneP25Ref.current = null;
      medianSeriesRef.current = null;
      analogSeriesRefs.current = [];
    };
  }, [height]);

  // ── Theme-aware layout tokens via MutationObserver on data-theme ─────
  useEffect(() => {
    if (typeof document === "undefined") return;
    const applyTokens = () => {
      const chart = chartRef.current;
      if (!chart) return;
      const t = readThemeTokens();
      chart.applyOptions({
        layout: { background: { color: t.bg }, textColor: t.ink3 },
        grid: { vertLines: { color: t.grid }, horzLines: { color: t.grid } },
        rightPriceScale: { borderColor: t.rule, textColor: t.ink3 },
        timeScale: { borderColor: t.rule },
        crosshair: {
          vertLine: { color: t.ink3 },
          horzLine: { color: t.ink3 },
        },
      });
      priceSeriesRef.current?.applyOptions({ color: t.query });
      medianSeriesRef.current?.applyOptions({ color: t.coneLine });
      coneP90Ref.current?.applyOptions({
        topColor: t.coneFill,
        bottomColor: t.coneFill,
        lineColor: t.coneLine,
      });
      coneP10Ref.current?.applyOptions({
        topColor: t.bg,
        bottomColor: t.bg,
        lineColor: t.coneLine,
      });
      coneP75Ref.current?.applyOptions({
        topColor: t.coneFill,
        bottomColor: t.coneFill,
      });
      coneP25Ref.current?.applyOptions({
        topColor: t.bg,
        bottomColor: t.bg,
      });
    };
    const mo = new MutationObserver((muts) => {
      for (const m of muts) {
        if (m.type === "attributes" && m.attributeName === "data-theme") {
          applyTokens();
          return;
        }
      }
    });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => mo.disconnect();
  }, []);

  // ── Push price data ──────────────────────────────────────────────────
  useEffect(() => {
    const s = priceSeriesRef.current;
    const chart = chartRef.current;
    if (!s || !chart || series.length === 0) return;
    const data = series.map(toLineData);
    s.setData(data);

    // Clamp the visible time range to [viewStart, viewEnd] to match the SVG
    // Fast view's range selection. fitContent is avoided because it would
    // override the user's selected range chips.
    const vs = series[Math.max(0, viewStart)];
    const ve = series[Math.min(series.length - 1, viewEnd - 1)];
    if (vs && ve) {
      chart.timeScale().setVisibleRange({
        from: Math.floor(vs.d.getTime() / 1000) as Time,
        to: Math.floor(ve.d.getTime() / 1000) as Time,
      });
    }
  }, [series, viewStart, viewEnd]);

  // ── Push cone data ───────────────────────────────────────────────────
  useEffect(() => {
    const p90 = coneP90Ref.current, p10 = coneP10Ref.current;
    const p75 = coneP75Ref.current, p25 = coneP25Ref.current;
    const med = medianSeriesRef.current;
    if (!p90 || !p10 || !p75 || !p25 || !med) return;

    if (!cone || !showCone || cone.length === 0) {
      p90.setData([]); p10.setData([]); p75.setData([]); p25.setData([]); med.setData([]);
      return;
    }

    const built = buildConeData(series, win, cone, forecastHorizon);
    const p10Data = buildConeLowerEdge(series, win, cone, forecastHorizon, "p10");
    const p25Data = buildConeLowerEdge(series, win, cone, forecastHorizon, "p25");
    p90.setData(built.p10p90);
    p10.setData(p10Data);
    p75.setData(built.p25p75);
    p25.setData(p25Data);
    med.setData(built.median);
  }, [cone, showCone, series, win, forecastHorizon]);

  // ── Push analog overlays ────────────────────────────────────────────
  //
  // Pro-view mirror of the SVG chart's four-state rendering (see
  // `line-chart.tsx:analogPaths`). Cases:
  //   - No pins + no hover            → palette color per rank, opacity
  //                                      emulated via rgba alpha ramp
  //                                      (.95, .85, .75, .65, .55, .45)
  //                                      and line-width ramp 2 → 1.
  //   - No pins + hover match         → rank color at alpha 1.0, width 3
  //                                      (brightness bump not available
  //                                      in lightweight-charts; we reach
  //                                      "pop" via alpha + width only).
  //   - Pins present, this pinned     → accent color, width 2 (or 3 if
  //                                      hovered).
  //   - Pins present, not pinned      → ink-4 muted, width 1, alpha .35
  //                                      (or .7 if hovered — "preview
  //                                      before pin" behavior).
  //
  // lightweight-charts v5 LineSeries has no native `opacity` option, so
  // we fake opacity with a pre-multiplied rgba color. lightweight-charts
  // also only accepts `lineWidth: 1 | 2 | 3 | 4` integers, which is why
  // the width ramp collapses at the top end.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    // Remove any previous analog series (cheapest correct approach — see
    // top-level docstring for why we don't pairwise-match).
    for (const s of analogSeriesRefs.current) {
      try { chart.removeSeries(s); } catch {
        // ignore — series may already be gone if chart was torn down mid-render
      }
    }
    analogSeriesRefs.current = [];

    if (!analogsOverlay || analogsOverlay.length === 0) return;

    const tokens = readThemeTokens();
    const hasAnyPin = analogsOverlay.some(a => a.pinned);

    // Rank-aligned opacity ramp. Matches the SVG view's ramp so a user
    // toggling Fast ↔ Pro sees the same visual ordering of #1..#6.
    const RAMP_ALPHA = [0.95, 0.85, 0.75, 0.65, 0.55, 0.45];

    analogsOverlay.forEach((a, rank) => {
      const data = buildAnalogData(series, win, a, forecastHorizon);
      if (data.length < 2) return;

      const isHovered = !!(a.id && hoveredAnalogId && a.id === hoveredAnalogId);
      const variant: "default" | "strong" | "context" =
        !hasAnyPin ? "default"
        : a.pinned ? "strong"
        : "context";

      let color: string;
      // lightweight-charts v5 accepts 1 | 2 | 3 | 4 as lineWidth. We
      // type this as `1 | 2 | 3` so we never exceed the hover bump.
      let lineWidth: 1 | 2 | 3;

      if (variant === "strong") {
        color = tokens.analogStrong;
        lineWidth = isHovered ? 3 : 2;
      } else if (variant === "context") {
        // Hovered-but-unpinned: un-fade from .35 to .7 so the user can
        // preview the overlay before deciding to pin it.
        color = hexToRgba(tokens.analogContext, isHovered ? 0.7 : 0.35);
        lineWidth = 1;
      } else {
        // Default palette mode — rank color with ramped alpha. The
        // hovered overlay pops to full alpha + width 3.
        const basePalette = tokens.palette[Math.min(rank, 5)];
        const alpha = isHovered ? 1.0 : RAMP_ALPHA[Math.min(rank, 5)];
        color = hexToRgba(basePalette, alpha);
        lineWidth = isHovered ? 3 : (rank === 0 ? 2 : 1);
      }

      const s = chart.addSeries(LineSeries, {
        color,
        lineWidth,
        lineStyle: LineStyle.Solid,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(data);
      analogSeriesRefs.current.push(s);
    });
  }, [analogsOverlay, series, win, forecastHorizon, hoveredAnalogId]);

  // ── Window band overlay (DOM, positioned from timeScale coordinates) ─
  // We implement the read-only query window as an absolutely-positioned
  // shaded div synced to the chart's timeScale via timeToCoordinate lookups.
  // This keeps the chart canvas untouched (no hidden series, no flicker) and
  // gives us native CSS styling for the label text.
  useEffect(() => {
    const chart = chartRef.current;
    const overlay = windowOverlayRef.current;
    if (!chart || !overlay) return;

    if (!showWindow) {
      overlay.style.display = "none";
      return;
    }

    const update = () => {
      const s1 = series[win.start];
      const s2 = series[win.start + win.len - 1];
      if (!s1 || !s2) {
        overlay.style.display = "none";
        return;
      }
      const t1 = Math.floor(s1.d.getTime() / 1000) as Time;
      const t2 = Math.floor(s2.d.getTime() / 1000) as Time;
      const x1 = chart.timeScale().timeToCoordinate(t1);
      const x2 = chart.timeScale().timeToCoordinate(t2);
      if (x1 === null || x2 === null) {
        // Window is outside visible range — hide the overlay.
        overlay.style.display = "none";
        return;
      }
      overlay.style.display = "block";
      overlay.style.left = `${Math.min(x1, x2)}px`;
      overlay.style.width = `${Math.max(2, Math.abs(x2 - x1))}px`;
    };
    update();
    const ts = chart.timeScale();
    ts.subscribeVisibleLogicalRangeChange(update);
    // Also update on chart resize — the size change listener fires before
    // width propagates to the timeScale, so we queue one microtask update.
    const ro = new ResizeObserver(() => queueMicrotask(update));
    const el = containerRef.current;
    if (el) ro.observe(el);
    return () => {
      try { ts.unsubscribeVisibleLogicalRangeChange(update); } catch { /* chart gone */ }
      ro.disconnect();
    };
  }, [series, win, showWindow, viewStart, viewEnd]);

  return (
    <div
      ref={containerRef}
      className="lw-chart"
      role="img"
      aria-label="Price chart, professional view"
      style={{ position: "relative", width: "100%", height }}
    >
      {/* Read-only query window band. Positioned by the effect above. */}
      {showWindow && (
        <div
          ref={windowOverlayRef}
          className="lw-chart__window"
          aria-hidden="true"
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            display: "none",
            pointerEvents: "none",
            // Color and border are driven by CSS tokens (see globals.css).
          }}
        >
          <span className="lw-chart__window-label">QUERY WINDOW &middot; {win.len}D</span>
        </div>
      )}
      {/* Corner note — only meaningful when a draggable window exists in Fast. */}
      {showWindow && (
        <div className="lw-chart__note" aria-live="polite">
          Window editing is in Fast view.
        </div>
      )}
    </div>
  );
}
