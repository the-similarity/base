"use client";

/**
 * Finance run detail page — /finance/[runId]
 *
 * Fetches GET /platform/runs/{runId} + GET /platform/runs/{runId}/scorecards
 * and renders the full run inspection view:
 *   - Metadata card (symbol, window_size, forward_bars, seed, created_at)
 *   - Metrics card (hit_rate, crps, coverage, profit_factor, max_drawdown, sharpe_ratio)
 *   - Trust card (trust_score with color, calibration_grade, decision)
 *   - Calibration table (per-percentile expected vs observed)
 *   - Risk flags as colored badges
 *   - Review section (if review exists in scorecard)
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  fetchRun,
  fetchScorecards,
  type Run,
  type Scorecard,
} from "../../../lib/platform-api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function dig(obj: Record<string, unknown>, ...keys: string[]): unknown {
  let cur: unknown = obj;
  for (const k of keys) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[k];
  }
  return cur;
}

function fmt(val: unknown, decimals = 4): string {
  if (val == null) return "-";
  const n = Number(val);
  if (Number.isNaN(n)) return "-";
  return n.toFixed(decimals);
}

function pct(val: unknown): string {
  if (val == null) return "-";
  const n = Number(val);
  if (Number.isNaN(n)) return "-";
  return `${(n * 100).toFixed(1)}%`;
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function FinanceRunDetailPage() {
  const params = useParams();
  const runId = params?.runId as string;

  const [run, setRun] = useState<Run | null>(null);
  const [scorecards, setScorecards] = useState<Scorecard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;

    // Fetch run + scorecards. Loading/error state is reset inside the
    // promise chain (not synchronously) to satisfy react-hooks/set-state-in-effect.
    Promise.resolve()
      .then(() => {
        if (!cancelled) {
          setLoading(true);
          setError(null);
        }
        return Promise.all([fetchRun(runId), fetchScorecards(runId)]);
      })
      .then(([r, sc]) => {
        if (!cancelled) {
          setRun(r);
          setScorecards(sc);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (loading) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <div className="deck-feed-empty">Loading run details...</div>
        </div>
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <p className="deck-page__label">
            <Link href="/finance" style={{ color: "inherit", textDecoration: "none" }}>
              Finance
            </Link>{" "}
            / {runId?.slice(0, 8)}
          </p>
          <div className="match-list-error" style={{ padding: 40 }}>
            <div className="match-list-error__icon">!</div>
            <p className="match-list-error__text">{error ?? "Run not found"}</p>
            <Link href="/finance" className="match-list-error__retry">
              Back to runs
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Extract fields from config / summary / scorecards
  const symbol = dig(run.config, "symbol") ?? dig(run.config, "ticker") ?? "-";
  const windowSize = dig(run.config, "window_size");
  const forwardBars = dig(run.config, "forward_bars");

  const hitRate = dig(run.summary, "hit_rate");
  const crps = dig(run.summary, "crps");
  const coverage = dig(run.summary, "coverage");
  const profitFactor = dig(run.summary, "profit_factor");
  const maxDrawdown = dig(run.summary, "max_drawdown");
  const sharpeRatio = dig(run.summary, "sharpe_ratio");

  const trustScore = dig(run.summary, "trust_score");
  const calGrade = dig(run.summary, "calibration_grade");
  const decision = dig(run.summary, "decision");
  const riskFlags = dig(run.summary, "risk_flags") as string[] | undefined;

  // Calibration data — expected vs observed per percentile
  const calibration = dig(run.summary, "calibration") as
    | Record<string, { expected: number; observed: number }>
    | undefined;

  // Review from scorecards
  const reviewCard = scorecards.find(
    (sc) => sc.name === "review" || sc.name === "trust"
  );

  // Trust color
  const trustN = Number(trustScore);
  const trustColor = Number.isNaN(trustN)
    ? "var(--text-muted)"
    : trustN >= 0.7
      ? "var(--positive)"
      : trustN >= 0.5
        ? "#8a6200"
        : "var(--negative)";

  return (
    <div className="deck-page">
      <div className="deck-page__inner">
        {/* Breadcrumb */}
        <p className="deck-page__label">
          <Link
            href="/finance"
            style={{ color: "inherit", textDecoration: "none" }}
          >
            Finance
          </Link>{" "}
          / {run.run_id.slice(0, 8)}
        </p>

        <h1 className="deck-page__title" style={{ marginBottom: 8 }}>
          {String(symbol)}
        </h1>
        <p className="deck-page__intro" style={{ marginBottom: 40 }}>
          {formatDate(run.created_at)} &middot; Seed {run.seed ?? "-"} &middot;{" "}
          <StatusBadge status={run.status} />
        </p>

        {/* ── Metadata ── */}
        <section className="deck-section">
          <p className="deck-section__tag">Configuration</p>
          <div className="detail-grid">
            <MetaCell label="Symbol" value={String(symbol)} />
            <MetaCell label="Window" value={windowSize != null ? String(windowSize) : "-"} />
            <MetaCell label="Forward Bars" value={forwardBars != null ? String(forwardBars) : "-"} />
            <MetaCell label="Seed" value={run.seed != null ? String(run.seed) : "-"} />
            <MetaCell label="Kind" value={run.kind} />
            <MetaCell label="Created" value={formatDate(run.created_at)} />
          </div>
        </section>

        {/* ── Metrics ── */}
        <section className="deck-section">
          <p className="deck-section__tag">Metrics</p>
          <div className="strategy-metrics">
            <MetricTile label="Hit Rate" value={pct(hitRate)} sentiment={metricSentiment(hitRate, 0.5)} />
            <MetricTile label="CRPS" value={fmt(crps)} sentiment="neutral" />
            <MetricTile label="Coverage" value={pct(coverage)} sentiment={metricSentiment(coverage, 0.8)} />
            <MetricTile label="Profit Factor" value={fmt(profitFactor, 2)} sentiment={metricSentiment(profitFactor, 1)} />
            <MetricTile label="Max Drawdown" value={pct(maxDrawdown)} sentiment={maxDrawdown != null && Number(maxDrawdown) < -0.1 ? "negative" : "neutral"} />
            <MetricTile label="Sharpe Ratio" value={fmt(sharpeRatio, 2)} sentiment={metricSentiment(sharpeRatio, 0)} />
          </div>
        </section>

        {/* ── Trust ── */}
        <section className="deck-section">
          <p className="deck-section__tag">Trust Assessment</p>
          <div className="detail-grid">
            <div>
              <p className="detail-stat-label">Trust Score</p>
              <p className="detail-stat-value" style={{ color: trustColor }}>
                {fmt(trustScore, 3)}
              </p>
            </div>
            <div>
              <p className="detail-stat-label">Calibration Grade</p>
              <p className="detail-stat-value">
                {calGrade != null ? String(calGrade) : "-"}
              </p>
            </div>
            <div>
              <p className="detail-stat-label">Decision</p>
              <p className="detail-stat-value">
                {decision != null ? String(decision) : "-"}
              </p>
            </div>
          </div>

          {/* Risk flags */}
          {riskFlags && riskFlags.length > 0 && (
            <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
              {riskFlags.map((flag, i) => (
                <span
                  key={i}
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    padding: "3px 10px",
                    borderRadius: "var(--radius-pill)",
                    border: "1px solid var(--negative)",
                    color: "var(--negative)",
                    background: "var(--negative-dim)",
                  }}
                >
                  {flag}
                </span>
              ))}
            </div>
          )}
        </section>

        {/* ── Calibration ── */}
        {calibration && Object.keys(calibration).length > 0 && (
          <section className="deck-section">
            <p className="deck-section__tag">Calibration</p>
            <div className="portfolio-table-wrap">
              <table className="portfolio-table">
                <thead>
                  <tr>
                    <th className="portfolio-table__th">Percentile</th>
                    <th className="portfolio-table__th portfolio-table__th--right">
                      Expected
                    </th>
                    <th className="portfolio-table__th portfolio-table__th--right">
                      Observed
                    </th>
                    <th className="portfolio-table__th portfolio-table__th--right">
                      Gap
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(calibration)
                    .sort(([a], [b]) => Number(a) - Number(b))
                    .map(([pctl, vals]) => {
                      const gap = vals.observed - vals.expected;
                      return (
                        <tr key={pctl} className="portfolio-table__row">
                          <td className="portfolio-table__td portfolio-table__td--mono">
                            P{pctl}
                          </td>
                          <td className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right">
                            {(vals.expected * 100).toFixed(1)}%
                          </td>
                          <td className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right">
                            {(vals.observed * 100).toFixed(1)}%
                          </td>
                          <td
                            className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right"
                            style={{
                              color:
                                Math.abs(gap) > 0.1
                                  ? "var(--negative)"
                                  : "var(--text-muted)",
                            }}
                          >
                            {gap >= 0 ? "+" : ""}
                            {(gap * 100).toFixed(1)}%
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* ── Scorecards ── */}
        {scorecards.length > 0 && (
          <section className="deck-section">
            <p className="deck-section__tag">Scorecards</p>
            {scorecards.map((sc) => (
              <div
                key={sc.name}
                style={{
                  border: "1px solid var(--border)",
                  background: "var(--bg-card)",
                  padding: "16px 20px",
                  marginBottom: 12,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 8,
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      fontWeight: 700,
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                    }}
                  >
                    {sc.name}
                  </span>
                  {sc.passed != null && (
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        fontFamily: "var(--font-mono)",
                        padding: "2px 8px",
                        borderRadius: "var(--radius-pill)",
                        border: `1px solid ${sc.passed ? "var(--positive)" : "var(--negative)"}`,
                        color: sc.passed ? "var(--positive)" : "var(--negative)",
                      }}
                    >
                      {sc.passed ? "PASS" : "FAIL"}
                    </span>
                  )}
                </div>
                {sc.overall_score != null && (
                  <p
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 14,
                      fontWeight: 600,
                      margin: "0 0 8px",
                    }}
                  >
                    Score: {sc.overall_score.toFixed(3)}
                  </p>
                )}
                {Object.keys(sc.metrics).length > 0 && (
                  <div className="detail-grid" style={{ marginBottom: 0 }}>
                    {Object.entries(sc.metrics).map(([k, v]) => (
                      <MetaCell key={k} label={k} value={String(v)} />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </section>
        )}

        {/* ── Review ── */}
        {reviewCard && reviewCard.metrics && (
          <section className="deck-section">
            <p className="deck-section__tag">Review</p>
            <div className="detail-summary">
              {dig(reviewCard.metrics as Record<string, unknown>, "commentary") !=
              null
                ? String(
                    dig(
                      reviewCard.metrics as Record<string, unknown>,
                      "commentary"
                    )
                  )
                : JSON.stringify(reviewCard.metrics, null, 2)}
            </div>
          </section>
        )}

        {/* Back link */}
        <div style={{ marginTop: 24 }}>
          <Link
            href="/finance"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              color: "var(--text-muted)",
              textDecoration: "none",
              borderBottom: "1px dotted var(--border-strong)",
            }}
          >
            Back to all runs
          </Link>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetaCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="detail-stat-label">{label}</p>
      <p className="detail-stat-value">{value}</p>
    </div>
  );
}

function MetricTile({
  label,
  value,
  sentiment,
}: {
  label: string;
  value: string;
  sentiment: "positive" | "negative" | "neutral";
}) {
  return (
    <div className="strategy-metric-card">
      <span className={`strategy-metric-value ${sentiment}`}>{value}</span>
      <span className="strategy-metric-label">{label}</span>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    complete: "var(--positive)",
    running: "var(--accent)",
    pending: "var(--text-muted)",
    failed: "var(--negative)",
  };
  const color = colorMap[status] ?? "var(--text-muted)";
  return (
    <span
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        padding: "3px 8px",
        borderRadius: "var(--radius-pill)",
        border: `1px solid ${color}`,
        color,
      }}
    >
      {status}
    </span>
  );
}

/** Determine sentiment color based on threshold. */
function metricSentiment(
  val: unknown,
  threshold: number
): "positive" | "negative" | "neutral" {
  if (val == null) return "neutral";
  const n = Number(val);
  if (Number.isNaN(n)) return "neutral";
  return n >= threshold ? "positive" : "negative";
}
