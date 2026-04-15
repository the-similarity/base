"""Synthetic data module — public surface.

Re-exports the stable contract types defined in :mod:`.contracts`. Downstream
code should import from ``the_similarity.synthetic`` (not the submodule) so
the implementation can move without breaking consumers.
"""
from the_similarity.synthetic.contracts import (
    FidelityReport,
    GeneratorProtocol,
    PrivacyReport,
    Provenance,
    Scorecard,
    ScorecardProtocol,
    SyntheticDataset,
    UtilityReport,
    iso_now,
)
from the_similarity.synthetic.fidelity import FidelityScorecard
from the_similarity.synthetic.privacy import PrivacyScorecard

__all__ = [
    "FidelityReport",
    "FidelityScorecard",
    "GeneratorProtocol",
    "PrivacyReport",
    "PrivacyScorecard",
    "Provenance",
    "Scorecard",
    "ScorecardProtocol",
    "SyntheticDataset",
    "UtilityReport",
    "iso_now",
]
