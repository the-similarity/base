/**
 * Insights screen — Lumen's NL composer + insight cards + forecast row.
 *
 * Composer accepts free text via a textarea; quick-action chips stage
 * common questions ("compare months", "coffee budget", etc).
 *
 * Insight cards are statically authored to match the design — Watch / Win /
 * Idea / Anomaly tones map onto Pill tone props.
 */
"use client";

import { useState } from "react";
import { Icon } from "../icons";
import { Pill, Topbar, SectionHead } from "../shared";
import type { ScreenProps } from "../screen-types";

export function ScreenInsights({ onCmdK }: ScreenProps) {
  const [input, setInput] = useState("");

  return (
    <div className="content-col screen-fade">
      <Topbar
        crumbs={["Workspace", "Insights"]}
        onCmdK={onCmdK}
        actions={
          <button className="btn">
            <Icon name="history" /> History
          </button>
        }
      />
      <div className="scroll">
        <div className="scroll-pad" style={{ maxWidth: 880 }}>
          <div className="row gap-12" style={{ alignItems: "center" }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: 10,
                background: "linear-gradient(135deg, #0a6b48, #c4b896)",
                display: "grid",
                placeItems: "center",
                color: "#fff",
              }}
            >
              <Icon name="sparkle" style={{ width: 18, height: 18 }} />
            </div>
            <div>
              <div className="h-display" style={{ fontSize: 30 }}>
                What&apos;s new in your money?
              </div>
              <div className="text-3 fz-13">
                Lumen reads your transactions and surfaces what matters.
              </div>
            </div>
          </div>

          {/* Composer */}
          <div className="card mt-20" style={{ padding: 14 }}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask Lumen — e.g. 'How much did I spend on coffee in March?'"
              style={{
                width: "100%",
                border: "none",
                resize: "none",
                outline: "none",
                minHeight: 60,
                fontSize: 14,
                lineHeight: 1.5,
                fontFamily: "inherit",
                background: "transparent",
              }}
            />
            <div className="row gap-6 mt-8">
              <button className="chip">Compare months</button>
              <button className="chip">Coffee budget</button>
              <button className="chip">Subscription audit</button>
              <button className="chip">Savings projection</button>
              <button className="btn accent right" style={{ borderRadius: 7 }}>
                Ask <Icon name="arrowUpRight" />
              </button>
            </div>
          </div>

          {/* Insight cards */}
          <div className="mt-24">
            <SectionHead title="This week's insights" sub="Updated 4h ago" />
            <div
              style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}
            >
              <div className="card card-pad">
                <div className="row gap-8 mb-12">
                  <Pill tone="warn" dot>
                    Watch
                  </Pill>
                  <span className="text-3 fz-11">Dining</span>
                </div>
                <div className="h-display" style={{ fontSize: 24, lineHeight: 1.2 }}>
                  Dining is on pace to hit{" "}
                  <span style={{ color: "var(--neg)" }}>$520</span> — 49% over your
                  $350 budget.
                </div>
                <div className="text-3 fz-12 mt-12">
                  Driven by 3 visits to Tartine ($89) and a 22% increase in lunch
                  spending vs March.
                </div>
                <div className="row gap-6 mt-12">
                  <button className="btn">View transactions</button>
                  <button className="btn">Adjust budget</button>
                </div>
              </div>

              <div className="card card-pad">
                <div className="row gap-8 mb-12">
                  <Pill tone="pos" dot>
                    Win
                  </Pill>
                  <span className="text-3 fz-11">Savings</span>
                </div>
                <div className="h-display" style={{ fontSize: 24, lineHeight: 1.2 }}>
                  You saved <span className="pos">$1,840</span> more than April 2025
                  — your highest month all year.
                </div>
                <div className="text-3 fz-12 mt-12">
                  If you keep this rate, you&apos;ll hit your Emergency Fund goal 6
                  weeks early.
                </div>
                <div className="row gap-6 mt-12">
                  <button className="btn">See breakdown</button>
                  <button className="btn">Accelerate goal</button>
                </div>
              </div>

              <div className="card card-pad">
                <div className="row gap-8 mb-12">
                  <Pill tone="info" dot>
                    Idea
                  </Pill>
                  <span className="text-3 fz-11">Cash optimization</span>
                </div>
                <div className="h-display" style={{ fontSize: 24, lineHeight: 1.2 }}>
                  Move $5,000 from Chase Checking (0.01% APY) to Marcus (4.40% APY)
                  for <span className="pos">+$220/yr</span>.
                </div>
                <div className="text-3 fz-12 mt-12">
                  Your checking balance has stayed above $7,000 for 4 months — well
                  above your $2,500 buffer.
                </div>
                <div className="row gap-6 mt-12">
                  <button className="btn primary">Move $5,000</button>
                  <button className="btn ghost">Not now</button>
                </div>
              </div>

              <div className="card card-pad">
                <div className="row gap-8 mb-12">
                  <Pill tone="neg" dot>
                    Anomaly
                  </Pill>
                  <span className="text-3 fz-11">Unusual</span>
                </div>
                <div className="h-display" style={{ fontSize: 24, lineHeight: 1.2 }}>
                  <span style={{ color: "var(--neg)" }}>Equinox</span> charged twice
                  this month — $245 on Apr 4 and Apr 26.
                </div>
                <div className="text-3 fz-12 mt-12">
                  Their billing cycle changed from monthly-on-the-4th to
                  monthly-on-the-26th. Next charge in 30 days.
                </div>
                <div className="row gap-6 mt-12">
                  <button className="btn">View charges</button>
                  <button className="btn">Mark expected</button>
                </div>
              </div>
            </div>
          </div>

          <div className="mt-24">
            <SectionHead title="Forecast" sub="Based on the last 6 months" />
            <div className="card card-pad">
              <div className="row gap-24">
                <div>
                  <div
                    className="text-3 fz-11"
                    style={{ textTransform: "uppercase", letterSpacing: "0.06em" }}
                  >
                    End of Q2
                  </div>
                  <div className="h-display num" style={{ fontSize: 30 }}>
                    $278,400
                  </div>
                  <div className="text-3 fz-12">Net worth · Jun 30, 2026</div>
                </div>
                <div>
                  <div
                    className="text-3 fz-11"
                    style={{ textTransform: "uppercase", letterSpacing: "0.06em" }}
                  >
                    End of year
                  </div>
                  <div className="h-display num" style={{ fontSize: 30 }}>
                    $321,800
                  </div>
                  <div className="text-3 fz-12">Dec 31, 2026</div>
                </div>
                <div>
                  <div
                    className="text-3 fz-11"
                    style={{ textTransform: "uppercase", letterSpacing: "0.06em" }}
                  >
                    Goal: house DP
                  </div>
                  <div className="h-display num" style={{ fontSize: 30 }}>
                    Q3 2028
                  </div>
                  <div className="text-3 fz-12">5 months ahead of plan</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
