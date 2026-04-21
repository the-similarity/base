"use client";

/**
 * Finance reviews list page — /finance/reviews
 *
 * Fetches GET /platform/reviews and renders a filterable table of all reviews.
 * Each row links to the parent run detail page at /finance/[runId].
 *
 * Features:
 * - Filter by status (pending, approved, flagged, rejected)
 * - Trust decision badges with color coding
 * - Status pills matching the existing design language
 * - Newest-first ordering (server default)
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchReviews, type Review } from "../../../lib/platform-api";

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
    return new Date(iso).toLocaleDateString("en-US", {
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
// Status filter options — matches ReviewStatus enum in finance_routes.py
// ---------------------------------------------------------------------------

const STATUS_OPTIONS = [
  { value: "", label: "All" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "flagged", label: "Flagged" },
  { value: "rejected", label: "Rejected" },
] as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function FinanceReviewsPage() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  const load = (status?: string) => {
    setLoading(true);
    setError(null);

    fetchReviews(status || undefined)
      .then((data) => setReviews(data))
      .catch((err) =>
        setError(err instanceof Error ? err.message : String(err))
      )
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load(statusFilter);
  }, [statusFilter]);

  return (
    <div className="deck-page">
      <div className="deck-page__inner">
        {/* Header */}
        <p className="deck-page__label">
          <Link
            href="/finance"
            style={{ color: "inherit", textDecoration: "none" }}
          >
            Finance
          </Link>{" "}
          / Reviews
        </p>
        <h1 className="deck-page__title">Reviews</h1>
        <p className="deck-page__intro">
          All reviews across finance runs. Filter by status to find reviews
          needing attention.
        </p>

        {/* Status filter */}
        <div style={{ marginBottom: 24, display: "flex", gap: 8 }}>
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setStatusFilter(opt.value)}
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                padding: "5px 14px",
                borderRadius: "var(--radius-pill, 999px)",
                border: `1px solid ${
                  statusFilter === opt.value
                    ? "var(--accent)"
                    : "var(--rule)"
                }`,
                background:
                  statusFilter === opt.value
                    ? "var(--accent-soft)"
                    : "transparent",
                color:
                  statusFilter === opt.value
                    ? "var(--accent)"
                    : "var(--ink-3)",
                cursor: "pointer",
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Loading */}
        {loading && (
          <div className="deck-feed-empty">Loading reviews...</div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="match-list-error" style={{ padding: 40 }}>
            <div className="match-list-error__icon">!</div>
            <p className="match-list-error__text">{error}</p>
            <button
              className="match-list-error__retry"
              onClick={() => load(statusFilter)}
            >
              Retry
            </button>
          </div>
        )}

        {/* Empty */}
        {!loading && !error && reviews.length === 0 && (
          <div className="deck-feed-empty">
            {statusFilter
              ? `No reviews with status "${statusFilter}".`
              : "No reviews yet. Create one from a run detail page."}
          </div>
        )}

        {/* Table */}
        {!loading && !error && reviews.length > 0 && (
          <div className="portfolio-table-wrap">
            <table className="portfolio-table">
              <thead>
                <tr>
                  <th className="portfolio-table__th">Run ID</th>
                  <th className="portfolio-table__th">Reviewer</th>
                  <th className="portfolio-table__th">Trust</th>
                  <th className="portfolio-table__th">Status</th>
                  <th className="portfolio-table__th">Date</th>
                  <th className="portfolio-table__th">Signal</th>
                </tr>
              </thead>
              <tbody>
                {reviews.map((rev) => (
                  <tr key={rev.review_id} className="portfolio-table__row">
                    {/* Run ID — links to run detail */}
                    <td className="portfolio-table__td portfolio-table__td--mono">
                      <Link
                        href={`/finance/${rev.run_id}`}
                        style={{
                          color: "inherit",
                          textDecoration: "none",
                          borderBottom: "1px dotted var(--rule-strong)",
                        }}
                      >
                        {truncateId(rev.run_id)}
                      </Link>
                    </td>

                    {/* Reviewer */}
                    <td className="portfolio-table__td portfolio-table__td--mono">
                      {rev.reviewer}
                    </td>

                    {/* Trust decision */}
                    <td className="portfolio-table__td">
                      <TrustDecisionBadge decision={rev.trust_decision} />
                    </td>

                    {/* Status */}
                    <td className="portfolio-table__td">
                      <ReviewStatusBadge status={rev.status} />
                    </td>

                    {/* Date */}
                    <td className="portfolio-table__td portfolio-table__td--mono">
                      {formatDate(rev.created_at)}
                    </td>

                    {/* Signal summary (truncated) */}
                    <td
                      className="portfolio-table__td"
                      style={{
                        maxWidth: 240,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        color: "var(--ink-3)",
                        fontSize: 12,
                      }}
                    >
                      {rev.signal_summary || "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Back link */}
        <div style={{ marginTop: 24 }}>
          <Link
            href="/finance"
            style={{
              fontFamily: "var(--mono)",
              fontSize: 12,
              color: "var(--ink-3)",
              textDecoration: "none",
              borderBottom: "1px dotted var(--rule-strong)",
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

/** Status pill for review lifecycle: pending, approved, flagged, rejected. */
function ReviewStatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    approved: "var(--positive)",
    pending: "var(--warn, #8a6200)",
    flagged: "var(--negative)",
    rejected: "var(--negative)",
  };
  const color = colorMap[status] ?? "var(--ink-3)";
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
      {status}
    </span>
  );
}
