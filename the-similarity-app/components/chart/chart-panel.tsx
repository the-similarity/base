import type { RangeView } from "../../lib/types";
import { areaPath, pointsToPath, scalePoints } from "../../lib/chart-utils";

export function ChartPanel({ view }: { view: RangeView }) {
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
