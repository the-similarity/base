"use client";

type OverlayChartProps = {
  queryValues: number[];
  matchValues: number[];
  queryLabel?: string;
  matchLabel?: string;
};

function clampRatio(value: number, min: number, max: number) {
  if (max === min) return 0.5;
  return (value - min) / (max - min);
}

function pointsToPath(points: Array<{ x: number; y: number }>) {
  return points
    .map(
      (p, i) =>
        `${i === 0 ? "M" : "L"} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`
    )
    .join(" ");
}

function normalizeToZeroOne(values: number[]): number[] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (max === min) return values.map(() => 0.5);
  return values.map((v) => (v - min) / (max - min));
}

export function OverlayChart({
  queryValues,
  matchValues,
  queryLabel = "Query",
  matchLabel = "Match",
}: OverlayChartProps) {
  const width = 760;
  const height = 268;
  const padTop = 12;
  const padBottom = 32;
  const innerH = height - padTop - padBottom;

  const normQuery = normalizeToZeroOne(queryValues);
  const normMatch = normalizeToZeroOne(matchValues);

  const maxLen = Math.max(normQuery.length, normMatch.length);
  const denominator = Math.max(maxLen - 1, 1);

  const queryPoints = normQuery.map((v, i) => ({
    x: (i / denominator) * width,
    y: padTop + innerH - v * innerH,
  }));

  const matchPoints = normMatch.map((v, i) => ({
    x: (i / denominator) * width,
    y: padTop + innerH - v * innerH,
  }));

  return (
    <div className="overlay-chart">
      <div className="card">
        <div className="chart-copy">
          <div>
            <p className="card-label">Overlay comparison</p>
            <h3 className="chart-title">Query vs. Match</h3>
          </div>
          <div className="legend">
            <span className="legend-item">
              <span className="legend-swatch query" />
              {queryLabel}
            </span>
            <span className="legend-item">
              <span className="legend-swatch match" />
              {matchLabel}
            </span>
          </div>
        </div>
        <div className="chart-shell">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="chart-svg"
            role="img"
            aria-label="Query and match overlay chart"
          >
            {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
              <line
                key={ratio}
                x1="0"
                x2={width}
                y1={padTop + innerH * (1 - ratio)}
                y2={padTop + innerH * (1 - ratio)}
                className="chart-grid-line"
              />
            ))}
            <path
              d={pointsToPath(matchPoints)}
              className="chart-line chart-line-muted"
            />
            <path
              d={pointsToPath(queryPoints)}
              className="chart-line chart-line-primary"
            />
            <text
              x="0"
              y={height - 4}
              className="chart-axis-label"
            >
              normalized series
            </text>
            <text
              x={width}
              y={height - 4}
              textAnchor="end"
              className="chart-axis-label"
            >
              {maxLen} bars
            </text>
          </svg>
        </div>
      </div>
    </div>
  );
}
