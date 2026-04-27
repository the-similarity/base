"use client";

/**
 * /prudent/rhymes — self-similarity showcase.
 *
 * Surfaces which days (or 7-day windows) "rhyme" — have structurally
 * similar trajectories even when the narratives differ. This is the
 * core thesis of the project in one view: different stories, same shape.
 */

import { useMemo } from "react";
import { useEngine } from "../_components/engine-context";
import { buildHistoryFromEntries } from "../storage";
import { parseNarrative, type HistoryDay, type Point } from "../engine";

export default function RhymesPage() {
  const { entries, openComposer } = useEngine();
  const avg = useMemo(
    () => (entries.length ? Math.round(entries.reduce((s, e) => s + e.avg, 0) / entries.length) : 50),
    [entries],
  );
  const history = useMemo(() => buildHistoryFromEntries(entries, avg), [entries, avg]);

  if (history.length < 7) return <EmptyState have={history.length} onCompose={openComposer} />;

  const pairs = useMemo(() => findTopRhymes(history, 3), [history]);
  const archetypes = useMemo(() => detectArchetypes(history), [history]);

  const top = pairs[0];

  return (
    <div className="prudent-rhymes-page" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Hero */}
      {top && (
        <section
          className="rhymes-hero"
          style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: 10,
            padding: "26px 30px",
          }}
        >
          <p
            className="serif"
            style={{
              fontFamily: "var(--serif)",
              fontSize: 22,
              fontStyle: "italic",
              color: "var(--ink)",
              margin: 0,
            }}
          >
            This week rhymes with the week of day −{history[top.b].day}.
          </p>
          <div className="mono" style={{ fontSize: 12, color: "var(--muted)", marginTop: 6 }}>
            RMSE {(-top.score).toFixed(2)} · {Math.round(100 * (1 - -top.score / 1.6))}% shape match
          </div>
          <div className="rhymes-hero-chart" style={{ marginTop: 20, display: "flex", gap: 20, alignItems: "center" }}>
            <OverlaySparklines
              a={sliceShape(history, top.a, 7)}
              b={sliceShape(history, top.b, 7)}
              width={520}
              height={110}
            />
          </div>
        </section>
      )}

      {/* Rhyme library */}
      {pairs.length > 0 && (
        <section
          style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: 10,
            padding: "20px 22px",
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>Rhyme library</div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 16 }}>
            Top {pairs.length} non-overlapping 7-day window matches
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {pairs.map((p, i) => (
              <RhymePairCard key={i} pair={p} history={history} />
            ))}
          </div>
        </section>
      )}

      {/* Archetypes */}
      <section
        style={{
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: 10,
          padding: "20px 22px",
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 2 }}>Common shapes</div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 14 }}>
          Archetypes detected across {history.length} days
        </div>
        <div className="rhymes-archetypes-grid" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          {archetypes.map((a) => (
            <ArchetypeCard key={a.name} arch={a} />
          ))}
        </div>
      </section>

      {/*
        Scoped responsive + dark-mode rules for /rhymes.
        - 900px: rhyme pair cards collapse 3-col (A | center | B) into a
          single column (A / center / B stacked); archetype grid drops to
          2 columns so each card keeps room for its mini-chart.
        - 600px: archetype grid single column, mini-sparkline shrinks.
        - Dark mode: the rhyme pair-card background uses var(--app-bg) which
          is nearly identical to --panel in dark — lift its background to
          var(--hover) for visible separation from the containing panel.
      */}
      <style>{`
        @media (max-width: 900px) {
          .prudent-rhymes-page .rhyme-pair-card {
            grid-template-columns: 1fr !important;
            text-align: left !important;
          }
          .prudent-rhymes-page .rhyme-pair-center {
            flex-direction: row !important;
            justify-content: space-between;
            width: 100%;
          }
          .prudent-rhymes-page .rhymes-archetypes-grid {
            grid-template-columns: repeat(2, 1fr) !important;
          }
        }
        @media (max-width: 600px) {
          .prudent-rhymes-page .rhymes-archetypes-grid {
            grid-template-columns: 1fr !important;
          }
        }
        /* Dark mode: outer panel (var(--panel)=#17191C) and inner card
           (var(--app-bg)=#0E0F11) differ by only ~6 lightness points —
           almost invisible. Use --hover which sits at #1D2024 for a clearer
           nested card feel. Applies to both pair-cards and archetype-cards. */
        .prudent-root.prudent-dark .prudent-rhymes-page .rhyme-pair-card,
        .prudent-root.prudent-dark .prudent-rhymes-page .archetype-card {
          background: var(--hover) !important;
          border-color: var(--line-mid) !important;
        }
      `}</style>
    </div>
  );
}

// ─── Top-3 non-overlapping rhymes ────────────────────────────────────

export interface RhymePair {
  a: number;
  b: number;
  score: number; // closer to 0 = better (negative rmse, per engine.findRhyme)
}

function findTopRhymes(history: HistoryDay[], k: number): RhymePair[] {
  const n = history.length;
  if (n < 14) return [];
  const shapes: number[][] = [];
  for (let i = 0; i < n - 6; i++) {
    const window = history.slice(i, i + 7).map((d) => d.avg);
    shapes.push(normalize(window));
  }
  const results: RhymePair[] = [];
  for (let i = 0; i < shapes.length; i++) {
    for (let j = i + 7; j < shapes.length; j++) {
      const rmse = rootMse(shapes[i], shapes[j]);
      results.push({ a: i, b: j, score: -rmse });
    }
  }
  results.sort((x, y) => y.score - x.score);
  // Greedy non-overlap
  const out: RhymePair[] = [];
  const used = new Set<number>();
  for (const r of results) {
    if (out.length >= k) break;
    let overlap = false;
    for (let k2 = 0; k2 < 7; k2++) {
      if (used.has(r.a + k2) || used.has(r.b + k2)) {
        overlap = true;
        break;
      }
    }
    if (overlap) continue;
    out.push(r);
    for (let k2 = 0; k2 < 7; k2++) {
      used.add(r.a + k2);
      used.add(r.b + k2);
    }
  }
  return out;
}

function normalize(arr: number[]): number[] {
  const m = arr.reduce((a, b) => a + b, 0) / arr.length;
  const s = Math.sqrt(arr.reduce((a, b) => a + (b - m) ** 2, 0) / arr.length) || 1;
  return arr.map((v) => (v - m) / s);
}

function rootMse(a: number[], b: number[]): number {
  const n = Math.min(a.length, b.length);
  let s = 0;
  for (let i = 0; i < n; i++) s += (a[i] - b[i]) ** 2;
  return Math.sqrt(s / n);
}

export function sliceShape(history: HistoryDay[], start: number, n: number): number[] {
  return history.slice(start, start + n).map((d) => d.avg);
}

// ─── Rhyme pair card ─────────────────────────────────────────────────

export function RhymePairCard({ pair, history }: { pair: RhymePair; history: HistoryDay[] }) {
  const A = history.slice(pair.a, pair.a + 7);
  const B = history.slice(pair.b, pair.b + 7);
  const themeA = dominantTheme(A);
  const themeB = dominantTheme(B);
  const rmse = -pair.score;
  const shapeMatch = Math.round(100 * Math.max(0, 1 - rmse / 1.6));

  return (
    <div
      className="rhyme-pair-card"
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 100px 1fr",
        gap: 14,
        padding: "16px 18px",
        border: "1px solid var(--line)",
        borderRadius: 8,
        background: "var(--app-bg)",
        alignItems: "center",
      }}
    >
      <PairSide week={A} color="var(--accent)" />
      <div
        className="rhyme-pair-center"
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 6,
          fontSize: 11,
          color: "var(--muted)",
        }}
      >
        <div className="mono tnum" style={{ fontSize: 13, color: "var(--ink)", fontWeight: 600 }}>
          {shapeMatch}%
        </div>
        <div className="mono" style={{ fontSize: 10 }}>RMSE {rmse.toFixed(2)}</div>
        <svg width="40" height="20">
          <line x1="0" x2="40" y1="10" y2="10" stroke="var(--warm)" strokeDasharray="2 2" />
        </svg>
        <div className="serif" style={{ fontSize: 11, fontStyle: "italic", textAlign: "center" }}>
          {themeA} ↔ {themeB}
        </div>
      </div>
      <PairSide week={B} color="var(--accent-mid)" right />
    </div>
  );
}

function PairSide({ week, color, right }: { week: HistoryDay[]; color: string; right?: boolean }) {
  const startDay = week[0].day;
  const endDay = week[week.length - 1].day;
  const text = week[3]?.text ?? "";
  const avg = week.reduce((s, d) => s + d.avg, 0) / week.length;
  return (
    <div style={{ textAlign: right ? "right" : "left" }}>
      <div className="mono" style={{ fontSize: 10, color: "var(--muted)", letterSpacing: "0.06em" }}>
        Day −{startDay} → Day −{endDay}
      </div>
      <p
        className="serif"
        style={{
          fontFamily: "var(--serif)",
          fontSize: 14,
          fontStyle: "italic",
          color: "var(--ink)",
          margin: "6px 0",
          display: "-webkit-box",
          WebkitLineClamp: 3,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}
      >
        {text || "(no narrative)"}
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 10, justifyContent: right ? "flex-end" : "flex-start" }}>
        <MiniSparkline values={week.map((d) => d.avg)} color={color} width={120} />
        <span
          className="tnum"
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: avg >= 50 ? "var(--green)" : "var(--warm-strong)",
          }}
        >
          {Math.round(avg)}
        </span>
      </div>
    </div>
  );
}

function dominantTheme(week: HistoryDay[]): string {
  // Peek at parsed events from the most-narrative day.
  const mid = week[3]?.text ?? week[0]?.text ?? "";
  if (!mid) return "—";
  const { events } = parseNarrative(mid);
  const tally = new Map<string, number>();
  for (const e of events) tally.set(e.tag, (tally.get(e.tag) ?? 0) + Math.abs(e.delta));
  let best = "—";
  let bestV = 0;
  for (const [t, v] of tally) if (v > bestV) { best = t; bestV = v; }
  return best;
}

// ─── Overlay sparklines (hero) ───────────────────────────────────────

export function OverlaySparklines({
  a,
  b,
  width,
  height,
}: {
  a: number[];
  b: number[];
  width: number;
  height: number;
}) {
  const pad = 8;
  const step = (width - pad * 2) / (Math.max(a.length, b.length) - 1);
  const y = (v: number) => pad + (1 - v / 100) * (height - pad * 2);
  const toPath = (arr: number[]) => {
    let d = `M ${pad} ${y(arr[0])}`;
    for (let i = 1; i < arr.length; i++) {
      const x0 = pad + (i - 1) * step;
      const x1 = pad + i * step;
      const mx = (x0 + x1) / 2;
      d += ` C ${mx} ${y(arr[i - 1])}, ${mx} ${y(arr[i])}, ${x1} ${y(arr[i])}`;
    }
    return d;
  };
  return (
    // Use viewBox so CSS width rules can scale the rendered size down
    // without distorting the drawn paths. max-width: 100% in parent lets
    // narrow viewports shrink it; the explicit width/height attributes are
    // retained so large viewports use the exact design size.
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ display: "block", maxWidth: "100%", height: "auto" }}
    >
      <line
        x1={pad}
        x2={width - pad}
        y1={y(50)}
        y2={y(50)}
        stroke="var(--line)"
        strokeDasharray="3 3"
      />
      <path d={toPath(b)} fill="none" stroke="var(--accent-mid)" strokeWidth="2" strokeDasharray="5 4" />
      <path d={toPath(a)} fill="none" stroke="var(--accent)" strokeWidth="2.5" />
      {a.map((v, i) => (
        <circle
          key={`a-${i}`}
          cx={pad + i * step}
          cy={y(v)}
          r="3"
          fill="var(--accent)"
          stroke="var(--panel)"
          strokeWidth="1.5"
        />
      ))}
      {b.map((v, i) => (
        <circle
          key={`b-${i}`}
          cx={pad + i * step}
          cy={y(v)}
          r="2"
          fill="var(--accent-mid)"
        />
      ))}
    </svg>
  );
}

function MiniSparkline({ values, color, width = 120 }: { values: number[]; color: string; width?: number }) {
  const H = 34;
  const pad = 3;
  const step = (width - pad * 2) / (values.length - 1 || 1);
  const y = (v: number) => pad + (1 - v / 100) * (H - pad * 2);
  let d = `M ${pad} ${y(values[0] ?? 50)}`;
  for (let i = 1; i < values.length; i++) {
    const x0 = pad + (i - 1) * step;
    const x1 = pad + i * step;
    const mx = (x0 + x1) / 2;
    d += ` C ${mx} ${y(values[i - 1])}, ${mx} ${y(values[i])}, ${x1} ${y(values[i])}`;
  }
  return (
    <svg width={width} height={H} style={{ display: "block" }}>
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

// ─── Archetypes ──────────────────────────────────────────────────────

interface Archetype {
  name: string;
  description: string;
  count: number;
  shape: (i: number, n: number) => number;
}

function detectArchetypes(history: HistoryDay[]): Archetype[] {
  // For each day, peek at its parsed series to characterize shape.
  const series = history.map((d) => parseNarrative(d.text).series);
  const classes = {
    rising: { name: "Rising morning", description: "PM > AM by >10pts", count: 0 } as Archetype,
    crash: { name: "Crash-recover", description: "peak → trough → recover", count: 0 } as Archetype,
    flat: { name: "Flat day", description: "low variance σ<6", count: 0 } as Archetype,
    volatile: { name: "Volatile day", description: "high variance σ>15", count: 0 } as Archetype,
  };
  const shape_rising = (i: number, n: number) => 40 + (i / n) * 30;
  const shape_crash = (i: number, n: number) => 70 - 60 * Math.sin((i / n) * Math.PI);
  const shape_flat = () => 50;
  const shape_volatile = (i: number, n: number) => 50 + 25 * Math.sin((i / n) * Math.PI * 4);
  classes.rising.shape = shape_rising;
  classes.crash.shape = shape_crash;
  classes.flat.shape = shape_flat;
  classes.volatile.shape = shape_volatile;

  for (const s of series) {
    if (s.length < 4) continue;
    const am = average(s.slice(0, Math.floor(s.length / 2)).map((p) => p.v));
    const pm = average(s.slice(Math.floor(s.length / 2)).map((p) => p.v));
    const all = s.map((p) => p.v);
    const m = average(all);
    const sd = Math.sqrt(average(all.map((v) => (v - m) ** 2)));
    const max = Math.max(...all);
    const min = Math.min(...all);
    const maxIdx = all.indexOf(max);
    const minIdx = all.indexOf(min);

    if (sd < 6) classes.flat.count++;
    else if (sd > 15) classes.volatile.count++;
    if (pm - am > 10) classes.rising.count++;
    if (maxIdx < minIdx && min < 35 && all[all.length - 1] - min > 15) classes.crash.count++;
  }
  return Object.values(classes);
}

function average(arr: number[]): number {
  return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
}

function ArchetypeCard({ arch }: { arch: Archetype }) {
  const W = 180;
  const H = 50;
  const n = 20;
  let d = `M 0 ${H - (arch.shape(0, n) / 100) * H}`;
  for (let i = 1; i < n; i++) {
    const x = (i / (n - 1)) * W;
    const y = H - (arch.shape(i, n) / 100) * H;
    d += ` L ${x} ${y}`;
  }
  return (
    <div
      className="archetype-card"
      style={{
        background: "var(--app-bg)",
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: "14px 16px",
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>{arch.name}</div>
      <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 2 }}>{arch.description}</div>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} style={{ marginTop: 10 }} preserveAspectRatio="none">
        <path d={d} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
      </svg>
      <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginTop: 8 }}>
        <span className="tnum" style={{ fontSize: 20, fontWeight: 600, color: "var(--ink)" }}>
          {arch.count}
        </span>
        <span style={{ fontSize: 11, color: "var(--muted)" }}>days</span>
      </div>
    </div>
  );
}

// ─── Empty state ─────────────────────────────────────────────────────

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
        Rhymes emerge after 7+ days.
      </p>
      <p style={{ fontSize: 13, color: "var(--muted)" }}>
        The engine compares 7-day windows for structural similarity — two weeks with different
        stories can still share a shape.
      </p>
      <div style={{ width: 240, height: 6, background: "var(--hover)", borderRadius: 4, overflow: "hidden", marginTop: 8 }}>
        <div
          style={{
            width: `${Math.min(100, (have / 7) * 100)}%`,
            height: "100%",
            background: "var(--accent)",
            borderRadius: 4,
          }}
        />
      </div>
      <span className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
        {have} / 7
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
