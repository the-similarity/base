"use client";

/**
 * Finance run comparison page — /finance/compare?ids=abc,def
 *
 * Fetches two runs by ID and displays a side-by-side comparison table.
 * Better metric highlighted green, worse red. Simple two-column layout.
 */

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { fetchRun, type Run } from "../../../lib/platform-api";

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

/** Metric definitions for the comparison table. */
interface MetricDef {
  label: string;
  /** Path into run.summary to extract the value. */
  path: string[];
  /** How to format the value. */
  format: (v: unknown) => string;
  /** "higher" = higher is better, "lower" = lower is better, "none" = no color. */
  direction: "higher" | "lower" | "none";
}

const METRICS: MetricDef[] = [
  { label: "Hit Rate", path: ["hit_rate"], format: pct, direction: "higher" },
  { label: "CRPS", path: ["crps"], format: (v) => fmt(v, 4), direction: "lower" },
  { label: "Coverage", path: ["coverage"], format: pct, direction: "higher" },
  { label: "Profit Factor", path: ["profit_factor"], format: (v) => fmt(v, 2), direction: "higher" },
  { label: "Max Drawdown", path: ["max_drawdown"], format: pct, direction: "higher" },
  { label: "Sharpe Ratio", path: ["sharpe_ratio"], format: (v) => fmt(v, 2), direction: "higher" },
  { label: "Trust Score", path: ["trust_score"], format: (v) => fmt(v, 3), direction: "higher" },
  { label: "Calibration Grade", path: ["calibration_grade"], format: (v) => (v != null ? String(v) : "-"), direction: "none" },
];

// ---------------------------------------------------------------------------
// Inner component (needs useSearchParams, must be wrapped in Suspense)
// ---------------------------------------------------------------------------

function CompareInner() {
  const searchParams = useSearchParams();
  const idsParam = searchParams.get("ids") ?? "";
  const ids = idsParam
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 2);

  const [runs, setRuns] = useState<(Run | null)[]>([null, null]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ids.length < 2) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all(ids.map((id) => fetchRun(id)))
      .then((results) => setRuns(results))
      .catch((err) =>
        setError(err instanceof Error ? err.message : String(err))
      )
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsParam]);

  if (ids.length < 2) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <p className="deck-page__label">
            <Link href="/finance" style={{ color: "inherit", textDecoration: "none" }}>
              Finance
            </Link>{" "}
            / Compare
          </p>
          <h1 className="deck-page__title">Compare Runs</h1>
          <div className="deck-feed-empty" style={{ marginTop: 32 }}>
            Select two runs from the{" "}
            <Link href="/finance" style={{ color: "var(--accent)" }}>
              finance runs list
            </Link>{" "}
            to compare.
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <div className="deck-feed-empty">Loading comparison...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <div className="match-list-error" style={{ padding: 40 }}>
            <div className="match-list-error__icon">!</div>
            <p className="match-list-error__text">{error}</p>
            <Link href="/finance" className="match-list-error__retry">
              Back to runs
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const [runA, runB] = runs;
  if (!runA || !runB) {
    return (
      <div className="deck-page">
        <div className="deck-page__inner">
          <div className="deck-feed-empty">One or both runs could not be loaded.</div>
        </div>
      </div>
    );
  }

  const symbolA = dig(runA.config, "symbol") ?? dig(runA.config, "ticker") ?? "-";
  const symbolB = dig(runB.config, "symbol") ?? dig(runB.config, "ticker") ?? "-";

  return (
    <div className="deck-page">
      <div className="deck-page__inner">
        <p className="deck-page__label">
          <Link href="/finance" style={{ color: "inherit", textDecoration: "none" }}>
            Finance
          </Link>{" "}
          / Compare
        </p>
        <h1 className="deck-page__title">
          {String(symbolA)} vs {String(symbolB)}
        </h1>
        <p className="deck-page__intro">
          Side-by-side comparison. Better metric highlighted in green, worse in red.
        </p>

        <div className="portfolio-table-wrap">
          <table className="portfolio-table">
            <thead>
              <tr>
                <th className="portfolio-table__th" style={{ width: "30%" }}>
                  Metric
                </th>
                <th className="portfolio-table__th portfolio-table__th--right">
                  <Link
                    href={`/finance/${runA.run_id}`}
                    style={{ color: "inherit", textDecoration: "none", borderBottom: "1px dotted var(--border-strong)" }}
                  >
                    {runA.run_id.slice(0, 8)}
                  </Link>
                  <br />
                  <span style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 500 }}>
                    {String(symbolA)}
                  </span>
                </th>
                <th className="portfolio-table__th portfolio-table__th--right">
                  <Link
                    href={`/finance/${runB.run_id}`}
                    style={{ color: "inherit", textDecoration: "none", borderBottom: "1px dotted var(--border-strong)" }}
                  >
                    {runB.run_id.slice(0, 8)}
                  </Link>
                  <br />
                  <span style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 500 }}>
                    {String(symbolB)}
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {METRICS.map((m) => {
                const valA = dig(runA.summary, ...m.path);
                const valB = dig(runB.summary, ...m.path);
                const nA = Number(valA);
                const nB = Number(valB);
                const canCompare =
                  m.direction !== "none" &&
                  !Number.isNaN(nA) &&
                  !Number.isNaN(nB) &&
                  nA !== nB;

                let colorA = "inherit";
                let colorB = "inherit";

                if (canCompare) {
                  const aWins =
                    m.direction === "higher" ? nA > nB : nA < nB;
                  colorA = aWins ? "var(--positive)" : "var(--negative)";
                  colorB = aWins ? "var(--negative)" : "var(--positive)";
                }

                return (
                  <tr key={m.label} className="portfolio-table__row">
                    <td className="portfolio-table__td" style={{ fontWeight: 600 }}>
                      {m.label}
                    </td>
                    <td
                      className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right"
                      style={{ color: colorA, fontWeight: canCompare ? 700 : 400 }}
                    >
                      {m.format(valA)}
                    </td>
                    <td
                      className="portfolio-table__td portfolio-table__td--mono portfolio-table__td--right"
                      style={{ color: colorB, fontWeight: canCompare ? 700 : 400 }}
                    >
                      {m.format(valB)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

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
// Page component — Suspense boundary required for useSearchParams
// ---------------------------------------------------------------------------

export default function FinanceComparePage() {
  return (
    <Suspense
      fallback={
        <div className="deck-page">
          <div className="deck-page__inner">
            <div className="deck-feed-empty">Loading comparison...</div>
          </div>
        </div>
      }
    >
      <CompareInner />
    </Suspense>
  );
}
