"use client";

import { useState } from "react";

import type { DashboardData, RangeKey, TabKey } from "../../lib/types";
import { SectionHeader } from "../ui/section-header";
import { MetricCard } from "../ui/metric-card";
import { ChartPanel } from "../chart/chart-panel";
import { SidePanel } from "./side-panel";
import { ConfidencePanel } from "./confidence-panel";
import { MatchesPanel } from "./matches-panel";
import { ForecastPanel } from "./forecast-panel";
import { ArchitecturePanel } from "./architecture-panel";
import { PipelinePanel } from "./pipeline-panel";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "overview", label: "Overview" },
  { key: "matches", label: "Matches" },
  { key: "forecast", label: "Forecast" },
  { key: "architecture", label: "Architecture" },
];

export function DashboardShell({ data }: { data: DashboardData }) {
  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [activeRange, setActiveRange] = useState<RangeKey>(data.defaultRange);
  const view = data.views[activeRange];
  const anchor = view.query[view.query.length - 1];
  const outlook = view.forecast.p50[view.forecast.p50.length - 1];

  const overviewCards = [
    {
      label: "Top match score",
      value: data.topMatches[0].score.toFixed(1),
      unit: "/100",
      delta: data.topMatches[0].delta,
    },
    {
      label: "Median terminal",
      value: outlook.toFixed(1),
      unit: "P50",
      delta: ((outlook - anchor) / anchor) * 100,
    },
    {
      label: "Tier 1 survivors",
      value: "124",
      unit: "windows",
      delta: 4.0,
    },
    {
      label: "Data source",
      value: data.dataSource === "api" ? "live" : "mock",
      unit: "payload",
    },
  ];

  return (
    <main className="page-shell">
      <div className="container">
        <header className="hero">
          <div>
            <p className="eyebrow">{data.hero.eyebrow}</p>
            <h1 className="page-title">{data.hero.title}</h1>
            <p className="hero-copy">{data.hero.description}</p>
          </div>
          <div className="hero-badges">
            {data.hero.badges.map((badge) => (
              <span className="badge" key={badge}>
                {badge}
              </span>
            ))}
            <span className="badge">{data.dataSource === "api" ? "API mode" : "Mock mode"}</span>
          </div>
        </header>

        <nav className="tab-nav" aria-label="Dashboard sections">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`tab ${activeTab === tab.key ? "active" : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <section className="section-block">
          <SectionHeader title="Session Overview" detail="TradingView/Bloomberg-lite styling with compact cards and tabular values." />
          <div className="card-grid">
            {overviewCards.map((card) => (
              <MetricCard key={card.label} label={card.label} value={card.value} unit={card.unit} delta={card.delta} />
            ))}
          </div>
        </section>

        <section className="section-block">
          <div className="section-head section-head-inline">
            <h2 className="section-header">Time Range</h2>
            <div className="time-range" role="tablist" aria-label="Time range selector">
              {data.ranges.map((range) => (
                <button
                  key={range}
                  type="button"
                  className={`time-range-item ${activeRange === range ? "active" : ""}`}
                  onClick={() => setActiveRange(range)}
                >
                  {range}
                </button>
              ))}
            </div>
          </div>
        </section>

        <div className="main-grid">
          <ChartPanel view={view} />
          <SidePanel view={view} dataSource={data.dataSource} />
        </div>

        {activeTab === "overview" ? (
          <>
            <ConfidencePanel activeRange={activeRange} data={data} />
            <PipelinePanel data={data} />
          </>
        ) : null}

        {activeTab === "matches" ? <MatchesPanel data={data} /> : null}
        {activeTab === "forecast" ? <ForecastPanel view={view} /> : null}
        {activeTab === "architecture" ? <ArchitecturePanel data={data} /> : null}
      </div>
    </main>
  );
}
