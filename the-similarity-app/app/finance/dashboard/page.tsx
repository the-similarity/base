"use client";

/**
 * Finance dashboard overview page — /finance/dashboard
 *
 * Aggregates all finance runs into a single screen answering:
 * "how are my backtests doing overall?"
 *
 * Sections:
 * 1. KPI cards row — total runs, avg hit rate, avg trust score, pass rate
 * 2. Recent runs table — last 10 runs with key metrics + navigation
 * 3. Trust score distribution — inline SVG bar chart by trust tier
 *
 * Data source: fetchRuns("finance") from lib/platform-api.ts.
 * All aggregations computed client-side from the full runs list.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchRuns, type Run } from "../../../lib/platform-api";

// ---------------------------------------------------------------------------
// Helpers — shared with finance/page.tsx, duplicated here to keep the page
// self-contained without a shared module refactor.
// ---------------------------------------------------------------------------

/** Truncate a UUID to the first 8 chars for display. */
function truncateId(id: string): string {
  return id.slice(0, 8);
}

/** Format ISO timestamp to a readable local date/time. */
function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", {
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

/** Safely extract a nested value from run config/summary. */
function dig(obj: Record<string, unknown>, ...keys: string[]): unknown {
  let cur: unknown = obj;
  for (const k of keys) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[k];
  }
  return cur;
}

/** Format a number to fixed decimals, or "-" if missing. */
function fmt(val: unknown, decimals = 3): string {
  if (val == null) return "-";
  const n = Number(val);
  if (Number.isNaN(n)) return "-";
  return n.toFixed(decimals);
}

// ---------------------------------------------------------------------------
// KPI computation — derives aggregate metrics from the full runs list.
// All averages skip runs where the relevant metric is missing/NaN.
// ---------------------------------------------------------------------------

interface KpiData {
  totalRuns: number;
  avgHitRate: string;
  avgTrustScore: string;
  passRate: string;
}

function computeKpis(runs: Run[]): KpiData {
  const total = runs.length;

  // Collect valid hit rates from run summaries.
  const hitRates = runs
    .map((r) => Number(dig(r.summary, "hit_rate")))
    .filter((n) => !Number.isNaN(n));
  const avgHR =
    hitRates.length > 0
      ? (hitRates.reduce((a, b) => a + b, 0) / hitRates.length).toFixed(3)
      : "-";

  // Collect valid trust scores from run summaries.
  const trustScores = runs
    .map((r) => Number(dig(r.summary, "trust_score")))
    .filter((n) => !Number.isNaN(n));
  const avgTS =
    trustScores.length > 0
      ? (trustScores.reduce((a, b) => a + b, 0) / trustScores.length).toFixed(3)
      : "-";

  // Pass rate: % of runs where trust_decision === "TRUSTED".
  // Falls back to trust_score >= 0.7 if trust_decision is absent.
  const passCount = runs.filter((r) => {
    const decision = dig(r.summary, "trust_decision");
    if (decision != null) return String(decision).toUpperCase() === "TRUSTED";
    const score = Number(dig(r.summary, "trust_score"));
    return !Number.isNaN(score) && score >= 0.7;
  }).length;
  const passRateStr = total > 0 ? `${((passCount / total) * 100).toFixed(1)}%` : "-";

  return {
    totalRuns: total,
    avgHitRate: avgHR,
    avgTrustScore: avgTS,
    passRate: passRateStr,
  };
}

// ---------------------------------------------------------------------------
// Trust tier distribution — buckets runs into green/amber/red tiers.
// Green: trust_score >= 0.7
// Amber: trust_score >= 0.5 and < 0.7
// Red: trust_score < 0.5
// Missing: trust_score is absent or NaN
// ---------------------------------------------------------------------------

interface TrustDistribution {
  green: number;
  amber: number;
  red: number;
  missing: number;
}

function computeTrustDistribution(runs: Run[]): TrustDistribution {
  let green = 0;
  let amber = 0;
  let red = 0;
  let missing = 0;

  for (const r of runs) {
    const raw = dig(r.summary, "trust_score");
    const n = Number(raw);
    if (raw == null || Number.isNaN(n)) {
      missing++;
    } else if (n >= 0.7) {
      green++;
    } else if (n >= 0.5) {
      amber++;
    } else {
      red++;
    }
  }

  return { green, amber, red, missing };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Single KPI card with label, value, and optional subtitle. */
function KpiCard({
  label,
  value,
  subtitle,
}: {
  label: string;
  value: string | number;
  subtitle?: string;
}) {
  return (
    <div
      style={{
        flex: "1 1 0",
        minWidth: 160,
        background: "var(--bg-card)",
        border: "1px solid var(--rule)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--s-5) var(--s-6)",
        transition: "border-color 0.15s",
      }}
      onMouseEnter={(e) =>
        (e.currentTarget.style.borderColor = "var(--rule-strong)")
      }
      onMouseLeave={(e) =>
        (e.currentTarget.style.borderColor = "var(--rule)")
      }
    >
      <div
        style={{
          fontFamily: "var(--sans)",
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--ink-3)",
          marginBottom: "var(--s-2)",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 26,
          fontWeight: 700,
          color: "var(--ink)",
          lineHeight: 1.2,
        }}
      >
        {value}
      </div>
      {subtitle && (
        <div
          style={{
            fontFamily: "var(--sans)",
            fontSize: 11,
            color: "var(--ink-4)",
            marginTop: "var(--s-1)",
          }}
        >
          {subtitle}
        </div>
      )}
    </div>
  );
}

/** Colored dot indicating trust level: green >= 0.7, amber >= 0.5, red < 0.5. */
function TrustDot({ score }: { score: unknown }) {
  if (score == null) return null;
  const n = Number(score);
  if (Number.isNaN(n)) return null;
  const color =
    n >= 0.7 ? "var(--positive)" : n >= 0.5 ? "#8a6200" : "var(--negative)";
  return (
    <span
      style={{
        display: "inline-block",
        width: 7,
        height: 7,
        borderRadius: "50%",
        background: color,
        marginRight: 6,
        verticalAlign: "middle",
      }}
    />
  );
}

/** Status pill showing run lifecycle state. */
function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    complete: "var(--positive)",
    running: "var(--accent)",
    pending: "var(--ink-4)",
    failed: "var(--negative)",
  };
  const color = colorMap[status] ?? "var(--ink-4)";
  return (
    <span
      style={{
        fontFamily: "var(--mono)",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        padding: "3px 8px",
        borderRadius: 999,
        border: `1px solid ${color}`,
        color,
      }}
    >
      {status}
    </span>
  );
}

/** Inline SVG horizontal bar for trust distribution visualization. */
function TrustDistributionChart({ dist }: { dist: TrustDistribution }) {
  const total = dist.green + dist.amber + dist.red + dist.missing;
  if (total === 0) return null;

  // Compute widths as percentages of total.
  const barData = [
    { label: "Trusted", count: dist.green, color: "var(--positive)", pct: (dist.green / total) * 100 },
    { label: "Marginal", count: dist.amber, color: "var(--warn)", pct: (dist.amber / total) * 100 },
    { label: "Untrusted", count: dist.red, color: "var(--negative)", pct: (dist.red / total) * 100 },
    { label: "No score", count: dist.missing, color: "var(--ink-4)", pct: (dist.missing / total) * 100 },
  ].filter((d) => d.count > 0);

  return (
    <div>
      {/* Stacked horizontal bar */}
      <div
        style={{
          display: "flex",
          height: 28,
          borderRadius: "var(--radius-md)",
          overflow: "hidden",
          border: "1px solid var(--rule)",
          marginBottom: "var(--s-4)",
        }}
      >
        {barData.map((d) => (
          <div
            key={d.label}
            title={`${d.label}: ${d.count} (${d.pct.toFixed(1)}%)`}
            style={{
              width: `${d.pct}%`,
              minWidth: d.pct > 0 ? 2 : 0,
              background: d.color,
              opacity: 0.75,
              transition: "opacity 0.15s",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
            onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.75")}
          />
        ))}
      </div>
      {/* Legend */}
      <div style={{ display: "flex", gap: "var(--s-6)", flexWrap: "wrap" }}>
        {barData.map((d) => (
          <div
            key={d.label}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--s-2)",
              fontFamily: "var(--sans)",
              fontSize: 11,
              color: "var(--ink-3)",
            }}
          >
            <span
              style={{
                display: "inline-block",
                width: 10,
                height: 10,
                borderRadius: 2,
                background: d.color,
                opacity: 0.75,
              }}
            />
            {d.label}: {d.count}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Navigation tabs shared between finance list and dashboard. */
function FinanceTabs({ active }: { active: "runs" | "dashboard" }) {
  const tabs = [
    { key: "runs" as const, label: "Runs", href: "/finance" },
    { key: "dashboard" as const, label: "Dashboard", href: "/finance/dashboard" },
  ];
  return (
    <div
      style={{
        display: "flex",
        gap: "var(--s-1)",
        marginBottom: "var(--s-7)",
        borderBottom: "1px solid var(--rule)",
      }}
    >
      {tabs.map((tab) => (
        <Link
          key={tab.key}
          href={tab.href}
          style={{
            fontFamily: "var(--sans)",
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: "0.04em",
            textTransform: "uppercase",
            textDecoration: "none",
            padding: "var(--s-3) var(--s-5)",
            borderBottom:
              active === tab.key
                ? "2px solid var(--ink)"
                : "2px solid transparent",
            color: active === tab.key ? "var(--ink)" : "var(--ink-3)",
            transition: "color 0.15s, border-color 0.15s",
            marginBottom: -1,
          }}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export default function FinanceDashboardPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    Promise.resolve()
      .then(() => {
        setLoading(true);
        setError(null);
        return fetchRuns("finance");
      })
      .then((data) => {
        // Sort newest first by created_at.
        data.sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        setRuns(data);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : String(err))
      )
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const kpis = computeKpis(runs);
  const trustDist = computeTrustDistribution(runs);
  const recentRuns = runs.slice(0, 10);

  return (
    <div
      style={{
        maxWidth: 960,
        margin: "0 auto",
        padding: "var(--s-8) var(--s-6)",
      }}
    >
      {/* Breadcrumb */}
      <p
        style={{
          fontFamily: "var(--sans)",
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--ink-3)",
          marginBottom: "var(--s-2)",
        }}
      >
        Platform / Finance
      </p>

      <h1
        style={{
          fontFamily: "var(--serif)",
          fontSize: 28,
          fontWeight: 400,
          color: "var(--ink)",
          margin: "0 0 var(--s-2) 0",
        }}
      >
        Dashboard
      </h1>

      <p
        style={{
          fontFamily: "var(--sans)",
          fontSize: 13,
          color: "var(--ink-3)",
          marginBottom: "var(--s-5)",
          lineHeight: 1.5,
        }}
      >
        Aggregate health of your finance backtests at a glance.
      </p>

      {/* Tabs */}
      <FinanceTabs active="dashboard" />

      {/* Loading */}
      {loading && (
        <div
          style={{
            padding: "var(--s-9)",
            textAlign: "center",
            fontFamily: "var(--sans)",
            color: "var(--ink-3)",
          }}
        >
          Loading finance runs...
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div
          style={{
            padding: "var(--s-8)",
            textAlign: "center",
            border: "1px solid var(--negative)",
            borderRadius: "var(--radius-lg)",
            background: "var(--negative-soft)",
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 22,
              fontWeight: 700,
              color: "var(--negative)",
              marginBottom: "var(--s-3)",
            }}
          >
            !
          </div>
          <p
            style={{
              fontFamily: "var(--sans)",
              fontSize: 13,
              color: "var(--ink-2)",
              marginBottom: "var(--s-4)",
            }}
          >
            {error}
          </p>
          <button
            onClick={load}
            style={{
              fontFamily: "var(--mono)",
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              padding: "var(--s-2) var(--s-5)",
              border: "1px solid var(--negative)",
              borderRadius: "var(--radius-md)",
              background: "transparent",
              color: "var(--negative)",
              cursor: "pointer",
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && runs.length === 0 && (
        <div
          style={{
            padding: "var(--s-9) var(--s-8)",
            textAlign: "center",
            border: "1px solid var(--rule)",
            borderRadius: "var(--radius-lg)",
            background: "var(--bg-card)",
          }}
        >
          <div
            style={{
              fontFamily: "var(--serif)",
              fontSize: 18,
              color: "var(--ink-2)",
              marginBottom: "var(--s-4)",
            }}
          >
            No finance runs yet
          </div>
          <p
            style={{
              fontFamily: "var(--sans)",
              fontSize: 13,
              color: "var(--ink-3)",
              lineHeight: 1.6,
              maxWidth: 480,
              margin: "0 auto",
            }}
          >
            Run a backtest via the API or CLI to populate this dashboard.
            <br />
            <code
              style={{
                fontFamily: "var(--mono)",
                fontSize: 12,
                background: "var(--bg-inset)",
                padding: "2px 6px",
                borderRadius: "var(--radius-sm)",
              }}
            >
              python -m the_similarity backtest --symbol AAPL --register
            </code>
          </p>
        </div>
      )}

      {/* Dashboard content — only rendered when we have runs */}
      {!loading && !error && runs.length > 0 && (
        <>
          {/* ── KPI Cards Row ──────────────────────────────────── */}
          <div
            style={{
              display: "flex",
              gap: "var(--s-4)",
              marginBottom: "var(--s-8)",
              flexWrap: "wrap",
            }}
          >
            <KpiCard
              label="Total Runs"
              value={kpis.totalRuns}
              subtitle="finance backtests"
            />
            <KpiCard
              label="Avg Hit Rate"
              value={kpis.avgHitRate}
              subtitle="across all runs"
            />
            <KpiCard
              label="Avg Trust Score"
              value={kpis.avgTrustScore}
              subtitle="confidence metric"
            />
            <KpiCard
              label="Pass Rate"
              value={kpis.passRate}
              subtitle="trusted decisions"
            />
          </div>

          {/* ── Trust Score Distribution ────────────────────────── */}
          <div
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--rule)",
              borderRadius: "var(--radius-lg)",
              padding: "var(--s-5) var(--s-6)",
              marginBottom: "var(--s-8)",
            }}
          >
            <h2
              style={{
                fontFamily: "var(--sans)",
                fontSize: 12,
                fontWeight: 600,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--ink-3)",
                margin: "0 0 var(--s-4) 0",
              }}
            >
              Trust Score Distribution
            </h2>
            <TrustDistributionChart dist={trustDist} />
          </div>

          {/* ── Recent Runs Table ──────────────────────────────── */}
          <div
            style={{
              background: "var(--bg-card)",
              border: "1px solid var(--rule)",
              borderRadius: "var(--radius-lg)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "var(--s-5) var(--s-6) var(--s-3)",
                borderBottom: "1px solid var(--rule)",
              }}
            >
              <h2
                style={{
                  fontFamily: "var(--sans)",
                  fontSize: 12,
                  fontWeight: 600,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  color: "var(--ink-3)",
                  margin: 0,
                }}
              >
                Recent Runs
              </h2>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontFamily: "var(--sans)",
                  fontSize: 13,
                }}
              >
                <thead>
                  <tr>
                    {["Run ID", "Symbol", "Hit Rate", "Trust", "Status", "Date"].map(
                      (header) => (
                        <th
                          key={header}
                          style={{
                            fontFamily: "var(--sans)",
                            fontSize: 10,
                            fontWeight: 700,
                            letterSpacing: "0.08em",
                            textTransform: "uppercase",
                            color: "var(--ink-4)",
                            textAlign:
                              header === "Hit Rate" || header === "Trust"
                                ? "right"
                                : "left",
                            padding: "var(--s-3) var(--s-4)",
                            borderBottom: "1px solid var(--rule)",
                          }}
                        >
                          {header}
                        </th>
                      )
                    )}
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.map((run) => {
                    const symbol =
                      dig(run.config, "symbol") ??
                      dig(run.config, "ticker") ??
                      "-";
                    const hitRate = dig(run.summary, "hit_rate");
                    const trustScore = dig(run.summary, "trust_score");

                    return (
                      <tr
                        key={run.run_id}
                        style={{
                          cursor: "pointer",
                          transition: "background 0.1s",
                        }}
                        onMouseEnter={(e) =>
                          (e.currentTarget.style.background = "var(--bg-hover)")
                        }
                        onMouseLeave={(e) =>
                          (e.currentTarget.style.background = "transparent")
                        }
                      >
                        <td
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 12,
                            padding: "var(--s-3) var(--s-4)",
                            borderBottom: "1px solid var(--rule)",
                          }}
                        >
                          <Link
                            href={`/finance/${run.run_id}`}
                            style={{
                              color: "inherit",
                              textDecoration: "none",
                              borderBottom: "1px dotted var(--rule-strong)",
                            }}
                          >
                            {truncateId(run.run_id)}
                          </Link>
                        </td>
                        <td
                          style={{
                            fontWeight: 600,
                            padding: "var(--s-3) var(--s-4)",
                            borderBottom: "1px solid var(--rule)",
                          }}
                        >
                          {String(symbol)}
                        </td>
                        <td
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 12,
                            textAlign: "right",
                            padding: "var(--s-3) var(--s-4)",
                            borderBottom: "1px solid var(--rule)",
                          }}
                        >
                          {fmt(hitRate)}
                        </td>
                        <td
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 12,
                            textAlign: "right",
                            padding: "var(--s-3) var(--s-4)",
                            borderBottom: "1px solid var(--rule)",
                          }}
                        >
                          <TrustDot score={trustScore} />
                          {fmt(trustScore)}
                        </td>
                        <td
                          style={{
                            padding: "var(--s-3) var(--s-4)",
                            borderBottom: "1px solid var(--rule)",
                          }}
                        >
                          <StatusBadge status={run.status} />
                        </td>
                        <td
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 12,
                            color: "var(--ink-3)",
                            padding: "var(--s-3) var(--s-4)",
                            borderBottom: "1px solid var(--rule)",
                          }}
                        >
                          {formatDate(run.created_at)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {/* Link to full runs list if there are more than 10 */}
            {runs.length > 10 && (
              <div
                style={{
                  padding: "var(--s-3) var(--s-6)",
                  borderTop: "1px solid var(--rule)",
                  textAlign: "center",
                }}
              >
                <Link
                  href="/finance"
                  style={{
                    fontFamily: "var(--sans)",
                    fontSize: 12,
                    fontWeight: 600,
                    color: "var(--ink-3)",
                    textDecoration: "none",
                  }}
                >
                  View all {runs.length} runs
                </Link>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
