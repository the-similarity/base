"use client";
import { useTerminal } from "../../lib/terminal-context";

export function DetailPanel() {
  const { state } = useTerminal();
  if (state.selectedIdx === null || !state.matches[state.selectedIdx]) return null;

  const match = state.matches[state.selectedIdx];
  const deltaClass = match.delta > 0 ? "positive" : match.delta < 0 ? "negative" : "";
  const deltaSign = match.delta > 0 ? "+" : "";

  return (
    <div className="detail-panel">
      <div className="terminal-panel-header">
        Match #{state.selectedIdx + 1} Detail
        <span>{match.window}</span>
      </div>

      <div className="detail-grid">
        <div>
          <div className="detail-stat-label">Confidence</div>
          <div className="detail-stat-value" style={{ color: "var(--positive)" }}>
            {match.score.toFixed(1)}
          </div>
        </div>
        <div>
          <div className="detail-stat-label">Delta</div>
          <div className="detail-stat-value" style={{
            color: deltaClass === "positive" ? "var(--positive)" : deltaClass === "negative" ? "var(--negative)" : "var(--text-secondary)"
          }}>
            {deltaSign}{match.delta.toFixed(1)}%
          </div>
        </div>
        <div>
          <div className="detail-stat-label">Method</div>
          <div className="detail-stat-value" style={{ fontSize: 12 }}>
            {match.method}
          </div>
        </div>
        <div>
          <div className="detail-stat-label">Regime</div>
          <div className="detail-stat-value" style={{ fontSize: 12 }}>
            {match.regime}
          </div>
        </div>
      </div>
    </div>
  );
}
