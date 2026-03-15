"use client";
import { useTerminal } from "../../lib/terminal-context";
import { METHOD_COLORS, METHOD_LABELS } from "../../lib/constants";
import { Sparkline } from "./sparkline";

export function DetailPanel() {
  const { state } = useTerminal();
  if (state.selectedIdx === null || !state.matches[state.selectedIdx]) return null;

  const match = state.matches[state.selectedIdx];
  const b = match.score_breakdown;
  const entries = Object.entries(b).filter(([, v]) => (v as number) > 0);

  return (
    <div className="detail-panel">
      <div className="terminal-panel-header">
        Match #{state.selectedIdx + 1} Detail
        <span>{match.start_date || `idx ${match.start_idx}–${match.end_idx}`}</span>
      </div>

      <div className="detail-grid">
        <div>
          <div className="detail-stat-label">Confidence</div>
          <div className="detail-stat-value" style={{ color: "var(--positive)" }}>
            {match.confidence_score.toFixed(1)}
          </div>
        </div>
        {match.transform_r2 > 0 && (
          <div>
            <div className="detail-stat-label">Transform R²</div>
            <div className="detail-stat-value">{match.transform_r2.toFixed(3)}</div>
          </div>
        )}
        {match.regime && (
          <div>
            <div className="detail-stat-label">Regime</div>
            <div className="detail-stat-value">{match.regime}</div>
          </div>
        )}
        <div>
          <div className="detail-stat-label">Window</div>
          <div className="detail-stat-value" style={{ fontSize: 12 }}>
            {match.end_idx - match.start_idx} bars
          </div>
        </div>
      </div>

      {match.matched_series && match.matched_series.length > 0 && (
        <div style={{ marginBottom: "var(--space-lg)" }}>
          <Sparkline data={match.matched_series} height={40} width={300} color="var(--chart-match)" />
        </div>
      )}

      <div className="detail-breakdown">
        {entries.map(([method, value]) => (
          <div key={method} className="detail-breakdown-row">
            <span className="detail-breakdown-label">{METHOD_LABELS[method] || method}</span>
            <div className="detail-breakdown-bar">
              <div
                className="detail-breakdown-fill"
                style={{
                  width: `${(value as number) * 100}%`,
                  background: METHOD_COLORS[method] || "var(--text-muted)",
                }}
              />
            </div>
            <span className="detail-breakdown-value">{((value as number) * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
