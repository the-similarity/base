/**
 * Labs screen — long-term biomarker tracking with optimal ranges.
 *
 * Each biomarker is a row showing:
 *   - Name + unit
 *   - Current value (instrument serif large)
 *   - Personal baseline (rolling avg of past draws)
 *   - Optimal range (clinical reference)
 *   - 5-point trendline with optimal range band shaded
 *   - Direction indicator (lower-better / higher-better / in-range)
 *
 * Grouped by category (metabolic / lipids / hormones / vitamins /
 * inflammation) so related markers cluster.
 *
 * The 5 historical draws span ~18 months. Last draw date is shown in
 * the topbar action area. New-upload button at the top right is a stub.
 */
"use client";

import { Topbar, SectionHead, Pill } from "../shared";
import { Icon } from "../icons";
import { LabTrend } from "../charts";
import { LABS, LAB_DATES } from "../data";
import type { LabBiomarker } from "../data";
import type { ScreenProps } from "../screen-types";

const CATEGORY_META: Record<LabBiomarker["category"], { label: string; color: string }> = {
  metabolic: { label: "Metabolic", color: "#5b8a72" },
  lipids: { label: "Lipids", color: "#c2655c" },
  hormones: { label: "Hormones", color: "#7d3aa9" },
  vitamins: { label: "Vitamins", color: "#c89a4a" },
  inflammation: { label: "Inflammation", color: "#5a7d9c" },
};

export function ScreenLabs({ onCmdK }: ScreenProps) {
  const lastDraw = LAB_DATES[LAB_DATES.length - 1];

  // Group by category
  const grouped = new Map<LabBiomarker["category"], LabBiomarker[]>();
  for (const lab of LABS) {
    const arr = grouped.get(lab.category) ?? [];
    arr.push(lab);
    grouped.set(lab.category, arr);
  }

  // In-range counts
  const inRange = LABS.filter((l) => l.current >= l.optimalLow && l.current <= l.optimalHigh).length;
  const outOfRange = LABS.length - inRange;
  const trendingUp = LABS.filter((l, i) => l.history[l.history.length - 1] > l.history[0] && l.direction !== "low").length +
    LABS.filter((l) => l.history[l.history.length - 1] < l.history[0] && l.direction === "low").length;

  // tiny lint guard
  void trendingUp;

  return (
    <div className="cadence-content-col cadence-screen-fade">
      <Topbar
        crumbs={["Workspace", "Labs"]}
        onCmdK={onCmdK}
        actions={
          <>
            <span className="cadence-text-3 cadence-fz-12">last draw {lastDraw}</span>
            <button className="cadence-btn">
              <Icon name="download" /> Upload
            </button>
          </>
        }
      />

      <div className="cadence-scroll">
        <div className="cadence-scroll-pad">
          <div className="cadence-h-eyebrow cadence-mb-8">Long-term biomarkers</div>
          <div className="cadence-h-display cadence-num" style={{ fontSize: 44 }}>
            {LABS.length} markers · {inRange} in optimal range
          </div>
          <div className="cadence-row cadence-gap-12 cadence-mt-12 cadence-mb-20">
            <Pill tone="pos" dot>{inRange} in optimal range</Pill>
            {outOfRange > 0 && <Pill tone="warn">{outOfRange} outside optimal</Pill>}
            <Pill tone="info">{LAB_DATES.length} historical draws over 18 months</Pill>
          </div>

          {Array.from(grouped.entries()).map(([cat, labs]) => {
            const meta = CATEGORY_META[cat];
            return (
              <div key={cat} className="cadence-mt-20">
                <SectionHead
                  title={
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                      <span style={{ width: 8, height: 8, borderRadius: 2, background: meta.color }} />
                      {meta.label}
                    </span>
                  }
                  sub={`${labs.length} markers`}
                />
                <div className="cadence-card" style={{ overflow: "hidden" }}>
                  <div className="cadence-lab-row cadence-lab-row-head">
                    <div>Marker</div>
                    <div className="cadence-right" style={{ marginLeft: 0, textAlign: "right" }}>Current</div>
                    <div>Optimal range</div>
                    <div>Personal baseline</div>
                    <div className="cadence-right" style={{ marginLeft: 0, textAlign: "right" }}>Trend (5 draws)</div>
                  </div>
                  {labs.map((l) => (
                    <LabRow key={l.id} l={l} color={meta.color} />
                  ))}
                </div>
              </div>
            );
          })}

          <div className="cadence-card cadence-card-tinted cadence-card-pad cadence-mt-24">
            <SectionHead title="Note on optimal ranges" sub="Methodology" />
            <div className="cadence-text-2 cadence-fz-13" style={{ lineHeight: 1.6 }}>
              The optimal ranges shown are the conventional clinical
              reference intervals — they tell you when a marker is
              technically in-range, NOT what&rsquo;s ideal. Your personal
              baseline tracks where YOUR body sits across past draws.
              Cadence flags drift from baseline before drift out of range.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface LabRowProps {
  l: LabBiomarker;
  color: string;
}

function LabRow({ l, color }: LabRowProps) {
  const inRange = l.current >= l.optimalLow && l.current <= l.optimalHigh;
  const dBaseline = l.current - l.baseline;
  const baselineGood =
    l.direction === "low" ? dBaseline <= 0 :
    l.direction === "high" ? dBaseline >= 0 :
    Math.abs(dBaseline) < (l.optimalHigh - l.optimalLow) * 0.15;
  return (
    <div className="cadence-lab-row">
      <div className="cadence-nm">
        {l.name}
        <div className="cadence-text-3 cadence-fz-11" style={{ marginTop: 2 }}>{l.unit}</div>
      </div>
      <div style={{ textAlign: "right" }}>
        <div className="cadence-vl" style={{ color: inRange ? color : "var(--neg)" }}>
          {l.current}
        </div>
      </div>
      <div className="cadence-text-3 cadence-fz-12 cadence-mono">
        {l.optimalLow}–{l.optimalHigh}
      </div>
      <div>
        <span className="cadence-mono cadence-fz-12" style={{ color: "var(--ink-2)", fontWeight: 500 }}>{l.baseline}</span>
        <Pill
          tone={baselineGood ? "pos" : "warn"}
          style={{ marginLeft: 6, height: 17, padding: "0 5px", fontSize: 10 }}
        >
          {dBaseline > 0 ? "+" : ""}
          {dBaseline.toFixed(Math.abs(dBaseline) < 1 ? 1 : 0)}
        </Pill>
      </div>
      <div style={{ textAlign: "right" }}>
        <LabTrend
          values={l.history}
          optimalLow={l.optimalLow}
          optimalHigh={l.optimalHigh}
          color={color}
          height={40}
        />
      </div>
    </div>
  );
}
