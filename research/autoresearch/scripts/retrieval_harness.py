"""Retrieval evaluation harness for comparing retrieval methods.

Provides a reproducible, metrics-driven comparison framework for evaluating
experimental retrieval functions against the baseline engine
(``the_similarity.api.search``).  The harness is **read-only** with respect
to the production codebase — it never mutates ``the_similarity/core/`` or
``the_similarity/api.py``.

Design invariants
-----------------
* Each retrieval function must conform to ``RetrievalFn`` — a callable that
  accepts ``(query, history, k)`` and returns a list of ``RetrievalResult``
  namedtuples (offset, score).
* Metric computation is deterministic given the same inputs.  No internal
  randomness beyond what the retrieval functions themselves inject.
* ``compare_walk_forward`` enforces no-lookahead by slicing history to
  ``[:query_start]`` before invoking retrievers — identical to the production
  backtester's protocol.
* JSON reports are self-contained and include enough metadata (git SHA,
  timestamp, benchmark id) for later ledger integration.

Metrics
-------
* **top_k_overlap** — Jaccard similarity of the offset sets returned by both
  retrievers.  Measures *agreement* at the set level.
* **rank_correlation** — Spearman rho over the shared results, measured by
  score rank.  High rho means the two methods agree on relative ordering.
* **rank_lift** — per-result signed change in rank between baseline and
  experimental.  Positive lift = the experimental method ranked the result
  higher.
* **recall_at_k** — fraction of the baseline's top-k that also appear in the
  experimental top-k.  A value of 1.0 means the experimental method
  ``covers`` the baseline set entirely.

Walk-forward metrics
--------------------
* For each top-k set, the harness extracts forward returns following each
  matched window and computes the mean absolute forward return (as a proxy
  for match quality).  This lets us compare whether the experimental
  retriever finds analogues whose forward paths are more predictive.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, Sequence

import numpy as np
from scipy import stats


# ---------------------------------------------------------------------------
# Public data contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetrievalResult:
    """A single retrieval hit returned by a retrieval function.

    Attributes
    ----------
    offset : int
        Start index of the matched window within the history array.
    score : float
        Similarity score assigned by the retriever.  Higher is better.
    """
    offset: int
    score: float


# Callable protocol for retrieval functions.
# Signature: (query: np.ndarray, history: np.ndarray, k: int) -> list[RetrievalResult]
RetrievalFn = Callable[[np.ndarray, np.ndarray, int], list[RetrievalResult]]


@dataclass
class QueryMetrics:
    """Per-query comparison metrics between baseline and experimental.

    All fields are deterministic given fixed retrieval outputs.
    """
    query_index: int
    top_k_overlap: float          # Jaccard similarity of offset sets
    rank_correlation: float       # Spearman rho over shared offsets
    rank_correlation_pvalue: float
    recall_at_k: float            # fraction of baseline top-k in experimental top-k
    rank_lifts: dict[int, int]    # offset -> signed rank change (baseline_rank - experimental_rank)
    baseline_offsets: list[int]
    experimental_offsets: list[int]


@dataclass
class WalkForwardQueryMetrics:
    """Per-query walk-forward evaluation comparing both retrievers' top-k sets.

    For each retriever's top-k matches we extract the ``forward_bars``-length
    return path that followed the matched window in history and compute the
    mean absolute return.  Lower MAE against actual forward returns is better.
    """
    query_index: int
    query_start: int
    baseline_mean_abs_forward: float
    experimental_mean_abs_forward: float
    actual_forward_return: float  # cumulative return over forward_bars


@dataclass
class ComparisonReport:
    """Aggregate comparison report written as JSON."""
    per_query: list[QueryMetrics]
    aggregate_top_k_overlap: float
    aggregate_rank_correlation: float
    aggregate_recall_at_k: float
    mean_rank_lift: float
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dictionary."""
        return {
            "metadata": self.metadata,
            "aggregate": {
                "top_k_overlap": self.aggregate_top_k_overlap,
                "rank_correlation": self.aggregate_rank_correlation,
                "recall_at_k": self.aggregate_recall_at_k,
                "mean_rank_lift": self.mean_rank_lift,
                "n_queries": len(self.per_query),
            },
            "per_query": [
                {
                    "query_index": q.query_index,
                    "top_k_overlap": q.top_k_overlap,
                    "rank_correlation": q.rank_correlation,
                    "rank_correlation_pvalue": q.rank_correlation_pvalue,
                    "recall_at_k": q.recall_at_k,
                    "rank_lifts": q.rank_lifts,
                    "baseline_offsets": q.baseline_offsets,
                    "experimental_offsets": q.experimental_offsets,
                }
                for q in self.per_query
            ],
        }


@dataclass
class WalkForwardReport:
    """Aggregate walk-forward comparison report."""
    per_query: list[WalkForwardQueryMetrics]
    baseline_mean_abs_forward: float
    experimental_mean_abs_forward: float
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata,
            "aggregate": {
                "baseline_mean_abs_forward": self.baseline_mean_abs_forward,
                "experimental_mean_abs_forward": self.experimental_mean_abs_forward,
                "n_queries": len(self.per_query),
            },
            "per_query": [
                {
                    "query_index": q.query_index,
                    "query_start": q.query_start,
                    "baseline_mean_abs_forward": q.baseline_mean_abs_forward,
                    "experimental_mean_abs_forward": q.experimental_mean_abs_forward,
                    "actual_forward_return": q.actual_forward_return,
                }
                for q in self.per_query
            ],
        }


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _jaccard(set_a: set, set_b: set) -> float:
    """Jaccard similarity = |A ∩ B| / |A ∪ B|.

    Returns 1.0 when both sets are empty (vacuously identical).
    """
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    return len(set_a & set_b) / len(union)


def _spearman_on_shared(
    baseline: list[RetrievalResult],
    experimental: list[RetrievalResult],
) -> tuple[float, float]:
    """Compute Spearman rank correlation over offsets present in both lists.

    If fewer than 2 shared offsets exist, returns (0.0, 1.0) — no
    meaningful correlation can be computed.

    Ranks are 1-indexed positions in each retriever's output list (which is
    assumed sorted by descending score).
    """
    # Build offset -> rank maps (1-indexed)
    baseline_rank = {r.offset: i + 1 for i, r in enumerate(baseline)}
    experimental_rank = {r.offset: i + 1 for i, r in enumerate(experimental)}

    shared = sorted(set(baseline_rank) & set(experimental_rank))
    if len(shared) < 2:
        return 0.0, 1.0

    b_ranks = [baseline_rank[o] for o in shared]
    e_ranks = [experimental_rank[o] for o in shared]
    rho, pval = stats.spearmanr(b_ranks, e_ranks)
    # scipy can return nan for constant inputs
    if np.isnan(rho):
        return 0.0, 1.0
    return float(rho), float(pval)


def _rank_lifts(
    baseline: list[RetrievalResult],
    experimental: list[RetrievalResult],
) -> dict[int, int]:
    """For each offset in the experimental set, compute rank lift.

    rank_lift = baseline_rank - experimental_rank.  Positive means the
    experimental retriever ranked the result higher (better).

    Offsets that appear only in the experimental set get a baseline_rank
    of ``len(baseline) + 1`` (one past the worst baseline rank) to
    quantify how far outside the baseline set they are.
    """
    baseline_rank = {r.offset: i + 1 for i, r in enumerate(baseline)}
    default_baseline_rank = len(baseline) + 1

    lifts: dict[int, int] = {}
    for i, r in enumerate(experimental):
        exp_rank = i + 1
        base_rank = baseline_rank.get(r.offset, default_baseline_rank)
        lifts[r.offset] = base_rank - exp_rank
    return lifts


def _recall_at_k(baseline: list[RetrievalResult], experimental: list[RetrievalResult]) -> float:
    """Fraction of baseline top-k offsets that appear in experimental top-k.

    Returns 1.0 when baseline is empty (vacuously all recalled).
    """
    if not baseline:
        return 1.0
    baseline_offsets = {r.offset for r in baseline}
    experimental_offsets = {r.offset for r in experimental}
    return len(baseline_offsets & experimental_offsets) / len(baseline_offsets)


# ---------------------------------------------------------------------------
# Main harness
# ---------------------------------------------------------------------------

class RetrievalHarness:
    """Compares two retrieval functions on the same query set.

    Parameters
    ----------
    baseline_fn : RetrievalFn
        The trusted retrieval function (typically wrapping
        ``the_similarity.api.search``).
    experimental_fn : RetrievalFn
        The experimental retrieval function under evaluation.

    Lifecycle
    ---------
    1. Instantiate with both retrieval functions.
    2. Call ``run_comparison`` with a dataset and query windows.
    3. Optionally call ``compare_walk_forward`` for forward-looking eval.
    4. Call ``generate_report`` to write JSON output.

    Thread safety: instances are **not** thread-safe.  Create separate
    instances per thread if needed.
    """

    def __init__(self, baseline_fn: RetrievalFn, experimental_fn: RetrievalFn):
        self._baseline_fn = baseline_fn
        self._experimental_fn = experimental_fn
        self._comparison_report: ComparisonReport | None = None
        self._walk_forward_report: WalkForwardReport | None = None

    # ---- Core comparison ------------------------------------------------

    def run_comparison(
        self,
        dataset: np.ndarray,
        query_windows: list[tuple[int, int]],
        k: int = 10,
    ) -> ComparisonReport:
        """Run both retrievers on the same queries and compute metrics.

        Parameters
        ----------
        dataset : np.ndarray
            1-D float64 history array.
        query_windows : list[tuple[int, int]]
            Each element is ``(start, end)`` defining the query slice
            ``dataset[start:end]``.
        k : int
            Number of results to retrieve per query.

        Returns
        -------
        ComparisonReport
            Contains per-query and aggregate metrics.

        Raises
        ------
        ValueError
            If dataset is not 1-D or query_windows is empty.
        """
        dataset = np.asarray(dataset, dtype=np.float64)
        if dataset.ndim != 1:
            raise ValueError(f"dataset must be 1-D, got {dataset.ndim}-D")
        if not query_windows:
            raise ValueError("query_windows must not be empty")

        per_query: list[QueryMetrics] = []

        for idx, (start, end) in enumerate(query_windows):
            query = dataset[start:end]

            # Both retrievers see identical inputs
            baseline_results = self._baseline_fn(query, dataset, k)
            experimental_results = self._experimental_fn(query, dataset, k)

            baseline_offsets = {r.offset for r in baseline_results}
            experimental_offsets = {r.offset for r in experimental_results}

            overlap = _jaccard(baseline_offsets, experimental_offsets)
            rho, pval = _spearman_on_shared(baseline_results, experimental_results)
            lifts = _rank_lifts(baseline_results, experimental_results)
            recall = _recall_at_k(baseline_results, experimental_results)

            per_query.append(QueryMetrics(
                query_index=idx,
                top_k_overlap=overlap,
                rank_correlation=rho,
                rank_correlation_pvalue=pval,
                recall_at_k=recall,
                rank_lifts={str(k_): v for k_, v in lifts.items()},  # JSON keys must be strings
                baseline_offsets=sorted(baseline_offsets),
                experimental_offsets=sorted(experimental_offsets),
            ))

        # Aggregate metrics — simple arithmetic means across queries
        agg_overlap = float(np.mean([q.top_k_overlap for q in per_query]))
        agg_rho = float(np.mean([q.rank_correlation for q in per_query]))
        agg_recall = float(np.mean([q.recall_at_k for q in per_query]))

        # Mean rank lift across all results in all queries
        all_lifts = []
        for q in per_query:
            all_lifts.extend(q.rank_lifts.values())
        mean_lift = float(np.mean(all_lifts)) if all_lifts else 0.0

        # Metadata
        metadata = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "k": k,
            "n_queries": len(query_windows),
            "dataset_length": len(dataset),
            "git_sha": _git_sha(),
        }

        self._comparison_report = ComparisonReport(
            per_query=per_query,
            aggregate_top_k_overlap=agg_overlap,
            aggregate_rank_correlation=agg_rho,
            aggregate_recall_at_k=agg_recall,
            mean_rank_lift=mean_lift,
            metadata=metadata,
        )
        return self._comparison_report

    # ---- Walk-forward comparison ----------------------------------------

    def compare_walk_forward(
        self,
        dataset: np.ndarray,
        k: int = 10,
        window_size: int = 60,
        forward_bars: int = 30,
        n_trials: int = 50,
        seed: int = 42,
    ) -> WalkForwardReport:
        """Run walk-forward comparison with no-lookahead enforcement.

        For each trial, a random query start is chosen such that:
        1. There is enough lookback history (>= 3 * window_size) before the
           query window.
        2. There are >= ``forward_bars`` data points after the query window.

        Both retrievers only see ``history[:query_start]`` — the slice
        **before** the query window, enforcing the no-lookahead invariant.

        For each retriever's top-k matches, the harness extracts the
        ``forward_bars``-length return path following each matched window
        in the *full* history and computes the mean absolute return across
        those paths.  This measures how predictive each retriever's
        analogues are.

        Parameters
        ----------
        dataset : np.ndarray
            1-D float64 history array.
        k : int
            Number of results per retriever.
        window_size : int
            Length of the query window.
        forward_bars : int
            Number of bars to look forward for evaluation.
        n_trials : int
            Number of random walk-forward trials.
        seed : int
            Random seed for trial position selection.

        Returns
        -------
        WalkForwardReport
        """
        dataset = np.asarray(dataset, dtype=np.float64)
        if dataset.ndim != 1:
            raise ValueError(f"dataset must be 1-D, got {dataset.ndim}-D")

        min_lookback = 3 * window_size
        # query occupies [query_start, query_start + window_size)
        # forward region occupies [query_start + window_size, query_start + window_size + forward_bars)
        min_start = min_lookback
        max_start = len(dataset) - window_size - forward_bars
        if max_start <= min_start:
            raise ValueError(
                f"dataset too short ({len(dataset)}) for window_size={window_size}, "
                f"forward_bars={forward_bars}. Need at least "
                f"{min_lookback + window_size + forward_bars} data points."
            )

        rng = np.random.default_rng(seed)
        positions = rng.integers(min_start, max_start, size=n_trials)

        per_query: list[WalkForwardQueryMetrics] = []

        for idx, qstart in enumerate(positions):
            qend = qstart + window_size
            query = dataset[qstart:qend]

            # No-lookahead: only history before the query window
            lookback = dataset[:qstart]

            baseline_results = self._baseline_fn(query, lookback, k)
            experimental_results = self._experimental_fn(query, lookback, k)

            # Actual forward return (cumulative log return or simple pct change)
            actual_forward = dataset[qend + forward_bars - 1] / dataset[qend] - 1.0 if dataset[qend] != 0 else 0.0

            # For each retriever: collect forward returns following each match
            def _mean_abs_forward(results: list[RetrievalResult]) -> float:
                """Mean absolute forward return across matches' forward windows.

                If a match offset + window_size + forward_bars exceeds the
                available lookback length, skip it (it would imply lookahead
                into the query region).
                """
                fwd_returns = []
                for r in results:
                    fwd_start = r.offset + window_size
                    fwd_end = fwd_start + forward_bars
                    # Only use matches whose forward window lies entirely within lookback
                    if fwd_end <= len(lookback) and lookback[fwd_start] != 0:
                        fwd_ret = lookback[fwd_end - 1] / lookback[fwd_start] - 1.0
                        fwd_returns.append(abs(fwd_ret))
                return float(np.mean(fwd_returns)) if fwd_returns else 0.0

            per_query.append(WalkForwardQueryMetrics(
                query_index=idx,
                query_start=int(qstart),
                baseline_mean_abs_forward=_mean_abs_forward(baseline_results),
                experimental_mean_abs_forward=_mean_abs_forward(experimental_results),
                actual_forward_return=float(actual_forward),
            ))

        agg_baseline = float(np.mean([q.baseline_mean_abs_forward for q in per_query])) if per_query else 0.0
        agg_experimental = float(np.mean([q.experimental_mean_abs_forward for q in per_query])) if per_query else 0.0

        metadata = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "k": k,
            "window_size": window_size,
            "forward_bars": forward_bars,
            "n_trials": n_trials,
            "seed": seed,
            "dataset_length": len(dataset),
            "git_sha": _git_sha(),
        }

        self._walk_forward_report = WalkForwardReport(
            per_query=per_query,
            baseline_mean_abs_forward=agg_baseline,
            experimental_mean_abs_forward=agg_experimental,
            metadata=metadata,
        )
        return self._walk_forward_report

    # ---- Report generation ---------------------------------------------

    def generate_report(self, output_path: str | Path) -> Path:
        """Write JSON report containing all collected results.

        Parameters
        ----------
        output_path : str or Path
            Destination file path. Parent directories are created if needed.

        Returns
        -------
        Path
            The resolved output path.

        Raises
        ------
        RuntimeError
            If neither ``run_comparison`` nor ``compare_walk_forward`` has
            been called yet.
        """
        if self._comparison_report is None and self._walk_forward_report is None:
            raise RuntimeError(
                "No results to report. Call run_comparison() or "
                "compare_walk_forward() first."
            )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        report: dict = {}
        if self._comparison_report is not None:
            report["comparison"] = self._comparison_report.to_dict()
        if self._walk_forward_report is not None:
            report["walk_forward"] = self._walk_forward_report.to_dict()

        with open(output, "w") as f:
            json.dump(report, f, indent=2)

        return output


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _git_sha() -> str:
    """Return the current short git SHA, or 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _baseline_retrieval_fn_factory() -> RetrievalFn:
    """Create a retrieval function wrapping ``the_similarity.api.search``.

    The returned callable conforms to ``RetrievalFn`` and converts
    ``MatchResult`` objects to ``RetrievalResult``.

    This factory import is deferred to avoid import-time overhead when
    running tests with mocks.
    """
    from the_similarity.api import search, load  # noqa: F811

    def baseline_fn(query: np.ndarray, history: np.ndarray, k: int) -> list[RetrievalResult]:
        results = search(query, history, top_k=k, exclude_self=True)
        return [
            RetrievalResult(offset=m.start_idx, score=m.confidence_score)
            for m in results.matches
        ]

    return baseline_fn


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """CLI entry point for running the retrieval harness.

    Usage::

        python retrieval_harness.py --dataset spy --k 10 --output report.json

    The ``--dataset`` argument names a CSV file in the project's data
    directory, or an absolute / relative path to a CSV file with a
    ``close`` column.
    """
    parser = argparse.ArgumentParser(
        description="Retrieval evaluation harness — compare baseline vs experimental retriever"
    )
    parser.add_argument(
        "--dataset", required=True,
        help="Dataset name (resolved via the_similarity.api.load) or path to CSV",
    )
    parser.add_argument("--k", type=int, default=10, help="Top-k results to compare")
    parser.add_argument("--output", default="report.json", help="Output JSON report path")
    parser.add_argument("--window-size", type=int, default=60, help="Query window size")
    parser.add_argument("--forward-bars", type=int, default=30, help="Forward bars for walk-forward")
    parser.add_argument("--n-trials", type=int, default=50, help="Number of walk-forward trials")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--mode",
        choices=["comparison", "walk_forward", "both"],
        default="both",
        help="Which evaluation to run",
    )

    args = parser.parse_args()

    # Load dataset
    from the_similarity.api import load
    ts = load(args.dataset)
    dataset = ts.values

    # Build retrieval functions
    baseline_fn = _baseline_retrieval_fn_factory()

    # Default experimental = same as baseline (useful for sanity check;
    # real experiments will import and pass a different function)
    experimental_fn = baseline_fn

    harness = RetrievalHarness(baseline_fn, experimental_fn)

    if args.mode in ("comparison", "both"):
        # Generate random query windows for comparison mode
        rng = np.random.default_rng(args.seed)
        n_queries = args.n_trials
        window_size = args.window_size
        max_start = len(dataset) - window_size
        if max_start <= 0:
            print(f"Dataset too short ({len(dataset)}) for window_size={window_size}")
            sys.exit(1)
        starts = rng.integers(0, max_start, size=n_queries)
        query_windows = [(int(s), int(s) + window_size) for s in starts]

        print(f"Running comparison: {n_queries} queries, k={args.k}")
        report = harness.run_comparison(dataset, query_windows, k=args.k)
        print(f"  top_k_overlap: {report.aggregate_top_k_overlap:.4f}")
        print(f"  rank_correlation: {report.aggregate_rank_correlation:.4f}")
        print(f"  recall_at_k: {report.aggregate_recall_at_k:.4f}")
        print(f"  mean_rank_lift: {report.mean_rank_lift:.4f}")

    if args.mode in ("walk_forward", "both"):
        print(f"Running walk-forward: {args.n_trials} trials, k={args.k}")
        wf_report = harness.compare_walk_forward(
            dataset,
            k=args.k,
            window_size=args.window_size,
            forward_bars=args.forward_bars,
            n_trials=args.n_trials,
            seed=args.seed,
        )
        print(f"  baseline_mean_abs_forward: {wf_report.baseline_mean_abs_forward:.6f}")
        print(f"  experimental_mean_abs_forward: {wf_report.experimental_mean_abs_forward:.6f}")

    output_path = harness.generate_report(args.output)
    print(f"Report written to {output_path}")


if __name__ == "__main__":
    main()
