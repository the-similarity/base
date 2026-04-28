/**
 * Today screen — the workstation home for Cadence.
 *
 * Four sections, top → bottom (post slop cut):
 *   1. Hero — date + recovery score + rhyme-with-date pill
 *   2. Two-column grid:
 *      Left  — Key metrics column (HRV, RHR, recovery, sleep score, energy,
 *              glucose) with delta vs personal baseline
 *      Right — DayTrajectory chart (today's HR overlayed against the top
 *              rhyme — overlay is hardcoded, no picker)
 *   3. Top rhyme card — featured analogue from engine.findRhymes(),
 *      drives navigation to /rhymes for the full pitch
 *
 * Removed in slop cut: SegControl overlay picker (rhyme overlay now always
 * on — it's the hero feature), RhymeHeatmap, TagDonut, ThreadRibbon
 * (decorative widgets without grounded data semantics).
 *
 * Self-similarity mechanic — the soul of the product:
 *   findRhymes() runs over the user's own 365-day history. The top rhyme
 *   is featured at the bottom of this screen ("Your body has rhymed with
 *   Feb 18 — what came next: …"), and the rhyming day's HR curve is
 *   overlayed on the DayTrajectory chart so the rhyme is VISIBLE not just
 *   stated.
 */
"use client";

import { useMemo } from "react";
import { Icon } from "../icons";
import { Pill, Topbar } from "../shared";
import { DayTrajectory, Ring } from "../charts";
import {
  BASELINE,
  BASELINE_HOURLY,
  DAYS,
  FMT,
  TAG_META,
  TODAY_HOURLY,
} from "../data";
import { findRhymes, OUTCOME_META } from "../../engine";
import type { ScreenProps } from "../screen-types";

export function ScreenToday({ onCmdK, onNavigate }: ScreenProps) {
  // Yesterday's day summary (DAYS[0]) — the headline metrics.
  // Note: in this demo "today" is anchored at 2026-04-27 and DAYS[0] is
  // the most recent COMPLETED day's reading (Whoop/Oura semantics).
  const today = DAYS[0];
  const last7 = DAYS.slice(0, 7);

  // Rhyme finder over user's own data. useMemo keeps the O(N · W · C)
  // sliding-window scan from re-running across re-renders that don't
  // mutate the input window.
  const rhymes = useMemo(() => findRhymes(DAYS, last7, { k: 5 }), [last7]);
  const top = rhymes[0];

  // Build the rhyming day's "HR curve" by stretching a baseline curve
  // by the day's RHR ratio. We don't store hourly HR for every historical
  // day in the demo; this approximation is good enough to show the rhyme
  // visually on the chart without claiming bigger than a demo-mock fidelity.
  const rhymeHourly = useMemo(() => {
    if (!top) return TODAY_HOURLY;
    const dayMid = top.window[0]; // most-recent day of the rhyming window
    const factor = dayMid.rhr / today.rhr;
    return BASELINE_HOURLY.map((p) => ({ h: p.h, hr: Math.round(p.hr * factor) }));
  }, [top, today]);

  // Pre-compute deltas vs baseline for every metric. Memoizable but
  // cheap so we just inline.
  const deltaTone = (cur: number, base: number, lowerBetter: boolean): "pos" | "neg" | "flat" => {
    const d = cur - base;
    if (Math.abs(d) < 0.5) return "flat";
    if (lowerBetter) return d < 0 ? "pos" : "neg";
    return d > 0 ? "pos" : "neg";
  };

  return (
    <div className="cadence-content-col cadence-screen-fade">
      <Topbar
        crumbs={["Workspace", "Today"]}
        onCmdK={onCmdK}
        actions={
          <>
            <button className="cadence-btn">
              <Icon name="download" /> Share
            </button>
            <button className="cadence-btn cadence-btn-primary" onClick={() => onNavigate("log")}>
              <Icon name="plus" /> Log
            </button>
          </>
        }
      />

      <div className="cadence-scroll">
        <div className="cadence-scroll-pad">
          {/* Hero */}
          <div style={{ display: "flex", alignItems: "flex-end", gap: 24, marginBottom: 4 }}>
            <div>
              <div className="cadence-h-eyebrow cadence-mb-8">
                Recovery · {FMT.longDate(today.date)}
              </div>
              <div className="cadence-h-display cadence-num" style={{ fontSize: 56 }}>
                {today.recovery}<span style={{ fontSize: 28, color: "var(--ink-3)" }}>%</span>
              </div>
              <div className="cadence-row cadence-gap-12 cadence-mt-12">
                <Pill tone={today.recovery >= 70 ? "pos" : today.recovery >= 50 ? "warn" : "neg"} dot>
                  {today.recovery >= 70 ? "Primed to train" : today.recovery >= 50 ? "Moderate" : "Take it easy"}
                </Pill>
                {top && (
                  <Pill tone="info">
                    Rhymes with {FMT.shortDate(top.window[0].date)} · {top.score}% match
                  </Pill>
                )}
                <span className="cadence-text-3 cadence-fz-12">
                  HRV {today.hrv}ms · RHR {today.rhr} · Sleep {today.sleep.toFixed(1)}h
                </span>
              </div>
            </div>
            <div className="cadence-right" style={{ marginLeft: "auto" }}>
              <div className="cadence-ring-wrap" style={{ width: 96, height: 96 }}>
                <Ring pct={today.recovery / 100} size={96} thickness={8} color="var(--accent)" />
                <div className="cadence-ring-text" style={{ fontSize: 24 }}>{today.recovery}</div>
              </div>
            </div>
          </div>

          {/* Top: metrics column + day trajectory */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "260px 1fr",
              gap: 14,
              marginTop: 24,
            }}
          >
            <div className="cadence-metric-col">
              <MetricRow
                icon="heart"
                label="HRV"
                value={today.hrv}
                unit="ms"
                delta={today.hrv - BASELINE.hrv}
                deltaUnit="ms"
                tone={deltaTone(today.hrv, BASELINE.hrv, false)}
              />
              <MetricRow
                icon="heartPulse"
                label="Resting HR"
                value={today.rhr}
                unit="bpm"
                delta={today.rhr - BASELINE.rhr}
                deltaUnit="bpm"
                tone={deltaTone(today.rhr, BASELINE.rhr, true)}
              />
              <MetricRow
                icon="circleArrow"
                label="Recovery"
                value={today.recovery}
                unit="%"
                delta={today.recovery - BASELINE.recovery}
                deltaUnit="pp"
                tone={deltaTone(today.recovery, BASELINE.recovery, false)}
              />
              <MetricRow
                icon="bed"
                label="Sleep score"
                value={today.sleepScore}
                unit="%"
                delta={today.sleepScore - BASELINE.sleepScore}
                deltaUnit="pp"
                tone={deltaTone(today.sleepScore, BASELINE.sleepScore, false)}
              />
              <MetricRow
                icon="zap"
                label="Energy"
                value={today.energy}
                unit="/100"
                delta={today.energy - BASELINE.energy}
                deltaUnit=""
                tone={deltaTone(today.energy, BASELINE.energy, false)}
              />
              <MetricRow
                icon="drop"
                label="Glucose (am)"
                value={today.glucose}
                unit="mg/dL"
                delta={today.glucose - BASELINE.glucose}
                deltaUnit=""
                tone={deltaTone(today.glucose, BASELINE.glucose, true)}
              />
            </div>

            <div className="cadence-card" style={{ padding: "16px 20px 8px 12px" }}>
              <div style={{ display: "flex", alignItems: "center", padding: "0 0 6px 12px" }}>
                <div className="cadence-title cadence-fz-13 cadence-fw-6">Heart rate today</div>
                <span className="cadence-text-3 cadence-fz-12" style={{ marginLeft: 10 }}>
                  {top ? `vs ${FMT.shortDate(top.window[0].date)} (rhyme)` : "vs your baseline"}
                </span>
              </div>
              {/* Overlay is hardcoded to the top rhyme — the picker was
                  removed in the slop cut so the hero feature (analogue
                  retrieval) is always visible without an interaction. */}
              <DayTrajectory
                primary={TODAY_HOURLY.map((p) => p.hr)}
                primaryLabel="Today"
                primaryColor="var(--accent)"
                overlays={[
                  {
                    key: "rhy",
                    label: "Rhyme",
                    data: rhymeHourly.map((p) => p.hr),
                    color: "var(--info)",
                    dashed: true,
                  },
                ]}
              />
            </div>
          </div>

          {/* Top rhyme — featured analogue, the bridge to /rhymes */}
          {top && (
            <div className="cadence-ai-bubble cadence-mt-20" style={{ display: "flex", gap: 18, alignItems: "flex-start" }}>
              <div style={{ flex: 1 }}>
                <div className="cadence-ai-head">
                  <span className="cadence-pulse" /> Top rhyme
                </div>
                <div>
                  Your last 7 days look like the week of{" "}
                  <b>{FMT.shortDate(top.window[top.window.length - 1].date)} – {FMT.shortDate(top.window[0].date)}</b>
                  {" "}(<b>{top.score}% match</b>{top.contextTag ? ` · ${TAG_META[top.contextTag].label}` : ""}).
                  In the 14 days that followed, you{" "}
                  <span style={{ color: OUTCOME_META[top.outcomeLabel].color, fontWeight: 600 }}>
                    {OUTCOME_META[top.outcomeLabel].label.replace("→ ", "")}
                  </span>
                  .
                </div>
                <div className="cadence-row cadence-gap-6 cadence-mt-12">
                  <button className="cadence-btn" onClick={() => onNavigate("rhymes")}>
                    See all rhymes <Icon name="arrowRight" />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────── helpers ───────────

interface MetricRowProps {
  icon: string;
  label: string;
  value: number;
  unit: string;
  delta: number;
  deltaUnit: string;
  tone: "pos" | "neg" | "flat";
}

function MetricRow({ icon, label, value, unit, delta, deltaUnit, tone }: MetricRowProps) {
  return (
    <div className="cadence-metric-row">
      <Icon name={icon} className="cadence-ico" />
      <div className="cadence-lab">{label}</div>
      <div>
        <span className="cadence-val">{value}</span>
        <span className="cadence-unit">{unit}</span>
      </div>
      <span className={`cadence-delta cadence-delta-${tone}`}>
        {delta > 0 ? "+" : ""}
        {Math.abs(delta) < 1 ? delta.toFixed(1) : delta.toFixed(0)}
        {deltaUnit}
      </span>
    </div>
  );
}

