/**
 * Log screen — chronological event ledger + quick-log composer.
 *
 * Top section:
 *   - Composer: input + 8 quick-add buttons (vitals / workout / meal /
 *     sleep / mood / supplement / alcohol / stress) — visual-only here,
 *     no actual write since v1 is session-state and the demo data is
 *     pre-seeded
 *   - Filter chips: All / Vitals / Workouts / Meals / Sleep / Mood /
 *     Supplements / Alcohol / Stress
 *
 * Body:
 *   - Day-grouped log rows (Today / Yesterday / N days ago) — each row
 *     is one logged event with timestamp, kind icon, title + detail,
 *     and optional metric payload (e.g. "HRV 64 · RHR 58").
 *
 * Local state:
 *   - `composerText`: the input contents (visual)
 *   - `filter`: active kind filter (or "all")
 *
 * Why a quick-log composer at the top: the most common interaction in a
 * personal-health app is "I just did X, capture it." The composer mirrors
 * Apple Notes / Day One — type a sentence, hit a quick-add chip to tag.
 * Real version would parse the sentence (à la Prudent's narrative engine)
 * but v1 is mock-only.
 */
"use client";

import { useMemo, useState } from "react";
import { Icon } from "../icons";
import { Topbar } from "../shared";
import { LOG_EVENTS, LOG_KIND_META, FMT } from "../data";
import type { LogEvent, LogKind } from "../data";
import type { ScreenProps } from "../screen-types";

const FILTERS: Array<{ value: "all" | LogKind; label: string }> = [
  { value: "all", label: "All" },
  { value: "vitals", label: "Vitals" },
  { value: "workout", label: "Workouts" },
  { value: "meal", label: "Meals" },
  { value: "sleep", label: "Sleep" },
  { value: "mood", label: "Mood" },
  { value: "supplement", label: "Supplements" },
  { value: "alcohol", label: "Alcohol" },
  { value: "stress", label: "Stress" },
];

const QUICK_ADDS: Array<{ kind: LogKind; label: string }> = [
  { kind: "vitals", label: "Vitals" },
  { kind: "workout", label: "Workout" },
  { kind: "meal", label: "Meal" },
  { kind: "sleep", label: "Sleep" },
  { kind: "mood", label: "Mood" },
  { kind: "supplement", label: "Supp" },
  { kind: "alcohol", label: "Drink" },
  { kind: "stress", label: "Stress" },
];

export function ScreenLog({ onCmdK }: ScreenProps) {
  const [composer, setComposer] = useState("");
  const [filter, setFilter] = useState<"all" | LogKind>("all");

  // Filter + sort newest-first.
  const visible = useMemo(() => {
    const filtered = filter === "all" ? LOG_EVENTS : LOG_EVENTS.filter((e) => e.kind === filter);
    return [...filtered].sort((a, b) => b.date.getTime() - a.date.getTime());
  }, [filter]);

  // Group by day for section dividers.
  const groups = useMemo(() => {
    const out: Map<string, LogEvent[]> = new Map();
    for (const e of visible) {
      const key = e.date.toISOString().slice(0, 10);
      const arr = out.get(key) ?? [];
      arr.push(e);
      out.set(key, arr);
    }
    return out;
  }, [visible]);

  return (
    <div className="cadence-content-col cadence-screen-fade">
      <Topbar
        crumbs={["Workspace", "Log"]}
        onCmdK={onCmdK}
        actions={
          <button className="cadence-btn cadence-btn-primary">
            <Icon name="plus" /> Add
          </button>
        }
      />

      <div className="cadence-scroll">
        <div className="cadence-scroll-pad">
          <div className="cadence-h-eyebrow cadence-mb-8">Event ledger · last 7 days</div>
          <div className="cadence-h-display cadence-num" style={{ fontSize: 36, marginBottom: 16 }}>
            {LOG_EVENTS.length} logged
          </div>

          {/* Composer */}
          <div className="cadence-composer">
            <Icon name="plus" style={{ color: "var(--ink-3)" }} />
            <input
              value={composer}
              onChange={(e) => setComposer(e.target.value)}
              placeholder="Capture something — &ldquo;ran 8k easy, hr 142&rdquo;…"
            />
            <div style={{ display: "flex", gap: 4 }}>
              {QUICK_ADDS.map((q) => (
                <button
                  key={q.kind}
                  className="cadence-btn"
                  style={{ height: 26, padding: "0 8px", fontSize: 11.5 }}
                  title={`Quick log: ${q.label}`}
                  onClick={() => {
                    setComposer((s) => (s.trim() ? `${s} #${q.kind}` : `[${q.label}] `));
                  }}
                >
                  <Icon name={LOG_KIND_META[q.kind].icon} style={{ width: 11, height: 11 }} />
                  {q.label}
                </button>
              ))}
            </div>
          </div>

          {/* Filter chips */}
          <div className="cadence-filter-bar" style={{ borderBottom: "none", padding: "8px 0 16px 0" }}>
            {FILTERS.map((f) => (
              <button
                key={f.value}
                className={`cadence-chip ${filter === f.value ? "is-active" : ""}`}
                onClick={() => setFilter(f.value)}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* Day-grouped log */}
          <div className="cadence-card" style={{ overflow: "hidden" }}>
            {Array.from(groups.entries()).map(([dayKey, events]) => {
              const date = new Date(dayKey);
              return (
                <div key={dayKey}>
                  <div
                    style={{
                      padding: "10px 16px",
                      background: "var(--surface-2)",
                      borderTop: "1px solid var(--border)",
                      borderBottom: "1px solid var(--border)",
                      display: "flex",
                      alignItems: "baseline",
                      gap: 10,
                    }}
                  >
                    <span className="cadence-h-eyebrow">{relativeDay(date)}</span>
                    <span className="cadence-text-3 cadence-fz-11">{FMT.longDate(date)}</span>
                    <span className="cadence-text-3 cadence-fz-11 cadence-right" style={{ marginLeft: "auto" }}>
                      {events.length} events
                    </span>
                  </div>
                  {events.map((e) => {
                    const meta = LOG_KIND_META[e.kind];
                    return (
                      <div className="cadence-log-row" key={e.id}>
                        <span className="cadence-tm">{FMT.time(e.date)}</span>
                        <div className="cadence-ic" style={{ background: meta.color + "22", color: meta.color, borderColor: meta.color + "44" }}>
                          <Icon name={meta.icon} />
                        </div>
                        <div className="cadence-body">
                          <div className="cadence-ttl">{e.title}</div>
                          <div className="cadence-sub">{e.detail}</div>
                        </div>
                        <div className="cadence-meta">{e.metric ?? meta.label}</div>
                        <button className="cadence-icon-btn" aria-label="more">
                          <Icon name="chevron" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              );
            })}
            {visible.length === 0 && (
              <div className="cadence-card-pad cadence-text-3 cadence-fz-13" style={{ textAlign: "center" }}>
                No events match this filter.
              </div>
            )}
          </div>

          {/* Counts breakdown */}
          <div className="cadence-row cadence-gap-12 cadence-mt-20">
            {(Object.keys(LOG_KIND_META) as LogKind[]).map((k) => {
              const n = LOG_EVENTS.filter((e) => e.kind === k).length;
              if (n === 0) return null;
              const meta = LOG_KIND_META[k];
              return (
                <div key={k} className="cadence-row cadence-gap-6 cadence-fz-12 cadence-text-3">
                  <span style={{ width: 6, height: 6, borderRadius: 999, background: meta.color }} />
                  {meta.label} <span className="cadence-mono" style={{ color: "var(--ink-2)", fontWeight: 600 }}>{n}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────── helpers ───────────

function relativeDay(d: Date): string {
  const today = new Date("2026-04-27T00:00:00Z");
  const ms = today.getTime() - d.getTime();
  const days = Math.round(ms / (1000 * 60 * 60 * 24));
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return `${days} days ago`;
}

