"""Generator comparison runner — score multiple generators and rank them.

Runs each registered generator against the same source data, evaluates all
three scorecards (fidelity, privacy, utility), and produces a ranked
:class:`ComparisonResult`. The ranking is deterministic: primary sort by
fidelity_score descending, tiebreak by utility_gap ascending (lower gap =
better downstream utility).

Usage
-----
::

    from the_similarity.synthetic.comparison import compare_generators

    result = compare_generators(
        source_data=my_dataframe,
        generators=["block_bootstrap", "regime_block_bootstrap"],
        n=500,
        seed=42,
    )
    print(result.best())

Design invariants
-----------------
- Determinism: identical ``(source_data, generators, n, seed)`` produces
  bit-identical results. Each generator gets its own deterministic seed
  derived from the base seed + generator index, so generators do not
  share RNG state.
- Fail-closed: a generator that raises during ``fit()`` or ``sample()``
  gets a :class:`GeneratorResult` with ``fidelity_score=0``,
  ``privacy_score=0``, ``utility_gap=float('inf')`` and ``error`` set.
  It will rank last but will not prevent other generators from running.
- The function does NOT import generators or scorecards at module load
  time — imports are deferred to :func:`compare_generators` so this
  module stays importable even when sibling PRs have not yet landed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from the_similarity.synthetic.contracts import (
    Provenance,
    SyntheticDataset,
    iso_now,
)


@dataclass
class GeneratorResult:
    """Evaluation result for a single generator in a comparison run.

    Fields
    ------
    generator_name:
        Registered name of the generator (e.g. ``"block_bootstrap"``).
    fidelity_score:
        Overall fidelity score in ``[0, 1]``. Higher is better. 0 on error.
    privacy_score:
        Overall privacy score in ``[0, 1]``. Higher is better. 0 on error.
    utility_gap:
        Transfer gap from the utility scorecard. Lower is better.
        ``float('inf')`` on error.
    overall_rank:
        1-based rank after sorting. Populated by :func:`compare_generators`.
    error:
        If the generator or a scorecard raised, the error message is
        captured here for diagnostics. ``None`` on success.
    """

    generator_name: str
    fidelity_score: float = 0.0
    privacy_score: float = 0.0
    utility_gap: float = float("inf")
    overall_rank: int = 0
    error: Optional[str] = None


@dataclass
class ComparisonResult:
    """Ranked comparison across multiple generators.

    ``results`` is sorted by ``overall_rank`` ascending (best first).
    Use :meth:`best` to get the top-ranked generator.
    """

    results: list[GeneratorResult] = field(default_factory=list)

    def best(self) -> GeneratorResult:
        """Return the top-ranked generator result.

        Raises
        ------
        ValueError:
            If ``results`` is empty (no generators were compared).
        """
        if not self.results:
            raise ValueError("No generator results to rank — comparison is empty")
        return self.results[0]

    def to_dict(self) -> dict[str, Any]:
        """JSON-serializable dict for report output."""
        return {
            "results": [
                {
                    "generator_name": r.generator_name,
                    "fidelity_score": r.fidelity_score,
                    "privacy_score": r.privacy_score,
                    "utility_gap": r.utility_gap,
                    "overall_rank": r.overall_rank,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


def _rank_results(results: list[GeneratorResult]) -> list[GeneratorResult]:
    """Sort results by fidelity descending, utility_gap ascending, assign ranks.

    Ranking rules:
    1. Primary: ``fidelity_score`` descending (higher fidelity = better).
    2. Tiebreak: ``utility_gap`` ascending (lower gap = better utility).
    3. Results with errors always sort last.

    Modifies ``overall_rank`` in-place and returns the sorted list.
    """
    # Sort key: error-free first, then fidelity desc, then utility_gap asc.
    # Python's sort is stable, so equal keys preserve insertion order.
    sorted_results = sorted(
        results,
        key=lambda r: (
            r.error is not None,      # False (0) < True (1) — errors go last
            -r.fidelity_score,        # Negate for descending sort
            r.utility_gap,            # Ascending — lower gap is better
        ),
    )
    for i, r in enumerate(sorted_results, start=1):
        r.overall_rank = i
    return sorted_results


def _resolve_generator(name: str) -> Any:
    """Resolve a generator name string to an instantiated generator object.

    Deferred import so this module stays importable even when sibling
    generator PRs (e.g. GaussianCopulaGenerator) have not yet landed.
    Unknown names raise ``ValueError``.
    """
    # Standard generators from copies.py.
    from the_similarity.synthetic.copies import (
        BlockBootstrapGenerator,
        RegimeBlockBootstrapGenerator,
    )

    _REGISTRY: dict[str, Any] = {
        "block_bootstrap": lambda: BlockBootstrapGenerator(),
        "regime_block_bootstrap": lambda: RegimeBlockBootstrapGenerator(),
    }

    # Try copula — may not exist yet (Agent 1 is adding it in parallel).
    try:
        from the_similarity.synthetic.copula import GaussianCopulaGenerator  # type: ignore[import-not-found]
        _REGISTRY["gaussian_copula"] = lambda: GaussianCopulaGenerator()
    except ImportError:
        pass

    if name not in _REGISTRY:
        raise ValueError(
            f"Unknown generator {name!r}. Available: {sorted(_REGISTRY.keys())}"
        )
    return _REGISTRY[name]()


def compare_generators(
    source_data: Any,
    generators: list[str],
    n: int,
    seed: int,
) -> ComparisonResult:
    """Compare multiple generators on the same source data.

    Parameters
    ----------
    source_data:
        Source data — numpy array or pandas DataFrame. Wrapped in a
        :class:`SyntheticDataset` internally.
    generators:
        List of generator names to compare (e.g. ``["block_bootstrap",
        "regime_block_bootstrap"]``).
    n:
        Number of synthetic timesteps to generate per generator.
    seed:
        Base RNG seed. Each generator gets ``seed + i`` where ``i`` is
        its 0-based index in ``generators``, ensuring deterministic but
        independent sampling.

    Returns
    -------
    ComparisonResult:
        Ranked results with ``best()`` returning the top-ranked generator.
    """
    # Wrap source data in a SyntheticDataset with real provenance.
    source_id = "comparison_source"
    real = SyntheticDataset(
        data=source_data,
        provenance=Provenance(
            source_id=source_id,
            generator_name="real",
            generator_version="0",
            seed=0,
            created_at=iso_now(),
        ),
    )

    results: list[GeneratorResult] = []

    for i, gen_name in enumerate(generators):
        # Each generator gets a unique, deterministic seed derived from
        # the base seed + its index. This ensures generators do not share
        # RNG state and results are reproducible.
        gen_seed = seed + i

        try:
            generator = _resolve_generator(gen_name)
            generator.fit(real)
            synth = generator.sample(n, seed=gen_seed)

            # Run all three scorecards. Each is independently imported
            # so one missing scorecard does not block the others.
            fidelity_score = 0.0
            privacy_score = 0.0
            utility_gap = float("inf")

            try:
                from the_similarity.synthetic.fidelity import FidelityScorecard
                fidelity_report = FidelityScorecard().evaluate(real, synth)
                fidelity_score = fidelity_report.overall_score
            except ImportError:
                pass

            try:
                from the_similarity.synthetic.privacy import PrivacyScorecard
                privacy_report = PrivacyScorecard().evaluate(real, synth)
                privacy_score = privacy_report.overall_score
            except ImportError:
                pass

            try:
                from the_similarity.synthetic.utility import UtilityScorecard
                utility_report = UtilityScorecard().evaluate(real, synth)
                utility_gap = utility_report.transfer_gap
            except ImportError:
                pass

            results.append(
                GeneratorResult(
                    generator_name=gen_name,
                    fidelity_score=fidelity_score,
                    privacy_score=privacy_score,
                    utility_gap=utility_gap,
                )
            )

        except Exception as exc:
            # Fail-closed: capture error, assign worst-possible scores so
            # this generator ranks last but does not crash the comparison.
            results.append(
                GeneratorResult(
                    generator_name=gen_name,
                    fidelity_score=0.0,
                    privacy_score=0.0,
                    utility_gap=float("inf"),
                    error=str(exc),
                )
            )

    ranked = _rank_results(results)
    return ComparisonResult(results=ranked)


__all__ = [
    "ComparisonResult",
    "GeneratorResult",
    "compare_generators",
]
