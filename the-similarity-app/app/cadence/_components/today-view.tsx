"use client";

import { useMemo } from "react";
import { useEngine } from "./engine-context";
import { useParsedNarrative } from "../use-parse";
import { buildHistoryFromEntries } from "../storage";
import { Panel } from "./shell";
import { seedDemoEntries } from "./demo-seed";

export default function TodayView() {
  const { text, entries, reloadEntries, openComposer } = useEngine();
  const { events, series } = useParsedNarrative(text);

  const avg = useMemo(() => Math.round(series.reduce((s, p) => s + p.v, 0) / (series.length || 1)), [series]);
  const latest = series[series.length - 1]?.v ?? 50;
  const baseline = useMemo(() => {
    const hist = buildHistoryFromEntries(entries, avg);
    return Math.round(hist.reduce((s, d) => s + d.avg, 0) / (hist.length || 1));
  }, [entries, avg]);

  const loadDemo = () => {
    seedDemoEntries();
    reloadEntries();
  };

  const trajectory = series.slice(-48);

  return (
    <div style={{ display: "grid", gap: 14 }}>
      {entries.length === 0 ? (
        <Panel title="Demo ready" subtitle="No data connected yet.">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <p style={{ margin: 0, color: "#475569" }}>
              Load a 14-day body dataset so you can explore rhymes, baseline drift, and context tags immediately.
            </p>
            <button onClick={loadDemo} style={{ background: "#0F766E", color: "white", borderRadius: 10, padding: "8px 12px", fontWeight: 700 }}>
              Load demo data
            </button>
          </div>
        </Panel>
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 14 }}>
        <Panel title="Day trajectory" subtitle="Primary stream vs your personal baseline.">
          <TrajectoryChart values={trajectory.map((p) => p.v)} baseline={baseline} />
        </Panel>

        <Panel title="Body status" subtitle="Personal baseline deltas (not population).">
          <Metric label="Recovery score" value={Math.round(latest)} delta={Math.round(latest - baseline)} />
          <Metric label="HRV trend" value={Math.max(1, Math.round(stdDev(trajectory.map((p) => p.v))))} delta={0} suffix="σ" />
          <Metric label="RHR proxy" value={Math.max(45, 65 - Math.round((latest - 50) / 2))} delta={Math.round((baseline - latest) / 3)} suffix="bpm" />
          <Metric label="Sleep quality" value={Math.round(Math.max(40, latest - 5))} delta={Math.round(latest - baseline)} />
        </Panel>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <Panel title="Rhyme heatmap" subtitle="7d × 12h intensity map">
          <HeatmapMini values={trajectory.map((p) => p.v)} />
        </Panel>
        <Panel title="Context share" subtitle="Weighted tags in current window">
          <TagSummary events={events} />
        </Panel>
      </div>

      <Panel title="Thread ribbon" subtitle="Recent logs; click into Thread for full timeline.">
        <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
          {entries.slice(0, 30).map((entry) => (
            <span
              key={entry.id}
              title={`${new Date(entry.createdAt).toLocaleDateString()} · ${Math.round(entry.avg)}`}
              style={{ width: 10, height: 10, borderRadius: 999, background: colorFor(entry.avg), border: "1px solid #94A3B8" }}
            />
          ))}
          <button onClick={openComposer} style={{ marginLeft: 8, background: "#E2E8F0", borderRadius: 8, padding: "4px 8px", color: "#334155" }}>
            + Add body note
          </button>
        </div>
      </Panel>
    </div>
  );
}

function Metric({ label, value, delta, suffix = "/100" }: { label: string; value: number; delta: number; suffix?: string }) {
  const positive = delta >= 0;
  return (
    <div style={{ borderTop: "1px solid #E2E8F0", padding: "10px 0", display: "flex", justifyContent: "space-between" }}>
      <div>
        <div style={{ fontSize: 12, color: "#64748B" }}>{label}</div>
        <div style={{ fontSize: 24, fontWeight: 700 }}>{value}<span style={{ fontSize: 13, color: "#64748B" }}> {suffix}</span></div>
      </div>
      <div style={{ fontSize: 12, color: positive ? "#0F766E" : "#B91C1C", alignSelf: "center" }}>
        {positive ? "+" : ""}{delta} vs baseline
      </div>
    </div>
  );
}

function TrajectoryChart({ values, baseline }: { values: number[]; baseline: number }) {
  const width = 660;
  const height = 220;
  const min = Math.min(...values, baseline - 10);
  const max = Math.max(...values, baseline + 10);
  const x = (i: number) => (i / Math.max(1, values.length - 1)) * width;
  const y = (v: number) => height - ((v - min) / (max - min || 1)) * height;
  const path = values.map((v, i) => `${i === 0 ? "M" : "L"}${x(i)} ${y(v)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height + 22}`} width="100%" height="220">
      <line x1={0} x2={width} y1={y(baseline)} y2={y(baseline)} stroke="#94A3B8" strokeDasharray="4 4" />
      <path d={path} fill="none" stroke="#0F766E" strokeWidth="3" />
      <text x={4} y={y(baseline) - 6} fontSize="11" fill="#64748B">baseline {baseline}</text>
    </svg>
  );
}

function HeatmapMini({ values }: { values: number[] }) {
  const rows = 7;
  const cols = 12;
  const cells = Array.from({ length: rows * cols }, (_, i) => values[i % values.length] ?? 50);
  return (
    <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 4 }}>
      {cells.map((v, i) => (
        <div key={i} style={{ height: 14, borderRadius: 4, background: `rgba(15,118,110,${0.12 + ((v - 35) / 65) * 0.7})` }} />
      ))}
    </div>
  );
}

function TagSummary({ events }: { events: Array<{ tag: string }> }) {
  const counts = events.reduce<Record<string, number>>((acc, event) => {
    acc[event.tag] = (acc[event.tag] || 0) + 1;
    return acc;
  }, {});
  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 5);
  if (!sorted.length) return <div style={{ color: "#64748B" }}>No tagged events yet — add a body note to start context tracking.</div>;
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {sorted.map(([tag, count]) => (
        <span key={tag} style={{ fontSize: 12, padding: "6px 8px", borderRadius: 999, background: "#E2E8F0", color: "#334155" }}>
          {tag} · {count}
        </span>
      ))}
    </div>
  );
}

function stdDev(values: number[]): number {
  if (!values.length) return 0;
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  return Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length);
}

function colorFor(v: number): string {
  if (v >= 70) return "#14B8A6";
  if (v >= 55) return "#84CC16";
  if (v >= 45) return "#F59E0B";
  return "#EF4444";
}
