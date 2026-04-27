/**
 * Cash Flow screen — 12-month income vs spending bars + breakdowns.
 *
 * Sections:
 *   1. Hero: net cash flow, in/out pills, savings-rate pill, range seg
 *   2. Bar chart: stacked monthly in/out
 *   3. Two-col: income sources + spending categories breakdowns
 *
 * The "Spending categories" list uses a pseudo-deterministic synthetic
 * value per category (i+1 * 1840 + Math.random) for visual variety. This
 * mirrors the design source — no real per-category aggregation here.
 */
"use client";

import { Icon } from "../icons";
import { Pill, Topbar, SectionHead, SegControl } from "../shared";
import { FlowBars } from "../charts";
import { CASHFLOW, CATEGORIES } from "../data";
import type { ScreenProps } from "../screen-types";

export function ScreenCashflow({ onCmdK }: ScreenProps) {
  const totalIn = CASHFLOW.reduce((s, m) => s + m.in, 0);
  const totalOut = CASHFLOW.reduce((s, m) => s + m.out, 0);
  const avgSavings = ((totalIn - totalOut) / totalIn) * 100;

  return (
    <div className="content-col screen-fade">
      <Topbar
        crumbs={["Workspace", "Cash Flow"]}
        onCmdK={onCmdK}
        actions={
          <button className="btn">
            <Icon name="download" /> Export
          </button>
        }
      />
      <div className="scroll">
        <div className="scroll-pad">
          <div className="row" style={{ alignItems: "flex-end" }}>
            <div>
              <div className="h-eyebrow mb-8">12-month cash flow · Net</div>
              <div className="h-display num" style={{ fontSize: 48 }}>
                +${(totalIn - totalOut).toLocaleString()}
              </div>
              <div className="row gap-8 mt-8">
                <Pill tone="pos" dot>
                  ${totalIn.toLocaleString()} in
                </Pill>
                <Pill tone="neg" dot>
                  ${totalOut.toLocaleString()} out
                </Pill>
                <Pill>{avgSavings.toFixed(0)}% avg savings rate</Pill>
              </div>
            </div>
            <div className="right">
              <SegControl
                value="12m"
                onChange={() => {}}
                options={[
                  { value: "3m", label: "3M" },
                  { value: "6m", label: "6M" },
                  { value: "12m", label: "12M" },
                  { value: "all", label: "All" },
                ]}
              />
            </div>
          </div>

          <div className="card card-pad mt-16">
            <FlowBars data={CASHFLOW} height={200} />
            <div className="row gap-16 mt-12 fz-12 text-3">
              <span className="row gap-6">
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: 2,
                    background: "var(--accent)",
                  }}
                />{" "}
                Income
              </span>
              <span className="row gap-6">
                <span
                  style={{
                    width: 10,
                    height: 10,
                    borderRadius: 2,
                    background: "var(--ink)",
                  }}
                />{" "}
                Spending
              </span>
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 14,
              marginTop: 20,
            }}
          >
            <div className="card card-pad">
              <SectionHead title="Income sources" sub="Last 12 months" />
              {[
                { n: "Stripe Payroll", v: 154274, c: "#5c4ad6", mark: "SP", pct: 92 },
                { n: "Freelance", v: 8400, c: "#0a6b48", mark: "FR", pct: 5 },
                {
                  n: "Interest & dividends",
                  v: 4180,
                  c: "#b07c1d",
                  mark: "I",
                  pct: 2,
                },
                { n: "Refunds", v: 982, c: "#7a7a75", mark: "R", pct: 1 },
              ].map((i) => (
                <div
                  key={i.n}
                  className="row gap-12"
                  style={{
                    padding: "10px 0",
                    borderBottom: "1px dashed var(--border)",
                  }}
                >
                  <div
                    className="merch"
                    style={{ background: i.c, width: 28, height: 28, fontSize: 11 }}
                  >
                    {i.mark}
                  </div>
                  <div className="grow">
                    <div className="fw-6 fz-13">{i.n}</div>
                    <div className="progress thin mt-4">
                      <div
                        className="fill"
                        style={{ width: i.pct + "%", background: i.c }}
                      />
                    </div>
                  </div>
                  <div className="num fw-6" style={{ textAlign: "right" }}>
                    ${i.v.toLocaleString()}
                  </div>
                </div>
              ))}
            </div>

            <div className="card card-pad">
              <SectionHead title="Spending categories" sub="Last 12 months" />
              {Object.entries(CATEGORIES)
                .filter(([k]) => !["income", "transfer"].includes(k))
                .slice(0, 6)
                .map(([k, c], i) => {
                  // Synthetic per-row value; deterministic per index so the
                  // layout is stable across renders within a session.
                  const v = (i + 1) * 1840 + ((i * 137) % 800);
                  const pct = 90 - i * 12;
                  return (
                    <div
                      key={k}
                      className="row gap-12"
                      style={{
                        padding: "10px 0",
                        borderBottom: "1px dashed var(--border)",
                      }}
                    >
                      <div
                        style={{
                          width: 28,
                          height: 28,
                          borderRadius: 7,
                          background: c.color + "18",
                          color: c.color,
                          display: "grid",
                          placeItems: "center",
                        }}
                      >
                        <Icon name={c.icon} />
                      </div>
                      <div className="grow">
                        <div className="fw-6 fz-13">{c.label}</div>
                        <div className="progress thin mt-4">
                          <div
                            className="fill"
                            style={{ width: pct + "%", background: c.color }}
                          />
                        </div>
                      </div>
                      <div className="num fw-6" style={{ textAlign: "right" }}>
                        ${v.toLocaleString()}
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
