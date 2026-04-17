"""Synthetic data module contracts.

Stable, typed interfaces for synthetic time-series generation and evaluation.
Downstream modules (generators, scorecards, pipelines, CLI, tests) import
exclusively from here. Changes to this file are breaking changes — treat as a
public API surface.

Design invariants
-----------------
- Datasets are immutable once constructed (dataclasses are frozen where
  practical). Reports are value objects — do not mutate after evaluation.
- `SyntheticDataset.data` may be a numpy ndarray (shape: ``(n_timesteps,
  n_series)``) or a pandas DataFrame (columns = series). Consumers must
  handle both; helpers in this module stay stdlib-only.
- `Provenance` is required — every dataset carries the seed, generator
  identity, and params needed to reproduce it bit-for-bit.
- Reports are fail-closed: `passed` defaults to False. A generator producing
  NaNs or a scorecard raising must surface `passed=False` with diagnostics in
  the metric dicts, not a silent pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Protocol, Union, runtime_checkable

# numpy / pandas are first-party dependencies (see pyproject.toml), but we
# keep the type refs as strings under `TYPE_CHECKING` to avoid import cost at
# module load time for downstream tools that only need the dataclass shapes.
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np
    import pandas as pd

    SeriesData = Union["np.ndarray", "pd.DataFrame"]
    IndexLike = Union["np.ndarray", "pd.Index", list]
else:
    SeriesData = Any
    IndexLike = Any


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@dataclass
class Provenance:
    """Reproducibility record attached to every SyntheticDataset.

    Every field is mandatory except `params` (which defaults to empty). A
    dataset with incomplete provenance must NOT be written to disk or passed
    to a scorecard — downstream auditing relies on these fields being stable.

    Fields
    ------
    source_id:
        Identifier for the source dataset or corpus (e.g. ``"spy-2020-2024"``).
        For real datasets this is the canonical series ID; for synthetic,
        the ID of the real dataset it was fit on.
    generator_name:
        Registered name of the generator (e.g. ``"gaussian_copula"``,
        ``"timegan"``). For real data, use ``"real"``.
    generator_version:
        Semantic version of the generator implementation. Bumped whenever
        the algorithm's output distribution can change.
    seed:
        Integer RNG seed used for sampling. Required for reproducibility.
    created_at:
        ISO-8601 UTC timestamp (string form). Use
        :func:`iso_now` for a canonical value.
    params:
        Free-form dict of generator hyperparameters used to produce this
        artifact. Must be JSON-serializable.
    """

    source_id: str
    generator_name: str
    generator_version: str
    seed: int
    created_at: str
    params: dict[str, Any] = field(default_factory=dict)


def iso_now() -> str:
    """Canonical ISO-8601 UTC timestamp for `Provenance.created_at`.

    Uses ``datetime.now(timezone.utc).isoformat(timespec='seconds')`` so
    timestamps sort lexicographically and round-trip through JSON cleanly.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


@dataclass
class SyntheticDataset:
    """A time-series dataset (real or synthetic) with provenance.

    `data` may be a numpy array (shape ``(T, N)`` or ``(T,)`` for a single
    series) or a pandas DataFrame. When a DataFrame is supplied, `index` and
    `columns` may be ``None`` (read from the frame). When a numpy array is
    supplied, `index` should hold the timestamps and `columns` the series
    names; both may still be ``None`` for unlabelled data.

    `provenance` is required — see :class:`Provenance`.
    """

    data: SeriesData
    index: Optional[IndexLike] = None
    columns: Optional[list[str]] = None
    provenance: Optional[Provenance] = None


# ---------------------------------------------------------------------------
# Evaluation reports
# ---------------------------------------------------------------------------


@dataclass
class FidelityReport:
    """How well the synthetic marginal / temporal / cross-series / tail
    statistics match the real dataset.

    Each metric dict is keyed by metric name (e.g. ``"ks"``, ``"acf_mae"``)
    with scalar values. `overall_score` is a caller-defined aggregate in
    ``[0, 1]`` (higher is better). `passed` encodes the gate decision.
    """

    marginals: dict[str, float] = field(default_factory=dict)
    temporal: dict[str, float] = field(default_factory=dict)
    cross_series: Optional[dict[str, float]] = None
    tails: dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    passed: bool = False


@dataclass
class PrivacyReport:
    """Privacy risk diagnostics for the synthetic dataset.

    - `nn_leakage`: nearest-neighbour distance stats vs. real set (DCR, NNDR).
    - `memorization`: exact/near-exact copy counts.
    - `membership_proxy`: membership-inference proxy scores (e.g. AUC).
    - `attribute_inference_risk`: per-column accuracy delta above random baseline
      when predicting that column from all others using a shallow decision tree
      trained on synthetic, evaluated on real. High deltas mean the synthetic
      structure leaks attribute relationships.
    - `holdout_leakage_ratio`: train_dcr / holdout_dcr. Values near 1.0 are
      healthy (generator did not over-memorize training set); values >> 1 signal
      that synthetic data clusters around the training split.
    - `tail_exposure_rate`: fraction of real tail records (top/bottom 1%) that
      have a near-neighbour (within 2 sigma) in synthetic data. Outlier
      re-identification is a common privacy failure mode.
    """

    nn_leakage: dict[str, float] = field(default_factory=dict)
    memorization: dict[str, float] = field(default_factory=dict)
    membership_proxy: dict[str, float] = field(default_factory=dict)
    attribute_inference_risk: dict[str, float] = field(default_factory=dict)
    holdout_leakage_ratio: float = 1.0
    tail_exposure_rate: float = 0.0
    overall_score: float = 0.0
    passed: bool = False


@dataclass
class UtilityReport:
    """Train-on-synthetic / test-on-real utility metrics.

    - `trts`: train-real-test-synthetic performance.
    - `tstr`: train-synthetic-test-real performance.
    - `real_baseline`: train-real-test-real baseline for reference.
    - `transfer_gap`: scalar gap (baseline - tstr) — lower is better.
    """

    trts: dict[str, float] = field(default_factory=dict)
    tstr: dict[str, float] = field(default_factory=dict)
    real_baseline: dict[str, float] = field(default_factory=dict)
    transfer_gap: float = 0.0
    passed: bool = False


@dataclass
class Scorecard:
    """Bundled fidelity + privacy + utility report for a dataset pair.

    `dataset` is the synthetic dataset under evaluation. Fidelity, privacy,
    and utility reports may each be ``None`` if that dimension was skipped —
    consumers must check before dereferencing.
    """

    dataset: SyntheticDataset
    fidelity: Optional[FidelityReport] = None
    privacy: Optional[PrivacyReport] = None
    utility: Optional[UtilityReport] = None

    @property
    def passed(self) -> bool:
        """Overall pass iff every present report passed. Missing reports do
        not count against the pass decision (opt-in gates)."""
        reports = [self.fidelity, self.privacy, self.utility]
        present = [r for r in reports if r is not None]
        if not present:
            return False
        return all(r.passed for r in present)


# ---------------------------------------------------------------------------
# Typed interfaces
# ---------------------------------------------------------------------------


@runtime_checkable
class GeneratorProtocol(Protocol):
    """Any synthetic-data generator must satisfy this protocol.

    Lifecycle
    ---------
    1. Instantiate (may take hyperparameters).
    2. Call :meth:`fit` with a real :class:`SyntheticDataset`.
    3. Call :meth:`sample` one or more times with an explicit seed.

    `name` and `version` are class/instance attributes used to populate
    :class:`Provenance`. `version` bumps whenever sampling behavior changes.
    """

    name: str
    version: str

    def fit(self, real: SyntheticDataset) -> None: ...
    def sample(self, n: int, seed: int) -> SyntheticDataset: ...


@runtime_checkable
class ScorecardProtocol(Protocol):
    """A scorecard evaluates a synthetic dataset against the real source.

    Implementations return one of :class:`FidelityReport`,
    :class:`PrivacyReport`, or :class:`UtilityReport`. Aggregating into a
    :class:`Scorecard` is the caller's responsibility.
    """

    def evaluate(
        self, real: SyntheticDataset, synth: SyntheticDataset
    ) -> Union[FidelityReport, PrivacyReport, UtilityReport]: ...


__all__ = [
    "Provenance",
    "SyntheticDataset",
    "FidelityReport",
    "PrivacyReport",
    "UtilityReport",
    "Scorecard",
    "GeneratorProtocol",
    "ScorecardProtocol",
    "iso_now",
]
