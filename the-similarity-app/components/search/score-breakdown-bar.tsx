"use client";

import { useState } from "react";
import { METHOD_COLORS, METHOD_LABELS } from "@/lib/constants";

// Source of truth for method colors/labels is `lib/constants.ts`. Previously
// this component duplicated the map with colored hues; the editorial deck
// re-theme collapses both into a single monochrome ramp, so we import.

const FALLBACK_COLOR = "var(--text-muted)";

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
                backgroundColor: METHOD_COLORS[method] ?? FALLBACK_COLOR,
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
                style={{ backgroundColor: METHOD_COLORS[method] ?? FALLBACK_COLOR }}
              />
              {METHOD_LABELS[method] ?? method}
            </span>
          );
        })}
      </div>
    </div>
  );
}
