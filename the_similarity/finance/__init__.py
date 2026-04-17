"""Finance subpackage — review artifacts, risk flags, and signal summaries.

This package provides the structured artifact layer for the finance pillar's
operating product. It sits between the raw backtest outputs (see
``the_similarity/core/backtester.py``) and the customer-facing API (see
``the-similarity-api/app/platform_routes.py``).

Key components
--------------
:class:`ReviewArtifact`
    A human-or-agent review decision on a finance run. Captures the
    reviewer's verdict (approved / flagged / rejected), risk flags,
    signal summary, and optional post-hoc realized outcomes.

:class:`ReviewStatus`
    Enum for the review lifecycle: PENDING -> APPROVED / FLAGGED / REJECTED.

:func:`detect_risk_flags`
    Auto-detects risk conditions from a BacktestReport summary dict.

:func:`generate_signal_summary`
    Produces a one-line human-readable summary of what a finance run found.
"""

from the_similarity.finance.review import ReviewArtifact, ReviewStatus
from the_similarity.finance.risk_flags import detect_risk_flags
from the_similarity.finance.signal_summary import generate_signal_summary

__all__ = [
    "ReviewArtifact",
    "ReviewStatus",
    "detect_risk_flags",
    "generate_signal_summary",
]
