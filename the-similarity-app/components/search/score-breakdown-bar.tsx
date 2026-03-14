"use client";

import { useState } from "react";

const METHOD_COLORS: Record<string, string> = {
  dtw: "#1a1a1a",
  pearson_warped: "#4a4a4a",
  bempedelis_r2: "#22a06b",
  bempedelis_smoothness: "#2ea87e",
  koopman: "#0066cc",
  wavelet_spectrum: "#8844cc",
  emd: "#cc6600",
  tda: "#cc0044",
  transfer_entropy: "#6688aa",
};

const METHOD_LABELS: Record<string, string> = {
  dtw: "DTW",
  pearson_warped: "Pearson",
  bempedelis_r2: "Bempedelis R\u00B2",
  bempedelis_smoothness: "Bempedelis Smooth",
  koopman: "Koopman",
  wavelet_spectrum: "Wavelet",
  emd: "EMD",
  tda: "TDA",
  transfer_entropy: "Transfer Entropy",
};

type ScoreBreakdownBarProps = {
  breakdown: Record<string, number>;
};

export function ScoreBreakdownBar({ breakdown }: ScoreBreakdownBarProps) {
  const [hoveredMethod, setHoveredMethod] = useState<string | null>(null);

  const entries = Object.entries(breakdown).filter(([, v]) => v > 0);
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  if (total === 0) return null;

  return (
    <div>
      <div className="score-bar">
        {entries.map(([method, value]) => {
          const pct = (value / total) * 100;
          return (
            <div
              key={method}
              className="score-bar-segment"
              style={{
                width: `${pct}%`,
                backgroundColor: METHOD_COLORS[method] ?? "#999",
                opacity: hoveredMethod && hoveredMethod !== method ? 0.4 : 1,
              }}
              onMouseEnter={() => setHoveredMethod(method)}
              onMouseLeave={() => setHoveredMethod(null)}
              title={`${METHOD_LABELS[method] ?? method}: ${value.toFixed(3)}`}
            />
          );
        })}
      </div>
      <div className="score-bar-legend">
        {entries.map(([method, value]) => {
          const pct = (value / total) * 100;
          if (pct < 15) return null;
          return (
            <span key={method} className="score-bar-legend-item">
              <span
                className="score-bar-legend-swatch"
                style={{ backgroundColor: METHOD_COLORS[method] ?? "#999" }}
              />
              {METHOD_LABELS[method] ?? method}
            </span>
          );
        })}
      </div>
    </div>
  );
}
