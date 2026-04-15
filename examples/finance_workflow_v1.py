"""Finance pilot v1 — end-to-end workflow.

Demonstrates the canonical user journey specified in
`docs/planning/finance_pilot_v1.md`:

    load data -> backtest (calibration anchor) -> search analogues ->
    project with trust filter -> run calibration-aware strategy ->
    print review summary.

Runs on synthetic trending-plus-seasonal data shipped in this script
so the example is self-contained. A real user swaps in
`the_similarity.load("spy.csv")` or similar.

Usage
-----
    python examples/finance_workflow_v1.py

Exit code is always 0 on success. The script prints a structured
summary block that a trader would read before pulling a trigger.

Design notes
------------
- The script is intentionally linear and over-commented; this is a
  reference workflow for design partners, not library code.
- All engine calls are the public `the_similarity.api` surface — no
  private helpers — so the script doubles as a smoke test that the
  pilot-grade workflow does not depend on internal modules.
- All thresholds use module defaults. A partner customising for their
  ticker can relax or tighten via the commented-out knobs near each
  call site.
"""

from __future__ import annotations

# Make the example runnable directly (`python examples/finance_workflow_v1.py`)
# from inside the repo checkout, without requiring an editable install.
# We prepend the repo root so imports prefer the local checkout over any
# globally installed version of `the_similarity`.
import os
import sys

_THIS = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS, os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import numpy as np  # noqa: E402

import the_similarity  # noqa: E402
from the_similarity.api import backtest, project, search  # noqa: E402
from the_similarity.config import Config  # noqa: E402
from the_similarity.core.decision_rules import (  # noqa: E402
    CalibrationAwareStrategy,
    DecisionRuleConfig,
    summarise_review,
)
from the_similarity.core.strategy import momentum_strategy  # noqa: E402
from the_similarity.core.trust_filter import TrustFilter  # noqa: E402


def _build_synthetic_history(n: int = 1500, seed: int = 42) -> np.ndarray:
    """Trend + seasonality + noise — enough structure that analogue
    search has a non-trivial signal to find."""
    rng = np.random.default_rng(seed)
    t = np.arange(n, dtype=np.float64)
    trend = 100.0 + 0.04 * t
    seasonal = 3.0 * np.sin(t * 0.05) + 1.5 * np.cos(t * 0.13)
    noise = rng.standard_normal(n) * 0.7
    return trend + seasonal + noise


def main() -> None:
    print("=" * 70)
    print("Finance pilot v1 — end-to-end workflow")
    print("=" * 70)

    # ---------------------------------------------------------------
    # 1. LOAD — in production, `the_similarity.load("spy.csv")`
    # ---------------------------------------------------------------
    history = _build_synthetic_history()
    ts = the_similarity.load(history)
    print(f"\n[1/5] Loaded history: {len(history)} bars")

    # Config is intentionally small/fast for the demo. A real pilot
    # enables more methods (e.g. bempedelis, koopman, wavelet) for
    # richer scoring at the cost of compute.
    config = Config(
        active_methods=["dtw", "pearson_warped"],
        tier1_candidates=80,
        tier2_candidates=6,
        stride=5,
    )

    # ---------------------------------------------------------------
    # 2. BACKTEST — the calibration anchor for the trust filter.
    #    In a real deployment this runs nightly or weekly; the
    #    resulting BacktestReport is cached and passed in daily.
    # ---------------------------------------------------------------
    print("\n[2/5] Running walk-forward backtest (calibration anchor)...")
    report = backtest(
        history,
        window_size=40,
        forward_bars=20,
        n_trials=12,
        config=config,
        seed=42,
        n_workers=1,
    )
    print(f"       valid trials     : {report.n_valid_trials}")
    print(f"       hit_rate         : {report.hit_rate:.1%}")
    print(f"       mean abs error   : {report.mean_error:.4f}")
    print(f"       calibration keys : {sorted(report.calibration)}")

    # ---------------------------------------------------------------
    # 3. SEARCH — find analogues for the current window. The query is
    #    the most recent 40 bars excluding the forward horizon, and
    #    the lookback is everything before that (no look-ahead).
    # ---------------------------------------------------------------
    query_vals = history[-80:-40]
    query = the_similarity.load(query_vals)
    lookback = the_similarity.load(history[:-80])
    results = search(query=query, history=lookback, top_k=8, config=config)
    print(f"\n[3/5] Search found {len(results.matches)} analogues "
          f"(top confidence {results.best.confidence_score if results.best else 0.0:.1f})")

    # ---------------------------------------------------------------
    # 4. PROJECT — weighted percentile forecast cone.
    # ---------------------------------------------------------------
    forecast = project(results, lookback, forward_bars=20, config=config)
    p50_end = float(forecast.curves[50][-1]) if 50 in forecast.curves else 0.0
    p10_end = float(forecast.curves.get(10, [0.0])[-1])
    p90_end = float(forecast.curves.get(90, [0.0])[-1])
    print(f"\n[4/5] Projection at horizon:")
    print(f"       P10 = {p10_end:+.4f}  P50 = {p50_end:+.4f}  "
          f"P90 = {p90_end:+.4f}")

    # ---------------------------------------------------------------
    # 5. DECIDE + REVIEW — run the calibration-aware strategy.
    #    The TrustFilter defaults are conservative; a partner can
    #    relax `min_matches` if their universe is thin.
    # ---------------------------------------------------------------
    strategy = momentum_strategy(min_confidence=50.0, forecast_threshold=0.005)
    aware = CalibrationAwareStrategy(
        base_strategy=strategy,
        trust_filter=TrustFilter(
            # min_matches=5,            # default
            # max_calibration_mae=0.15, # default
            # min_score=0.5,            # default
        ),
        decision_config=DecisionRuleConfig(
            entry_percentile=25,
            entry_threshold=0.003,
        ),
        calibration_report=report,
    )
    signals = aware.evaluate(
        matches=results.matches,
        history=ts.values,
        forecast=forecast,
        regime_state=(
            {"regime": results.matches[0].regime}
            if results.matches and results.matches[0].regime
            else None
        ),
    )
    review = summarise_review(signals, n_matches=len(results.matches))

    print("\n[5/5] Review")
    print("-" * 70)
    print(review.to_text())
    print("-" * 70)

    # Emit a machine-readable block too so downstream tooling can pipe
    # this (e.g. a Slack bot / a markdown report).
    if signals:
        s = signals[0]
        print("\nDecision:")
        print(f"  direction      = {s.signal_type.value}")
        print(f"  position_size  = {s.position_size:.3f}")
        print(f"  trust          = {s.trust.trust}")
        print(f"  trust_score    = {s.trust.score:.3f}")
        print(f"  threshold_met  = {s.threshold_met}")
    else:
        print("\nDecision: no base signal emitted by strategy — stand down.")

    print("\nDone.")


if __name__ == "__main__":
    main()
