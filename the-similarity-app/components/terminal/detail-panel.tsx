"use client";
import { useTerminal } from "../../lib/terminal-context";
import { METHOD_LABELS_CAMEL, METHOD_COLORS } from "../../lib/constants";
import type { ScoreBreakdown, MatchResult } from "../../lib/types";

const snakeToCamel = (s: string) =>
  s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase());

const METHOD_COLORS_CAMEL: Record<string, string> =
  Object.fromEntries(
    Object.entries(METHOD_COLORS).map(([k, v]) => [snakeToCamel(k), v]),
  );

const METHOD_DESCRIPTIONS: Record<string, string> = {
  dtw: "Shape alignment",
  pearsonWarped: "Correlation post-warp",
  bempedelisR2: "Self-similarity fit",
  bempedelisSmoothness: "Transform smoothness",
  koopman: "Dynamical similarity",
  waveletSpectrum: "Fractal spectrum",
  emd: "Multi-scale match",
  tda: "Topological structure",
  transferEntropy: "Predictive information",
};

// Default weights for computing weighted contribution
const DEFAULT_WEIGHTS: Record<string, number> = {
  dtw: 0.15,
  pearsonWarped: 0.15,
  bempedelisR2: 0.1,
  bempedelisSmoothness: 0.1,
  koopman: 0.12,
  waveletSpectrum: 0.1,
  emd: 0.08,
  tda: 0.1,
  transferEntropy: 0.1,
};

function confidenceLevel(score: number): string {
  if (score >= 80) return "high";
  if (score >= 60) return "moderate";
  return "low";
}

function generateSummary(match: MatchResult): string {
  const breakdown = match.scoreBreakdown;
  const entries = Object.entries(breakdown) as [keyof ScoreBreakdown, number][];

  // Compute weighted contributions
  const weighted = entries
    .filter(([, v]) => v > 0)
    .map(([method, value]) => ({
      method,
      value,
      contribution: value * (DEFAULT_WEIGHTS[method] || 0.1),
    }))
    .sort((a, b) => b.contribution - a.contribution);

  const top2 = weighted.slice(0, 2);
  const level = confidenceLevel(match.confidenceScore);

  const parts: string[] = [];
  parts.push(`This match scored ${match.confidenceScore.toFixed(1)}/100`);

  if (top2.length >= 2) {
    const desc0 = METHOD_DESCRIPTIONS[top2[0].method] || top2[0].method;
    const label0 = METHOD_LABELS_CAMEL[top2[0].method] || top2[0].method;
    const desc1 = METHOD_DESCRIPTIONS[top2[1].method] || top2[1].method;
    const label1 = METHOD_LABELS_CAMEL[top2[1].method] || top2[1].method;
    parts.push(
      `, primarily driven by strong ${desc0.toLowerCase()} (${label0}: ${top2[0].value.toFixed(2)}) and good ${desc1.toLowerCase()} (${label1}: ${top2[1].value.toFixed(2)}).`,
    );
  } else if (top2.length === 1) {
    const desc0 = METHOD_DESCRIPTIONS[top2[0].method] || top2[0].method;
    const label0 = METHOD_LABELS_CAMEL[top2[0].method] || top2[0].method;
    parts.push(
      `, primarily driven by ${desc0.toLowerCase()} (${label0}: ${top2[0].value.toFixed(2)}).`,
    );
  } else {
    parts.push(".");
  }

  parts.push(` Confidence: ${level}.`);

  return parts.join("");
}

function computeForwardReturn(forwardWindow: number[]): {
  direction: string;
  arrow: string;
  returnPct: number;
  color: string;
} {
  if (forwardWindow.length < 2) {
    return { direction: "Neutral", arrow: "\u2192", returnPct: 0, color: "var(--text-muted)" };
  }
  const first = forwardWindow[0];
  const last = forwardWindow[forwardWindow.length - 1];
  const returnPct = first !== 0 ? ((last - first) / Math.abs(first)) * 100 : 0;

  if (returnPct > 0.5) {
    return { direction: "Bullish", arrow: "\u2197", returnPct, color: "var(--positive)" };
  } else if (returnPct < -0.5) {
    return { direction: "Bearish", arrow: "\u2198", returnPct, color: "var(--negative)" };
  }
  return { direction: "Neutral", arrow: "\u2192", returnPct, color: "var(--text-muted)" };
}

export function DetailPanel() {
  const { state } = useTerminal();
  if (state.selectedIdx === null || !state.matches[state.selectedIdx]) return null;

  const match = state.matches[state.selectedIdx];
  const window = match.startDate && match.endDate
    ? `${match.startDate} \u2192 ${match.endDate}`
    : `[${match.startIdx}\u2013${match.endIdx}]`;

  const breakdown = match.scoreBreakdown;
  const entries = Object.entries(breakdown)
    .filter(([, v]) => (v as number) > 0)
    .sort((a, b) => (b[1] as number) - (a[1] as number));

  const strengths = Object.entries(breakdown).filter(([, v]) => (v as number) > 0.7);
  const weaknesses = Object.entries(breakdown).filter(
    ([, v]) => (v as number) > 0 && (v as number) < 0.3,
  );

  const summary = generateSummary(match);
  const forecast = match.forwardWindow ? computeForwardReturn(match.forwardWindow) : null;

  return (
    <div className="detail-panel">
      <div className="terminal-panel-header">
        Match #{state.selectedIdx + 1} Detail
        <span>{window}</span>
      </div>

      {/* Natural Language Summary */}
      <div className="detail-summary">{summary}</div>

      <div className="detail-grid">
        <div>
          <div className="detail-stat-label">Confidence</div>
          <div className="detail-stat-value" style={{ color: "var(--positive)" }}>
            {match.confidenceScore.toFixed(1)}
          </div>
        </div>
        <div>
          <div className="detail-stat-label">R&#178; Fit</div>
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

      {/* Strengths & Weaknesses */}
      {(strengths.length > 0 || weaknesses.length > 0) && (
        <div className="detail-strengths-weaknesses">
          <div>
            <div className="detail-stat-label" style={{ marginBottom: "var(--space-sm)" }}>
              Strengths
            </div>
            {strengths.length > 0 ? (
              strengths.map(([method, value]) => (
                <div key={method} className="detail-strength">
                  <span className="detail-sw-score">
                    {((value as number) * 100).toFixed(0)}
                  </span>
                  <span>{METHOD_DESCRIPTIONS[method] || method}</span>
                </div>
              ))
            ) : (
              <div className="detail-sw-empty">None above 70</div>
            )}
          </div>
          <div>
            <div className="detail-stat-label" style={{ marginBottom: "var(--space-sm)" }}>
              Weaknesses
            </div>
            {weaknesses.length > 0 ? (
              weaknesses.map(([method, value]) => (
                <div key={method} className="detail-weakness">
                  <span className="detail-sw-score">
                    {((value as number) * 100).toFixed(0)}
                  </span>
                  <span>{METHOD_DESCRIPTIONS[method] || method}</span>
                </div>
              ))
            ) : (
              <div className="detail-sw-empty">None below 30</div>
            )}
          </div>
        </div>
      )}

      {/* Forecast Context */}
      {forecast && match.forwardWindow && (
        <div className="detail-forecast-context">
          <span className="detail-forecast-arrow" style={{ color: forecast.color }}>
            {forecast.arrow}
          </span>
          <div className="detail-forecast-info">
            <span className="detail-forecast-direction" style={{ color: forecast.color }}>
              {forecast.direction}
            </span>
            <span className="detail-forecast-return">
              Forward return: {forecast.returnPct >= 0 ? "+" : ""}
              {forecast.returnPct.toFixed(1)}%
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
