"use client";

/**
 * TodayView — the default /prudent landing body.
 *
 * This module owns the Today-page surfaces:
 *   - KeyMetrics column (avg valence, uplift, volatility, peak/trough)
 *   - DayTrajectory chart (valence over time with compare overlay)
 *   - RhymeHeatmap (7-day × 12-hour intensity grid)
 *   - TagDonut (share of weighted events)
 *   - ThreadRibbon (30-day history strip)
 *
 * NOT in this file anymore:
 *   - ComposerModal + TweaksPanel. These used to live here but were
 *     route-local as a result — clicking "+ New entry" from any
 *     /prudent sub-route flipped context state but rendered no modal
 *     because today-view only mounts at /prudent itself. They now live
 *     in `app/prudent/layout.tsx` so they mount once for the whole
 *     /prudent tree and work from every route.
 *
 * Why one big file:
 *   These surfaces share a lot of small helpers (Sparkline, LegendDot,
 *   interp, formatHour). Splitting them across files would either duplicate
 *   the helpers or force a third module. Wave 2 agents own the other route
 *   pages; they can cherry-pick the pieces they need from here without
 *   affecting this module's internal cohesion.
 *
 * State ownership:
 *   - `entries`, `text`, `composerOpen`, `readOnlyEntry`, `tweaks` all live
 *     in EngineContext (mounted by app/prudent/layout.tsx).
 *   - Parse state is derived locally via `useParsedNarrative(text)` so each
 *     render reflects the latest composer draft immediately for KeyMetrics
 *     and DayTrajectory, which display the live-parsed numbers even when
 *     the composer is closed.
 */

import { useEffect, useMemo, useRef, useState, Fragment } from "react";
import {
  parseNarrative,
  findRhyme,
  type Event,
  type Point,
  type HistoryDay,
} from "../engine";
import { buildHistoryFromEntries, type StoredEntry } from "../storage";
import { useParsedNarrative } from "../use-parse";
import { useEngine, type CompareMode } from "./engine-context";
import { seedDemoEntries } from "./demo-seed";

// ═══════════════════════════════════════════════════════════════════════
// Root
// ═══════════════════════════════════════════════════════════════════════

export default function TodayView() {
  // TodayView reads a trimmed slice of EngineContext:
  //   - `entries` drives the 30-day ThreadRibbon + buildHistoryFromEntries.
  //   - `text` feeds useParsedNarrative so KeyMetrics / DayTrajectory show
  //     the same live-parsed series as the composer, regardless of whether
  //     the composer is currently open (it can be — but the composer itself
  //     is mounted by app/prudent/layout.tsx now).
  //   - `tweaks` + `setTweak` power the Compare chip in DayTrajectory.
  //   - `openComposer` / `openReadOnly` fire from ThreadRibbon dot clicks.
  //   - `reloadEntries` is used by the demo-seed banner below.
  // The ComposerModal + TweaksPanel renders (and the `composerOpen`,
  // `readOnlyEntry`, `closeComposer`, `persistEntry`, `setText` bindings
  // they needed) moved to the layout — see the module docstring above.
  const {
    entries,
    text,
    tweaks,
    setTweak,
    openComposer,
    openReadOnly,
    reloadEntries,
  } = useEngine();

  // Investor / first-visit helper — when the journal is empty we surface a
  // one-line banner that pops 14 days of pre-seeded entries into storage so
  // heatmap/rhymes/patterns populate immediately. The banner disappears as
  // soon as any entry exists, so normal user flows never see it after the
  // first log.
  const loadDemo = () => {
    seedDemoEntries();
    reloadEntries();
  };
  const showDemoBanner = entries.length === 0;

  // Parse the draft live so KeyMetrics / DayTrajectory reflect the latest
  // composer input even when the modal is closed (the composer shares the
  // same `text` via EngineContext).
  const { events, series } = useParsedNarrative(text);
  const avg = useMemo(
    () => Math.round(series.reduce((a, b) => a + b.v, 0) / series.length),
    [series],
  );
  const peak = useMemo(
    () => series.reduce((a, b) => (b.v > a.v ? b : a), series[0] ?? { v: 50, t: 0 }),
    [series],
  );
  const trough = useMemo(
    () => series.reduce((a, b) => (b.v < a.v ? b : a), series[0] ?? { v: 50, t: 0 }),
    [series],
  );

  const history = useMemo(
    () => buildHistoryFromEntries(entries, avg),
    [entries, avg],
  );
  const rhyme = useMemo(
    () => findRhyme(history.slice(0, -1), series),
    [history, series],
  );

  const yesterday = useMemo(() => {
    const y = history[history.length - 2];
    if (!y) return null;
    return parseNarrative(y.text).series;
  }, [history]);

  const rhymeSeries = useMemo<Point[] | null>(() => {
    if (!rhyme) return null;
    const w = history.slice(rhyme.startIdx, rhyme.startIdx + 7);
    const targetAvg = w.reduce((a, d) => a + d.avg, 0) / w.length;
    const base = parseNarrative(w[3]?.text || "").series;
    const baseAvg = base.reduce((a, b) => a + b.v, 0) / base.length;
    return base.map((p) => ({ t: p.t, v: p.v - baseAvg + targetAvg }));
  }, [rhyme, history]);

  const compareSeries =
    tweaks.compare === "yesterday"
      ? yesterday
      : tweaks.compare === "rhyme"
        ? rhymeSeries
        : null;
  const compareLabel =
    tweaks.compare === "yesterday"
      ? "Yesterday"
      : tweaks.compare === "rhyme"
        ? "Rhyming week (day −" + (history[rhyme?.startIdx ?? 0]?.day ?? "?") + ")"
        : null;

  // Ribbon dot click — route today to the composer, past days to the
  // read-only viewer.
  const onRibbonDotClick = (day: number) => {
    if (day === 0) {
      openComposer();
      return;
    }
    const match = entries.find((e) => e.day === day);
    if (match) openReadOnly(match);
  };

  return (
    <>
      {showDemoBanner && <DemoSeedBanner onLoad={loadDemo} />}
      <div className="prudent-grid-top">
        <KeyMetrics
          series={series}
          events={events}
          history={history}
          avg={avg}
          peak={peak}
          trough={trough}
        />
        <DayTrajectory
          series={series}
          events={events}
          compareSeries={compareSeries}
          compareLabel={compareLabel}
          setCompare={(v) => setTweak("compare", v)}
          compareMode={tweaks.compare}
        />
      </div>

      <div className="prudent-grid-mid">
        <RhymeHeatmap
          history={history}
          rhymeStart={rhyme?.startIdx}
          rhymeScore={rhyme?.score ?? null}
        />
        <TagDonut events={events} />
      </div>

      <ThreadRibbon
        history={history}
        rhymeStart={rhyme?.startIdx}
        onDotClick={onRibbonDotClick}
      />
      {/* ComposerModal + TweaksPanel render at the layout level — see
          app/prudent/layout.tsx — so they mount once for the entire
          /prudent tree and work from every sub-route. */}
    </>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Demo seed banner (first-visit helper)
// ═══════════════════════════════════════════════════════════════════════

/**
 * Thin banner rendered above the today grid when the journal is empty.
 *
 * Purpose: give a first-time visitor (commonly an investor walking the
 * product) a one-click path to seed 14 days of pre-built entries so the
 * heatmap, rhymes, patterns, and sparklines all populate immediately.
 *
 * The banner is entirely additive — it adds one DOM node above the
 * existing grid and disappears as soon as any entry exists, so normal
 * user flows never see it after their first log.
 */
function DemoSeedBanner({ onLoad }: { onLoad: () => void }) {
  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "12px 16px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 12,
        marginBottom: 4,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>
          First time here?
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)" }}>
          Load 14 days of demo data to see the full experience.
        </div>
      </div>
      <button
        onClick={onLoad}
        style={{
          background: "var(--ink)",
          color: "var(--app-bg)",
          padding: "8px 14px",
          borderRadius: 7,
          fontSize: 13,
          fontWeight: 500,
          whiteSpace: "nowrap",
        }}
      >
        Load demo data →
      </button>
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Key metrics column
// ═══════════════════════════════════════════════════════════════════════

interface KeyMetricsProps {
  series: Point[];
  events: Event[];
  history: HistoryDay[];
  avg: number;
  peak: Point;
  trough: Point;
}

function KeyMetrics({ series, events, history, avg, peak, trough }: KeyMetricsProps) {
  const lastN = history.slice(-14).map((d) => d.avg);
  const upliftCount = events.filter((e) => e.delta > 0).length;
  const downCount = events.filter((e) => e.delta < 0).length;
  const avgCompare = Math.round(history.slice(-8, -1).reduce((a, b) => a + b.avg, 0) / 7);
  const variance = Math.round(
    Math.sqrt(series.reduce((a, b) => a + (b.v - avg) ** 2, 0) / series.length),
  );

  // Volatility delta vs the last-7-days baseline. Falls back to a neutral 0
  // when the journal has fewer than 7 prior days — see dashboard commit
  // "slop(prudent): compute volatility delta from prior-week history".
  const priorWeek = history.slice(-8, -1).map((d) => d.avg);
  let volatilityDelta = 0;
  let volatilityDeltaKind: "neutral" | undefined = "neutral";
  if (priorWeek.length >= 7) {
    const wkMean = priorWeek.reduce((a, b) => a + b, 0) / priorWeek.length;
    const wkStd = Math.sqrt(
      priorWeek.reduce((a, b) => a + (b - wkMean) ** 2, 0) / priorWeek.length,
    );
    volatilityDelta = Number((variance - wkStd).toFixed(2));
    volatilityDeltaKind = undefined;
  }

  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "16px 18px 18px 18px",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 4,
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 600 }}>Key metrics</div>
      </div>

      <Metric
        label="Avg valence"
        value={avg}
        unit="/100"
        delta={avg - avgCompare}
        deltaSuffix="% vs 7d"
        sparkline={lastN}
        stroke="var(--accent)"
        fill
      />
      <Metric
        label="Uplift events"
        value={upliftCount}
        unit="ev"
        delta={upliftCount - downCount}
        deltaSuffix="net"
        sparklineCustom={<EventsSpark events={events} />}
      />
      <Metric
        label="Volatility"
        value={variance}
        unit="σ"
        delta={volatilityDelta}
        deltaSuffix="vs wk"
        deltaKind={volatilityDeltaKind}
        sparklineCustom={<VolatilitySpark series={series} stroke="var(--accent)" />}
      />
      <Metric
        label="Peak · trough"
        value={`${Math.round(peak.v)} · ${Math.round(trough.v)}`}
        unit="span"
        delta={Math.round(peak.v - trough.v)}
        deltaSuffix="range"
        deltaKind="neutral"
        sparklineCustom={<PeakTroughSpark series={series} peak={peak} trough={trough} />}
        noborder
      />
    </section>
  );
}

interface MetricProps {
  label: string;
  value: number | string;
  unit: string;
  delta: number;
  deltaSuffix: string;
  sparkline?: number[];
  sparklineCustom?: React.ReactNode;
  stroke?: string;
  fill?: boolean;
  deltaKind?: "neutral";
  noborder?: boolean;
}

// Colored filled triangle glyphs — defined at module scope so React's hooks
// lint doesn't flag them as "component created during render".
const TriUp = () => (
  <svg width="7" height="7" viewBox="0 0 7 7" fill="currentColor">
    <path d="M3.5 1L6.5 6h-6z" />
  </svg>
);
const TriDown = () => (
  <svg width="7" height="7" viewBox="0 0 7 7" fill="currentColor">
    <path d="M3.5 6L6.5 1h-6z" />
  </svg>
);

function Metric({
  label,
  value,
  unit,
  delta,
  deltaSuffix,
  sparkline,
  sparklineCustom,
  stroke = "var(--accent)",
  fill = false,
  deltaKind,
  noborder,
}: MetricProps) {
  const up: boolean | null = deltaKind === "neutral" ? null : delta >= 0;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 120px",
        gap: 14,
        alignItems: "center",
        padding: "16px 0 14px 0",
        borderBottom: noborder ? "none" : "1px solid var(--line)",
      }}
    >
      <div>
        <div
          style={{
            fontSize: 10.5,
            color: "var(--muted)",
            marginBottom: 8,
            fontWeight: 500,
            letterSpacing: "0.02em",
          }}
        >
          {label}
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 5 }}>
          <div
            className="tnum"
            style={{
              fontSize: 30,
              fontWeight: 600,
              letterSpacing: "-0.03em",
              color: "var(--ink)",
              lineHeight: 1,
            }}
          >
            {value}
          </div>
          <div
            className="mono"
            style={{
              fontSize: 10.5,
              color: "var(--faint)",
              fontWeight: 500,
              letterSpacing: "0.02em",
            }}
          >
            {unit}
          </div>
        </div>
        <div
          className="tnum"
          style={{
            fontSize: 11,
            marginTop: 8,
            color: up === null ? "var(--muted)" : up ? "var(--green)" : "var(--warm-strong)",
            fontWeight: 500,
            display: "inline-flex",
            alignItems: "center",
            gap: 5,
          }}
        >
          {up === null ? (
            <span
              style={{
                width: 5,
                height: 5,
                background: "currentColor",
                borderRadius: "50%",
                display: "inline-block",
                opacity: 0.6,
              }}
            />
          ) : up ? (
            <TriUp />
          ) : (
            <TriDown />
          )}
          <span>{Math.abs(delta).toFixed(delta % 1 === 0 ? 0 : 2)}</span>
          <span style={{ color: "var(--faint)", fontWeight: 400, marginLeft: 2 }}>
            {deltaSuffix}
          </span>
        </div>
      </div>
      <div style={{ width: 120, height: 52, display: "flex", alignItems: "center" }}>
        {sparklineCustom || (
          <Sparkline data={sparkline ?? []} stroke={stroke} fill={fill} width={120} height={48} />
        )}
      </div>
    </div>
  );
}

interface SparklineProps {
  data: number[];
  stroke?: string;
  fill?: boolean;
  width?: number;
  height?: number;
}

function Sparkline({
  data,
  stroke = "var(--accent)",
  fill = false,
  width = 120,
  height = 40,
}: SparklineProps) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const pad = 4;
  const W = width;
  const H = height - pad * 2;
  const step = W / (data.length - 1);
  const y = (v: number) => pad + (1 - (v - min) / (max - min || 1)) * H;
  const pts = data.map((v, i) => [i * step, y(v)] as const);
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const mx = (x0 + x1) / 2;
    d += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
  }
  const fillPath = `${d} L ${W} ${height} L 0 ${height} Z`;
  const last = pts[pts.length - 1];
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      {fill && <path d={fillPath} fill={stroke} opacity="0.12" />}
      <path d={d} fill="none" stroke={stroke} strokeWidth="1.5" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r="2.5" fill={stroke} />
    </svg>
  );
}

function EventsSpark({ events }: { events: Event[] }) {
  const maxT = 16 * 60;
  const width = 120;
  const height = 48;
  return (
    <svg width={width} height={height}>
      <line
        x1="0"
        x2={width}
        y1={height / 2}
        y2={height / 2}
        stroke="var(--line-mid)"
        strokeWidth="1"
      />
      {events.map((e, i) => {
        const x = (e.time / maxT) * width;
        const up = e.delta > 0;
        const mag = Math.min(1, Math.abs(e.delta) / 20);
        const h = Math.max(2, mag * (height / 2 - 3));
        return (
          <rect
            key={i}
            x={x - 1.5}
            y={up ? height / 2 - h : height / 2}
            width="3"
            height={h}
            fill={up ? "var(--green)" : "var(--warm-strong)"}
            rx="1.5"
          />
        );
      })}
    </svg>
  );
}

function VolatilitySpark({ series, stroke }: { series: Point[]; stroke: string }) {
  const data: number[] = [];
  const w = 12;
  for (let i = w; i < series.length; i += Math.floor(series.length / 12)) {
    const slice = series.slice(i - w, i).map((p) => p.v);
    const mean = slice.reduce((a, b) => a + b, 0) / slice.length;
    const std = Math.sqrt(slice.reduce((a, b) => a + (b - mean) ** 2, 0) / slice.length);
    data.push(std);
  }
  return <Sparkline data={data} stroke={stroke} fill width={120} height={48} />;
}

function PeakTroughSpark({
  series,
  peak,
  trough,
}: {
  series: Point[];
  peak: Point;
  trough: Point;
}) {
  const width = 120;
  const height = 48;
  const min = 0;
  const max = 100;
  const pts = series
    .filter((_, i) => i % 5 === 0)
    .map((p, i, arr) => [
      (i / (arr.length - 1)) * width,
      (1 - (p.v - min) / (max - min)) * height,
    ] as const);
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const mx = (x0 + x1) / 2;
    d += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
  }
  const maxT = 16 * 60;
  const px = (peak.t / maxT) * width;
  const tx = (trough.t / maxT) * width;
  return (
    <svg width={width} height={height}>
      <path
        d={d}
        fill="none"
        stroke="var(--muted)"
        strokeWidth="1"
        strokeLinecap="round"
        opacity="0.45"
      />
      <circle
        cx={px}
        cy={(1 - peak.v / 100) * height}
        r="3.25"
        fill="var(--green)"
        stroke="var(--panel)"
        strokeWidth="1.5"
      />
      <circle
        cx={tx}
        cy={(1 - trough.v / 100) * height}
        r="3.25"
        fill="var(--warm-strong)"
        stroke="var(--panel)"
        strokeWidth="1.5"
      />
    </svg>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Day Trajectory — main chart
// ═══════════════════════════════════════════════════════════════════════

interface DayTrajectoryProps {
  series: Point[];
  events: Event[];
  compareSeries: Point[] | null;
  compareLabel: string | null;
  setCompare: (v: CompareMode) => void;
  compareMode: CompareMode;
}

function DayTrajectory({
  series,
  events,
  compareSeries,
  compareLabel,
  setCompare,
  compareMode,
}: DayTrajectoryProps) {
  const [hover, setHover] = useState<{ t: number; v: number; x: number; y: number } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(780);
  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setWidth(Math.max(500, e.contentRect.width));
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "16px 18px 18px 18px",
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 8,
          gap: 12,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Valence over time</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
            Integrated trajectory · 5-min resolution · today vs comparison
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
          <button
            onClick={() => setCompare(compareMode === "rhyme" ? "yesterday" : "rhyme")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              padding: "6px 11px",
              fontSize: 12,
              background: "var(--panel)",
              border: "1px solid var(--line-mid)",
              borderRadius: 7,
              color: "var(--muted)",
              fontWeight: 500,
            }}
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M2 4h8l-2-2M10 8H2l2 2" />
            </svg>
            <span style={{ color: "var(--muted)" }}>Compare ·</span>
            <span style={{ color: "var(--ink)", fontWeight: 500 }}>
              {compareMode === "yesterday"
                ? "Yesterday"
                : compareMode === "rhyme"
                  ? "Rhyming week"
                  : "None"}
            </span>
            <svg width="8" height="8" viewBox="0 0 9 9" fill="none" stroke="currentColor" strokeWidth="1.3" style={{ opacity: 0.6 }}>
              <path d="M2 3.5L4.5 6 7 3.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>

      <div ref={wrapRef} style={{ position: "relative", marginTop: 8 }}>
        <TrajectoryChart
          series={series}
          events={events}
          compareSeries={compareSeries}
          width={width}
          height={280}
          hover={hover}
          setHover={setHover}
        />
      </div>

      <div
        style={{
          display: "flex",
          gap: 18,
          paddingTop: 6,
          borderTop: "1px solid var(--line)",
          marginTop: 4,
          fontSize: 12,
          color: "var(--muted)",
        }}
      >
        <LegendDot color="var(--accent)" label="Today · narrative" />
        {compareSeries && compareLabel && (
          <LegendDot color="var(--accent-mid)" label={compareLabel} dashed />
        )}
        <LegendDot color="var(--green)" label="Uplift event" dotOnly />
        <LegendDot color="var(--warm-strong)" label="Downturn event" dotOnly />
      </div>
    </section>
  );
}

function LegendDot({
  color,
  label,
  dashed,
  dotOnly,
}: {
  color: string;
  label: string;
  dashed?: boolean;
  dotOnly?: boolean;
}) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      {dotOnly ? (
        <span
          style={{
            width: 6,
            height: 6,
            background: color,
            borderRadius: "50%",
            display: "inline-block",
          }}
        />
      ) : (
        <svg width="18" height="6">
          <line
            x1="0"
            x2="18"
            y1="3"
            y2="3"
            stroke={color}
            strokeWidth="2"
            strokeDasharray={dashed ? "3 2" : ""}
          />
        </svg>
      )}
      <span>{label}</span>
    </span>
  );
}

interface TrajectoryChartProps {
  series: Point[];
  events: Event[];
  compareSeries: Point[] | null;
  width: number;
  height: number;
  hover: { t: number; v: number; x: number; y: number } | null;
  setHover: (h: { t: number; v: number; x: number; y: number } | null) => void;
}

function TrajectoryChart({
  series,
  events,
  compareSeries,
  width,
  height,
  hover,
  setHover,
}: TrajectoryChartProps) {
  const pad = { top: 14, right: 18, bottom: 28, left: 30 };
  const W = width - pad.left - pad.right;
  const H = height - pad.top - pad.bottom;
  const maxT = 16 * 60;
  const xAt = (t: number) => pad.left + (t / maxT) * W;
  const yAt = (v: number) => pad.top + (1 - v / 100) * H;

  const gridY = [0, 25, 50, 75, 100];
  const gridX = [0, 3 * 60, 6 * 60, 9 * 60, 12 * 60, 15 * 60];

  const smooth = (pts: Point[]) => {
    if (pts.length < 2) return "";
    let d = `M ${xAt(pts[0].t)} ${yAt(pts[0].v)}`;
    for (let i = 1; i < pts.length; i++) {
      const x0 = xAt(pts[i - 1].t);
      const y0 = yAt(pts[i - 1].v);
      const x1 = xAt(pts[i].t);
      const y1 = yAt(pts[i].v);
      const mx = (x0 + x1) / 2;
      d += ` C ${mx} ${y0}, ${mx} ${y1}, ${x1} ${y1}`;
    }
    return d;
  };

  const todayPath = smooth(series);
  const comparePath = compareSeries ? smooth(compareSeries) : "";
  const areaPath = series.length
    ? `${todayPath} L ${xAt(series[series.length - 1].t)} ${yAt(0)} L ${xAt(series[0].t)} ${yAt(0)} Z`
    : "";

  const gradId = "prudentTodayGrad";

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const t = ((x - pad.left) / W) * maxT;
    if (t < 0 || t > maxT) {
      setHover(null);
      return;
    }
    let best = series[0];
    let bestD = Infinity;
    for (const p of series) {
      const d = Math.abs(p.t - t);
      if (d < bestD) {
        bestD = d;
        best = p;
      }
    }
    setHover({ t: best.t, v: best.v, x: xAt(best.t), y: yAt(best.v) });
  };

  return (
    <svg
      width={width}
      height={height}
      onMouseMove={onMove}
      onMouseLeave={() => setHover(null)}
      style={{ display: "block", cursor: "crosshair" }}
    >
      <defs>
        <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>

      {gridY.map((v) => (
        <g key={v}>
          <line
            x1={pad.left}
            x2={pad.left + W}
            y1={yAt(v)}
            y2={yAt(v)}
            stroke="var(--line-mid)"
            strokeWidth="1"
            strokeDasharray={v === 0 || v === 100 ? "" : "1 3"}
            opacity={v === 50 ? 0.7 : 0.45}
          />
          <text
            x={pad.left - 8}
            y={yAt(v) + 3}
            textAnchor="end"
            fontSize="9.5"
            fill="var(--faint)"
            className="tnum mono"
            fontWeight="500"
          >
            {v}
          </text>
        </g>
      ))}

      {gridX.map((t) => (
        <text
          key={t}
          x={xAt(t)}
          y={pad.top + H + 16}
          textAnchor="middle"
          fontSize="9.5"
          fill="var(--faint)"
          className="mono"
          fontWeight="500"
        >
          {formatHour(t)}
        </text>
      ))}

      <path d={areaPath} fill={`url(#${gradId})`} />

      {compareSeries && (
        <path
          d={comparePath}
          fill="none"
          stroke="var(--accent-mid)"
          strokeWidth="1.75"
          strokeDasharray="4 3"
          strokeLinecap="round"
          opacity="0.9"
        />
      )}

      <path
        d={todayPath}
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {events.map((ev, i) => {
        const val = interp(series, ev.time);
        const up = ev.delta > 0;
        const col = up ? "var(--green)" : "var(--warm-strong)";
        const labelY = yAt(val) - 18 - (i % 2) * 8;
        return (
          <g key={i}>
            <line
              x1={xAt(ev.time)}
              x2={xAt(ev.time)}
              y1={yAt(val) - 4}
              y2={labelY + 4}
              stroke={col}
              strokeWidth="0.75"
              opacity="0.35"
            />
            <circle
              cx={xAt(ev.time)}
              cy={yAt(val)}
              r="4"
              fill="var(--accent)"
              stroke="var(--panel)"
              strokeWidth="2"
            />
            <text
              x={xAt(ev.time)}
              y={labelY}
              textAnchor="middle"
              fontSize="9"
              fill={col}
              className="tnum mono"
              fontWeight="600"
              letterSpacing="-0.01em"
            >
              {up ? "+" : ""}
              {ev.delta.toFixed(0)}
            </text>
          </g>
        );
      })}

      {hover && (
        <g>
          <line
            x1={hover.x}
            x2={hover.x}
            y1={pad.top}
            y2={pad.top + H}
            stroke="var(--ink)"
            strokeWidth="1"
            opacity="0.18"
            strokeDasharray="2 2"
          />
          <circle cx={hover.x} cy={hover.y} r="5" fill="var(--accent)" stroke="var(--panel)" strokeWidth="2" />
          <g>
            <rect
              x={Math.min(width - 100, hover.x + 8)}
              y={Math.max(pad.top, hover.y - 32)}
              width="92"
              height="26"
              rx="4"
              fill="var(--ink)"
            />
            <text
              x={Math.min(width - 100, hover.x + 8) + 46}
              y={Math.max(pad.top, hover.y - 32) + 11}
              textAnchor="middle"
              fontSize="10"
              fill="var(--app-bg)"
              className="tnum"
              fontWeight="600"
            >
              {formatHour(hover.t, true)}
            </text>
            <text
              x={Math.min(width - 100, hover.x + 8) + 46}
              y={Math.max(pad.top, hover.y - 32) + 22}
              textAnchor="middle"
              fontSize="10"
              fill="var(--faint)"
              className="tnum"
            >
              valence {Math.round(hover.v)}
            </text>
          </g>
        </g>
      )}
    </svg>
  );
}

function interp(pts: Point[], t: number): number {
  if (!pts.length) return 50;
  if (t <= pts[0].t) return pts[0].v;
  if (t >= pts[pts.length - 1].t) return pts[pts.length - 1].v;
  for (let i = 1; i < pts.length; i++) {
    if (pts[i].t >= t) {
      const a = pts[i - 1];
      const b = pts[i];
      const k = (t - a.t) / (b.t - a.t || 1);
      return a.v + k * (b.v - a.v);
    }
  }
  return 50;
}

function formatHour(minutes: number, full = false): string {
  const totalMin = 7 * 60 + minutes;
  const h24 = Math.floor(totalMin / 60) % 24;
  const m = totalMin % 60;
  const ampm = h24 >= 12 ? "PM" : "AM";
  const h12 = ((h24 + 11) % 12) + 1;
  if (full) return `${h12}:${m.toString().padStart(2, "0")} ${ampm}`;
  return `${h12} ${ampm}`;
}

// ═══════════════════════════════════════════════════════════════════════
// Rhyme heatmap
// ═══════════════════════════════════════════════════════════════════════

function RhymeHeatmap({
  history,
  rhymeStart,
  rhymeScore,
}: {
  history: HistoryDay[];
  rhymeStart: number | undefined;
  rhymeScore: number | null;
}) {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const week = history.slice(-7);

  const cells = week.map((d) => {
    let seed = (d.day + 17) * 37;
    const rand = () => {
      seed = (seed * 9301 + 49297) % 233280;
      return seed / 233280;
    };
    const base = d.avg / 100;
    return Array.from({ length: 12 }, (_, col) => {
      const tn = col / 11;
      const shape = 0.35 * Math.sin(tn * Math.PI - 0.4) + 0.15 * Math.cos(tn * Math.PI * 2);
      const v = base * 0.6 + shape * 0.35 + (rand() - 0.5) * 0.15;
      return { v: Math.max(0, Math.min(1, v)), day: d.day };
    });
  });

  const isRhymeRow = (row: number): boolean => {
    if (rhymeStart === null || rhymeStart === undefined) return false;
    const histIdx = history.length - 7 + row;
    return histIdx >= rhymeStart && histIdx < rhymeStart + 7;
  };

  const hours = Array.from({ length: 12 }, (_, i) => {
    const hr = (8 + i) % 12 === 0 ? 12 : (8 + i) % 12;
    const suf = i + 8 < 12 ? "AM" : "PM";
    return `${hr}${suf}`;
  });

  const STEP_BG = [
    "rgba(59,130,246,0.06)",
    "rgba(59,130,246,0.16)",
    "rgba(59,130,246,0.32)",
    "rgba(59,130,246,0.58)",
    "rgba(59,130,246,1.0)",
  ];
  const stepFor = (v: number): number => {
    if (v < 0.15) return 0;
    if (v < 0.35) return 1;
    if (v < 0.55) return 2;
    if (v < 0.75) return 3;
    return 4;
  };
  const stepText = (step: number): string =>
    step >= 3 ? "#fff" : step === 0 ? "var(--faint)" : "var(--ink)";

  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "14px 16px 16px 16px",
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
          gap: 12,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Busiest valence</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
            Last 7 days · hour-of-day intensity
          </div>
        </div>
        <div
          style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: 10.5,
              color: "var(--muted)",
              fontVariantNumeric: "tabular-nums",
            }}
          >
            <span>0</span>
            <div style={{ display: "flex", gap: 2 }}>
              {STEP_BG.map((bg, i) => (
                <div
                  key={i}
                  style={{
                    width: 12,
                    height: 12,
                    background: bg,
                    borderRadius: 3,
                  }}
                />
              ))}
            </div>
            <span>100</span>
          </div>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "42px repeat(12, 1fr)",
          gap: 5,
          alignItems: "center",
        }}
      >
        <div />
        {cells.map((row, ri) => (
          <Fragment key={ri}>
            <div
              style={{
                fontSize: 11,
                color: isRhymeRow(ri) ? "var(--warm-strong)" : "var(--muted)",
                fontWeight: isRhymeRow(ri) ? 600 : 500,
                textAlign: "right",
                paddingRight: 8,
                letterSpacing: "0.01em",
              }}
            >
              {days[ri]}
            </div>
            {row.map((cell, ci) => {
              const step = stepFor(cell.v);
              const val = Math.round(cell.v * 10);
              return (
                <div
                  key={ci}
                  style={{
                    aspectRatio: "1.3",
                    background: STEP_BG[step],
                    color: stepText(step),
                    borderRadius: 7,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 11,
                    fontWeight: step >= 3 ? 600 : 500,
                    fontVariantNumeric: "tabular-nums",
                    boxShadow: isRhymeRow(ri)
                      ? "inset 0 0 0 1.5px rgba(249,115,22,0.45)"
                      : "none",
                    transition: "transform 120ms ease",
                  }}
                >
                  {val}
                </div>
              );
            })}
          </Fragment>
        ))}
        <div />
        {hours.map((h, i) => (
          <div
            key={i}
            className="mono"
            style={{
              fontSize: 9.5,
              color: "var(--faint)",
              textAlign: "center",
              paddingTop: 6,
              fontVariantNumeric: "tabular-nums",
              fontWeight: 500,
            }}
          >
            {h}
          </div>
        ))}
      </div>

      {rhymeStart !== null && rhymeStart !== undefined && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginTop: 14,
            padding: "10px 12px",
            borderRadius: 8,
            background: "rgba(249,115,22,0.07)",
            border: "1px solid rgba(249,115,22,0.22)",
            fontSize: 12,
            color: "var(--ink)",
          }}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 16 16"
            fill="none"
            stroke="var(--warm-strong)"
            strokeWidth="1.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 8a5 5 0 019-3L13 6M13 8a5 5 0 01-9 3L3 10" />
            <path d="M13 3v3h-3M3 13v-3h3" />
          </svg>
          <span style={{ fontWeight: 500 }}>
            This week rhymes with day −{history[rhymeStart].day} → −
            {history[rhymeStart + 6]?.day}.
          </span>
          <span style={{ color: "var(--muted)", fontWeight: 500 }} className="tnum">
            RMSE {rhymeScore !== null ? (-rhymeScore).toFixed(2) : "—"}
          </span>
          <span style={{ flex: 1 }} />
        </div>
      )}
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Tag donut
// ═══════════════════════════════════════════════════════════════════════

function TagDonut({ events }: { events: Event[] }) {
  const totals: Record<string, number> = {};
  events.forEach((e) => {
    totals[e.tag] = (totals[e.tag] || 0) + Math.abs(e.delta);
  });
  const entries = Object.entries(totals).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((a, b) => a + b[1], 0) || 1;

  const palette = [
    "#3B82F6",
    "#F97316",
    "#16A34A",
    "#8B5CF6",
    "#0E7490",
    "#EAB308",
    "#64748B",
  ];

  const slices = entries.map((e, i) => ({
    label: e[0],
    value: e[1],
    frac: e[1] / total,
    color: palette[i % palette.length],
  }));

  const size = 220;
  const cx = size / 2;
  const cy = size / 2;
  const r = 82;
  const strokeW = 18;
  const C = 2 * Math.PI * r;
  const gapDeg = 4;
  const gapFrac = gapDeg / 360;

  const arcs = slices.reduce<
    { label: string; value: number; frac: number; color: string; arcLen: number; rot: number }[]
  >((acc, s) => {
    const offset = acc.reduce((sum, a) => sum + a.frac * 360, 0);
    const arcFrac = Math.max(0, s.frac - gapFrac);
    const arcLen = arcFrac * C;
    const rot = -90 + offset + gapDeg / 2;
    acc.push({ ...s, arcLen, rot });
    return acc;
  }, []);

  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "14px 16px 16px 16px",
        minWidth: 0,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 10,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Tag mix</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
            Share of today&apos;s weighted events
          </div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 18, alignItems: "center" }}>
        <svg width={size} height={size} style={{ flexShrink: 0 }}>
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke="var(--line)"
            strokeWidth={strokeW}
            opacity={arcs.length === 0 ? 1 : 0.5}
          />
          {arcs.map((a, i) => (
            <g key={i} transform={`rotate(${a.rot} ${cx} ${cy})`}>
              <circle
                cx={cx}
                cy={cy}
                r={r}
                fill="none"
                stroke={a.color}
                strokeWidth={strokeW}
                strokeLinecap="round"
                strokeDasharray={`${a.arcLen} ${C - a.arcLen}`}
                strokeDashoffset="0"
              />
            </g>
          ))}
          <text
            x={cx}
            y={cy - 10}
            textAnchor="middle"
            fontSize="10"
            fill="var(--muted)"
            letterSpacing="0.06em"
            style={{ textTransform: "uppercase", fontWeight: 500 }}
          >
            Events
          </text>
          <text
            x={cx}
            y={cy + 14}
            textAnchor="middle"
            fontSize="28"
            fontWeight="600"
            fill="var(--ink)"
            className="tnum"
            letterSpacing="-0.02em"
          >
            {events.length}
          </text>
          <text
            x={cx}
            y={cy + 30}
            textAnchor="middle"
            fontSize="10.5"
            fill="var(--green)"
            className="tnum"
            fontWeight={500}
          >
            + {events.filter((e) => e.delta > 0).length} uplift
          </text>
        </svg>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 9 }}>
          {arcs.map((a, i) => (
            <div
              key={i}
              style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}
            >
              <span
                style={{
                  width: 9,
                  height: 9,
                  background: a.color,
                  borderRadius: "50%",
                  display: "inline-block",
                  flexShrink: 0,
                }}
              />
              <span
                style={{
                  color: "var(--ink)",
                  textTransform: "capitalize",
                  fontWeight: 500,
                }}
              >
                {a.label}
              </span>
              <span style={{ flex: 1 }} />
              <span
                style={{ color: "var(--muted)", fontWeight: 500 }}
                className="tnum"
              >
                {Math.round(a.frac * 100)}%
              </span>
            </div>
          ))}
          {arcs.length === 0 && (
            <div style={{ fontSize: 12, color: "var(--faint)" }}>
              No tags yet — write an entry to populate.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// Thread ribbon
// ═══════════════════════════════════════════════════════════════════════

function ThreadRibbon({
  history,
  rhymeStart,
  onDotClick,
}: {
  history: HistoryDay[];
  rhymeStart: number | undefined;
  onDotClick?: (day: number) => void;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "16px 18px 18px 18px",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
          gap: 12,
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Thread · 30 days</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
            {hoverIdx !== null ? (
              <span
                className="serif"
                style={{
                  fontFamily: "var(--serif)",
                  fontStyle: "italic",
                  fontSize: 13,
                  color: "var(--ink)",
                  letterSpacing: "-0.005em",
                }}
              >
                day −{history[hoverIdx].day} — &ldquo;{history[hoverIdx].text.slice(0, 70)}…&rdquo;
              </span>
            ) : (
              "Each dot is a day's average valence · hover to read the narrative"
            )}
          </div>
        </div>
      </div>
      <HistorySvg
        history={history}
        rhymeStart={rhymeStart}
        onHover={setHoverIdx}
        hoverIdx={hoverIdx}
        onDotClick={onDotClick}
      />
    </section>
  );
}

function HistorySvg({
  history,
  rhymeStart,
  onHover,
  hoverIdx,
  onDotClick,
}: {
  history: HistoryDay[];
  rhymeStart: number | undefined;
  onHover: (i: number | null) => void;
  hoverIdx: number | null;
  onDotClick?: (day: number) => void;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000);
  useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setWidth(Math.max(600, e.contentRect.width));
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);
  const h = 100;
  const pad = { l: 20, r: 20, t: 16, b: 20 };
  const W = width - pad.l - pad.r;
  const H = h - pad.t - pad.b;
  const bw = W / history.length;
  const xAt = (i: number) => pad.l + i * bw + bw / 2;
  const yAt = (v: number) => pad.t + (1 - v / 100) * H;

  const pts = history.map((d, i) => ({ x: xAt(i), y: yAt(d.avg), d, i }));
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) {
    const p0 = pts[i - 1];
    const p1 = pts[i];
    const mx = (p0.x + p1.x) / 2;
    d += ` C ${mx} ${p0.y}, ${mx} ${p1.y}, ${p1.x} ${p1.y}`;
  }
  const areaD = `${d} L ${pts[pts.length - 1].x} ${yAt(0)} L ${pts[0].x} ${yAt(0)} Z`;

  return (
    <div ref={wrapRef}>
      <svg width={width} height={h} style={{ display: "block" }}>
        <defs>
          <linearGradient id="prudentThreadGrad" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line
          x1={pad.l}
          x2={pad.l + W}
          y1={yAt(50)}
          y2={yAt(50)}
          stroke="var(--line)"
          strokeDasharray="3 3"
        />
        {rhymeStart !== null && rhymeStart !== undefined && (
          <>
            <rect
              x={pad.l + rhymeStart * bw}
              y={pad.t - 6}
              width={bw * 7}
              height={H + 12}
              fill="var(--warm)"
              opacity="0.09"
              rx="6"
            />
            <rect
              x={pad.l + rhymeStart * bw}
              y={pad.t - 6}
              width={bw * 7}
              height={H + 12}
              fill="none"
              stroke="var(--warm-strong)"
              strokeWidth="1"
              opacity="0.28"
              rx="6"
            />
          </>
        )}
        <path d={areaD} fill="url(#prudentThreadGrad)" />
        <path d={d} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" />
        {pts.map((p) => (
          <g
            key={p.i}
            onMouseEnter={() => onHover(p.i)}
            onMouseLeave={() => onHover(null)}
            onClick={() => onDotClick?.(p.d.day)}
            style={{ cursor: onDotClick ? "pointer" : "default" }}
          >
            <rect x={pad.l + p.i * bw} y={pad.t} width={bw} height={H} fill="transparent" />
            <circle
              cx={p.x}
              cy={p.y}
              r={p.d.day === 0 ? 4.5 : hoverIdx === p.i ? 3.5 : 2}
              fill={p.d.day === 0 ? "var(--accent)" : "var(--panel)"}
              stroke="var(--accent)"
              strokeWidth={p.d.day === 0 ? 2 : 1.4}
            />
          </g>
        ))}
        <text
          x={pad.l}
          y={h - 4}
          fontSize="10"
          fill="var(--faint)"
          className="mono"
          fontWeight="500"
        >
          30d
        </text>
        <text
          x={pad.l + W / 2}
          y={h - 4}
          textAnchor="middle"
          fontSize="10"
          fill="var(--faint)"
          className="mono"
          fontWeight="500"
        >
          15d
        </text>
        <text
          x={pad.l + W}
          y={h - 4}
          textAnchor="end"
          fontSize="10"
          fill="var(--faint)"
          className="mono"
          fontWeight="500"
        >
          today
        </text>
      </svg>
    </div>
  );
}

// Silence unused-import warning for types that readers commonly expect here.
export type { StoredEntry };
