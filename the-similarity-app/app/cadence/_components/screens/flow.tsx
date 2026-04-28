/**
 * Flow screen — multi-channel time-series view of today's vitals.
 *
 * Stacks 4 channels vertically as small-multiples (Lumen's cashflow but
 * for biomarkers): HRV, HR, glucose, activity. Each row carries:
 *   - label + current value + unit
 *   - delta vs baseline pill
 *   - 24h sparkline filling the row width
 *   - on-hover tooltip via SVG <title> on each chart
 *
 * Range selector at the top toggles 1D / 3D / 1W / 1M (visual-only — the
 * data fixtures only provide 24h hourly resolution; longer ranges
 * downsample DAYS to one point per day).
 *
 * Why small-multiples instead of one stacked chart: each channel has a
 * different y-axis scale (HRV 40-90, HR 50-110, glucose 80-140, activity
 * 0-10) and overlaying them loses information. Small multiples also let
 * the user scan top-to-bottom and spot regime shifts (e.g. "post-lunch
 * glucose spike correlates with HR rise") without dual-axis confusion.
 */
"use client";

import { useState } from "react";
import { Icon } from "../icons";
import { Pill, Topbar, SectionHead, SegControl } from "../shared";
import { ChannelMini, Sparkline } from "../charts";
import { BASELINE, DAYS, FMT, TODAY_FLOW } from "../data";
import type { ScreenProps } from "../screen-types";

type RangeChoice = "1D" | "3D" | "1W" | "1M";

export function ScreenFlow({ onCmdK }: ScreenProps) {
  const [range, setRange] = useState<RangeChoice>("1D");

  const today = DAYS[0];
  // For ranges other than 1D we downsample DAYS into one point per day,
  // collapsing the 24h channel into a single daily aggregate. This keeps
  // the chart shape consistent across range toggles.
  const dailyBars = (() => {
    const n = range === "3D" ? 3 : range === "1W" ? 7 : range === "1M" ? 30 : 0;
    if (!n) return null;
    return DAYS.slice(0, n).reverse(); // oldest → newest
  })();

  return (
    <div className="cadence-content-col cadence-screen-fade">
      <Topbar
        crumbs={["Workspace", "Flow"]}
        onCmdK={onCmdK}
        actions={
          <SegControl
            value={range}
            onChange={(v) => setRange(v as RangeChoice)}
            options={[
              { value: "1D", label: "1D" },
              { value: "3D", label: "3D" },
              { value: "1W", label: "1W" },
              { value: "1M", label: "1M" },
            ]}
          />
        }
      />

      <div className="cadence-scroll">
        <div className="cadence-scroll-pad">
          <div className="cadence-h-eyebrow cadence-mb-8">
            Multi-channel vitals · {FMT.longDate(today.date)}
          </div>
          <div className="cadence-h-display cadence-num" style={{ fontSize: 36, marginBottom: 4 }}>
            4 channels in parallel
          </div>
          <div className="cadence-text-3 cadence-fz-12 cadence-mb-20">
            {range === "1D"
              ? "Hourly HRV / HR / Glucose / Activity for the last 24 hours."
              : `Daily aggregate over the last ${range === "3D" ? "3" : range === "1W" ? "7" : "30"} days.`}
          </div>

          {TODAY_FLOW.map((ch) => {
            const cur = ch.series[ch.series.length - 1];
            const base =
              ch.key === "hrv" ? BASELINE.hrv :
              ch.key === "hr" ? BASELINE.rhr :
              ch.key === "glucose" ? BASELINE.glucose :
              ch.key === "activity" ? 4 : 0;
            const delta = cur - base;
            const lowerBetter = ch.key === "hr" || ch.key === "glucose";
            const tone =
              Math.abs(delta) < 0.5 ? "default" :
              lowerBetter ? (delta < 0 ? "pos" : "neg") :
              (delta > 0 ? "pos" : "neg");
            return (
              <div className="cadence-card cadence-mb-12" style={{ padding: "16px 18px 4px 18px" }} key={ch.key}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 6 }}>
                  <div className="cadence-title cadence-fz-13 cadence-fw-6" style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: ch.color }} />
                    {ch.label}
                  </div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                    <span className="cadence-h-display cadence-num" style={{ fontSize: 24, color: ch.color }}>{cur}</span>
                    <span className="cadence-text-3 cadence-fz-12">{ch.unit}</span>
                  </div>
                  <Pill tone={tone}>
                    {delta > 0 ? "+" : ""}
                    {delta.toFixed(0)}{ch.unit} vs baseline
                  </Pill>
                  <span className="cadence-text-3 cadence-fz-12 cadence-right" style={{ marginLeft: "auto" }}>
                    range {ch.range[0]}–{ch.range[1]} {ch.unit}
                  </span>
                </div>
                {range === "1D" ? (
                  <ChannelMini channel={ch} height={88} />
                ) : (
                  <DailyBars
                    days={dailyBars!}
                    accessor={
                      ch.key === "hrv" ? (d) => d.hrv :
                      ch.key === "hr" ? (d) => d.rhr :
                      ch.key === "glucose" ? (d) => d.glucose :
                      (d) => d.trainingLoad
                    }
                    color={ch.color}
                  />
                )}
              </div>
            );
          })}

          {/* Cross-channel section: small relationship card */}
          <div className="cadence-card cadence-card-pad cadence-mt-20">
            <SectionHead
              title="Cross-channel relationships"
              sub="Quick correlations across today's flow"
            />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14 }}>
              <RelationCard
                a="HRV"
                b="Sleep score"
                value={today.hrv >= BASELINE.hrv && today.sleepScore >= BASELINE.sleepScore ? "synchronized" : "diverging"}
                detail="Both above baseline"
                color="var(--accent)"
              />
              <RelationCard
                a="HR"
                b="Activity"
                value="tight"
                detail="0.83 correlation today"
                color="var(--info)"
              />
              <RelationCard
                a="Glucose"
                b="Meals"
                value="3 spikes"
                detail="9am · 1pm · 8pm"
                color="var(--warn)"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────── helpers ───────────

interface DailyBarsProps {
  days: import("../data").DaySummary[];
  accessor: (d: import("../data").DaySummary) => number;
  color: string;
}

function DailyBars({ days, accessor, color }: DailyBarsProps) {
  const values = days.map(accessor);
  return (
    <div style={{ padding: "8px 0 4px 0" }}>
      <Sparkline data={values} width={760} height={88} stroke={color} smooth={false} />
    </div>
  );
}

interface RelationCardProps {
  a: string;
  b: string;
  value: string;
  detail: string;
  color: string;
}

function RelationCard({ a, b, value, detail, color }: RelationCardProps) {
  return (
    <div className="cadence-card cadence-card-tinted cadence-card-pad" style={{ borderLeft: `3px solid ${color}` }}>
      <div className="cadence-text-3 cadence-fz-11" style={{ textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 550 }}>
        {a} <Icon name="arrowRight" style={{ width: 10, height: 10, display: "inline" }} /> {b}
      </div>
      <div className="cadence-h-display" style={{ fontSize: 20, marginTop: 6 }}>{value}</div>
      <div className="cadence-text-3 cadence-fz-12 cadence-mt-4">{detail}</div>
    </div>
  );
}
