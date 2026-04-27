/**
 * Goals screen — long-horizon outcomes with projected completion.
 *
 * Each goal is a card showing:
 *   - Name + metric
 *   - Current value vs target
 *   - Due date
 *   - Progress ring (0-100%)
 *   - Trend pill (ahead / on track / behind)
 *   - Projection sentence ("Projected hit Sep 14 — 2 weeks early")
 *
 * Goals vs Targets:
 *   - Targets = recurring nightly/weekly commitments (hit-rate)
 *   - Goals   = multi-month outcomes (trajectory + projection)
 *
 * The projection in the demo is hard-coded per goal; real version would
 * fit a regression line through the metric's historical trajectory and
 * extrapolate against the due date.
 */
"use client";

import { Topbar, SectionHead, Pill } from "../shared";
import { Ring } from "../charts";
import { GOALS } from "../data";
import type { Goal } from "../data";
import type { ScreenProps } from "../screen-types";

const TREND_META: Record<Goal["trend"], { label: string; color: string; tone: "pos" | "warn" | "neg" }> = {
  ahead: { label: "Ahead of schedule", color: "#5b8a72", tone: "pos" },
  ontrack: { label: "On track", color: "#5a7d9c", tone: "pos" },
  behind: { label: "Behind schedule", color: "#c2655c", tone: "neg" },
};

export function ScreenGoals({ onCmdK }: ScreenProps) {
  const ahead = GOALS.filter((g) => g.trend === "ahead").length;
  const onTrack = GOALS.filter((g) => g.trend === "ontrack").length;
  const behind = GOALS.filter((g) => g.trend === "behind").length;

  return (
    <div className="content-col screen-fade">
      <Topbar crumbs={["Workspace", "Goals"]} onCmdK={onCmdK} />

      <div className="scroll">
        <div className="scroll-pad">
          <div className="h-eyebrow mb-8">Long-horizon outcomes</div>
          <div className="h-display num" style={{ fontSize: 44 }}>
            {GOALS.length} goals · {ahead + onTrack}/{GOALS.length} on track
          </div>
          <div className="row gap-12 mt-12 mb-20">
            {ahead > 0 && <Pill tone="pos" dot>{ahead} ahead</Pill>}
            <Pill tone="info">{onTrack} on track</Pill>
            {behind > 0 && <Pill tone="neg" dot>{behind} behind</Pill>}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 14 }}>
            {GOALS.map((g) => (
              <GoalCard key={g.id} g={g} />
            ))}
          </div>

          {/* Add-goal stub */}
          <div className="card tinted card-pad mt-20" style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div className="grow">
              <div className="title fz-13 fw-6">Add a goal</div>
              <div className="text-3 fz-12 mt-4">
                Goals work best when they&rsquo;re a single quantifiable outcome
                with a hard date. Cadence projects completion from your
                current trajectory.
              </div>
            </div>
            <button className="btn primary">+ New goal</button>
          </div>

          {/* Methodology */}
          <div className="card card-pad mt-20">
            <SectionHead title="How projections work" sub="Methodology" />
            <div className="text-2 fz-13" style={{ lineHeight: 1.6 }}>
              For each goal, Cadence fits a linear-trend regression through
              your historical metric (e.g. weekly long-run pace) and
              extrapolates against the due date. Trend = <b>ahead</b> when
              projected completion falls before due − 1 week, <b>on track</b>
              within ±1 week, <b>behind</b> after due + 1 week.
              <br /><br />
              Real goal projections fold in your rhyme outcomes too — if
              your last training-block rhyme led to overtraining, the
              system widens the projection&rsquo;s uncertainty band.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

interface GoalCardProps {
  g: Goal;
}

function GoalCard({ g }: GoalCardProps) {
  const meta = TREND_META[g.trend];
  return (
    <div className="card card-pad-lg" style={{ display: "flex", gap: 18, alignItems: "center" }}>
      <div className="ring-wrap" style={{ width: 84, height: 84 }}>
        <Ring pct={g.progress} size={84} thickness={7} color={meta.color} />
        <div className="ring-text" style={{ fontSize: 18 }}>{Math.round(g.progress * 100)}%</div>
      </div>
      <div className="grow" style={{ minWidth: 0 }}>
        <div className="title fz-13 fw-6">{g.name}</div>
        <div className="text-3 fz-11" style={{ marginTop: 2 }}>{g.metric}</div>
        <div className="row gap-8 mt-12 fz-12 text-2">
          <span><b>Now:</b> {g.current}</span>
          <span><b>Target:</b> {g.target}</span>
          <span style={{ marginLeft: "auto" }}><b>Due:</b> {g.due}</span>
        </div>
        <div className="row gap-8 mt-12">
          <Pill tone={meta.tone} dot>{meta.label}</Pill>
          <span className="text-3 fz-12">{g.projection}</span>
        </div>
      </div>
    </div>
  );
}
