/**
 * Today screen — the workstation home for Cadence.
 *
 * Sections (top → bottom):
 *   1. Hero — date + recovery score + "your body is rhyming with…" headline
 *   2. Two-column grid:
 *      Left  — Key metrics column (HRV, RHR, recovery, sleep score, energy,
 *              glucose) with delta vs personal baseline
 *      Right — DayTrajectory chart (today's HR with overlay options)
 *   3. Two-column grid:
 *      Left  — RhymeHeatmap (7-day × 12-hour intensity grid)
 *      Right — TagDonut (last 30 days context distribution)
 *   4. ThreadRibbon (30-day recovery history strip)
 *   5. Top rhyme card — featured analogue from engine.findRhymes()
 *
 * Local state:
 *   - `overlay`: which of "yesterday" / "rhyme" / "baseline" overlays the
 *      DayTrajectory chart shows (visual-only here, default "rhyme" so the
 *      first-impression sells the self-similarity mechanic)
 *
 * Self-similarity mechanic — the soul of the product:
 *   findRhymes() runs over the user's own 365-day history. The top rhyme
 *   is featured at the bottom of this screen ("Your body has rhymed with
 *   Feb 18 — what came next: …"), and the rhyming day's HR curve is
 *   overlayed on the DayTrajectory chart so the rhyme is VISIBLE not just
 *   stated.
 */
"use client";

import { useMemo, useState } from "react";
import { Icon } from "../icons";
import { Pill, Topbar, SectionHead, SegControl } from "../shared";
import {
  DayTrajectory,
  RhymeHeatmap,
  TagDonut,
  ThreadRibbon,
  Ring,
} from "../charts";
import {
  BASELINE,
  BASELINE_HOURLY,
  DAYS,
  FMT,
  TAG_META,
  TODAY_HOURLY,
  YESTERDAY_HOURLY,
} from "../data";
import type { DaySummary } from "../data";
import { findRhymes, OUTCOME_META } from "../../engine";
import type { ScreenProps } from "../screen-types";

// Overlay choice = which compare line is layered on the DayTrajectory.
type OverlayChoice = "yesterday" | "rhyme" | "baseline";

export function ScreenToday({ onCmdK, onNavigate }: ScreenProps) {
  const [overlay, setOverlay] = useState<OverlayChoice>("rhyme");

  // Yesterday's day summary (DAYS[0]) — the headline metrics.
  // Note: in this demo "today" is anchored at 2026-04-27 and DAYS[0] is
  // the most recent COMPLETED day's reading (Whoop/Oura semantics).
  const today = DAYS[0];
  const last7 = DAYS.slice(0, 7);
  const last30 = DAYS.slice(0, 30);

  // Rhyme finder over user's own data. useMemo is critical here: the
  // sliding-window scan is O(N · W · C) and the screen re-renders on
  // overlay toggle. Without memoization we'd re-scan 350+ windows
  // every click.
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
    <div className="content-col screen-fade">
      <Topbar
        crumbs={["Workspace", "Today"]}
        onCmdK={onCmdK}
        actions={
          <>
            <button className="btn">
              <Icon name="download" /> Share
            </button>
            <button className="btn primary" onClick={() => onNavigate("log")}>
              <Icon name="plus" /> Log
            </button>
          </>
        }
      />

      <div className="scroll">
        <div className="scroll-pad">
          {/* Hero */}
          <div style={{ display: "flex", alignItems: "flex-end", gap: 24, marginBottom: 4 }}>
            <div>
              <div className="h-eyebrow mb-8">
                Recovery · {FMT.longDate(today.date)}
              </div>
              <div className="h-display num" style={{ fontSize: 56 }}>
                {today.recovery}<span style={{ fontSize: 28, color: "var(--ink-3)" }}>%</span>
              </div>
              <div className="row gap-12 mt-12">
                <Pill tone={today.recovery >= 70 ? "pos" : today.recovery >= 50 ? "warn" : "neg"} dot>
                  {today.recovery >= 70 ? "Primed to train" : today.recovery >= 50 ? "Moderate" : "Take it easy"}
                </Pill>
                {top && (
                  <Pill tone="info">
                    Rhymes with {FMT.shortDate(top.window[0].date)} · {top.score}% match
                  </Pill>
                )}
                <span className="text-3 fz-12">
                  HRV {today.hrv}ms · RHR {today.rhr} · Sleep {today.sleep.toFixed(1)}h
                </span>
              </div>
            </div>
            <div className="right" style={{ marginLeft: "auto" }}>
              <div className="ring-wrap" style={{ width: 96, height: 96 }}>
                <Ring pct={today.recovery / 100} size={96} thickness={8} color="var(--accent)" />
                <div className="ring-text" style={{ fontSize: 24 }}>{today.recovery}</div>
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
            <div className="metric-col">
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

            <div className="card" style={{ padding: "16px 20px 8px 12px" }}>
              <div style={{ display: "flex", alignItems: "center", padding: "0 0 6px 12px" }}>
                <div className="title fz-13 fw-6">Heart rate today</div>
                <span className="text-3 fz-12" style={{ marginLeft: 10 }}>
                  vs {overlay === "rhyme" && top ? `${FMT.shortDate(top.window[0].date)} (rhyme)` : overlay === "yesterday" ? "yesterday" : "your baseline"}
                </span>
                <div className="right" style={{ marginLeft: "auto" }}>
                  <SegControl
                    value={overlay}
                    onChange={(v) => setOverlay(v as OverlayChoice)}
                    options={[
                      { value: "rhyme", label: "Rhyme" },
                      { value: "yesterday", label: "Yesterday" },
                      { value: "baseline", label: "Baseline" },
                    ]}
                  />
                </div>
              </div>
              <DayTrajectory
                primary={TODAY_HOURLY.map((p) => p.hr)}
                primaryLabel="Today"
                primaryColor="var(--accent)"
                overlays={
                  overlay === "rhyme"
                    ? [{ key: "rhy", label: "Rhyme", data: rhymeHourly.map((p) => p.hr), color: "var(--info)", dashed: true }]
                    : overlay === "yesterday"
                      ? [{ key: "yst", label: "Yesterday", data: YESTERDAY_HOURLY.map((p) => p.hr), color: "var(--ink-3)", dashed: true }]
                      : [{ key: "bln", label: "Baseline", data: BASELINE_HOURLY.map((p) => p.hr), color: "var(--ink-3)", dashed: true }]
                }
              />
            </div>
          </div>

          {/* Mid: rhyme heatmap + tag donut */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.4fr 1fr",
              gap: 14,
              marginTop: 20,
            }}
          >
            <div className="card card-pad">
              <SectionHead
                title="Energy heatmap"
                sub="Last 7 days · 2-hour bins · darker = higher energy"
              />
              <RhymeHeatmap days={last7} />
              <div className="row gap-8 mt-16 fz-11 text-3">
                <span>Less</span>
                <div className="row gap-4">
                  {[0.1, 0.3, 0.5, 0.7, 0.9].map((v) => (
                    <div
                      key={v}
                      style={{
                        width: 12,
                        height: 12,
                        borderRadius: 2,
                        background: `rgba(91,138,114,${0.10 + v * 0.7})`,
                      }}
                    />
                  ))}
                </div>
                <span>More</span>
              </div>
            </div>

            <div className="card card-pad">
              <SectionHead title="Context" sub="Last 30 days" />
              <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                <div className="donut-c" style={{ width: 160, height: 160 }}>
                  <TagDonut days={last30} size={160} thickness={20} />
                </div>
                <div className="grow">
                  {tagBreakdown(last30).slice(0, 5).map((row) => (
                    <div className="legend-row" key={row.key}>
                      <span className="sw" style={{ background: row.color }} />
                      <span className="lab">{row.label}</span>
                      <span className="pct">{row.pct}%</span>
                      <span className="amt">{row.n}d</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* 30-day thread ribbon */}
          <div className="card card-pad mt-20">
            <SectionHead
              title="30-day thread"
              sub="Bar height = recovery · color = context"
            />
            <ThreadRibbon days={last30} height={56} />
          </div>

          {/* Top rhyme — featured analogue */}
          {top && (
            <div className="ai-bubble mt-20" style={{ display: "flex", gap: 18, alignItems: "flex-start" }}>
              <div style={{ flex: 1 }}>
                <div className="ai-head">
                  <span className="pulse" /> Top rhyme
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
                <div className="row gap-6 mt-12">
                  <button className="btn" onClick={() => onNavigate("rhymes")}>
                    See all rhymes <Icon name="arrowRight" />
                  </button>
                  <button className="btn ghost" onClick={() => setOverlay("rhyme")}>
                    Overlay on chart
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
    <div className="metric-row">
      <Icon name={icon} className="ico" />
      <div className="lab">{label}</div>
      <div>
        <span className="val">{value}</span>
        <span className="unit">{unit}</span>
      </div>
      <span className={`delta ${tone}`}>
        {delta > 0 ? "+" : ""}
        {Math.abs(delta) < 1 ? delta.toFixed(1) : delta.toFixed(0)}
        {deltaUnit}
      </span>
    </div>
  );
}

interface TagBreakdownRow {
  key: string;
  label: string;
  color: string;
  n: number;
  pct: number;
}

function tagBreakdown(days: DaySummary[]): TagBreakdownRow[] {
  const counts: Record<string, number> = {};
  for (const d of days) {
    const t = d.tag ?? "normal";
    counts[t] = (counts[t] || 0) + 1;
  }
  const total = days.length || 1;
  return Object.entries(counts)
    .map(([key, n]) => ({
      key,
      label: TAG_META[key as keyof typeof TAG_META]?.label ?? key,
      color: TAG_META[key as keyof typeof TAG_META]?.color ?? "#7a7a75",
      n,
      pct: Math.round((n / total) * 100),
    }))
    .sort((a, b) => b.n - a.n);
}
