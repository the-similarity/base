/**
 * Dashboard screen — the workstation home.
 *
 * Sections (top → bottom):
 *   1. Hero — net worth + signed-month delta + range segmented control
 *   2. Net-worth area chart (12 months)
 *   3. KPI grid (Income / Spending / Savings rate / Investments)
 *   4. Spending breakdown donut + Recent activity list (two-col)
 *   5. AI insight bubble
 *   6. Spending heatmap + Upcoming charges (two-col)
 *
 * Local state:
 *   - `range`: which time-range chip is selected (visual-only here)
 *   - `hideBalances`: blur all $ values via the eye icon in the topbar
 *
 * Net-worth math: assets = sum(positive balances), debts = sum(|negative|),
 * net = assets - debts. Categories donut filters TX to the last 30 days.
 */
"use client";

import { useState } from "react";
import { Icon } from "../icons";
import { Pill, Topbar, MerchantBadge, SectionHead, SegControl } from "../shared";
import { Sparkline, AreaChart, Donut, SpendHeatmap } from "../charts";
import { ACCOUNTS, CASHFLOW, CATEGORIES, FMT, NETWORTH, TX } from "../data";
import type { ScreenProps } from "../screen-types";

export function ScreenDashboard({ onCmdK, onNavigate }: ScreenProps) {
  const [range, setRange] = useState("1Y");
  const [hideBalances, setHideBalances] = useState(false);

  const monthIn = CASHFLOW[CASHFLOW.length - 1].in;
  const monthOut = CASHFLOW[CASHFLOW.length - 1].out;
  const savingsRate = ((monthIn - monthOut) / monthIn) * 100;

  const totalAssets = ACCOUNTS.filter((a) => a.balance > 0).reduce(
    (s, a) => s + a.balance,
    0
  );
  const totalDebt = Math.abs(
    ACCOUNTS.filter((a) => a.balance < 0).reduce((s, a) => s + a.balance, 0)
  );
  const netWorth = totalAssets - totalDebt;

  // Donut by category for the last 30 days. Anchor at 2026-04-27 to match
  // the demo data window.
  const today = new Date("2026-04-27T00:00:00Z");
  const monthAgo = new Date(today);
  monthAgo.setDate(monthAgo.getDate() - 30);
  const recent = TX.filter((t) => t.date >= monthAgo && t.amount < 0);
  const byCat: Record<string, number> = {};
  recent.forEach((t) => {
    byCat[t.category] = (byCat[t.category] || 0) + Math.abs(t.amount);
  });
  const slices = Object.entries(byCat)
    .map(([cat, v]) => ({
      cat,
      value: v,
      color: CATEGORIES[cat].color,
      label: CATEGORIES[cat].label,
    }))
    .sort((a, b) => b.value - a.value);
  const monthSpend = slices.reduce((s, x) => s + x.value, 0);

  // Helper that respects the hide-balances toggle. fn() is the formatter
  // applied when balances are visible.
  const formatHidden = (n: number, fn: (n: number) => string) =>
    hideBalances ? "••••" : fn(n);

  return (
    <div className="content-col screen-fade">
      <Topbar
        crumbs={["Workspace", "Dashboard"]}
        onCmdK={onCmdK}
        actions={
          <>
            <button
              className="icon-btn"
              onClick={() => setHideBalances((v) => !v)}
              title="Hide balances"
            >
              <Icon name={hideBalances ? "eyeOff" : "eye"} />
            </button>
            <button className="btn">
              <Icon name="download" /> Export
            </button>
            <button className="btn primary">
              <Icon name="plus" /> Add
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
                Net worth ·{" "}
                {new Date().toLocaleDateString("en-US", {
                  month: "long",
                  day: "numeric",
                  year: "numeric",
                })}
              </div>
              <div className="h-display num" style={{ fontSize: 56 }}>
                {formatHidden(netWorth, (n) =>
                  "$" + n.toLocaleString("en-US", { maximumFractionDigits: 0 })
                )}
              </div>
              <div className="row gap-12 mt-12">
                <Pill tone="pos" dot>
                  +$12,494 this month
                </Pill>
                <Pill tone="default">+4.97% YoY</Pill>
                <span className="text-3 fz-12">
                  Assets {FMT.usdShort(totalAssets)} · Debts {FMT.usdShort(totalDebt)}
                </span>
              </div>
            </div>
            <div className="right">
              <SegControl
                value={range}
                onChange={setRange}
                options={[
                  { value: "1M", label: "1M" },
                  { value: "3M", label: "3M" },
                  { value: "6M", label: "6M" },
                  { value: "1Y", label: "1Y" },
                  { value: "ALL", label: "All" },
                ]}
              />
            </div>
          </div>

          {/* Net worth chart */}
          <div className="card mt-16" style={{ padding: "16px 20px 8px 12px" }}>
            <AreaChart
              data={NETWORTH}
              accent="var(--accent)"
              height={220}
              formatY={(v) => "$" + (v / 1000).toFixed(0) + "k"}
              gradientId="dash-networth"
            />
          </div>

          {/* KPIs */}
          <div className="kpi-grid mt-20">
            <div className="kpi">
              <div className="label">
                <Icon name="arrowDown" /> Income · April
              </div>
              <div className="value num pos">
                {formatHidden(monthIn, (n) => "+$" + n.toLocaleString())}
              </div>
              <div className="delta">
                <span className="pos arrow">↑</span> 4.2% vs mar
                <span style={{ marginLeft: "auto" }}>
                  <Sparkline
                    data={CASHFLOW.map((c) => c.in)}
                    stroke="var(--pos)"
                    width={70}
                    height={24}
                  />
                </span>
              </div>
            </div>
            <div className="kpi">
              <div className="label">
                <Icon name="arrowUp" /> Spending · April
              </div>
              <div className="value num">
                {formatHidden(monthOut, (n) => "$" + n.toLocaleString())}
              </div>
              <div className="delta">
                <span className="neg arrow">↑</span> 6.8% vs mar
                <span style={{ marginLeft: "auto" }}>
                  <Sparkline
                    data={CASHFLOW.map((c) => c.out)}
                    stroke="var(--ink-2)"
                    width={70}
                    height={24}
                  />
                </span>
              </div>
            </div>
            <div className="kpi">
              <div className="label">
                <Icon name="leaf" /> Savings rate
              </div>
              <div className="value num">
                {savingsRate.toFixed(0)}
                <span style={{ fontSize: 18 }}>%</span>
              </div>
              <div className="delta">
                <span className="pos arrow">↑</span> on track for 30%
              </div>
            </div>
            <div className="kpi">
              <div className="label">
                <Icon name="trend" /> Investments
              </div>
              <div className="value num pos">
                {formatHidden(190509, (n) => "$" + n.toLocaleString())}
              </div>
              <div className="delta">
                <span className="pos arrow">↑</span> +$3,840 today (1.91%)
                <span style={{ marginLeft: "auto" }}>
                  <Sparkline
                    data={[180, 178, 182, 184, 187, 185, 189, 188, 192, 190.5]}
                    stroke="var(--pos)"
                    width={70}
                    height={24}
                  />
                </span>
              </div>
            </div>
          </div>

          {/* Two col: spending donut + recent transactions */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1.3fr",
              gap: 14,
              marginTop: 20,
            }}
          >
            <div className="card">
              <div className="card-pad" style={{ paddingBottom: 8 }}>
                <SectionHead title="Spending breakdown" sub="Last 30 days" />
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 18,
                    padding: "4px 0 12px",
                  }}
                >
                  <div className="donut-c" style={{ width: 160, height: 160 }}>
                    <Donut slices={slices} size={160} thickness={20} />
                    <div className="center">
                      <div className="col" style={{ alignItems: "center", gap: 2 }}>
                        <div
                          className="text-3 fz-11"
                          style={{ textTransform: "uppercase", letterSpacing: "0.06em" }}
                        >
                          Total
                        </div>
                        <div className="h-display" style={{ fontSize: 24 }}>
                          ${monthSpend.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="grow">
                    {slices.slice(0, 5).map((s) => (
                      <div className="legend-row" key={s.cat}>
                        <span className="sw" style={{ background: s.color }} />
                        <span className="lab">{s.label}</span>
                        <span className="pct">
                          {((s.value / monthSpend) * 100).toFixed(0)}%
                        </span>
                        <span className="amt">${s.value.toFixed(0)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            <div className="card">
              <div
                style={{
                  padding: "14px 16px 6px 16px",
                  display: "flex",
                  alignItems: "center",
                }}
              >
                <div className="row gap-8" style={{ alignItems: "baseline" }}>
                  <div className="title fz-13 fw-6">Recent activity</div>
                  <div className="text-3 fz-12">Last 7 days · 14 transactions</div>
                </div>
                <button
                  className="btn ghost right"
                  onClick={() => onNavigate("transactions")}
                >
                  View all <Icon name="arrowRight" />
                </button>
              </div>
              <div>
                {TX.slice(0, 7).map((t) => (
                  <div
                    key={t.id}
                    className="tx-row"
                    style={{
                      gridTemplateColumns: "1fr 110px 28px",
                      padding: "9px 16px",
                    }}
                  >
                    <div className="merch-cell">
                      <MerchantBadge name={t.merchant} size={28} />
                      <div className="col" style={{ minWidth: 0 }}>
                        <div className="merch-name">{t.merchant}</div>
                        <div className="merch-sub">
                          {t.date.toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                          })}{" "}
                          · {CATEGORIES[t.category].label}
                        </div>
                      </div>
                    </div>
                    <div
                      className={`num right ${t.amount > 0 ? "pos fw-6" : ""}`}
                      style={{ textAlign: "right" }}
                    >
                      {t.amount > 0 ? "+" : ""}
                      {FMT.usd(t.amount)}
                    </div>
                    <button className="icon-btn">
                      <Icon name="chevron" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* AI insight */}
          <div className="ai-bubble mt-20">
            <div className="ai-head">
              <span className="pulse" /> Lumen Insight
            </div>
            <div>
              You spent <b>$412 on dining</b> this month — 18% above your $350
              budget and the highest of any category by share. <b>Tartine</b> and{" "}
              <b>Sweetgreen</b> account for $148 of that. Want to bump the dining
              budget to $450 next month, or set a weekly cap at $90?
            </div>
            <div className="row gap-6 mt-12">
              <button className="btn">Bump budget</button>
              <button className="btn">Set weekly cap</button>
              <button className="btn ghost">Dismiss</button>
            </div>
          </div>

          {/* Bottom: heatmap + upcoming */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.2fr 1fr",
              gap: 14,
              marginTop: 20,
            }}
          >
            <div className="card card-pad">
              <SectionHead
                title="Spending heatmap"
                sub="Last 7 weeks · darker = more spent"
              />
              <SpendHeatmap tx={TX} />
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
                        background: `rgba(10,107,72,${0.15 + v * 0.7})`,
                      }}
                    />
                  ))}
                </div>
                <span>More</span>
              </div>
            </div>

            <div className="card">
              <div className="card-pad" style={{ paddingBottom: 4 }}>
                <SectionHead title="Upcoming" sub="Next 7 days" />
              </div>
              {[
                {
                  d: "May 1",
                  name: "AWS",
                  amt: -42.3,
                  color: "#b07c1d",
                  mark: "AW",
                  kind: "Subscription",
                },
                {
                  d: "May 2",
                  name: "Spotify",
                  amt: -11.99,
                  color: "#0a6b48",
                  mark: "S",
                  kind: "Subscription",
                },
                {
                  d: "May 4",
                  name: "Equinox",
                  amt: -245.0,
                  color: "#1a1a1a",
                  mark: "E",
                  kind: "Subscription",
                },
                {
                  d: "May 5",
                  name: "Stripe Payroll",
                  amt: 6428.1,
                  color: "#5c4ad6",
                  mark: "SP",
                  kind: "Income",
                },
                {
                  d: "May 5",
                  name: "Sapphire bill",
                  amt: -2184.32,
                  color: "#0d2a4d",
                  mark: "CH",
                  kind: "Card payment",
                },
              ].map((u, i) => (
                <div
                  key={i}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "50px 1fr 100px",
                    gap: 12,
                    alignItems: "center",
                    padding: "9px 16px",
                    borderBottom: "1px solid var(--border)",
                  }}
                >
                  <div className="text-3 fz-12 mono">{u.d}</div>
                  <div className="merch-cell">
                    <div
                      className="merch"
                      style={{
                        background: u.color,
                        width: 26,
                        height: 26,
                        fontSize: 11,
                        flex: "0 0 26px",
                      }}
                    >
                      {u.mark}
                    </div>
                    <div className="col">
                      <div className="merch-name">{u.name}</div>
                      <div className="merch-sub">{u.kind}</div>
                    </div>
                  </div>
                  <div
                    className={`num ${u.amt > 0 ? "pos fw-6" : ""}`}
                    style={{ textAlign: "right" }}
                  >
                    {u.amt > 0 ? "+" : ""}
                    {FMT.usd(u.amt)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
