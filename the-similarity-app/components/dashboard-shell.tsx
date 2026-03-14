"use client";

import { useState } from "react";

import type { DashboardData, RangeKey, RangeView, TabKey } from "../lib/types";

const tabs: Array<{ key: TabKey; label: string }> = [
  { key: "overview", label: "Overview" },
  { key: "matches", label: "Matches" },
  { key: "forecast", label: "Forecast" },
  { key: "architecture", label: "Architecture" },
];

function formatSigned(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`;
}

function clampRatio(value: number, min: number, max: number) {
  if (max === min) {
    return 0.5;
  }

  return (value - min) / (max - min);
}

function pointsToPath(points: Array<{ x: number; y: number }>) {
  return points.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");
}

function areaPath(upper: Array<{ x: number; y: number }>, lower: Array<{ x: number; y: number }>) {
  const top = pointsToPath(upper);
  const bottom = [...lower]
    .reverse()
    .map((point) => `L ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");

  return `${top} ${bottom} Z`;
}

function scalePoints(
  values: number[],
  startIndex: number,
  totalSlots: number,
  width: number,
  height: number,
  min: number,
  max: number,
) {
  const denominator = Math.max(totalSlots - 1, 1);

  return values.map((value, index) => {
    const x = ((startIndex + index) / denominator) * width;
    const y = height - clampRatio(value, min, max) * height;
    return { x, y };
  });
}

function SectionHeader({ title, detail }: { title: string; detail?: string }) {
  return (
    <div className="section-head">
      <h2 className="section-header">{title}</h2>
      {detail ? <p className="section-detail">{detail}</p> : null}
    </div>
  );
}

function MetricCard({
  label,
  value,
  unit,
  delta,
}: {
  label: string;
  value: string;
  unit?: string;
  delta?: number;
}) {
  return (
    <article className="card stat-card">
      <div className="metric-dot" aria-hidden="true" />
      <p className="card-label">{label}</p>
      <div className="metric-value-row">
        <span className="card-value">{value}</span>
        {unit ? <span className="card-unit">{unit}</span> : null}
      </div>
      {delta !== undefined ? (
        <p className={`card-delta ${delta >= 0 ? "positive" : "negative"}`}>{formatSigned(delta)}</p>
      ) : (
        <p className="card-delta neutral">Stable run</p>
      )}
    </article>
  );
}

function ChartPanel({ view }: { view: RangeView }) {
  const width = 760;
  const height = 268;
  const forecastAnchor = view.query[view.query.length - 1];
  const forecastP10 = [forecastAnchor, ...view.forecast.p10];
  const forecastP50 = [forecastAnchor, ...view.forecast.p50];
  const forecastP90 = [forecastAnchor, ...view.forecast.p90];
  const totalSlots = view.query.length + view.forecast.p50.length;
  const allValues = [...view.query, ...view.bestMatch, ...forecastP10, ...forecastP90];
  const min = Math.min(...allValues) - 1.5;
  const max = Math.max(...allValues) + 1.5;
  const queryPoints = scalePoints(view.query, 0, totalSlots, width, height, min, max);
  const matchPoints = scalePoints(view.bestMatch, 0, totalSlots, width, height, min, max);
  const p10Points = scalePoints(forecastP10, view.query.length - 1, totalSlots, width, height, min, max);
  const p50Points = scalePoints(forecastP50, view.query.length - 1, totalSlots, width, height, min, max);
  const p90Points = scalePoints(forecastP90, view.query.length - 1, totalSlots, width, height, min, max);
  const dividerX = ((view.query.length - 1) / Math.max(totalSlots - 1, 1)) * width;
  const latestPoint = p50Points[p50Points.length - 1];

  return (
    <section className="card chart-card">
      <div className="chart-copy">
        <div>
          <p className="card-label">Active study</p>
          <h3 className="chart-title">{view.label}</h3>
        </div>
        <div className="legend">
          <span className="legend-item">
            <span className="legend-swatch query" />
            Query
          </span>
          <span className="legend-item">
            <span className="legend-swatch match" />
            Best match
          </span>
          <span className="legend-item">
            <span className="legend-swatch forecast" />
            Median cone
          </span>
        </div>
      </div>
      <div className="chart-shell">
        <svg viewBox={`0 0 ${width} ${height + 28}`} className="chart-svg" role="img" aria-label="Pattern match forecast chart">
          <defs>
            <linearGradient id="forecast-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.12" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
            </linearGradient>
          </defs>
          {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
            <line
              key={ratio}
              x1="0"
              x2={width}
              y1={height * ratio}
              y2={height * ratio}
              className="chart-grid-line"
            />
          ))}
          <path d={areaPath(p90Points, p10Points)} className="chart-area" />
          <path d={pointsToPath(matchPoints)} className="chart-line chart-line-muted" />
          <path d={pointsToPath(queryPoints)} className="chart-line chart-line-primary" />
          <path d={pointsToPath(p50Points)} className="chart-line chart-line-forecast" />
          <line x1={dividerX} x2={dividerX} y1="0" y2={height} className="chart-divider" />
          <circle cx={latestPoint.x} cy={latestPoint.y} r="4" className="chart-dot" />
          <g transform={`translate(${Math.min(latestPoint.x + 10, width - 52)}, ${latestPoint.y - 18})`}>
            <rect width="44" height="18" rx="5" className="chart-tag-bg" />
            <text x="22" y="12.5" textAnchor="middle" className="chart-tag-text">
              {view.forecast.p50[view.forecast.p50.length - 1].toFixed(1)}
            </text>
          </g>
          <text x="0" y={height + 20} className="chart-axis-label">
            query window
          </text>
          <text x={Math.max(dividerX + 8, width - 130)} y={height + 20} className="chart-axis-label">
            forward bars
          </text>
        </svg>
      </div>
    </section>
  );
}

function SidePanel({
  view,
  dataSource,
}: {
  view: RangeView;
  dataSource: DashboardData["dataSource"];
}) {
  const lastMedian = view.forecast.p50[view.forecast.p50.length - 1];
  const lastLow = view.forecast.p10[view.forecast.p10.length - 1];
  const lastHigh = view.forecast.p90[view.forecast.p90.length - 1];
  const coneSpread = lastHigh - lastLow;

  return (
    <aside className="card panel-card">
      <div className="panel-block">
        <p className="card-label">Current configuration</p>
        <div className="kv-list">
          <div className="kv-row">
            <span>Normalization</span>
            <strong>logreturn_zscore</strong>
          </div>
          <div className="kv-row">
            <span>Window stride</span>
            <strong>5 bars</strong>
          </div>
          <div className="kv-row">
            <span>Tier 1 survivors</span>
            <strong>124</strong>
          </div>
          <div className="kv-row">
            <span>Tier 2 methods</span>
            <strong>DTW, Pearson, Bempedelis</strong>
          </div>
        </div>
      </div>
      <div className="panel-block">
        <p className="card-label">Cone at horizon</p>
        <div className="metric-value-row">
          <span className="card-value">{lastMedian.toFixed(1)}</span>
          <span className="card-unit">P50</span>
        </div>
        <p className="card-delta positive">{formatSigned(5.8)}</p>
        <div className="mini-grid">
          <div>
            <span className="mini-label">P10</span>
            <strong>{lastLow.toFixed(1)}</strong>
          </div>
          <div>
            <span className="mini-label">P90</span>
            <strong>{lastHigh.toFixed(1)}</strong>
          </div>
          <div>
            <span className="mini-label">Spread</span>
            <strong>{coneSpread.toFixed(1)}</strong>
          </div>
          <div>
            <span className="mini-label">Matches</span>
            <strong>20</strong>
          </div>
        </div>
      </div>
      <div className="panel-block">
        <p className="card-label">Notes</p>
        <p className="panel-note">
          {dataSource === "api"
            ? "This frontend is reading a real dashboard payload from the configured API repository."
            : "This frontend is currently using its mock adapter fallback, but it now targets an HTTP payload instead of local Python modules."}
        </p>
      </div>
    </aside>
  );
}

function ConfidencePanel({
  activeRange,
  data,
}: {
  activeRange: RangeKey;
  data: DashboardData;
}) {
  const rangeModifier = activeRange === "ALL" ? 0.04 : activeRange === "1D" ? -0.06 : 0;

  return (
    <section className="section-block">
      <SectionHeader title="Confidence Stack" detail="Composite method contribution for the current top analog." />
      <div className="card breakdown-card">
        {data.baseBreakdown.map((item) => {
          const value = Math.max(0.12, Math.min(0.98, item.value + rangeModifier));

          return (
            <div className="breakdown-row" key={item.label}>
              <div className="breakdown-meta">
                <span className="breakdown-label">{item.label}</span>
                <span className="breakdown-value">{Math.round(value * 100)}</span>
              </div>
              <div className="breakdown-track">
                <div className="breakdown-fill" style={{ width: `${value * 100}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function MatchesPanel({ data }: { data: DashboardData }) {
  return (
    <section className="section-block">
      <SectionHeader title="Top Matches" detail="Ranked windows returned by the search pipeline." />
      <div className="card-row">
        {data.topMatches.map((match) => (
          <article className="card match-card" key={match.label}>
            <p className="card-label">{match.label}</p>
            <div className="metric-value-row">
              <span className="card-value">{match.score.toFixed(1)}</span>
              <span className="card-unit">score</span>
            </div>
            <p className={`card-delta ${match.delta >= 0 ? "positive" : "negative"}`}>{formatSigned(match.delta)}</p>
            <div className="match-meta">
              <span>{match.window}</span>
              <span>{match.method}</span>
              <span>{match.regime}</span>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function ForecastPanel({ view }: { view: RangeView }) {
  const terminalLow = view.forecast.p10[view.forecast.p10.length - 1];
  const terminalMid = view.forecast.p50[view.forecast.p50.length - 1];
  const terminalHigh = view.forecast.p90[view.forecast.p90.length - 1];
  const anchor = view.query[view.query.length - 1];
  const rows = [
    { label: "Bear band", value: terminalLow, delta: ((terminalLow - anchor) / anchor) * 100 },
    { label: "Median path", value: terminalMid, delta: ((terminalMid - anchor) / anchor) * 100 },
    { label: "Bull band", value: terminalHigh, delta: ((terminalHigh - anchor) / anchor) * 100 },
  ];

  return (
    <section className="section-block">
      <SectionHeader title="Forecast Cone" detail="Weighted percentile projection from forward paths that followed each historical analog." />
      <div className="forecast-grid">
        {rows.map((row) => (
          <article className="card forecast-card" key={row.label}>
            <p className="card-label">{row.label}</p>
            <div className="metric-value-row">
              <span className="card-value">{row.value.toFixed(1)}</span>
              <span className="card-unit">terminal</span>
            </div>
            <p className={`card-delta ${row.delta >= 0 ? "positive" : "negative"}`}>{formatSigned(row.delta)}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function ArchitecturePanel({ data }: { data: DashboardData }) {
  return (
    <section className="section-block">
      <SectionHeader title="Module Layout" detail="Direct translation of the architecture doc into a frontend operator map." />
      <div className="module-grid">
        {data.architectureCards.map((card) => (
          <article className="card module-card" key={card.module}>
            <p className="card-label">{card.module}</p>
            <p className="module-copy">{card.responsibility}</p>
            <p className="module-scale">{card.scale}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

function PipelinePanel({ data }: { data: DashboardData }) {
  return (
    <section className="section-block">
      <SectionHeader title="Pipeline Readout" detail="The app surfaces the same sequence described in the architecture document." />
      <div className="card pipeline-card">
        {data.pipelineSteps.map((step, index) => (
          <div className="pipeline-step" key={step}>
            <span className="pipeline-index">{String(index + 1).padStart(2, "0")}</span>
            <span className="pipeline-text">{step}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

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
