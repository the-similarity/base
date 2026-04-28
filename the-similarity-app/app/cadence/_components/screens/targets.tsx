/**
 * Targets screen — active short-horizon commitments with progress.
 *
 * Each target is a row showing:
 *   - Name (e.g. "Sleep ≥ 7.5h nightly")
 *   - Current value (last 7-day average)
 *   - Goal value
 *   - Progress bar (0-100%)
 *   - Hit rate (last 14 days fraction)
 *   - Streak (consecutive days hitting target)
 *   - Right-side icon button stub (settings)
 *
 * Targets vs Goals (separation of concerns):
 *   - Targets are recurring nightly/weekly commitments — measured by
 *     hit-rate.
 *   - Goals are long-horizon outcomes (months out) — measured by
 *     trajectory + projected completion. Lives in /goals.
 *
 * The bottom card surfaces an aggregate "Hit rate this week" KPI and a
 * mini bar chart of per-day target-hit count.
 */
"use client";

import { Topbar, SectionHead, Pill } from "../shared";
import { TARGETS, DAYS, FMT } from "../data";
import type { Target } from "../data";
import type { ScreenProps } from "../screen-types";

export function ScreenTargets({ onCmdK }: ScreenProps) {
  const last7 = DAYS.slice(0, 7);

  // Aggregate hit-count per day across all targets — visual-only proxy
  // computed from the target.current vs target.goal direction.
  const dailyHits = last7.map((d) => {
    let n = 0;
    for (const t of TARGETS) {
      if (t.id === "sleep-min" && d.sleep >= t.goal) n++;
      if (t.id === "hrv-week" && d.hrv >= t.goal) n++;
      if (t.id === "recovery" && d.recovery >= t.goal) n++;
      if (t.id === "load-band" && d.trainingLoad >= 6 && d.trainingLoad <= 8) n++;
      if (t.id === "steps" && d.steps >= t.goal) n++;
    }
    return n;
  });

  const overallHit = TARGETS.reduce((s, t) => s + t.hitRate, 0) / TARGETS.length;
  const longestStreak = Math.max(...TARGETS.map((t) => t.streak));

  return (
    <div className="cadence-content-col cadence-screen-fade">
      <Topbar crumbs={["Workspace", "Targets"]} onCmdK={onCmdK} />

      <div className="cadence-scroll">
        <div className="cadence-scroll-pad">
          <div className="cadence-h-eyebrow cadence-mb-8">Active commitments</div>
          <div className="cadence-h-display cadence-num" style={{ fontSize: 44 }}>
            {TARGETS.length} targets · {Math.round(overallHit * 100)}% hit rate
          </div>
          <div className="cadence-row cadence-gap-12 cadence-mt-12 cadence-mb-20">
            <Pill tone={overallHit >= 0.7 ? "pos" : overallHit >= 0.5 ? "warn" : "neg"} dot>
              {overallHit >= 0.7 ? "On track" : overallHit >= 0.5 ? "Inconsistent" : "Drifting"}
            </Pill>
            <Pill tone="info">longest streak {longestStreak}d</Pill>
          </div>

          {/* Per-target rows */}
          <div className="cadence-card" style={{ overflow: "hidden" }}>
            {TARGETS.map((t) => (
              <TargetRow key={t.id} t={t} />
            ))}
          </div>

          {/* Aggregate this-week chart */}
          <div className="cadence-card cadence-card-pad cadence-mt-20">
            <SectionHead
              title="This week"
              sub={`Targets hit per day · last 7 days · max ${TARGETS.length}`}
            />
            <div style={{ display: "grid", gridTemplateColumns: `repeat(7, 1fr)`, gap: 6, alignItems: "end", height: 140 }}>
              {dailyHits.map((h, i) => {
                const day = last7[i];
                const dow = day.date.toLocaleDateString("en-US", { weekday: "short" });
                const pct = TARGETS.length === 0 ? 0 : h / TARGETS.length;
                return (
                  <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                    <div className="cadence-mono" style={{ fontSize: 11, color: "var(--ink)" }}>{h}/{TARGETS.length}</div>
                    <div
                      style={{
                        width: "100%",
                        height: `${4 + pct * 100}px`,
                        background: pct >= 0.8 ? "var(--accent)" : pct >= 0.5 ? "var(--warn)" : "var(--ink-4)",
                        borderRadius: 4,
                      }}
                      title={`${dow} ${FMT.shortDate(day.date)}: ${h}/${TARGETS.length} targets`}
                    />
                    <div className="cadence-text-3 cadence-fz-11">{dow}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* New target stub */}
          <div className="cadence-card cadence-card-tinted cadence-card-pad cadence-mt-20" style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div className="cadence-grow">
              <div className="cadence-title cadence-fz-13 cadence-fw-6">Add a target</div>
              <div className="cadence-text-3 cadence-fz-12 cadence-mt-4">
                Targets work best when they&rsquo;re short-horizon (nightly /
                weekly) and quantifiable. For multi-month outcomes use Goals.
              </div>
            </div>
            <button className="cadence-btn cadence-btn-primary">+ New target</button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface TargetRowProps {
  t: Target;
}

function TargetRow({ t }: TargetRowProps) {
  // Compute display-relative progress fraction.
  const pct =
    t.direction === "max"
      ? Math.max(0, Math.min(1, 1 - (t.current - t.goal) / t.goal))
      : t.direction === "range"
        ? 1 - Math.min(1, Math.abs(t.current - t.goal) / t.goal)
        : Math.min(1, t.current / t.goal);
  const fillColor = pct >= 0.85 ? "accent" : pct >= 0.6 ? "warn" : "neg";
  return (
    <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--border)" }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <span style={{ width: 8, height: 8, borderRadius: 2, background: t.color }} />
        <div className="cadence-title cadence-fz-13 cadence-fw-6">{t.name}</div>
        <div className="cadence-text-3 cadence-fz-12">
          last 7d avg <span className="cadence-mono" style={{ color: "var(--ink)", fontWeight: 600 }}>{t.current}{t.unit}</span> ·
          goal <span className="cadence-mono">{t.goal}{t.unit}</span>
        </div>
        <span className="cadence-right" style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          <Pill tone={t.streak >= 5 ? "pos" : t.streak > 0 ? "default" : "neg"}>
            {t.streak > 0 ? `${t.streak}d streak` : "no streak"}
          </Pill>
          <Pill tone={t.hitRate >= 0.7 ? "pos" : t.hitRate >= 0.5 ? "warn" : "neg"}>
            {Math.round(t.hitRate * 100)}% (14d)
          </Pill>
        </span>
      </div>
      <div className="cadence-progress cadence-mt-12">
        <div className={`cadence-fill cadence-fill-${fillColor}`} style={{ width: `${pct * 100}%`, background: t.color }} />
      </div>
    </div>
  );
}
