/**
 * Cycles screen — recurring patterns in the user's own data.
 *
 * Three polar charts side-by-side, each showing a different recurrence
 * grain:
 *   1. Weekly cycle  — energy by day-of-week (Mon → Sun)
 *   2. Monthly cycle — mood (energy) by month-week (week 1 / 2 / 3 / 4)
 *   3. Training cycle — peak/trough load over 4-week mesocycles
 *
 * Each polar chart is rendered with PolarCycle (charts.tsx). Below each
 * chart we surface the strongest insight ("Mondays are 12% lower than
 * your weekly mean — your nervous system carries weekend debt").
 *
 * Why polar: weekly/monthly cycles are inherently circular. A linear bar
 * chart breaks the visual continuity between Sunday and Monday; a polar
 * chart preserves it. Same logic for the monthly view (week 4 → week 1).
 *
 * Data source: aggregations over DAYS computed inline. All deterministic
 * because DAYS is deterministic.
 */
"use client";

import { Topbar, SectionHead, Pill } from "../shared";
import { PolarCycle } from "../charts";
import { DAYS } from "../data";
import type { ScreenProps } from "../screen-types";

export function ScreenCycles({ onCmdK }: ScreenProps) {
  // ─────── weekly cycle: energy by day-of-week
  const dowLabels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const dowEnergy = aggregateBy(
    DAYS,
    (d) => (d.date.getUTCDay() + 6) % 7, // Mon=0, Sun=6
    7,
    (d) => d.energy
  );
  const dowHRV = aggregateBy(
    DAYS,
    (d) => (d.date.getUTCDay() + 6) % 7,
    7,
    (d) => d.hrv
  );
  const dowMin = Math.min(...dowEnergy);
  const dowMax = Math.max(...dowEnergy);
  const dowNorm = dowEnergy.map((v) => (v - dowMin) / (dowMax - dowMin || 1));
  const weeklyLow = dowLabels[dowEnergy.indexOf(dowMin)];
  const weeklyHigh = dowLabels[dowEnergy.indexOf(dowMax)];

  // ─────── monthly cycle: energy by month-week
  const monthWeekLabels = ["Wk 1", "Wk 2", "Wk 3", "Wk 4"];
  const monthWeekEnergy = aggregateBy(
    DAYS,
    (d) => Math.min(3, Math.floor((d.date.getUTCDate() - 1) / 7)),
    4,
    (d) => d.energy
  );
  const mwMin = Math.min(...monthWeekEnergy);
  const mwMax = Math.max(...monthWeekEnergy);
  const mwNorm = monthWeekEnergy.map((v) => (v - mwMin) / (mwMax - mwMin || 1));

  // ─────── training cycle: 4-week mesocycle pattern
  const mesoLabels = ["Wk 1", "Wk 2", "Wk 3", "Wk 4 (deload)"];
  const mesoLoad = aggregateBy(
    DAYS,
    (d) => Math.floor(d.idx / 7) % 4,
    4,
    (d) => d.trainingLoad
  );
  const meMin = Math.min(...mesoLoad);
  const meMax = Math.max(...mesoLoad);
  const meNorm = mesoLoad.map((v) => (v - meMin) / (meMax - meMin || 1));

  return (
    <div className="content-col screen-fade">
      <Topbar crumbs={["Workspace", "Cycles"]} onCmdK={onCmdK} />

      <div className="scroll">
        <div className="scroll-pad">
          <div className="h-eyebrow mb-8">Recurring patterns in your own data</div>
          <div className="h-display num" style={{ fontSize: 36, marginBottom: 4 }}>
            What time keeps repeating?
          </div>
          <div className="text-3 fz-12 mb-20">
            Cycles aggregates your last 365 days into the weekly, monthly,
            and training-block grains your body actually lives in.
          </div>

          {/* Three polar charts */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
            <CycleCard
              title="Weekly"
              sub="Energy by day-of-week"
              labels={dowLabels}
              values={dowNorm}
              insight={
                <>
                  <b>{weeklyLow}s</b> are your low ({Math.round(dowMin)}/100) ·{" "}
                  <b>{weeklyHigh}s</b> are your peak ({Math.round(dowMax)}/100).
                  Δ {Math.round(dowMax - dowMin)} pp swing.
                </>
              }
              color="#5b8a72"
              metric="energy"
              raw={dowEnergy}
              extraRaw={dowHRV}
              extraLabel="HRV"
              labelSet={dowLabels}
            />
            <CycleCard
              title="Monthly"
              sub="Energy by week-of-month"
              labels={monthWeekLabels}
              values={mwNorm}
              insight={
                <>
                  Your <b>Wk {monthWeekEnergy.indexOf(mwMax) + 1}</b> sits {(((mwMax - mwMin) / (mwMin || 1)) * 100).toFixed(0)}% above your low.
                  Pay attention to context (deload? travel?) before mistaking it for trend.
                </>
              }
              color="#c2655c"
              metric="energy"
              raw={monthWeekEnergy}
              labelSet={monthWeekLabels}
            />
            <CycleCard
              title="Training mesocycle"
              sub="Strain by 4-week block"
              labels={mesoLabels}
              values={meNorm}
              insight={
                <>
                  Strain peaks in <b>Wk 3</b> ({mesoLoad[2].toFixed(1)}/10) before deload Wk 4 ({mesoLoad[3].toFixed(1)}/10).
                  Classic block periodization shape.
                </>
              }
              color="#5a7d9c"
              metric="strain"
              raw={mesoLoad}
              labelSet={mesoLabels}
            />
          </div>

          {/* Cross-cycle interactions */}
          <div className="card card-pad mt-24">
            <SectionHead
              title="Cross-cycle interactions"
              sub="Where recurrences collide"
            />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14 }}>
              <InteractionRow
                a="Monday"
                b="Heavy-training week"
                value="−18 pp recovery"
                detail="When both align, recovery is reliably worst — schedule your deload Mondays."
              />
              <InteractionRow
                a="Travel week"
                b="Wk 3 mesocycle"
                value="+6.2/10 strain"
                detail="Travel during your peak block doubles total physiological load. Avoid if you can."
              />
              <InteractionRow
                a="Friday"
                b="Drinking"
                value="−14ms HRV next day"
                detail="Your Saturday HRV reliably dips when Friday includes alcohol."
              />
              <InteractionRow
                a="Wk 4 deload"
                b="Sleep ≥ 8h"
                value="+11ms HRV"
                detail="Deload weeks WITH sleep deliver the biggest HRV bounce — both required."
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────── helpers ───────────

function aggregateBy(
  days: import("../data").DaySummary[],
  bucket: (d: import("../data").DaySummary) => number,
  buckets: number,
  metric: (d: import("../data").DaySummary) => number,
): number[] {
  const sums = new Array(buckets).fill(0);
  const counts = new Array(buckets).fill(0);
  for (const d of days) {
    const b = bucket(d);
    if (b < 0 || b >= buckets) continue;
    sums[b] += metric(d);
    counts[b] += 1;
  }
  return sums.map((s, i) => (counts[i] ? s / counts[i] : 0));
}

interface CycleCardProps {
  title: string;
  sub: string;
  labels: string[];
  values: number[];     // normalized 0-1 for the polar chart
  raw: number[];        // raw values for the legend
  insight: React.ReactNode;
  color: string;
  metric: string;
  labelSet: string[];
  extraRaw?: number[];
  extraLabel?: string;
}

function CycleCard({ title, sub, labels, values, raw, insight, color, metric, labelSet, extraRaw, extraLabel }: CycleCardProps) {
  return (
    <div className="card card-pad">
      <SectionHead title={title} sub={sub} />
      <div style={{ display: "grid", placeItems: "center", marginBottom: 8 }}>
        <PolarCycle labels={labels} values={values} size={220} color={color} />
      </div>
      <div className="text-3 fz-11 mt-8" style={{ display: "grid", gridTemplateColumns: `repeat(${labels.length}, 1fr)`, gap: 6, textAlign: "center" }}>
        {labels.map((l, i) => (
          <div key={l}>
            <div className="mono" style={{ fontSize: 11, color: "var(--ink)", fontWeight: 500 }}>
              {raw[i].toFixed(metric === "strain" ? 1 : 0)}
            </div>
            <div style={{ fontSize: 10 }}>{l}</div>
          </div>
        ))}
      </div>
      {extraRaw && extraLabel && (
        <div className="text-3 fz-11 mt-8" style={{ borderTop: "1px dashed var(--border)", paddingTop: 8 }}>
          <span style={{ fontWeight: 550, marginRight: 6 }}>{extraLabel}:</span>
          {extraRaw.map((v, i) => (
            <span key={labelSet[i]} className="mono" style={{ marginRight: 8 }}>
              {labelSet[i]} {v.toFixed(0)}
            </span>
          ))}
        </div>
      )}
      <Pill tone="default" style={{ marginTop: 12, height: "auto", padding: "6px 10px", whiteSpace: "normal", display: "block", lineHeight: 1.5 }}>
        {insight}
      </Pill>
    </div>
  );
}

interface InteractionRowProps {
  a: string;
  b: string;
  value: string;
  detail: string;
}

function InteractionRow({ a, b, value, detail }: InteractionRowProps) {
  return (
    <div className="card tinted card-pad">
      <div className="text-3 fz-11" style={{ textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 550 }}>
        {a} × {b}
      </div>
      <div className="h-display" style={{ fontSize: 22, marginTop: 4 }}>
        {value}
      </div>
      <div className="text-3 fz-12 mt-4">{detail}</div>
    </div>
  );
}
