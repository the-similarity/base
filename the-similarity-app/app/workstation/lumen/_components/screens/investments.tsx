/**
 * Investments screen — portfolio value + holdings table + allocation/movers.
 *
 * Holdings render a per-row sparkline whose 12 ticks are synthesized from
 * cost↔price interpolation plus a sin() jitter so visually adjacent rows
 * have distinct shapes. The overall portfolio area chart down-scales the
 * net-worth series by 0.72 to approximate "non-cash" value.
 */
"use client";

import { useState } from "react";
import { Icon } from "../icons";
import { Pill, Topbar, SectionHead, SegControl } from "../shared";
import { Sparkline, AreaChart } from "../charts";
import { HOLDINGS, NETWORTH } from "../data";
import type { ScreenProps } from "../screen-types";

export function ScreenInvestments({ onCmdK }: ScreenProps) {
  const [range, setRange] = useState("1Y");

  const totalValue = HOLDINGS.reduce((s, h) => s + h.shares * h.price, 0);
  const totalCost = HOLDINGS.reduce((s, h) => s + h.shares * h.cost, 0);
  const gain = totalValue - totalCost;
  const gainPct = (gain / totalCost) * 100;

  // Synthesize a non-cash portfolio series from the net-worth points.
  const months = NETWORTH.map((n) => ({
    m: n.m,
    v: Math.round(n.v * 0.72 + Math.sin(n.v / 100000) * 5000),
  }));

  return (
    <div className="content-col screen-fade">
      <Topbar
        crumbs={["Workspace", "Investments"]}
        onCmdK={onCmdK}
        actions={
          <>
            <button className="btn">
              <Icon name="download" /> 1099
            </button>
            <button className="btn primary">
              <Icon name="plus" /> Buy
            </button>
          </>
        }
      />
      <div className="scroll">
        <div className="scroll-pad">
          <div className="row" style={{ alignItems: "flex-end" }}>
            <div>
              <div className="h-eyebrow mb-8">Portfolio value</div>
              <div className="h-display num" style={{ fontSize: 48 }}>
                $
                {totalValue.toLocaleString("en-US", { maximumFractionDigits: 0 })}
              </div>
              <div className="row gap-8 mt-8">
                <Pill tone="pos" dot>
                  +$
                  {gain.toLocaleString("en-US", { maximumFractionDigits: 0 })} (
                  {gainPct.toFixed(2)}%) all time
                </Pill>
                <Pill>+$3,840 today</Pill>
              </div>
            </div>
            <div className="right">
              <SegControl
                value={range}
                onChange={setRange}
                options={["1D", "1W", "1M", "3M", "1Y", "ALL"].map((v) => ({
                  value: v,
                  label: v,
                }))}
              />
            </div>
          </div>

          <div className="card mt-16" style={{ padding: "12px 12px 4px" }}>
            <AreaChart
              data={months}
              height={220}
              accent="var(--pos)"
              formatY={(v) => "$" + (v / 1000).toFixed(0) + "k"}
              gradientId="invest-area"
            />
          </div>

          <div className="mt-20">
            <SectionHead
              title="Holdings"
              sub={`${HOLDINGS.length} positions`}
              actions={
                <SegControl
                  value="value"
                  onChange={() => {}}
                  options={[
                    { value: "value", label: "By value" },
                    { value: "gain", label: "By gain" },
                  ]}
                />
              }
            />
            <div className="card">
              <div className="holding-row head">
                <span></span>
                <span>Holding</span>
                <span style={{ textAlign: "right" }}>Shares</span>
                <span style={{ textAlign: "right" }}>Price</span>
                <span style={{ textAlign: "right" }}>Market value</span>
                <span style={{ textAlign: "right" }}>Total return</span>
              </div>
              {HOLDINGS.map((h) => {
                const value = h.shares * h.price;
                const cost = h.shares * h.cost;
                const r = ((value - cost) / cost) * 100;
                // 12 synthetic ticks interpolating cost→price plus jitter so
                // each holding's spark line is visually distinct.
                const ticks = Array.from(
                  { length: 12 },
                  (_, i) =>
                    h.cost +
                    (h.price - h.cost) * (i / 11) +
                    Math.sin(i * h.shares) * (h.price - h.cost) * 0.15
                );
                return (
                  <div key={h.ticker} className="holding-row">
                    <div className="ticker" style={{ background: h.color }}>
                      {h.ticker.slice(0, 3)}
                    </div>
                    <div className="col">
                      <div className="fw-6 fz-13">{h.ticker}</div>
                      <div className="text-3 fz-11">{h.name}</div>
                    </div>
                    <div className="num text-2" style={{ textAlign: "right" }}>
                      {h.shares.toFixed(2)}
                    </div>
                    <div className="num text-2" style={{ textAlign: "right" }}>
                      ${h.price.toFixed(2)}
                    </div>
                    <div className="num fw-6" style={{ textAlign: "right" }}>
                      $
                      {value.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div className={`num fw-6 ${r >= 0 ? "pos" : "neg"}`}>
                        {r >= 0 ? "+" : ""}
                        {r.toFixed(2)}%
                      </div>
                      <div
                        style={{ marginLeft: "auto", width: 80, marginTop: 2 }}
                      >
                        <Sparkline
                          data={ticks}
                          stroke={r >= 0 ? "var(--pos)" : "var(--neg)"}
                          width={80}
                          height={20}
                          dot={false}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
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
              <SectionHead title="Allocation" sub="Asset class" />
              {[
                { l: "US Stocks", v: 64, c: "#0a6b48" },
                { l: "Intl. Stocks", v: 14, c: "#2e5d8c" },
                { l: "Bonds", v: 12, c: "#7a7a75" },
                { l: "Real Estate", v: 6, c: "#5c4a8c" },
                { l: "Cash", v: 4, c: "#b07c1d" },
              ].map((a) => (
                <div key={a.l} style={{ marginBottom: 10 }}>
                  <div className="row mb-4 fz-12">
                    <span className="row gap-6">
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: 2,
                          background: a.c,
                        }}
                      />{" "}
                      {a.l}
                    </span>
                    <span className="right num fw-6">{a.v}%</span>
                  </div>
                  <div className="progress thin">
                    <div
                      className="fill"
                      style={{ width: a.v + "%", background: a.c }}
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="card card-pad">
              <SectionHead title="Top movers · today" sub="By dollar change" />
              {[
                { t: "NVDA", n: "NVIDIA", v: 1182.4, d: 4.32, c: "#3b8d40" },
                { t: "AAPL", n: "Apple Inc.", v: 218.74, d: 1.21, c: "#111" },
                { t: "VTI", n: "Total Market", v: 268.42, d: 0.84, c: "#a4262c" },
                { t: "MSFT", n: "Microsoft", v: 432.16, d: -0.52, c: "#1d6cb1" },
                { t: "BND", n: "Total Bond", v: 72.1, d: -0.18, c: "#7a7a75" },
              ].map((m) => (
                <div
                  key={m.t}
                  className="row gap-12"
                  style={{
                    padding: "8px 0",
                    borderBottom: "1px dashed var(--border)",
                  }}
                >
                  <div
                    className="ticker"
                    style={{ background: m.c, width: 28, height: 28, fontSize: 10 }}
                  >
                    {m.t}
                  </div>
                  <div className="col grow">
                    <div className="fw-6 fz-13">{m.t}</div>
                    <div className="text-3 fz-11">{m.n}</div>
                  </div>
                  <div className="col" style={{ alignItems: "flex-end" }}>
                    <div className="num fw-6 fz-13">${m.v.toFixed(2)}</div>
                    <div className={`num fz-11 ${m.d >= 0 ? "pos" : "neg"}`}>
                      {m.d >= 0 ? "+" : ""}
                      {m.d.toFixed(2)}%
                    </div>
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
