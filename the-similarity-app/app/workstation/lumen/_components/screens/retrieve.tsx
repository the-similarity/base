/**
 * Retrieve — the headline workstation screen for /workstation/lumen.
 *
 * Purpose: explain what The Similarity does, surface the most recent
 * finance runs at a glance, and route the user into the canonical
 * workstation route (`/workstation`) for actually running a query.
 *
 * Data lifecycle:
 *   - On mount, fetch the last N finance runs from the platform API.
 *   - While the request is in flight, show "—" placeholders in the
 *     Recent runs KPI / list.
 *   - On error, log to console + render a soft empty state. We do not
 *     surface raw error strings on this hero screen — the dedicated
 *     /finance routes handle deep error reporting.
 *
 * Hardcoded values (callout for future work):
 *   - "Datasets" KPI value is the literal `12`. The real registry-based
 *     count would require a /platform/datasets aggregate endpoint.
 *   - "Methods" KPI value is the literal `9`. Matches the engine config
 *     and is unlikely to drift, but a future refactor could pull this
 *     from `the_similarity/config.py`.
 *   - "1.13M+ rows" mirrors the project's headline number from
 *     CLAUDE.md → daily refresh; not yet wired to a data API.
 */
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Topbar } from "../shared";
import { Icon } from "../icons";
import { fetchRuns, type Run } from "../../../../../lib/platform-api";
import type { ScreenProps } from "../screen-types";

// =====================================================================
// Helpers — kept local because they're only used on this screen.
// =====================================================================

/**
 * Truncate a run_id to its first 8 characters with a dotted underline
 * — short enough for tabular layout, but the full id is surfaced as a
 * native title tooltip on hover.
 */
function shortRunId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id;
}

/**
 * Read a string-ish value out of the run summary, falling back to
 * "—" if the key is missing or the value isn't a primitive. Defensive
 * because the registry's `summary` is typed as `Record<string, unknown>`
 * and the real shape varies per backtest config.
 */
function readSummary(run: Run, key: string): string {
  const v = run.summary?.[key];
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    // Hit-rate / calibration numbers come through as 0..1 floats; show
    // them as percentages when they look like rates.
    if (key === "hit_rate" || key === "trust_score") {
      return (v * 100).toFixed(1) + "%";
    }
    return String(v);
  }
  if (typeof v === "string") return v;
  return "—";
}

/**
 * Map a run status to a Lumen status pill modifier class.
 * `is-complete | is-running | is-failed | is-pending` are styled in
 * styles.tsx. Unknown statuses fall back to is-pending.
 */
function statusClass(status: string): string {
  switch (status) {
    case "complete":
    case "succeeded":
    case "completed":
      return "is-complete";
    case "running":
      return "is-running";
    case "failed":
    case "errored":
      return "is-failed";
    default:
      return "is-pending";
  }
}

// =====================================================================
// Screen
// =====================================================================

export function ScreenRetrieve({ onCmdK }: ScreenProps) {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchRuns("finance")
      .then((r) => {
        if (!cancelled) setRuns(r);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        // Don't surface raw error to the user on the hero screen —
        // log + soft-fail. The full /finance app handles error UX.
        // eslint-disable-next-line no-console
        console.warn("Lumen retrieve: fetchRuns(finance) failed", e);
        setLoadError(String(e));
        setRuns([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Recent-runs KPI value: number, "—" while loading.
  const runsKpiValue =
    runs === null ? "—" : runs.length.toLocaleString("en-US");

  // Last calibration: pull the most recent run's calibration_grade or
  // fall back to "—" while loading / when no runs exist.
  const lastCalibration =
    runs && runs.length > 0 ? readSummary(runs[0], "calibration_grade") : "—";

  // Top 5 rows for the Recent runs card. Already newest-first per
  // platform API contract.
  const top5 = runs?.slice(0, 5) ?? [];

  return (
    <div className="lumen-content-col lumen-screen-fade">
      <Topbar
        crumbs={["Workspace", "Retrieve"]}
        onCmdK={onCmdK}
        actions={
          <Link href="/workstation" className="lumen-btn is-primary">
            <Icon name="link" /> Open workstation
          </Link>
        }
      />
      <div className="lumen-scroll">
        <div className="lumen-scroll-pad">
          {/* Hero */}
          <div className="lumen-mb-24">
            <div className="lumen-eyebrow lumen-mb-12">
              Retrieve · what rhymes?
            </div>
            <div
              className="lumen-display"
              style={{ fontSize: 56, marginBottom: 14 }}
            >
              1.13M+ rows
            </div>
            <div
              className="lumen-text-2"
              style={{ fontSize: 16, maxWidth: 640, lineHeight: 1.5 }}
            >
              Find structural analogs in time-series — past patterns
              that match the present.
            </div>
          </div>

          {/* KPI grid */}
          <div className="lumen-kpi-grid lumen-mb-24">
            <div className="lumen-kpi">
              <div className="lumen-label">Datasets</div>
              <div className="lumen-value">12</div>
              <div className="lumen-delta">1.13M+ rows · daily refresh</div>
            </div>
            <div className="lumen-kpi">
              <div className="lumen-label">Methods</div>
              <div className="lumen-value">9</div>
              <div
                className="lumen-delta"
                title="DTW · Bempedelis · Koopman · SAX · Matrix Profile · Wavelet · TDA · EMD · Transfer Entropy"
                style={{
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                DTW · Bempedelis · Koopman · SAX · Matrix Profile ·
                Wavelet · TDA · EMD · Transfer Entropy
              </div>
            </div>
            <div className="lumen-kpi">
              <div className="lumen-label">Recent runs</div>
              <div className="lumen-value">{runsKpiValue}</div>
              <div className="lumen-delta">finance pillar</div>
            </div>
            <div className="lumen-kpi">
              <div className="lumen-label">Last calibration</div>
              <div className="lumen-value">{lastCalibration}</div>
              <div className="lumen-delta">most recent run</div>
            </div>
          </div>

          {/* Recent runs card */}
          <div className="lumen-card lumen-mb-24">
            <div
              className="lumen-section-head"
              style={{ padding: "14px 16px 8px 16px" }}
            >
              <div className="lumen-title">Recent runs</div>
              <div className="lumen-sub">
                Latest finance backtests in the registry.
              </div>
              <div className="lumen-actions">
                <Link href="/finance" className="lumen-btn is-ghost">
                  View all
                </Link>
              </div>
            </div>
            {/* Header row */}
            <div
              className="lumen-tx-row is-head"
              style={{
                gridTemplateColumns: "120px 1fr 110px 90px 90px 90px",
              }}
            >
              <div>Run</div>
              <div>Symbol</div>
              <div>Date</div>
              <div>Hit rate</div>
              <div>Grade</div>
              <div>Status</div>
            </div>
            {/* Loading / empty / data states */}
            {runs === null && (
              <div
                className="lumen-text-3"
                style={{ padding: 22, textAlign: "center", fontSize: 13 }}
              >
                Loading runs…
              </div>
            )}
            {runs !== null && top5.length === 0 && (
              <div
                className="lumen-text-3"
                style={{ padding: 22, textAlign: "center", fontSize: 13 }}
              >
                {loadError
                  ? "Run registry unavailable. Open the workstation to register a run."
                  : "No finance runs registered yet."}
              </div>
            )}
            {top5.map((r) => {
              const dateStr = (() => {
                try {
                  return new Date(r.created_at)
                    .toISOString()
                    .slice(0, 10);
                } catch {
                  return "—";
                }
              })();
              const symbol = readSummary(r, "symbol");
              const hitRate = readSummary(r, "hit_rate");
              const grade = readSummary(r, "calibration_grade");
              return (
                <Link
                  key={r.run_id}
                  href={`/finance/${r.run_id}`}
                  className="lumen-tx-row"
                  style={{
                    gridTemplateColumns: "120px 1fr 110px 90px 90px 90px",
                    textDecoration: "none",
                    color: "inherit",
                  }}
                  title={r.run_id}
                >
                  <div
                    className="lumen-mono"
                    style={{
                      borderBottom: "1px dotted var(--ink-4)",
                      width: "fit-content",
                    }}
                  >
                    {shortRunId(r.run_id)}
                  </div>
                  <div>{symbol}</div>
                  <div className="lumen-text-3 lumen-mono">{dateStr}</div>
                  <div className="lumen-num">{hitRate}</div>
                  <div className="lumen-num">{grade}</div>
                  <div>
                    <span className={`lumen-status ${statusClass(r.status)}`}>
                      {r.status || "pending"}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>

          {/* Insight bubble */}
          <div className="lumen-ai-bubble">
            <div className="lumen-ai-head">
              <span className="lumen-pulse" /> Insight
            </div>
            <div>
              The Similarity finds structural analogs across 1.13M+
              rows of market data using 9 complementary methods — DTW,
              Koopman, Bempedelis, SAX/MASS, Matrix Profile, Wavelet
              Leaders, TDA, EMD, and Transfer Entropy. Open the
              workstation to run a query.
            </div>
            <div
              className="lumen-row lumen-gap-8 lumen-mt-12"
              style={{ flexWrap: "wrap" }}
            >
              <Link href="/workstation" className="lumen-btn is-primary">
                <Icon name="link" /> Open workstation
              </Link>
              <Link href="/finance" className="lumen-btn">
                View runs
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
