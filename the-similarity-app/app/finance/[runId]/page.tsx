"use client";

/**
 * Finance run detail page — /finance/[runId]
 *
 * Fetches GET /platform/runs/{runId} + GET /platform/runs/{runId}/scorecards
 * + GET /platform/runs/{runId}/artifacts and renders the full run inspection
 * view with the following sections:
 *
 *   1. Breadcrumb navigation (Finance > Runs > {run_id}) with back + compare
 *   2. Status lifecycle bar (pending → running → succeeded/failed) + timestamps
 *   3. Grouped metric cards:
 *      - Accuracy: Hit Rate, CRPS
 *      - Coverage: Coverage, Calibration Grade
 *      - Risk: Max Drawdown, Sharpe Ratio, Profit Factor
 *   4. Trust assessment (trust_score, calibration_grade, decision, risk flags)
 *   5. Calibration chart (45-degree line SVG) + table
 *   6. Artifacts list with name, content_type, size
 *   7. Collapsible run config JSON viewer
 *   8. Scorecards + review section
 *
 * Design language: monospace for data, serif for headings, system font for
 * body text. Matches the existing workstation/finance page styling.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  fetchRun,
  fetchScorecards,
  fetchArtifacts,
  type Run,
  type Scorecard,
  type Artifact,
} from "../../../lib/platform-api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Safely dig into a nested object by key path. Returns undefined if any
 *  intermediate key is missing or the value is not an object. */
function dig(obj: Record<string, unknown>, ...keys: string[]): unknown {
  let cur: unknown = obj;
  for (const k of keys) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[k];
  }
  return cur;
}

/** Format a numeric value to fixed decimal places, or "-" if missing/NaN. */
function fmt(val: unknown, decimals = 4): string {
  if (val == null) return "-";
  const n = Number(val);
  if (Number.isNaN(n)) return "-";
  return n.toFixed(decimals);
}

/** Format a numeric value as a percentage string, or "-" if missing/NaN. */
function pct(val: unknown): string {
  if (val == null) return "-";
  const n = Number(val);
  if (Number.isNaN(n)) return "-";
  return `${(n * 100).toFixed(1)}%`;
}

/** Format ISO timestamp to a human-readable locale string. */
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

/** Format byte count to human-readable size string (KB/MB/GB). */
function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function FinanceRunDetailPage() {
  const params = useParams();
  const runId = params?.runId as string;

  const [run, setRun] = useState<Run | null>(null);
  const [scorecards, setScorecards] = useState<Scorecard[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Collapsible state for the run config JSON viewer
  const [configOpen, setConfigOpen] = useState(false);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;

    // Fetch run + scorecards + artifacts in parallel. Loading/error state
    // is reset inside the promise chain to satisfy react-hooks rules.
    Promise.resolve()
      .then(() => {
        if (!cancelled) {
          setLoading(true);
          setError(null);
        }
        return Promise.all([
          fetchRun(runId),
          fetchScorecards(runId),
          fetchArtifacts(runId),
        ]);
      })
      .then(([r, sc, art]) => {
        if (!cancelled) {
          setRun(r);
          setScorecards(sc);
          setArtifacts(art);
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

  // ── Loading state ──
  if (loading) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <div className="deck-feed-empty">Loading run details...</div>
        </div>
      </div>
    );
  }

  // ── Error state ──
  if (error || !run) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <Breadcrumb runId={runId} />
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

  // ── Extract fields from config / summary / scorecards ──
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

  // Trust color — green if >= 0.7, yellow-ish if >= 0.5, red otherwise
  const trustN = Number(trustScore);
  const trustColor = Number.isNaN(trustN)
    ? "var(--ink-3)"
    : trustN >= 0.7
      ? "var(--positive)"
      : trustN >= 0.5
        ? "var(--warn)"
        : "var(--negative)";

  return (
    <div className="deck-page">
      <div className="deck-page__inner">
        {/* ── Breadcrumb ── */}
        <Breadcrumb runId={run.run_id} />

        {/* ── Navigation actions ── */}
        <div className="nav-actions">
          <Link href="/finance" className="nav-btn">
            &larr; Back
          </Link>
          <Link
            href={`/finance/compare?ids=${run.run_id}`}
            className="nav-btn"
          >
            Compare with...
          </Link>
        </div>

        {/* ── Title + status ── */}
        <h1 className="deck-page__title" style={{ marginBottom: 8 }}>
          {String(symbol)}
        </h1>
        <p className="deck-page__intro" style={{ marginBottom: 24 }}>
          {formatDate(run.created_at)} &middot; Seed {run.seed ?? "-"} &middot;
          Window {windowSize != null ? String(windowSize) : "-"} &middot;
          Forward {forwardBars != null ? String(forwardBars) : "-"}
        </p>

        {/* ── Status lifecycle ── */}
        <StatusLifecycle status={run.status} createdAt={run.created_at} />

        {/* ── Grouped metric cards ── */}
        <section className="deck-section">
          <p className="deck-section__tag">Metrics</p>

          {/* Accuracy group */}
          <div className="metric-group">
            <p className="metric-group__label">Accuracy</p>
            <div className="metric-group__cards">
              <MetricTile
                label="Hit Rate"
                value={pct(hitRate)}
                sentiment={metricSentiment(hitRate, 0.5)}
              />
              <MetricTile
                label="CRPS"
                value={fmt(crps)}
                sentiment="neutral"
              />
            </div>
          </div>

          {/* Coverage group */}
          <div className="metric-group">
            <p className="metric-group__label">Coverage</p>
            <div className="metric-group__cards">
              <MetricTile
                label="Coverage"
                value={pct(coverage)}
                sentiment={metricSentiment(coverage, 0.8)}
              />
              <MetricTile
                label="Cal. Grade"
                value={calGrade != null ? String(calGrade) : "-"}
                sentiment="neutral"
              />
            </div>
          </div>

          {/* Risk group */}
          <div className="metric-group">
            <p className="metric-group__label">Risk</p>
            <div className="metric-group__cards">
              <MetricTile
                label="Max Drawdown"
                value={pct(maxDrawdown)}
                sentiment={
                  maxDrawdown != null && Number(maxDrawdown) < -0.1
                    ? "negative"
                    : "neutral"
                }
              />
              <MetricTile
                label="Sharpe Ratio"
                value={fmt(sharpeRatio, 2)}
                sentiment={metricSentiment(sharpeRatio, 0)}
              />
              <MetricTile
                label="Profit Factor"
                value={fmt(profitFactor, 2)}
                sentiment={metricSentiment(profitFactor, 1)}
              />
            </div>
          </div>
        </section>

        {/* ── Trust assessment ── */}
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

          {/* Risk flags as colored badges */}
          {riskFlags && riskFlags.length > 0 && (
            <div
              style={{
                marginTop: 16,
                display: "flex",
                gap: 8,
                flexWrap: "wrap",
              }}
            >
              {riskFlags.map((flag, i) => (
                <span
                  key={i}
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    fontWeight: 700,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    padding: "3px 10px",
                    borderRadius: 2,
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
        </section>

        {/* ── Calibration chart + table ── */}
        {calibration && Object.keys(calibration).length > 0 && (
          <section className="deck-section">
            <p className="deck-section__tag">Calibration</p>

            {/* SVG calibration chart — 45-degree diagonal = perfect calibration */}
            <CalibrationChart calibration={calibration} />

            {/* Table below the chart for exact values */}
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
                                  : "var(--ink-3)",
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

        {/* ── Artifacts list ── */}
        {artifacts.length > 0 && (
          <section className="deck-section">
            <p className="deck-section__tag">
              Artifacts ({artifacts.length})
            </p>
            <div className="artifact-list">
              {artifacts.map((art) => (
                <div key={art.name} className="artifact-row">
                  <span className="artifact-row__name">{art.name}</span>
                  <span className="artifact-row__type">
                    {art.content_type ?? "unknown"}
                  </span>
                  <span className="artifact-row__size">
                    {formatBytes(art.size_bytes)}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ── Run config (collapsible) ── */}
        <section className="deck-section">
          <p className="deck-section__tag">Configuration</p>
          <button
            className="config-toggle"
            onClick={() => setConfigOpen(!configOpen)}
            aria-expanded={configOpen}
          >
            <span>
              {configOpen ? "Hide" : "Show"} full configuration (
              {Object.keys(run.config).length} keys)
            </span>
            <span
              className={`config-toggle__chevron${configOpen ? " config-toggle__chevron--open" : ""}`}
            >
              &#9660;
            </span>
          </button>
          {configOpen && (
            <div className="config-body">
              {JSON.stringify(run.config, null, 2)}
            </div>
          )}
        </section>

        {/* ── Scorecards ── */}
        {scorecards.length > 0 && (
          <section className="deck-section">
            <p className="deck-section__tag">Scorecards</p>
            {scorecards.map((sc) => (
              <div
                key={sc.name}
                style={{
                  border: "1px solid var(--rule)",
                  background: "var(--bg-card)",
                  padding: "16px 20px",
                  marginBottom: 12,
                  borderRadius: "var(--radius-md)",
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
                      fontFamily: "var(--mono)",
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
                      className={`pill ${sc.passed ? "pill--pos" : "pill--neg"}`}
                    >
                      {sc.passed ? "PASS" : "FAIL"}
                    </span>
                  )}
                </div>
                {sc.overall_score != null && (
                  <p
                    style={{
                      fontFamily: "var(--mono)",
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

        {/* ── Back link (bottom) ── */}
        <div style={{ marginTop: 24, paddingBottom: 40 }}>
          <Link href="/finance" className="nav-btn">
            &larr; Back to all runs
          </Link>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/**
 * Breadcrumb: Finance > Runs > {run_id short}
 * Provides wayfinding context at the top of the detail page.
 */
function Breadcrumb({ runId }: { runId: string }) {
  return (
    <nav className="breadcrumb" aria-label="Breadcrumb">
      <Link href="/finance">Finance</Link>
      <span className="breadcrumb__sep">/</span>
      <span>Runs</span>
      <span className="breadcrumb__sep">/</span>
      <span className="breadcrumb__current">{runId?.slice(0, 8)}</span>
    </nav>
  );
}

/** Simple key/value display cell used in detail grids. */
function MetaCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="detail-stat-label">{label}</p>
      <p className="detail-stat-value">{value}</p>
    </div>
  );
}

/**
 * MetricTile — a single metric in a card with prominent value and small label.
 * Sentiment controls the value color: positive (green), negative (red), neutral.
 */
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

/**
 * StatusLifecycle — visual status indicator showing the run through its
 * lifecycle stages: pending -> running -> succeeded/failed.
 *
 * Steps are connected by lines. The current/final step is highlighted.
 * A timestamp for creation is shown on the right.
 */
function StatusLifecycle({
  status,
  createdAt,
}: {
  status: string;
  createdAt: string;
}) {
  // Normalize status to a known lifecycle position
  const normalized = status.toLowerCase();

  // Determine which steps are complete/active/failed based on current status
  const isFailed = normalized === "failed";
  const isComplete = normalized === "complete" || normalized === "succeeded";
  const isRunning = normalized === "running";
  const isPending = normalized === "pending";

  /**
   * Step state derivation:
   * - "pending" status: pending=active, running=future, result=future
   * - "running" status: pending=complete, running=active, result=future
   * - "complete/succeeded": pending=complete, running=complete, result=complete
   * - "failed": pending=complete, running=complete, result=failed
   */
  const pendingState: StepState = isPending ? "active" : "complete";
  const runningState: StepState = isPending
    ? "future"
    : isRunning
      ? "active"
      : "complete";
  const resultState: StepState = isComplete
    ? "complete"
    : isFailed
      ? "failed"
      : "future";

  return (
    <div className="run-status-lifecycle">
      <Step label="Pending" state={pendingState} />
      <Connector complete={pendingState === "complete"} />
      <Step label="Running" state={runningState} />
      <Connector complete={runningState === "complete"} />
      <Step
        label={isFailed ? "Failed" : "Succeeded"}
        state={resultState}
      />
      <span className="run-status-timestamp">{formatDate(createdAt)}</span>
    </div>
  );
}

type StepState = "future" | "active" | "complete" | "failed";

/** Individual step in the status lifecycle bar. */
function Step({ label, state }: { label: string; state: StepState }) {
  const classMap: Record<StepState, string> = {
    future: "run-status-step",
    active: "run-status-step run-status-step--active",
    complete: "run-status-step run-status-step--complete",
    failed: "run-status-step run-status-step--failed",
  };
  return (
    <div className={classMap[state]}>
      <span className="run-status-step__dot" />
      <span>{label}</span>
    </div>
  );
}

/** Connecting line between lifecycle steps. */
function Connector({ complete }: { complete: boolean }) {
  return (
    <div
      className={`run-status-connector${complete ? " run-status-connector--complete" : ""}`}
    />
  );
}

/**
 * CalibrationChart — inline SVG rendering of expected vs observed percentiles.
 *
 * The 45-degree diagonal represents perfect calibration. Points above the
 * diagonal indicate over-coverage (model is too wide), points below indicate
 * under-coverage (model is too narrow).
 *
 * Uses no external chart library — pure inline SVG with CSS class hooks
 * for theming (see .cal-chart styles in globals.css).
 *
 * Chart dimensions:
 * - SVG viewBox: 0 0 300 260
 * - Plot area: 40,10 to 280,230 (240x220 effective drawing region)
 * - X axis: Expected percentile (0-100%)
 * - Y axis: Observed percentile (0-100%)
 */
function CalibrationChart({
  calibration,
}: {
  calibration: Record<string, { expected: number; observed: number }>;
}) {
  // Sort entries by expected value for a clean line plot
  const entries = Object.entries(calibration)
    .map(([, vals]) => ({
      expected: vals.expected,
      observed: vals.observed,
    }))
    .sort((a, b) => a.expected - b.expected);

  if (entries.length === 0) return null;

  // Plot area geometry (inside the SVG viewBox)
  const left = 40;
  const top = 10;
  const right = 280;
  const bottom = 230;
  const plotW = right - left; // 240
  const plotH = bottom - top; // 220

  /** Map a 0-1 value to x pixel coordinate within the plot area. */
  const xOf = (v: number) => left + v * plotW;
  /** Map a 0-1 value to y pixel coordinate (inverted — 0 at bottom). */
  const yOf = (v: number) => bottom - v * plotH;

  // Build SVG path for the data line connecting calibration points
  const pathParts = entries.map(
    (e, i) =>
      `${i === 0 ? "M" : "L"} ${xOf(e.expected).toFixed(1)} ${yOf(e.observed).toFixed(1)}`
  );
  const dataPath = pathParts.join(" ");

  // Grid lines at 25%, 50%, 75%
  const gridTicks = [0.25, 0.5, 0.75];

  return (
    <svg
      className="cal-chart"
      viewBox="0 0 300 260"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Calibration chart showing expected vs observed percentiles"
    >
      {/* Grid lines — horizontal */}
      {gridTicks.map((t) => (
        <line
          key={`h-${t}`}
          className="grid-line"
          x1={left}
          y1={yOf(t)}
          x2={right}
          y2={yOf(t)}
        />
      ))}
      {/* Grid lines — vertical */}
      {gridTicks.map((t) => (
        <line
          key={`v-${t}`}
          className="grid-line"
          x1={xOf(t)}
          y1={top}
          x2={xOf(t)}
          y2={bottom}
        />
      ))}

      {/* Plot area border */}
      <rect
        x={left}
        y={top}
        width={plotW}
        height={plotH}
        fill="none"
        stroke="var(--rule)"
        strokeWidth={1}
      />

      {/* 45-degree diagonal — perfect calibration reference line */}
      <line
        className="diag-line"
        x1={left}
        y1={bottom}
        x2={right}
        y2={top}
      />

      {/* Data line connecting calibration points */}
      <path className="data-line" d={dataPath} />

      {/* Data dots at each calibration point */}
      {entries.map((e, i) => (
        <circle
          key={i}
          className="data-dot"
          cx={xOf(e.expected)}
          cy={yOf(e.observed)}
          r={3}
        />
      ))}

      {/* Axis labels — X axis (Expected) */}
      <text className="axis-label" x={left} y={bottom + 16} textAnchor="middle">
        0%
      </text>
      <text className="axis-label" x={xOf(0.5)} y={bottom + 16} textAnchor="middle">
        50%
      </text>
      <text className="axis-label" x={right} y={bottom + 16} textAnchor="middle">
        100%
      </text>
      <text
        className="axis-label"
        x={xOf(0.5)}
        y={bottom + 28}
        textAnchor="middle"
      >
        EXPECTED
      </text>

      {/* Axis labels — Y axis (Observed) */}
      <text className="axis-label" x={left - 6} y={bottom + 4} textAnchor="end">
        0%
      </text>
      <text className="axis-label" x={left - 6} y={yOf(0.5) + 3} textAnchor="end">
        50%
      </text>
      <text className="axis-label" x={left - 6} y={top + 4} textAnchor="end">
        100%
      </text>
      <text
        className="axis-label"
        x={10}
        y={yOf(0.5)}
        textAnchor="middle"
        transform={`rotate(-90, 10, ${yOf(0.5)})`}
      >
        OBSERVED
      </text>
    </svg>
  );
}

/** Determine sentiment color based on threshold comparison.
 *  Values >= threshold are positive, below are negative. */
function metricSentiment(
  val: unknown,
  threshold: number
): "positive" | "negative" | "neutral" {
  if (val == null) return "neutral";
  const n = Number(val);
  if (Number.isNaN(n)) return "neutral";
  return n >= threshold ? "positive" : "negative";
}
