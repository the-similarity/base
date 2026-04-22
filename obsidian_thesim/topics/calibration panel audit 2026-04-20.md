# Calibration panel audit — 2026-04-20

**Context:** PR #220 added `SearchResponse.metrics: CalibrationMetrics` wired to the trust strip in `the-similarity-app/components/workstation/workstation.tsx`. PR #228 threaded pinning through `effectiveAnalogs`, so metrics reflect pin-filtered analogs. The **expanded calibration panel** (opens via "Open calibration panel →") was flagged as "needs audit" — the task here is to verify every element inside that panel reads from the real `trustMetrics` object rather than synthetic placeholders left over from pre-#220 scaffolding.

## Before — panel inventory

| Element | Source lines (pre-fix) | Status | Notes |
|---------|-----------------------|--------|-------|
| Reliability SVG — y=x identity dashed line | 1514-1516 | Correct | Definitional reference, always drawn. |
| Reliability SVG — per-bucket scatter dots | 1521-1539 | **Partial** — wired to `trustMetrics.reliability[]` but every dot is `fill="var(--positive)"`; no color encoding of deviation from identity. Deceptive: a badly-calibrated bucket looks identical to a perfect one. |
| Reliability SVG — "not enough data" placeholder | 1522-1524 | Correct | Shown when `reliability.length === 0`. |
| Reliability caption — "matches observed frequencies to within N pp" | 1543-1555 | Correct | Uses max absolute deviation from identity. Changes per query. |
| "Coverage vs target" SVG — 80% target dashed line | 1562-1563 | Correct | Definitional. |
| "Coverage vs target" SVG — 12 bars | 1569-1580 | **SYNTHETIC** — renders 12 identical bars, each at height `trustMetrics.coverage`. Looks like a rolling-coverage time series but is actually 12 copies of one number. This is exactly the "frozen fake numbers" quants will notice first. |
| "Coverage vs target" caption | 1582-1586 | Correct | Reads `trustMetrics.coverage` and `trustMetrics.regimeDrift`. |
| "Honesty note" | 1588-1594 | Correct | Static prose; intentional. |
| ℹ tooltips on metric labels | — | **MISSING** | No inline explainer for Coverage / CRPS / Hit rate / Grade / Regime drift. Quants have to context-switch to docs. |
| Empty-state card for `grade === "unknown"` | — | **MISSING** | The panel still renders both SVGs with "not enough data" text inside them. No CTA, no explanation of what "enough data" means. |
| Grade explanation | — | **MISSING** | The grade badge is shown in the trust strip but the computation (coverage gap ≤ 0.05, CRPS ≤ 0.05, hit ≥ 0.58 → A) is only documented in `lib/data.ts::gradeFromMetrics`. No inline explainer in the panel. |
| CRPS-over-time chart | — | Not present | Would require per-run history from a backend run registry — out of scope for `SearchResponse`. |

## After — what shipped

1. **Reliability scatter now colors by deviation from y=x**:
   - `|observed - predicted| < 0.10` → green (`var(--positive)`)
   - `0.10 ≤ deviation < 0.20` → amber (`var(--warn)`)
   - `deviation ≥ 0.20` → red (`var(--negative)`)
   Each dot has a `<title>` child so hover surfaces `predicted X.XX · observed Y.YY · deviation Z.ZZ`.
2. **Synthetic 12-bar coverage chart replaced** with a real per-bucket reliability bar chart — one bar per reliability entry, height = observed frequency, with the predicted-quantile label below and the 80% identity reference line at the target quantile. This derives entirely from `trustMetrics.reliability[]`, so it changes per query and per pin-set.
3. **Empty-state card** shown when `grade === "unknown"`: replaces both diagrams with a single muted card explaining that fewer than 3 analogs with forward windows is insufficient, with a "Trigger backtest sweep →" affordance (target TBD — currently links to `#` and logs to console; see inline comment). The same card text appears when `reliability` is empty.
4. **Grade explanation block** added below the reliability diagram, using the thresholds from `lib/data.ts::gradeFromMetrics` as the source of truth (A: gap ≤ 5%, CRPS ≤ 0.05, hit ≥ 0.58; B/C thresholds listed inline).
5. **ℹ tooltips** added to Coverage / CRPS / Hit rate / Regime drift / Grade in the trust strip, implemented via native `title` attribute on a small inline SVG glyph. One-sentence plain-English explanation per metric. Matches the task spec's acceptance shortcut ("native `title` attr is an acceptable shortcut").

## Invariants preserved

- `effectiveAnalogs` (pin-gated) still drives `computeCalibrationMetrics`. Pinning 2 analogs → panel updates.
- The `apiMetrics ?? computeCalibrationMetrics(...)` migration path noted in the existing comment (L1422-1425) is unchanged — when the backend `metrics` field from `SearchResponse` is threaded through, the panel will pick it up with no additional wiring because the data shape (`CalibrationResult`) already mirrors `CalibrationMetrics` exactly (see `lib/types.ts` L137-146 vs `lib/data.ts` L440-448).
- No changes outside the trust strip / trust panel region. Dataset dropdown, search row, analog cards, pin banner, chart area all untouched.

## Related code

- `the-similarity-app/components/workstation/workstation.tsx` — panel region
- `the-similarity-app/lib/data.ts` — `computeCalibrationMetrics`, `gradeFromMetrics` (source of truth for thresholds)
- `the-similarity-app/lib/types.ts` — `CalibrationMetrics` (backend shape)
- `the_similarity/core/metrics.py` — backend CRPS / hit_rate / calibration computation
- [[Calibration and coverage]]
- [[CRPS score]]
