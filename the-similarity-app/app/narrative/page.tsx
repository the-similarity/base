"use client";

/**
 * Narrative page — natural-language to trajectory compilation UI.
 *
 * The user types a free-text narrative describing a sequence of market or
 * world events (e.g., "Fed raises rates, inflation spikes, unemployment
 * rises"). Hitting "Compile" sends the text to /api/narrative which
 * returns:
 *   - parsed events table
 *   - a synthetic trajectory line chart
 *   - a list of similar historical patterns
 *
 * States handled: empty (initial), loading, error, results.
 */

import { useState, useCallback } from "react";
import { LineChart } from "../../components/chart/line-chart";

/* ── Types mirroring the API response ───────────────────────────────── */

interface ParsedEvent {
  index: number;
  label: string;
  impact: "positive" | "negative" | "neutral";
  magnitude: number;
}

interface SimilarHistory {
  label: string;
  score: number;
  period: string;
}

interface NarrativeResult {
  events: ParsedEvent[];
  trajectory: number[];
  similarHistories: SimilarHistory[];
}

/* ── Impact badge color helper ──────────────────────────────────────── */

function impactColor(impact: string): string {
  if (impact === "positive") return "var(--positive)";
  if (impact === "negative") return "var(--negative)";
  return "var(--text-muted)";
}

function impactBgColor(impact: string): string {
  if (impact === "positive") return "var(--positive-dim)";
  if (impact === "negative") return "var(--negative-dim)";
  return "var(--bg-inset)";
}

/* ── Page component ─────────────────────────────────────────────────── */

export default function NarrativePage() {
  const [text, setText] = useState("");
  const [result, setResult] = useState<NarrativeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCompile = useCallback(async () => {
    const trimmed = text.trim();
    if (!trimmed) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch("/api/narrative", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: trimmed }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `Request failed (${res.status})`);
      }

      const data: NarrativeResult = await res.json();
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  }, [text]);

  /* Handle Cmd/Ctrl+Enter to submit from the textarea. */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        handleCompile();
      }
    },
    [handleCompile],
  );

  return (
    <div className="narrative-page">
      {/* ── Input section ── */}
      <section className="narrative-input-section">
        <div className="narrative-input-header">
          <h1 className="narrative-input-title">Narrative</h1>
          <p className="narrative-input-subtitle">
            Describe a sequence of events in plain language. The engine compiles
            your narrative into a trajectory and finds similar historical patterns.
          </p>
        </div>

        <textarea
          className="narrative-textarea"
          placeholder="e.g. The central bank unexpectedly raises rates by 75bps. Equity markets sell off sharply. Credit spreads widen. Two months later, inflation data softens and the market stabilizes..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={5}
          disabled={loading}
        />

        <div className="narrative-actions">
          <button
            className="narrative-compile-btn"
            onClick={handleCompile}
            disabled={loading || !text.trim()}
          >
            {loading ? "Compiling..." : "Compile"}
          </button>
          <span className="narrative-hint mono-label">Ctrl+Enter to submit</span>
        </div>
      </section>

      {/* ── Loading state ── */}
      {loading && (
        <div className="narrative-loading">
          <div className="chart-loading-spinner" />
          <span>Compiling narrative into trajectory...</span>
        </div>
      )}

      {/* ── Error state ── */}
      {error && (
        <div className="narrative-error">
          <div className="match-list-error__icon">!</div>
          <p className="narrative-error-text">{error}</p>
          <button
            className="match-list-error__retry"
            onClick={handleCompile}
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Results ── */}
      {result && !loading && (
        <div className="narrative-results">
          {/* ── Trajectory chart ── */}
          <section className="narrative-section">
            <h2 className="narrative-section-label">Compiled Trajectory</h2>
            <div className="narrative-chart-wrap">
              <LineChart
                data={result.trajectory}
                width={720}
                height={220}
                label="Compiled narrative trajectory"
              />
            </div>
          </section>

          {/* ── Parsed events table ── */}
          <section className="narrative-section">
            <h2 className="narrative-section-label">
              Parsed Events
              <span className="narrative-section-count">
                {result.events.length}
              </span>
            </h2>
            <div className="narrative-events-table-wrap">
              <table className="narrative-events-table">
                <thead>
                  <tr>
                    <th className="narrative-th">#</th>
                    <th className="narrative-th">Event</th>
                    <th className="narrative-th">Impact</th>
                    <th className="narrative-th narrative-th--right">Magnitude</th>
                  </tr>
                </thead>
                <tbody>
                  {result.events.map((event) => (
                    <tr key={event.index} className="narrative-tr">
                      <td className="narrative-td narrative-td--mono">
                        {event.index + 1}
                      </td>
                      <td className="narrative-td">{event.label}</td>
                      <td className="narrative-td">
                        <span
                          className="narrative-impact-badge"
                          style={{
                            color: impactColor(event.impact),
                            background: impactBgColor(event.impact),
                            borderColor: impactColor(event.impact),
                          }}
                        >
                          {event.impact}
                        </span>
                      </td>
                      <td className="narrative-td narrative-td--mono narrative-td--right">
                        {(event.magnitude * 100).toFixed(0)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* ── Similar histories ── */}
          <section className="narrative-section">
            <h2 className="narrative-section-label">
              Similar Histories
              <span className="narrative-section-count">
                {result.similarHistories.length}
              </span>
            </h2>
            <div className="narrative-histories">
              {result.similarHistories.map((hist) => (
                <div key={hist.label} className="narrative-history-card">
                  <div className="narrative-history-score">
                    {(hist.score * 100).toFixed(0)}
                  </div>
                  <div className="narrative-history-info">
                    <span className="narrative-history-label">{hist.label}</span>
                    <span className="narrative-history-period">{hist.period}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}

      {/* ── Empty state (no submission yet, no loading, no error) ── */}
      {!result && !loading && !error && (
        <div className="narrative-empty">
          <div className="narrative-empty-art">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <rect x="4" y="8" width="40" height="32" rx="3" stroke="var(--border-strong)" strokeWidth="1.5" fill="none" />
              <line x1="10" y1="16" x2="38" y2="16" stroke="var(--border)" strokeWidth="1" />
              <line x1="10" y1="22" x2="32" y2="22" stroke="var(--border)" strokeWidth="1" />
              <line x1="10" y1="28" x2="28" y2="28" stroke="var(--border)" strokeWidth="1" />
            </svg>
          </div>
          <p className="narrative-empty-title">
            Describe your scenario
          </p>
          <p className="narrative-empty-hint">
            Write a sequence of events in plain language. The engine will compile
            it into a trajectory and find similar historical patterns.
          </p>
        </div>
      )}
    </div>
  );
}
