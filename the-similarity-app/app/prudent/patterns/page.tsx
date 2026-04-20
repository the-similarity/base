"use client";

/**
 * /prudent/patterns — statistical insights grid.
 *
 * Six cards that each compress one slice of the user's data into a
 * number + a shape + a one-line interpretation. Investor-readable in
 * under 5 seconds per card.
 */

import { useMemo } from "react";
import { useEngine } from "../_components/engine-context";
import type { StoredEntry } from "../storage";
import type { Point } from "../engine";

export default function PatternsPage() {
  const { entries, openComposer } = useEngine();

  const stats = useMemo(() => computeAll(entries), [entries]);

  if (entries.length < 5) return <EmptyState have={entries.length} onCompose={openComposer} />;

  return (
    <div
      className="prudent-patterns-page"
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
        gap: 16,
      }}
    >
      <WeeklyShapeCard avgs={stats.weekday} />
      <DayShapeCard shape={stats.hourly} peakT={stats.peakHour} troughT={stats.troughHour} />
      <StabilityCard sigma={stats.sigma30} weekly={stats.sigmaWeekly} />
      <MomentumCard r={stats.autocorr} pairs={stats.consecutivePairs} />
      <AMPMCard am={stats.amAvg} pm={stats.pmAvg} />
      <EventCadenceCard avgPerDay={stats.eventsAvg} hist={stats.eventsHist} />

      {/*
        Scoped dark-mode polish for /patterns.

        The page already uses grid-template-columns: repeat(auto-fit, minmax(320px, 1fr))
        so it reflows cleanly at every viewport without extra media queries. The only
        outstanding issue is dark-mode chart contrast: radar rings/spokes and axis
        midlines use var(--line) (#23262B in dark) at 0.4-0.6 opacity which
        effectively vanishes against a #17191C panel. Override stroke to a brighter
        --line-mid equivalent for SVG primitives inside this page in dark mode.
      */}
      <style>{`
        .prudent-root.prudent-dark .prudent-patterns-page svg line[stroke="var(--line)"],
        .prudent-root.prudent-dark .prudent-patterns-page svg circle[stroke="var(--line)"] {
          stroke: var(--line-mid) !important;
          opacity: 0.9 !important;
        }
        /* The event cadence histogram uses var(--line-mid) bars on empty slots
           through the Timeline helper; in dark these are already visible. The
           bars in stability/cadence cards draw --accent at 0.8 opacity which
           holds up well against a dark panel, so no additional overrides. */
      `}</style>
    </div>
  );
}

// ─── Card 1: weekly shape ─────────────────────────────────────────────

function WeeklyShapeCard({ avgs }: { avgs: number[] }) {
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const validValues = avgs.filter((v) => !Number.isNaN(v));
  if (validValues.length === 0) return <Card title="Your week" subtitle="no data"><span /></Card>;
  const max = Math.max(...validValues);
  const min = Math.min(...validValues);
  const bestIdx = avgs.indexOf(max);
  const worstIdx = avgs.indexOf(min);

  // radar points: 7 spokes
  const cx = 140;
  const cy = 130;
  const radius = 90;
  const pts = avgs.map((v, i) => {
    const angle = (i / 7) * Math.PI * 2 - Math.PI / 2;
    const r = Number.isNaN(v) ? 0 : (v / 100) * radius;
    return [cx + Math.cos(angle) * r, cy + Math.sin(angle) * r];
  });
  const polygonD = pts.map(([x, y]) => `${x},${y}`).join(" ");

  return (
    <Card title="Your week" subtitle="avg valence by weekday">
      <svg width={280} height={260} style={{ display: "block", margin: "0 auto" }}>
        {/* rings */}
        {[0.25, 0.5, 0.75, 1].map((r) => (
          <circle
            key={r}
            cx={cx}
            cy={cy}
            r={radius * r}
            fill="none"
            stroke="var(--line)"
            strokeWidth="1"
            opacity={0.6}
          />
        ))}
        {/* spokes + labels */}
        {days.map((d, i) => {
          const a = (i / 7) * Math.PI * 2 - Math.PI / 2;
          const lx = cx + Math.cos(a) * (radius + 14);
          const ly = cy + Math.sin(a) * (radius + 14);
          return (
            <g key={i}>
              <line
                x1={cx}
                y1={cy}
                x2={cx + Math.cos(a) * radius}
                y2={cy + Math.sin(a) * radius}
                stroke="var(--line)"
                strokeWidth="1"
                opacity={0.4}
              />
              <text
                x={lx}
                y={ly}
                textAnchor="middle"
                dy="0.35em"
                fontSize="10"
                fill="var(--muted)"
                fontWeight={500}
              >
                {d}
              </text>
            </g>
          );
        })}
        {/* shape */}
        <polygon points={polygonD} fill="var(--accent)" fillOpacity="0.16" stroke="var(--accent)" strokeWidth="2" />
        {pts.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="3" fill="var(--accent)" />
        ))}
      </svg>
      <Interpretation>
        {days[bestIdx]}s average <b>{Math.round(max)}</b>; {days[worstIdx]}s <b>{Math.round(min)}</b>.
      </Interpretation>
    </Card>
  );
}

// ─── Card 2: day shape ────────────────────────────────────────────────

function DayShapeCard({ shape, peakT, troughT }: { shape: Point[]; peakT: number; troughT: number }) {
  const W = 280;
  const H = 140;
  const pad = 10;
  if (shape.length < 2) return <Card title="Your day" subtitle="no data"><span /></Card>;
  const maxT = shape[shape.length - 1].t;
  const x = (t: number) => pad + (t / maxT) * (W - pad * 2);
  const y = (v: number) => pad + (1 - v / 100) * (H - pad * 2);
  let d = `M ${x(shape[0].t)} ${y(shape[0].v)}`;
  for (let i = 1; i < shape.length; i++) {
    const x0 = x(shape[i - 1].t);
    const x1 = x(shape[i].t);
    const mx = (x0 + x1) / 2;
    d += ` C ${mx} ${y(shape[i - 1].v)}, ${mx} ${y(shape[i].v)}, ${x1} ${y(shape[i].v)}`;
  }
  const areaD = `${d} L ${x(maxT)} ${H} L ${x(0)} ${H} Z`;

  return (
    <Card title="Your day" subtitle="avg shape, hour by hour">
      <svg width={W} height={H + 24} style={{ display: "block", margin: "8px auto" }}>
        <defs>
          <linearGradient id="dayg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.2" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1={pad} x2={W - pad} y1={y(50)} y2={y(50)} stroke="var(--line)" strokeDasharray="3 3" />
        <path d={areaD} fill="url(#dayg)" />
        <path d={d} fill="none" stroke="var(--accent)" strokeWidth="2" />
        <text x={pad} y={H + 16} fontSize="9" fill="var(--faint)">
          7 AM
        </text>
        <text x={W - pad} y={H + 16} fontSize="9" fill="var(--faint)" textAnchor="end">
          11 PM
        </text>
      </svg>
      <Interpretation>
        You peak around <b>{fmtHourOfDay(peakT)}</b>; the dip bottoms at <b>{fmtHourOfDay(troughT)}</b>.
      </Interpretation>
    </Card>
  );
}

// ─── Card 3: stability ────────────────────────────────────────────────

function StabilityCard({ sigma, weekly }: { sigma: number; weekly: number[] }) {
  const label = sigma < 8 ? "steady" : sigma < 14 ? "rolling" : "volatile";
  const max = Math.max(...weekly, 20);
  return (
    <Card title="Stability" subtitle="valence σ over 30 days">
      <BigNum value={sigma.toFixed(1)} unit="σ" />
      <WordChip>{label}</WordChip>
      <div style={{ display: "flex", gap: 8, alignItems: "flex-end", height: 52, marginTop: 10 }}>
        {weekly.map((w, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              height: `${Math.min(100, (w / max) * 100)}%`,
              background: "var(--accent)",
              borderRadius: 3,
              opacity: 0.8,
            }}
          />
        ))}
      </div>
      <Interpretation>
        Last 4 weeks: <b>{weekly.map((w) => w.toFixed(1)).join(" · ")}</b>.
      </Interpretation>
    </Card>
  );
}

// ─── Card 4: momentum ────────────────────────────────────────────────

function MomentumCard({ r, pairs }: { r: number; pairs: Array<[number, number]> }) {
  const label =
    Math.abs(r) < 0.2 ? "each day is its own" : Math.abs(r) < 0.5 ? "soft carry-over" : "momentum is real";
  return (
    <Card title="Momentum" subtitle="does today predict tomorrow?">
      <BigNum value={r.toFixed(2)} unit="r₁" />
      <WordChip>{label}</WordChip>
      <svg width={280} height={120} style={{ display: "block", margin: "10px auto 0" }}>
        <line x1={20} x2={260} y1={100} y2={100} stroke="var(--line)" />
        <line x1={20} x2={20} y1={10} y2={100} stroke="var(--line)" />
        {pairs.map(([x, y], i) => (
          <circle
            key={i}
            cx={20 + (x / 100) * 240}
            cy={100 - (y / 100) * 90}
            r="3"
            fill="var(--accent)"
            opacity={0.6}
          />
        ))}
        <text x={20} y={115} fontSize="9" fill="var(--faint)">
          today
        </text>
        <text x={260} y={115} fontSize="9" fill="var(--faint)" textAnchor="end">
          avg
        </text>
      </svg>
    </Card>
  );
}

// ─── Card 5: AM vs PM ─────────────────────────────────────────────────

function AMPMCard({ am, pm }: { am: number; pm: number }) {
  const diff = am - pm;
  const label =
    diff > 5 ? "morning type" : diff < -5 ? "evening type" : "even-keel";
  return (
    <Card title="When you peak" subtitle="morning vs evening">
      <div style={{ display: "flex", gap: 18, alignItems: "baseline", marginTop: 8 }}>
        <div>
          <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
            AM
          </div>
          <div
            className="tnum"
            style={{
              fontSize: 32,
              fontWeight: 600,
              color: diff > 5 ? "var(--accent)" : "var(--ink)",
              letterSpacing: "-0.02em",
            }}
          >
            {am.toFixed(0)}
          </div>
        </div>
        <div style={{ fontSize: 18, color: "var(--faint)" }}>vs</div>
        <div>
          <div style={{ fontSize: 10, color: "var(--muted)", letterSpacing: "0.06em", textTransform: "uppercase" }}>
            PM
          </div>
          <div
            className="tnum"
            style={{
              fontSize: 32,
              fontWeight: 600,
              color: diff < -5 ? "var(--accent)" : "var(--ink)",
              letterSpacing: "-0.02em",
            }}
          >
            {pm.toFixed(0)}
          </div>
        </div>
      </div>
      <WordChip>{label}</WordChip>
      {/* comparative bar */}
      <div style={{ marginTop: 12 }}>
        <div style={{ height: 8, background: "var(--hover)", borderRadius: 4, position: "relative", overflow: "hidden" }}>
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: `${Math.min(100, am)}%`,
              background: "var(--accent)",
              opacity: 0.6,
            }}
          />
        </div>
        <div style={{ height: 8, background: "var(--hover)", borderRadius: 4, position: "relative", overflow: "hidden", marginTop: 6 }}>
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              bottom: 0,
              width: `${Math.min(100, pm)}%`,
              background: "var(--warm)",
              opacity: 0.7,
            }}
          />
        </div>
      </div>
    </Card>
  );
}

// ─── Card 6: event cadence ───────────────────────────────────────────

function EventCadenceCard({ avgPerDay, hist }: { avgPerDay: number; hist: number[] }) {
  const max = Math.max(...hist, 1);
  const richPct = hist.slice(3).reduce((a, b) => a + b, 0) / hist.reduce((a, b) => a + b, 1);
  return (
    <Card title="Event density" subtitle="noticed moments per day">
      <BigNum value={avgPerDay.toFixed(1)} unit="avg" />
      <WordChip>{Math.round(richPct * 100)}% rich days</WordChip>
      <div style={{ display: "flex", gap: 4, alignItems: "flex-end", height: 60, marginTop: 10 }}>
        {hist.map((h, i) => (
          <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
            <div
              style={{
                width: "100%",
                height: `${(h / max) * 100}%`,
                background: "var(--accent)",
                borderRadius: 3,
                minHeight: h > 0 ? 4 : 0,
                opacity: 0.85,
              }}
            />
            <span className="mono" style={{ fontSize: 9, color: "var(--faint)" }}>
              {i === 7 ? "7+" : i}
            </span>
          </div>
        ))}
      </div>
      <Interpretation>
        Days with 3+ events are "rich" — they have enough texture to parse.
      </Interpretation>
    </Card>
  );
}

// ─── Shared pieces ───────────────────────────────────────────────────

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "18px 20px",
        display: "flex",
        flexDirection: "column",
        gap: 4,
        minHeight: 280,
      }}
    >
      <div style={{ fontSize: 14, fontWeight: 600 }}>{title}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8 }}>{subtitle}</div>
      {children}
    </section>
  );
}

function BigNum({ value, unit }: { value: string; unit: string }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
      <span
        className="tnum"
        style={{
          fontSize: 36,
          fontWeight: 600,
          color: "var(--ink)",
          letterSpacing: "-0.02em",
        }}
      >
        {value}
      </span>
      <span style={{ fontSize: 12, color: "var(--faint)" }}>{unit}</span>
    </div>
  );
}

function WordChip({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: 11,
        padding: "3px 8px",
        borderRadius: 999,
        background: "var(--hover)",
        color: "var(--muted)",
        fontWeight: 600,
        alignSelf: "flex-start",
        marginTop: 4,
      }}
    >
      {children}
    </span>
  );
}

function Interpretation({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontSize: 12, color: "var(--muted)", marginTop: "auto", paddingTop: 12, lineHeight: 1.5 }}>
      {children}
    </div>
  );
}

function EmptyState({ have, onCompose }: { have: number; onCompose: () => void }) {
  return (
    <section
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "72px 24px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 14,
        textAlign: "center",
      }}
    >
      <p className="serif" style={{ fontFamily: "var(--serif)", fontSize: 22, fontStyle: "italic" }}>
        Patterns need data to surface.
      </p>
      <p style={{ fontSize: 13, color: "var(--muted)" }}>
        Log 5+ days and the engine will compute your weekly shape, momentum, and more.
      </p>
      <div style={{ width: 240, height: 6, background: "var(--hover)", borderRadius: 4, overflow: "hidden", marginTop: 8 }}>
        <div
          style={{
            width: `${(have / 5) * 100}%`,
            height: "100%",
            background: "var(--accent)",
            borderRadius: 4,
          }}
        />
      </div>
      <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
        {have} / 5
      </span>
      <button
        onClick={onCompose}
        style={{
          marginTop: 8,
          background: "var(--warm)",
          color: "#fff",
          padding: "10px 18px",
          borderRadius: 8,
          fontSize: 13,
          fontWeight: 500,
        }}
      >
        ＋ Log entry
      </button>
    </section>
  );
}

// ─── Computation ─────────────────────────────────────────────────────

interface AllStats {
  weekday: number[];
  hourly: Point[];
  peakHour: number;
  troughHour: number;
  sigma30: number;
  sigmaWeekly: number[];
  autocorr: number;
  consecutivePairs: Array<[number, number]>;
  amAvg: number;
  pmAvg: number;
  eventsAvg: number;
  eventsHist: number[];
}

function computeAll(entries: StoredEntry[]): AllStats {
  return {
    weekday: weekdayAvgs(entries),
    hourly: hourlyShape(entries),
    ...hourlyPeaks(hourlyShape(entries)),
    sigma30: sigmaOfAvgs(entries, 30),
    sigmaWeekly: weeklySigmas(entries),
    autocorr: autocorrelationLag1(entries),
    consecutivePairs: consecutivePairs(entries),
    amAvg: windowAvg(entries, 0, 5 * 60),
    pmAvg: windowAvg(entries, 11 * 60, 16 * 60),
    eventsAvg: entries.length
      ? entries.reduce((s, e) => s + e.events.length, 0) / entries.length
      : 0,
    eventsHist: eventsHistogram(entries),
  };
}

function weekdayAvgs(entries: StoredEntry[]): number[] {
  const sums = [0, 0, 0, 0, 0, 0, 0];
  const counts = [0, 0, 0, 0, 0, 0, 0];
  for (const e of entries) {
    // JS getDay: 0=Sun..6=Sat. Shift to 0=Mon..6=Sun.
    const w = (new Date(e.createdAt).getDay() + 6) % 7;
    sums[w] += e.avg;
    counts[w]++;
  }
  return sums.map((s, i) => (counts[i] ? s / counts[i] : NaN));
}

function hourlyShape(entries: StoredEntry[]): Point[] {
  if (!entries.length) return [];
  const n = entries[0].series.length;
  const acc = new Array(n).fill(0);
  for (const e of entries) {
    for (let i = 0; i < Math.min(n, e.series.length); i++) acc[i] += e.series[i].v;
  }
  return acc.map((v, i) => ({ t: entries[0].series[i].t, v: v / entries.length }));
}

function hourlyPeaks(shape: Point[]): { peakHour: number; troughHour: number } {
  if (!shape.length) return { peakHour: 0, troughHour: 0 };
  let peak = shape[0];
  let trough = shape[0];
  for (const p of shape) {
    if (p.v > peak.v) peak = p;
    if (p.v < trough.v) trough = p;
  }
  return { peakHour: peak.t, troughHour: trough.t };
}

function sigmaOfAvgs(entries: StoredEntry[], days: number): number {
  const recent = entries.slice(0, days).map((e) => e.avg);
  if (recent.length < 2) return 0;
  const m = recent.reduce((a, b) => a + b, 0) / recent.length;
  return Math.sqrt(recent.reduce((a, b) => a + (b - m) ** 2, 0) / recent.length);
}

function weeklySigmas(entries: StoredEntry[]): number[] {
  const weeks: number[][] = [[], [], [], []];
  const now = Date.now();
  for (const e of entries) {
    const daysAgo = Math.floor((now - new Date(e.createdAt).getTime()) / 86400000);
    const wIdx = Math.floor(daysAgo / 7);
    if (wIdx >= 0 && wIdx < 4) weeks[wIdx].push(e.avg);
  }
  return weeks.reverse().map((w) => {
    if (w.length < 2) return 0;
    const m = w.reduce((a, b) => a + b, 0) / w.length;
    return Math.sqrt(w.reduce((a, b) => a + (b - m) ** 2, 0) / w.length);
  });
}

function autocorrelationLag1(entries: StoredEntry[]): number {
  if (entries.length < 3) return 0;
  // Sort ASC by time so pairs are consecutive.
  const sorted = entries.slice().sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
  const avgs = sorted.map((e) => e.avg);
  const m = avgs.reduce((a, b) => a + b, 0) / avgs.length;
  let num = 0;
  let den = 0;
  for (let i = 0; i < avgs.length - 1; i++) num += (avgs[i] - m) * (avgs[i + 1] - m);
  for (let i = 0; i < avgs.length; i++) den += (avgs[i] - m) ** 2;
  return den ? num / den : 0;
}

function consecutivePairs(entries: StoredEntry[]): Array<[number, number]> {
  const sorted = entries.slice().sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
  const pairs: Array<[number, number]> = [];
  for (let i = 0; i < sorted.length - 1; i++) pairs.push([sorted[i].avg, sorted[i + 1].avg]);
  return pairs;
}

function windowAvg(entries: StoredEntry[], startT: number, endT: number): number {
  if (!entries.length) return 50;
  let sum = 0;
  let count = 0;
  for (const e of entries) {
    for (const p of e.series) {
      if (p.t >= startT && p.t <= endT) {
        sum += p.v;
        count++;
      }
    }
  }
  return count ? sum / count : 50;
}

function eventsHistogram(entries: StoredEntry[]): number[] {
  const bins = new Array(8).fill(0); // 0, 1, 2, 3, 4, 5, 6, 7+
  for (const e of entries) {
    const n = Math.min(7, e.events.length);
    bins[n]++;
  }
  return bins;
}

function fmtHourOfDay(t: number): string {
  // t is minutes after 7 AM wake
  const totalMin = 7 * 60 + t;
  const h24 = Math.floor(totalMin / 60) % 24;
  const ampm = h24 >= 12 ? "PM" : "AM";
  const h12 = ((h24 + 11) % 12) + 1;
  return `${h12} ${ampm}`;
}
