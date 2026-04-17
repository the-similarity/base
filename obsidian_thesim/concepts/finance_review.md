> [!warning] Status: placeholder
> Review workflow is a schema only. No process drives status transitions yet.

# Finance Review Workflow

## What it is

The **review workflow** is the human-in-the-loop checkpoint between a backtest result and an actionable decision. Every registered finance run can have a `ReviewArtifact` attached that captures the review decision, risk flags, and a condensed signal summary.

## Status transitions

```
pending → approved
pending → flagged → approved | rejected
pending → rejected
```

- **pending** — default state after registration. No review has been performed.
- **approved** — the forecast is considered reliable and actionable.
- **flagged** — automated risk flags or a reviewer flagged concerns. Requires human resolution.
- **rejected** — the forecast is unreliable for this regime. Do not act on it.

Status is stored in `ReviewArtifact.status` and surfaced via the review API endpoint.

## Risk flags

Automated checks that run when a review is created:

| Flag | Trigger | Severity |
|------|---------|----------|
| `low_coverage` | P10-P90 coverage < 0.65 | High |
| `poor_calibration` | calibration_grade D or F | High |
| `low_trust` | trust_score < 0.4 | High |
| `few_trials` | n_valid_trials < 10 | Medium |
| `high_crps` | crps > 0.05 | Medium |
| `regime_mismatch` | current regime differs from training regime | Medium |
| `stale_data` | data age > 5 trading days | Low |

When any high-severity flag fires, the review auto-transitions to `flagged` instead of staying `pending`.

## Signal summary

A condensed narrative generated from the search results and forecast:

> "Top 5 analogues span 2008-03, 2011-08, 2015-08, 2018-12, 2020-03 — all post-shock recovery regimes. P50 projects +3.2% over 20 bars. Calibration grade B. Trust 0.72. Risk: regime_mismatch (current regime is low-vol trending, analogues are high-vol recovery)."

The signal summary is stored in `ReviewArtifact.signal_summary` and displayed in the UI's run detail page.

## API endpoints (Agent 2)

```
POST   /platform/runs/{run_id}/review     — create/update review
GET    /platform/runs/{run_id}/review     — get review status + flags
PATCH  /platform/runs/{run_id}/review     — update status (approve/reject)
```

## Code paths

- Review artifact: `the_similarity/finance/review.py` (Agent 2)
- API routes: `the-similarity-api/app/platform_routes.py`
- Platform contracts: `the_similarity/platform/contracts.py`

## Related

- [[trust_artifact]] — trust_score drives the `low_trust` risk flag
- [[calibration_artifact]] — calibration_grade drives the `poor_calibration` flag
- [[finance_benchmark]] — benchmark results feed into review comparisons
