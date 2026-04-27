"use client";

/**
 * /prudent/thread — vertical scroll of every logged entry, newest first.
 *
 * Feels like a literary journal meets an analytics ledger: a summary strip
 * of all-time stats at the top, then a month-grouped list of entry cards
 * below. Each card is clickable to open the composer in read-only mode
 * (handled via `useEngine().openReadOnly(entry)`).
 *
 * Zero local persistence — all data comes from the layout-level EngineProvider.
 */

import { useMemo } from "react";
import { useEngine } from "../_components/engine-context";
import { fmtShortDate, fmtClockTime } from "../_components/shell";
import type { StoredEntry } from "../storage";
import type { Point } from "../engine";

export default function ThreadPage() {
  const { entries, openComposer, openReadOnly } = useEngine();

  const stats = useMemo(() => computeStats(entries), [entries]);
  const byMonth = useMemo(() => groupByMonth(entries), [entries]);

  if (entries.length === 0) return <EmptyState onCompose={openComposer} />;

  return (
    <div className="prudent-thread-page" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <SummaryStrip stats={stats} />
      {byMonth.map(([label, group]) => (
        <div key={label} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <MonthHeader label={label} />
          {group.map((entry) => (
            <EntryCard
              key={entry.id}
              entry={entry}
              onClick={() => openReadOnly(entry)}
            />
          ))}
        </div>
      ))}

      {/*
        Scoped responsive + dark-mode rules.
        - 1100px: summary strip drops the 200px sparkline column so the four
          stats stay readable (sparkline wraps beneath as full-width).
        - 900px: 4-col strip becomes 2x2.
        - 820px: entry cards drop the fixed sparkline column and let the
          narrative span full width; timestamp collapses to a single line.
        - Dark mode: increase card hover shadow opacity since the default
          20/22/26 ink tone is invisible against a #0E0F11 canvas.
      */}
      <style>{`
        @media (max-width: 1100px) {
          .prudent-thread-page .summary-strip {
            grid-template-columns: repeat(4, 1fr) !important;
          }
          .prudent-thread-page .summary-strip .summary-spark {
            grid-column: 1 / -1;
            width: 100% !important;
          }
          .prudent-thread-page .summary-strip .summary-spark svg {
            width: 100%;
          }
        }
        @media (max-width: 900px) {
          .prudent-thread-page .summary-strip {
            grid-template-columns: repeat(2, 1fr) !important;
            gap: 18px !important;
          }
        }
        @media (max-width: 820px) {
          .prudent-thread-page .entry-card {
            grid-template-columns: 1fr !important;
            gap: 10px !important;
          }
          .prudent-thread-page .entry-card .entry-spark {
            width: 100% !important;
          }
          .prudent-thread-page .entry-card .entry-spark svg {
            width: 100%;
          }
        }
        /* Dark-mode: default hover shadow uses near-black ink tint that
           disappears on a dark canvas; strengthen via a class hook that
           EntryCard reads below in its onMouseEnter handler. */
        .prudent-root.prudent-dark .prudent-thread-page .entry-card:hover {
          border-color: var(--line-mid) !important;
          box-shadow: 0 4px 16px -6px rgba(0,0,0,0.45) !important;
        }
      `}</style>
    </div>
  );
}

// ─── Summary strip ────────────────────────────────────────────────────

interface Stats {
  total: number;
  streak: number;
  avgAll: number;
  high: number;
  low: number;
  last30: number[];
}

function computeStats(entries: StoredEntry[]): Stats {
  if (entries.length === 0) {
    return { total: 0, streak: 0, avgAll: 50, high: 50, low: 50, last30: [] };
  }
  const avgAll = Math.round(entries.reduce((s, e) => s + e.avg, 0) / entries.length);
  const high = Math.max(...entries.map((e) => e.avg));
  const low = Math.min(...entries.map((e) => e.avg));
  return {
    total: entries.length,
    streak: currentStreak(entries),
    avgAll,
    high,
    low,
    last30: lastNDaysAvgs(entries, 30),
  };
}

function currentStreak(entries: StoredEntry[]): number {
  if (!entries.length) return 0;
  const dayKeys = new Set(entries.map((e) => dayKey(new Date(e.createdAt))));
  let streak = 0;
  const today = new Date();
  for (let d = 0; d < 365; d++) {
    const k = dayKey(new Date(today.getTime() - d * 86400000));
    if (dayKeys.has(k)) streak++;
    else break;
  }
  return streak;
}

function lastNDaysAvgs(entries: StoredEntry[], n: number): number[] {
  const byDay = new Map<string, number>();
  for (const e of entries) byDay.set(dayKey(new Date(e.createdAt)), e.avg);
  const out: number[] = [];
  const today = new Date();
  for (let d = n - 1; d >= 0; d--) {
    const k = dayKey(new Date(today.getTime() - d * 86400000));
    out.push(byDay.get(k) ?? 50);
  }
  return out;
}

function dayKey(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function SummaryStrip({ stats }: { stats: Stats }) {
  return (
    <section
      className="summary-strip"
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "18px 22px",
        display: "grid",
        gridTemplateColumns: "repeat(4, 1fr) 200px",
        gap: 24,
        alignItems: "center",
      }}
    >
      <Stat label="Total" value={stats.total} unit="entries" />
      <Stat label="Streak" value={stats.streak} unit="days" />
      <Stat label="Avg valence" value={stats.avgAll} unit="/100" />
      <Stat label="Range" value={`${stats.low}–${stats.high}`} unit="span" />
      <div className="summary-spark" style={{ width: 200, height: 52 }}>
        <MiniSparkline values={stats.last30} />
      </div>
    </section>
  );
}

function Stat({ label, value, unit }: { label: string; value: number | string; unit: string }) {
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500, marginBottom: 4 }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
        <span
          className="tnum"
          style={{
            fontSize: 26,
            fontWeight: 600,
            color: "var(--ink)",
            letterSpacing: "-0.02em",
          }}
        >
          {value}
        </span>
        <span style={{ fontSize: 11, color: "var(--faint)" }}>{unit}</span>
      </div>
    </div>
  );
}

// ─── Month header ─────────────────────────────────────────────────────

function MonthHeader({ label }: { label: string }) {
  return (
    <div
      className="mono"
      style={{
        fontSize: 10,
        letterSpacing: "0.14em",
        textTransform: "uppercase",
        color: "var(--faint)",
        fontWeight: 600,
        paddingTop: 6,
        paddingBottom: 2,
        borderTop: "1px solid var(--line)",
      }}
    >
      {label}
    </div>
  );
}

function groupByMonth(entries: StoredEntry[]): Array<[string, StoredEntry[]]> {
  const groups = new Map<string, StoredEntry[]>();
  for (const e of entries) {
    const d = new Date(e.createdAt);
    const key = d.toLocaleDateString("en-US", { month: "long", year: "numeric" });
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(e);
  }
  return Array.from(groups.entries());
}

// ─── Entry card ───────────────────────────────────────────────────────

export function EntryCard({ entry, onClick }: { entry: StoredEntry; onClick: () => void }) {
  const created = new Date(entry.createdAt);
  const tags = Array.from(new Set(entry.events.map((ev) => ev.tag))).slice(0, 5);
  const tone = valenceTone(entry.avg);

  return (
    <button
      onClick={onClick}
      className="entry-card"
      style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: 10,
        padding: "18px 20px",
        display: "grid",
        gridTemplateColumns: "120px 1fr 160px",
        gap: 16,
        alignItems: "center",
        textAlign: "left",
        cursor: "pointer",
        transition: "box-shadow 120ms ease, border-color 120ms ease",
      }}
      onMouseEnter={(e) => {
        // Hover shadow ink tint — invisible on dark bg, so dark-mode CSS
        // override in the page-level <style> block above lifts it.
        e.currentTarget.style.boxShadow = "0 4px 16px -8px rgba(20,22,26,0.12)";
        e.currentTarget.style.borderColor = "var(--line-mid)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = "none";
        e.currentTarget.style.borderColor = "var(--line)";
      }}
    >
      {/* Left: timestamp + avg pill */}
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink)" }}>
          {fmtShortDate(created)}
        </div>
        <div className="mono" style={{ fontSize: 11, color: "var(--muted)" }}>
          {fmtClockTime(created)}
        </div>
        <div
          className="tnum"
          style={{
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            marginTop: 4,
            padding: "3px 8px",
            borderRadius: 999,
            background: tone.bg,
            color: tone.fg,
            fontSize: 11,
            fontWeight: 600,
            alignSelf: "flex-start",
          }}
        >
          {Math.round(entry.avg)}
        </div>
      </div>

      {/* Middle: narrative + tags */}
      <div style={{ minWidth: 0 }}>
        <p
          className="serif"
          style={{
            fontFamily: "var(--serif)",
            fontSize: 16,
            fontStyle: "italic",
            lineHeight: 1.55,
            color: "var(--ink)",
            margin: 0,
            display: "-webkit-box",
            WebkitLineClamp: 3,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {entry.text || "(empty entry)"}
        </p>
        {tags.length > 0 && (
          <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
            {tags.map((t) => (
              <TagDot key={t} tag={t} />
            ))}
            <span className="mono" style={{ fontSize: 10, color: "var(--faint)", alignSelf: "center" }}>
              {entry.events.length} events
            </span>
          </div>
        )}
      </div>

      {/* Right: sparkline */}
      <div className="entry-spark" style={{ width: 160, height: 54 }}>
        <Sparkline series={entry.series} />
      </div>
    </button>
  );
}

function valenceTone(v: number): { bg: string; fg: string } {
  if (v >= 60) return { bg: "rgba(22,163,74,0.12)", fg: "var(--green)" };
  if (v >= 40) return { bg: "rgba(156,163,175,0.15)", fg: "var(--muted)" };
  return { bg: "rgba(249,115,22,0.12)", fg: "var(--warm-strong)" };
}

function TagDot({ tag }: { tag: string }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 5,
        fontSize: 11,
        color: "var(--muted)",
        fontWeight: 500,
        padding: "2px 7px",
        borderRadius: 5,
        background: "var(--hover)",
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: "50%", background: tagColor(tag) }} />
      {tag}
    </span>
  );
}

function tagColor(tag: string): string {
  const palette = ["#3B82F6", "#F97316", "#16A34A", "#7A4789", "#3D7B87", "#B6A13A", "#8A8F96"];
  let h = 0;
  for (let i = 0; i < tag.length; i++) h = (h * 31 + tag.charCodeAt(i)) >>> 0;
  return palette[h % palette.length];
}

// ─── Sparkline ────────────────────────────────────────────────────────

function Sparkline({ series }: { series: Point[] }) {
  if (series.length < 2) return null;
  const W = 160;
  const H = 54;
  const pad = 4;
  const step = (W - pad * 2) / (series.length - 1);
  const y = (v: number) => pad + (1 - v / 100) * (H - pad * 2);
  let d = `M ${pad} ${y(series[0].v)}`;
  for (let i = 1; i < series.length; i++) {
    const x0 = pad + (i - 1) * step;
    const x1 = pad + i * step;
    const mx = (x0 + x1) / 2;
    d += ` C ${mx} ${y(series[i - 1].v)}, ${mx} ${y(series[i].v)}, ${x1} ${y(series[i].v)}`;
  }
  const areaD = `${d} L ${pad + (series.length - 1) * step} ${H} L ${pad} ${H} Z`;
  return (
    <svg width={W} height={H} style={{ display: "block" }}>
      <defs>
        <linearGradient id="tg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaD} fill="url(#tg)" />
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth="1.5" />
    </svg>
  );
}

function MiniSparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const W = 200;
  const H = 52;
  const pad = 4;
  const step = (W - pad * 2) / (values.length - 1);
  const y = (v: number) => pad + (1 - v / 100) * (H - pad * 2);
  let d = `M ${pad} ${y(values[0])}`;
  for (let i = 1; i < values.length; i++) {
    const x0 = pad + (i - 1) * step;
    const x1 = pad + i * step;
    const mx = (x0 + x1) / 2;
    d += ` C ${mx} ${y(values[i - 1])}, ${mx} ${y(values[i])}, ${x1} ${y(values[i])}`;
  }
  return (
    <svg width={W} height={H} style={{ display: "block" }}>
      <path d={d} fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────

function EmptyState({ onCompose }: { onCompose: () => void }) {
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
      <p
        className="serif"
        style={{ fontFamily: "var(--serif)", fontSize: 22, fontStyle: "italic", color: "var(--ink)" }}
      >
        Your thread starts here.
      </p>
      <p style={{ fontSize: 13, color: "var(--muted)", maxWidth: 420, lineHeight: 1.55 }}>
        Write a few sentences about your day. The engine compiles the narrative into a
        chart and remembers it — so next month you can see which days rhyme.
      </p>
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
        ＋ Log first entry
      </button>
    </section>
  );
}
