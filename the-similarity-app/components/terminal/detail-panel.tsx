"use client";
import { useTerminal } from "../../lib/terminal-context";
import { METHOD_LABELS_CAMEL, METHOD_COLORS } from "../../lib/constants";

const snakeToCamel = (s: string) =>
  s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());

const METHOD_COLORS_CAMEL: Record<string, string> =
  Object.fromEntries(
    Object.entries(METHOD_COLORS).map(([k, v]) => [snakeToCamel(k), v]),
  );

export function DetailPanel() {
  const { state } = useTerminal();
  if (state.selectedIdx === null || !state.matches[state.selectedIdx]) return null;

  const match = state.matches[state.selectedIdx];
  const window = match.startDate && match.endDate
    ? `${match.startDate} → ${match.endDate}`
    : `[${match.startIdx}–${match.endIdx}]`;

  const breakdown = match.scoreBreakdown;
  const entries = Object.entries(breakdown)
    .filter(([, v]) => (v as number) > 0)
    .sort((a, b) => (b[1] as number) - (a[1] as number));

  return (
    <div className="detail-panel">
      <div className="terminal-panel-header">
        Match #{state.selectedIdx + 1} Detail
        <span>{window}</span>
      </div>

      <div className="detail-grid">
        <div>
          <div className="detail-stat-label">Confidence</div>
          <div className="detail-stat-value" style={{ color: "var(--positive)" }}>
            {match.confidenceScore.toFixed(1)}
          </div>
        </div>
        <div>
          <div className="detail-stat-label">R² Fit</div>
          <div className="detail-stat-value">
            {match.transformR2.toFixed(3)}
          </div>
        </div>
        {match.forwardWindow && (
          <div>
            <div className="detail-stat-label">Fwd Bars</div>
            <div className="detail-stat-value">
              {match.forwardWindow.length}
            </div>
          </div>
        )}
      </div>

      {entries.length > 0 && (
        <div className="detail-breakdown">
          {entries.map(([method, value]) => (
            <div key={method} className="detail-breakdown-row">
              <span className="detail-breakdown-label">
                {METHOD_LABELS_CAMEL[method] || method}
              </span>
              <div className="detail-breakdown-bar">
                <div
                  className="detail-breakdown-fill"
                  style={{
                    width: `${(value as number) * 100}%`,
                    background: METHOD_COLORS_CAMEL[method] || "var(--text-muted)",
                  }}
                />
              </div>
              <span className="detail-breakdown-value">
                {((value as number) * 100).toFixed(0)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
