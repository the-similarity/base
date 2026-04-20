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

import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  fetchRun,
  fetchScorecards,
  fetchReview,
  createReview,
  updateReview,
  type Run,
  type Scorecard,
  type Review,
  type ReviewCreateBody,
  type ReviewUpdateBody,
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
  const [review, setReview] = useState<Review | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state for create/update review forms
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showUpdateModal, setShowUpdateModal] = useState(false);

  /** Load run data, scorecards, and existing review. */
  const loadData = useCallback(() => {
    if (!runId) return;
    setLoading(true);
    setError(null);

    // Fetch run + scorecards + review in parallel.
    // Review fetch may 404 (no review yet) — that's expected.
    Promise.all([
      fetchRun(runId),
      fetchScorecards(runId),
      fetchReview(runId).catch(() => null),
    ])
      .then(([r, sc, rev]) => {
        setRun(r);
        setScorecards(sc);
        setReview(rev);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [runId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

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

  // Trust score color thresholds — aligned with the backend decision gate
  // in the_similarity/platform/adapters/trust.py:
  //   >= 0.7  -> green  (TRUSTED decision)
  //   >= 0.5  -> amber  (REVIEW decision)
  //   <  0.5  -> red    (REJECTED decision)
  // NOTE: The trust score is an UNCALIBRATED heuristic (v1). See trust.py
  // module docstring for details. Check UNCALIBRATED flag before gating
  // production decisions on this value.
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
        {review ? (
          <section className="deck-section">
            <p className="deck-section__tag">Review</p>
            <div
              style={{
                border: "1px solid var(--rule)",
                background: "var(--bg-card)",
                padding: "16px 20px",
              }}
            >
              {/* Header row: reviewer + trust decision badge */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 12,
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 12,
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                  }}
                >
                  Reviewed by {review.reviewer}
                </span>
                <TrustDecisionBadge decision={review.trust_decision} />
              </div>

              {/* Status + dates */}
              <div className="detail-grid" style={{ marginBottom: 12 }}>
                <MetaCell label="Status" value={review.status} />
                <MetaCell label="Created" value={formatDate(review.created_at)} />
                <MetaCell
                  label="Updated"
                  value={review.updated_at ? formatDate(review.updated_at) : "-"}
                />
              </div>

              {/* Signal summary */}
              {review.signal_summary && (
                <div style={{ marginBottom: 12 }}>
                  <p className="detail-stat-label">Signal Summary</p>
                  <p
                    style={{
                      fontFamily: "var(--sans)",
                      fontSize: 13,
                      lineHeight: 1.5,
                      color: "var(--ink-2)",
                      margin: "4px 0 0",
                    }}
                  >
                    {review.signal_summary}
                  </p>
                </div>
              )}

              {/* Notes */}
              {review.notes && (
                <div style={{ marginBottom: 12 }}>
                  <p className="detail-stat-label">Notes</p>
                  <p
                    style={{
                      fontFamily: "var(--sans)",
                      fontSize: 13,
                      lineHeight: 1.5,
                      color: "var(--ink-2)",
                      margin: "4px 0 0",
                    }}
                  >
                    {review.notes}
                  </p>
                </div>
              )}

              {/* Risk flags */}
              {review.risk_flags && review.risk_flags.length > 0 && (
                <div
                  style={{
                    marginBottom: 12,
                    display: "flex",
                    gap: 8,
                    flexWrap: "wrap",
                  }}
                >
                  {review.risk_flags.map((flag, i) => (
                    <span
                      key={i}
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 10,
                        fontWeight: 700,
                        letterSpacing: "0.06em",
                        textTransform: "uppercase",
                        padding: "3px 10px",
                        borderRadius: "var(--radius-pill, 999px)",
                        border: "1px solid var(--negative)",
                        color: "var(--negative)",
                        background: "var(--negative-soft)",
                      }}
                    >
                      {flag}
                    </span>
                  ))}
                </div>
              )}

              {/* Realized outcome */}
              {review.realized_outcome && (
                <div style={{ marginBottom: 12 }}>
                  <p className="detail-stat-label">Realized Outcome</p>
                  <pre
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                      color: "var(--ink-3)",
                      margin: "4px 0 0",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {JSON.stringify(review.realized_outcome, null, 2)}
                  </pre>
                </div>
              )}

              {/* Update button */}
              <button
                onClick={() => setShowUpdateModal(true)}
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  padding: "6px 16px",
                  border: "1px solid var(--rule-strong)",
                  borderRadius: "var(--radius-sm, 2px)",
                  background: "var(--bg-inset)",
                  color: "var(--ink-2)",
                  cursor: "pointer",
                  marginTop: 4,
                }}
              >
                Update Review
              </button>
            </div>
          </section>
        ) : (
          <section className="deck-section">
            <p className="deck-section__tag">Review</p>
            <div
              style={{
                border: "1px solid var(--rule)",
                background: "var(--bg-card)",
                padding: "20px",
                textAlign: "center",
              }}
            >
              <p
                style={{
                  fontFamily: "var(--sans)",
                  fontSize: 13,
                  color: "var(--ink-3)",
                  margin: "0 0 12px",
                }}
              >
                No review yet. Create one to record your trust assessment.
              </p>
              <button
                onClick={() => setShowCreateModal(true)}
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  padding: "8px 20px",
                  border: "1px solid var(--accent)",
                  borderRadius: "var(--radius-sm, 2px)",
                  background: "var(--accent-soft)",
                  color: "var(--accent)",
                  cursor: "pointer",
                }}
              >
                Create Review
              </button>
            </div>
          </section>
        )}

        {/* ── Scorecard review (legacy) ── */}
        {reviewCard && reviewCard.metrics && !review && (
          <section className="deck-section">
            <p className="deck-section__tag">Scorecard Review (Legacy)</p>
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

        {/* ── Create Review Modal ── */}
        {showCreateModal && (
          <CreateReviewModal
            runId={runId}
            onClose={() => setShowCreateModal(false)}
            onCreated={() => {
              setShowCreateModal(false);
              loadData();
            }}
          />
        )}

        {/* ── Update Review Modal ── */}
        {showUpdateModal && review && (
          <UpdateReviewModal
            runId={runId}
            existing={review}
            onClose={() => setShowUpdateModal(false)}
            onUpdated={() => {
              setShowUpdateModal(false);
              loadData();
            }}
          />
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

/** Badge for trust decisions: TRUSTED (green), REVIEW (yellow), REJECTED (red). */
function TrustDecisionBadge({ decision }: { decision: string }) {
  const colorMap: Record<string, string> = {
    TRUSTED: "var(--positive)",
    REVIEW: "var(--warn, #8a6200)",
    REJECTED: "var(--negative)",
  };
  const color = colorMap[decision] ?? "var(--ink-3)";
  return (
    <span
      style={{
        fontFamily: "var(--mono)",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        padding: "3px 8px",
        borderRadius: "var(--radius-pill, 999px)",
        border: `1px solid ${color}`,
        color,
      }}
    >
      {decision}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Shared modal styles — reused by Create and Update modals
// ---------------------------------------------------------------------------

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: "rgba(0, 0, 0, 0.5)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
};

const modalStyle: React.CSSProperties = {
  background: "var(--bg-elevated)",
  border: "1px solid var(--rule)",
  borderRadius: "var(--radius-md, 4px)",
  padding: 24,
  width: "100%",
  maxWidth: 520,
  maxHeight: "80vh",
  overflow: "auto",
};

const fieldLabelStyle: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 10,
  fontWeight: 600,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  color: "var(--ink-3)",
  display: "block",
  marginBottom: 4,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "6px 10px",
  fontFamily: "var(--mono)",
  fontSize: 12,
  border: "1px solid var(--rule)",
  borderRadius: "var(--radius-sm, 2px)",
  background: "var(--bg-inset)",
  color: "var(--ink)",
};

const textareaStyle: React.CSSProperties = {
  ...inputStyle,
  minHeight: 80,
  resize: "vertical" as const,
};

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  cursor: "pointer",
};

const btnPrimaryStyle: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  padding: "8px 20px",
  border: "1px solid var(--accent)",
  borderRadius: "var(--radius-sm, 2px)",
  background: "var(--accent-soft)",
  color: "var(--accent)",
  cursor: "pointer",
};

const btnSecondaryStyle: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  padding: "8px 20px",
  border: "1px solid var(--rule)",
  borderRadius: "var(--radius-sm, 2px)",
  background: "transparent",
  color: "var(--ink-3)",
  cursor: "pointer",
};

// ---------------------------------------------------------------------------
// Create Review Modal
// ---------------------------------------------------------------------------

function CreateReviewModal({
  runId,
  onClose,
  onCreated,
}: {
  runId: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [reviewer, setReviewer] = useState("");
  const [signalSummary, setSignalSummary] = useState("");
  const [trustDecision, setTrustDecision] = useState("REVIEW");
  const [riskFlagsRaw, setRiskFlagsRaw] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!reviewer.trim()) return;

    setSubmitting(true);
    setSubmitError(null);

    // Parse comma-separated risk flags into an array, trimming whitespace.
    const riskFlags = riskFlagsRaw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    const body: ReviewCreateBody = {
      reviewer: reviewer.trim(),
      signal_summary: signalSummary.trim(),
      trust_decision: trustDecision,
      risk_flags: riskFlags,
      notes: notes.trim(),
    };

    createReview(runId, body)
      .then(() => onCreated())
      .catch((err) =>
        setSubmitError(err instanceof Error ? err.message : String(err))
      )
      .finally(() => setSubmitting(false));
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <h2
          style={{
            fontFamily: "var(--serif)",
            fontSize: 20,
            fontWeight: 600,
            margin: "0 0 16px",
            letterSpacing: "-0.01em",
          }}
        >
          Create Review
        </h2>

        <form onSubmit={handleSubmit}>
          {/* Reviewer */}
          <div style={{ marginBottom: 14 }}>
            <label style={fieldLabelStyle}>Reviewer *</label>
            <input
              style={inputStyle}
              type="text"
              placeholder="Agent ID or email"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
              required
            />
          </div>

          {/* Trust decision */}
          <div style={{ marginBottom: 14 }}>
            <label style={fieldLabelStyle}>Trust Decision</label>
            <select
              style={selectStyle}
              value={trustDecision}
              onChange={(e) => setTrustDecision(e.target.value)}
            >
              <option value="TRUSTED">TRUSTED</option>
              <option value="REVIEW">REVIEW</option>
              <option value="REJECTED">REJECTED</option>
            </select>
          </div>

          {/* Signal summary */}
          <div style={{ marginBottom: 14 }}>
            <label style={fieldLabelStyle}>Signal Summary</label>
            <textarea
              style={textareaStyle}
              placeholder="1-3 sentence summary of what this run found"
              value={signalSummary}
              onChange={(e) => setSignalSummary(e.target.value)}
            />
          </div>

          {/* Risk flags */}
          <div style={{ marginBottom: 14 }}>
            <label style={fieldLabelStyle}>Risk Flags</label>
            <input
              style={inputStyle}
              type="text"
              placeholder="Comma-separated (e.g. OVERFITTING, LOW_COVERAGE)"
              value={riskFlagsRaw}
              onChange={(e) => setRiskFlagsRaw(e.target.value)}
            />
          </div>

          {/* Notes */}
          <div style={{ marginBottom: 20 }}>
            <label style={fieldLabelStyle}>Notes</label>
            <textarea
              style={textareaStyle}
              placeholder="Free-form reviewer notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {/* Error message */}
          {submitError && (
            <p
              style={{
                color: "var(--negative)",
                fontFamily: "var(--mono)",
                fontSize: 11,
                marginBottom: 12,
              }}
            >
              {submitError}
            </p>
          )}

          {/* Actions */}
          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
            <button
              type="button"
              style={btnSecondaryStyle}
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
            <button type="submit" style={btnPrimaryStyle} disabled={submitting}>
              {submitting ? "Submitting..." : "Submit Review"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Update Review Modal
// ---------------------------------------------------------------------------

function UpdateReviewModal({
  runId,
  existing,
  onClose,
  onUpdated,
}: {
  runId: string;
  existing: Review;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [status, setStatus] = useState(existing.status);
  const [trustDecision, setTrustDecision] = useState(existing.trust_decision);
  const [riskFlagsRaw, setRiskFlagsRaw] = useState(
    existing.risk_flags.join(", ")
  );
  const [notes, setNotes] = useState(existing.notes);
  const [realizedOutcomeRaw, setRealizedOutcomeRaw] = useState(
    existing.realized_outcome
      ? JSON.stringify(existing.realized_outcome, null, 2)
      : ""
  );
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);

    const riskFlags = riskFlagsRaw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);

    // Parse realized outcome JSON if provided.
    let realizedOutcome: Record<string, unknown> | undefined;
    if (realizedOutcomeRaw.trim()) {
      try {
        realizedOutcome = JSON.parse(realizedOutcomeRaw);
      } catch {
        setSubmitError("Realized outcome must be valid JSON.");
        setSubmitting(false);
        return;
      }
    }

    const body: ReviewUpdateBody = {
      status,
      trust_decision: trustDecision,
      notes: notes.trim(),
      risk_flags: riskFlags,
      ...(realizedOutcome !== undefined && {
        realized_outcome: realizedOutcome,
      }),
    };

    updateReview(runId, body)
      .then(() => onUpdated())
      .catch((err) =>
        setSubmitError(err instanceof Error ? err.message : String(err))
      )
      .finally(() => setSubmitting(false));
  };

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <h2
          style={{
            fontFamily: "var(--serif)",
            fontSize: 20,
            fontWeight: 600,
            margin: "0 0 16px",
            letterSpacing: "-0.01em",
          }}
        >
          Update Review
        </h2>

        <form onSubmit={handleSubmit}>
          {/* Status */}
          <div style={{ marginBottom: 14 }}>
            <label style={fieldLabelStyle}>Status</label>
            <select
              style={selectStyle}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="flagged">Flagged</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>

          {/* Trust decision */}
          <div style={{ marginBottom: 14 }}>
            <label style={fieldLabelStyle}>Trust Decision</label>
            <select
              style={selectStyle}
              value={trustDecision}
              onChange={(e) => setTrustDecision(e.target.value)}
            >
              <option value="TRUSTED">TRUSTED</option>
              <option value="REVIEW">REVIEW</option>
              <option value="REJECTED">REJECTED</option>
            </select>
          </div>

          {/* Risk flags */}
          <div style={{ marginBottom: 14 }}>
            <label style={fieldLabelStyle}>Risk Flags</label>
            <input
              style={inputStyle}
              type="text"
              placeholder="Comma-separated (e.g. OVERFITTING, LOW_COVERAGE)"
              value={riskFlagsRaw}
              onChange={(e) => setRiskFlagsRaw(e.target.value)}
            />
          </div>

          {/* Notes */}
          <div style={{ marginBottom: 14 }}>
            <label style={fieldLabelStyle}>Notes</label>
            <textarea
              style={textareaStyle}
              placeholder="Updated reviewer notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          {/* Realized outcome */}
          <div style={{ marginBottom: 20 }}>
            <label style={fieldLabelStyle}>Realized Outcome (JSON)</label>
            <textarea
              style={{ ...textareaStyle, minHeight: 60 }}
              placeholder='{"pnl": 0.05, "direction_correct": true}'
              value={realizedOutcomeRaw}
              onChange={(e) => setRealizedOutcomeRaw(e.target.value)}
            />
          </div>

          {/* Error message */}
          {submitError && (
            <p
              style={{
                color: "var(--negative)",
                fontFamily: "var(--mono)",
                fontSize: 11,
                marginBottom: 12,
              }}
            >
              {submitError}
            </p>
          )}

          {/* Actions */}
          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
            <button
              type="button"
              style={btnSecondaryStyle}
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
            <button type="submit" style={btnPrimaryStyle} disabled={submitting}>
              {submitting ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
