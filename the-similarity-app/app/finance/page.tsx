"use client";

/**
 * Finance runs list page — /finance
 *
 * Fetches GET /platform/runs?kind=finance and renders a sortable table
 * of backtest runs. Each row links to the detail page at /finance/[runId].
 *
 * Handles:
 * - Loading skeleton while fetching
 * - Empty state when no runs exist yet
 * - Error state with retry
 * - Sort by created_at (newest first, default)
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchRuns, type Run } from "../../lib/platform-api";

// ---------------------------------------------------------------------------
// Navigation tabs — shared visual between list and dashboard pages.
// ---------------------------------------------------------------------------

/** Tab bar linking between /finance (runs list) and /finance/dashboard. */
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
// Helpers
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
// Component
// ---------------------------------------------------------------------------

export default function FinanceRunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /** Selected run IDs for comparison (checkbox). */
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const load = () => {
    // Reset loading/error state inside a microtask so callers from both
    // event handlers (onClick) and useEffect satisfy react-hooks/set-state-in-effect.
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
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const compareUrl =
    selected.size >= 2
      ? `/finance/compare?ids=${Array.from(selected).slice(0, 2).join(",")}`
      : null;

  return (
    <div className="deck-page">
      <div className="deck-page__inner">
        {/* Header */}
        <p className="deck-page__label">Platform / Finance</p>
        <h1 className="deck-page__title">Finance Runs</h1>
        <p className="deck-page__intro">
          Backtest runs from the finance adapter. Click a row to inspect
          metrics, scorecards, and trust decisions.
        </p>

        {/* Tabs — navigate between Runs list and Dashboard */}
        <FinanceTabs active="runs" />

        {/* Compare action */}
        {compareUrl && (
          <div style={{ marginBottom: 24 }}>
            <Link
              href={compareUrl}
              className="search-sidebar__run-btn"
              style={{
                display: "inline-block",
                width: "auto",
                padding: "8px 20px",
                textDecoration: "none",
              }}
            >
              Compare {selected.size} runs
            </Link>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="deck-feed-empty">Loading finance runs...</div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="match-list-error" style={{ padding: 40 }}>
            <div className="match-list-error__icon">!</div>
            <p className="match-list-error__text">{error}</p>
            <button className="match-list-error__retry" onClick={load}>
              Retry
            </button>
          </div>
        )}

        {/* Empty */}
        {!loading && !error && runs.length === 0 && (
          <div className="deck-feed-empty">
            No finance runs yet. Run a backtest with the finance adapter to see
            results here.
          </div>
        )}

        {/* Table */}
        {!loading && !error && runs.length > 0 && (
          <div className="portfolio-table-wrap">
            <table className="portfolio-table">
              <thead>
                <tr>
                  <th className="portfolio-table__th" style={{ width: 40 }}></th>
                  <th className="portfolio-table__th">Run ID</th>
                  <th className="portfolio-table__th">Date</th>
                  <th className="portfolio-table__th">Symbol</th>
                  <th className="portfolio-table__th portfolio-table__th--right">
                    Hit Rate
                  </th>
                  <th className="portfolio-table__th portfolio-table__th--right">
                    Trust
                  </th>
                  <th className="portfolio-table__th">Cal. Grade</th>
                  <th className="portfolio-table__th">Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const symbol =
                    dig(run.config, "symbol") ?? dig(run.config, "ticker") ?? "-";
                  const hitRate = dig(run.summary, "hit_rate");
                  const trustScore = dig(run.summary, "trust_score");
                  const calGrade = dig(run.summary, "calibration_grade");
                  const isSelected = selected.has(run.run_id);

                  return (
                    <tr
                      key={run.run_id}
                      className="portfolio-table__row"
                      style={{ cursor: "pointer" }}
                    >
                      {/* Checkbox cell */}
                      <td
                        className="portfolio-table__td"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(run.run_id)}
                          aria-label={`Select run ${truncateId(run.run_id)}`}
                        />
                      </td>
                      {/* Run ID — clickable link */}
                      <td className="portfolio-table__td portfolio-table__td--mono">
                        <Link
                          href={`/finance/${run.run_id}`}
                          style={{
                            color: "inherit",
                            textDecoration: "none",
                            borderBottom: "1px dotted var(--border-strong)",
                          }}
                        >
                          {truncateId(run.run_id)}
                        </Link>
                      </td>
                      <td className="portfolio-table__td portfolio-table__td--mono">
                        {formatDate(run.created_at)}
                      </td>
                      <td className="portfolio-table__td" style={{ fontWeight: 600 }}>
                        {String(symbol)}
                      </td>
                      <td className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right">
                        {fmt(hitRate)}
                      </td>
                      <td className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right">
                        <TrustDot score={trustScore} />
                        {fmt(trustScore)}
                      </td>
                      <td className="portfolio-table__td portfolio-table__td--mono">
                        {calGrade != null ? String(calGrade) : "-"}
                      </td>
                      <td className="portfolio-table__td">
                        <StatusBadge status={run.status} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Colored dot indicating trust level: green >= 0.7, yellow >= 0.5, red < 0.5. */
function TrustDot({ score }: { score: unknown }) {
  if (score == null) return null;
  const n = Number(score);
  if (Number.isNaN(n)) return null;
  const color = n >= 0.7 ? "var(--positive)" : n >= 0.5 ? "#8a6200" : "var(--negative)";
  return (
    <span
      className="status-dot"
      style={{ background: color, marginRight: 6, verticalAlign: "middle" }}
    />
  );
}

/** Status pill showing run lifecycle state. */
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
