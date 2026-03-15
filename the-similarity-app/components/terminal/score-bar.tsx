"use client";
import { METHOD_COLORS } from "../../lib/constants";
import type { ScoreBreakdown } from "../../lib/types";

export function ScoreBar({ breakdown }: { breakdown: ScoreBreakdown }) {
  const entries = Object.entries(breakdown).filter(([, v]) => (v as number) > 0);
  const total = entries.reduce((s, [, v]) => s + (v as number), 0) || 1;

  return (
    <div className="score-bar-track">
      {entries.map(([method, value]) => (
        <div
          key={method}
          className="score-bar-fill"
          style={{
            width: `${((value as number) / total) * 100}%`,
            background: METHOD_COLORS[method] || "var(--text-muted)",
          }}
        />
      ))}
    </div>
  );
}
