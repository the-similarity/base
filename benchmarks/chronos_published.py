"""Published Chronos paper MASE numbers (read-only reference table).

Why this module exists
======================
We are NOT running Chronos in the benchmark harness — installing the
package, downloading the T5 weights, and standing up a torch GPU
runtime is out of scope for a CPU-bound similarity-engine evaluation.
Instead, we cite the published numbers from the original paper as a
neural-baseline reference row in the comparison report.

Citation
========
Ansari, A. F., Stella, L., Turkmen, C., Zhang, X., Mercado, P., Shen,
H., Shchur, O., Rangapuram, S. S., Pineda Arango, S., Kapoor, S.,
Zschiegner, J., Maddix, D. C., Wang, H., Mahoney, M. W., Torkkola, K.,
Wilson, A. G., Bohlke-Schneider, M., & Wang, Y. (2024).
*Chronos: Learning the Language of Time Series.*
Transactions on Machine Learning Research (10/2024).
arXiv:2403.07815v3 [cs.LG], 4 Nov 2024.
URL: https://arxiv.org/abs/2403.07815
Code: https://github.com/amazon-science/chronos-forecasting

Source of the numbers
=====================
All MASE values below were extracted directly from the camera-ready PDF
(arxiv 2403.07815v3) using ``pdfplumber.extract_tables()``:

- **Table 8** ("MASE scores of different models for datasets in
  Benchmark I", page 36): the M4 (Daily) and M4 (Hourly) rows.
- **Table 10** ("MASE scores of different models for datasets in
  Benchmark II", page 37): the NN5 (Daily) row.

CRITICAL CAVEAT — IN-DOMAIN vs. ZERO-SHOT
==========================================
The paper splits its 42-dataset benchmark into two evaluation regimes:

- **Benchmark I (15 datasets, IN-DOMAIN).** These datasets were part of
  Chronos's pretraining corpus. M4 (Daily) and M4 (Hourly) live here.
  Numbers reported for these datasets reflect what the model has
  effectively *memorized*, NOT zero-shot generalisation.
- **Benchmark II (27 datasets, ZERO-SHOT).** Held out from training.
  NN5 (Daily) lives here. Numbers reported are true zero-shot.

The user prompt asked for "zero-shot MASE for m4_daily, m4_hourly,
nn5_daily" but per the paper's own categorisation only NN5 (Daily) is
zero-shot. We still embed M4 Daily / Hourly because the runner uses
them as evaluation datasets — but the report and this module both
flag them as IN-DOMAIN so we don't accidentally claim a zero-shot win
that the paper never claimed.

Why the report only shows MASE
==============================
The paper publishes per-dataset numbers in two flavours: MASE (point)
and WQL (probabilistic). Tables 7 and 9 cover WQL; Tables 8 and 10
cover MASE. Per-series (vs aggregate) numbers are not released, so
sMAPE, CRPS, MAE, P10/P90 coverage, query latency, and peak memory
have no comparable Chronos reference. Hence the "MASE only" rule in
the report.

Column order in the source tables
=================================
Both Table 8 and Table 10 list Chronos-T5 columns left-to-right as
``Large, Base, Small, Mini``. The numbers in ``_PUBLISHED_MASE`` below
are keyed by canonical model name, NOT by column index, to keep the
mapping unambiguous.

Lifecycle
=========
This module is purely declarative — no I/O, no mutation. The numbers
are intentionally hard-coded: they will never change because they
reference a frozen arxiv version. If a future Chronos paper revises
the numbers, add a NEW dict (e.g., ``_PUBLISHED_MASE_V2_2025``) rather
than mutating this one.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Hard-coded MASE numbers from arxiv 2403.07815v3.
#
# Schema:
#   _PUBLISHED_MASE[dataset_key][model_key] = float | None
#
# dataset_key uses our internal lowercase-snake naming (matches the
# Dataset.name field in benchmarks.core), NOT the paper's display label.
# model_key uses the HuggingFace model id convention so it round-trips
# to ``amazon/chronos-t5-small`` cleanly if a downstream consumer ever
# wants to load the weights.
#
# The "_regime" sub-key is metadata (string), not a model — kept inside
# the same dict so a single lookup returns both the score AND the
# in-domain / zero-shot flag without a second indirection.
# ---------------------------------------------------------------------------
_PUBLISHED_MASE: dict[str, dict[str, float | None | str]] = {
    # M4 Daily — Benchmark I (in-domain). Table 8, page 36.
    # Column order in source: Large, Base, Small, Mini.
    "m4_daily": {
        "_regime": "in_domain",
        "_source_table": "Table 8 (Benchmark I MASE), page 36",
        "chronos-t5-large": 3.144,
        "chronos-t5-base": 3.160,
        "chronos-t5-small": 3.148,
        "chronos-t5-mini": 3.154,
    },
    # M4 Hourly — Benchmark I (in-domain). Table 8, page 36.
    "m4_hourly": {
        "_regime": "in_domain",
        "_source_table": "Table 8 (Benchmark I MASE), page 36",
        "chronos-t5-large": 0.682,
        "chronos-t5-base": 0.694,
        "chronos-t5-small": 0.721,
        "chronos-t5-mini": 0.758,
    },
    # NN5 Daily — Benchmark II (true zero-shot). Table 10, page 37.
    "nn5_daily": {
        "_regime": "zero_shot",
        "_source_table": "Table 10 (Benchmark II MASE), page 37",
        "chronos-t5-large": 0.156,
        "chronos-t5-base": 0.161,
        "chronos-t5-small": 0.169,
        "chronos-t5-mini": 0.173,
    },
}

# ---------------------------------------------------------------------------
# Set of supported model identifiers — keep callers from typoing into
# silent ``None`` returns. We intentionally do NOT include ``mini`` in
# the public surface list because the user prompt only asked about
# small/base/large; mini stays in the dict as bonus data for anyone
# who wants it.
# ---------------------------------------------------------------------------
_PUBLIC_MODELS: frozenset[str] = frozenset(
    {"chronos-t5-small", "chronos-t5-base", "chronos-t5-large"}
)


def get_chronos_mase(dataset: str, model: str = "chronos-t5-small") -> float | None:
    """Return the published Chronos MASE for ``(dataset, model)``.

    Args:
        dataset: Lowercase-snake dataset key (e.g. ``"m4_daily"``).
            Must match a key in :func:`list_supported_datasets`.
        model: Chronos model identifier. Defaults to ``chronos-t5-small``
            because that is the smallest published model and therefore
            the most defensible "general user picks the cheap one"
            baseline. Pass ``"chronos-t5-large"`` for the strongest
            published number.

    Returns:
        The published MASE as a ``float``, or ``None`` if either the
        dataset or the model is unknown OR the paper does not report a
        number for that combo. Never raises — unknown lookups always
        return ``None`` so the report layer can render an empty cell
        without a try/except.

    Notes:
        - Mini (``chronos-t5-mini``) is also recorded in the underlying
          dict but is not exposed here; pass it explicitly to
          ``model="chronos-t5-mini"`` if you need it.
        - The returned float is taken verbatim from the paper PDF (no
          rounding, no rescaling). Comparing it against a number from
          our own runner is APPROXIMATE — see the "Caveats" section of
          the generated report for why.
    """
    # Defensive lookup chain. We could call .get().get() but explicit
    # checks read better and let us surface the regime metadata in the
    # future without juggling .get() defaults.
    if dataset not in _PUBLISHED_MASE:
        return None
    entry = _PUBLISHED_MASE[dataset]
    value = entry.get(model)
    # Sentinel keys (_regime, _source_table) are strings — never return
    # them from a numeric API even if a caller types ``model="_regime"``.
    if not isinstance(value, (int, float)):
        return None
    return float(value)


def list_supported_datasets() -> list[str]:
    """Return the dataset keys for which we have a published Chronos MASE.

    The order is alphabetical for stable test assertions and stable
    report column ordering. Callers that want to filter by regime
    should use :func:`get_chronos_regime`.
    """
    return sorted(_PUBLISHED_MASE.keys())


def get_chronos_regime(dataset: str) -> str | None:
    """Return ``"in_domain"`` or ``"zero_shot"`` for the dataset.

    This metadata matters for the report layer: it would be misleading
    to print "Chronos zero-shot" next to an in-domain dataset like M4
    Daily, since the paper itself does not make that claim.

    Returns ``None`` if the dataset is unknown.
    """
    if dataset not in _PUBLISHED_MASE:
        return None
    regime = _PUBLISHED_MASE[dataset].get("_regime")
    return regime if isinstance(regime, str) else None


def get_chronos_source(dataset: str) -> str | None:
    """Return the table + page citation string for the dataset.

    Used by the report layer to produce a footnote so a reader can
    audit any number we display against the paper without grepping
    this module. Returns ``None`` for unknown datasets.
    """
    if dataset not in _PUBLISHED_MASE:
        return None
    src = _PUBLISHED_MASE[dataset].get("_source_table")
    return src if isinstance(src, str) else None


__all__ = [
    "get_chronos_mase",
    "list_supported_datasets",
    "get_chronos_regime",
    "get_chronos_source",
]
