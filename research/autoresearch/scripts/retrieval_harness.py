"""Retrieval harness: evaluate analog-retrieval quality of embedding functions.

This module defines a protocol for retrieval functions and a harness that
measures how well a retrieval method finds good analogs (windows whose
forward evolution is similar to the query's forward evolution).

The harness is agnostic to the retrieval implementation — it accepts any
callable that conforms to ``RetrievalFn`` and evaluates it against a held-out
test set.

Protocol:
  A ``RetrievalFn`` takes a query embedding index and returns the top-k
  most similar embedding indices.  The harness then compares the forward
  returns of the retrieved analogs against the query's actual forward returns.

Lifecycle:
  1. Caller provides embeddings, forward-return data, and a retrieval function.
  2. ``run_retrieval_eval`` iterates over test indices, calls the retrieval
     function, and computes retrieval quality metrics.
  3. Results are returned as a ``RetrievalReport``.

Immutability:
  - The harness does not mutate any input arrays.
  - The returned report is a plain dataclass snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import numpy as np


class RetrievalFn(Protocol):
    """Protocol for retrieval functions.

    A retrieval function takes a query index (int) and returns an array
    of the top-k most similar indices (excluding the query itself).
    """

    def __call__(self, query_idx: int) -> np.ndarray:
        """Return top-k neighbor indices for the given query index."""
        ...


@dataclass
class RetrievalReport:
    """Results from a retrieval evaluation run.

    Attributes:
        n_queries: number of test queries evaluated.
        mean_forward_mae: mean absolute error of retrieved analogs'
            forward returns vs. query forward returns.
        mean_rank_correlation: average Spearman rank correlation between
            retrieved analog forward returns and query forward returns.
        coverage: fraction of queries that returned at least one result.
    """

    n_queries: int
    mean_forward_mae: float
    mean_rank_correlation: float
    coverage: float


def run_retrieval_eval(
    retrieval_fn: RetrievalFn,
    test_indices: np.ndarray,
    forward_returns: np.ndarray,
    *,
    k: int = 10,
) -> RetrievalReport:
    """Evaluate a retrieval function on held-out test queries.

    For each test index, the retrieval function is called to get the top-k
    most similar training windows.  Quality is measured by how well the
    retrieved analogs' forward returns predict the query's actual forward
    returns.

    Parameters:
        retrieval_fn: callable conforming to ``RetrievalFn``.
        test_indices: array of query indices to evaluate.
        forward_returns: array of shape ``(n_windows,)`` with the forward
            return (e.g. 30-bar cumulative return) for each window.
        k: number of neighbors to retrieve per query.

    Returns:
        A ``RetrievalReport`` with aggregate metrics.
    """
    maes: list[float] = []
    rank_corrs: list[float] = []
    n_covered = 0

    for qidx in test_indices:
        neighbors = retrieval_fn(int(qidx))
        if len(neighbors) == 0:
            continue
        n_covered += 1

        # MAE: how close are the neighbors' forward returns to the query's?
        query_fwd = forward_returns[qidx]
        neighbor_fwds = forward_returns[neighbors[:k]]
        mae = float(np.mean(np.abs(neighbor_fwds - query_fwd)))
        maes.append(mae)

        # Rank correlation: do the neighbors rank similarly to the query?
        # Simplified: correlation of neighbor forward returns with query value
        if len(neighbor_fwds) > 1 and np.std(neighbor_fwds) > 1e-12:
            # Spearman-like: correlation of ranks
            rank_corr = float(np.corrcoef(
                np.arange(len(neighbor_fwds)),
                np.abs(neighbor_fwds - query_fwd),
            )[0, 1])
            rank_corrs.append(rank_corr)

    n_queries = len(test_indices)
    return RetrievalReport(
        n_queries=n_queries,
        mean_forward_mae=float(np.mean(maes)) if maes else float("nan"),
        mean_rank_correlation=float(np.mean(rank_corrs)) if rank_corrs else float("nan"),
        coverage=n_covered / max(n_queries, 1),
    )
