"""Synthetic Copies v2 — generator comparison demo.

Shows how to:
  1. Load a source CSV.
  2. Run both generators (block_bootstrap + gaussian_copula, if available).
  3. Score each with fidelity / privacy / utility scorecards.
  4. Compare results and promote the best generator.

Works even if only block_bootstrap is available (the gaussian_copula import
is guarded by try/except so this script runs on any merge state).

Usage:
    python examples/synthetic_copies_comparison.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np

from the_similarity.synthetic.contracts import (
    FidelityReport,
    PrivacyReport,
    Provenance,
    Scorecard,
    SyntheticDataset,
    UtilityReport,
    iso_now,
)
from the_similarity.synthetic.copies import BlockBootstrapGenerator
from the_similarity.synthetic.fidelity import FidelityScorecard
from the_similarity.synthetic.privacy import PrivacyScorecard
from the_similarity.synthetic.utility import UtilityScorecard


# ---------------------------------------------------------------------------
# Optional second generator — Agent 1 may not have landed yet.
# ---------------------------------------------------------------------------

_GaussianCopulaGenerator: Optional[type] = None
try:
    # Agent 1 ships the copula in its own module (copula.py), not copies.py.
    from the_similarity.synthetic.copula import (  # type: ignore[import-not-found]
        GaussianCopulaGenerator,
    )
    _GaussianCopulaGenerator = GaussianCopulaGenerator
except (ImportError, AttributeError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CSV = Path(__file__).resolve().parent.parent / "the_similarity" / "synthetic" / "demos" / "sample.csv"


def load_real() -> SyntheticDataset:
    """Load the bundled sample.csv as a SyntheticDataset."""
    import pandas as pd

    df = pd.read_csv(SAMPLE_CSV)
    return SyntheticDataset(
        data=df,
        columns=list(df.columns),
        provenance=Provenance(
            source_id="sample",
            generator_name="real",
            generator_version="0",
            seed=0,
            created_at=iso_now(),
        ),
    )


def score(
    real: SyntheticDataset, synth: SyntheticDataset
) -> tuple[FidelityReport, PrivacyReport, UtilityReport]:
    """Run all three scorecards and return the reports."""
    fidelity = FidelityScorecard().evaluate(real, synth)
    privacy = PrivacyScorecard().evaluate(real, synth)
    utility = UtilityScorecard().evaluate(real, synth)
    return fidelity, privacy, utility


def print_report(name: str, fidelity: FidelityReport, privacy: PrivacyReport, utility: UtilityReport) -> None:
    """Print a compact summary for one generator."""
    print(f"\n{'='*60}")
    print(f"Generator: {name}")
    print(f"{'='*60}")
    print(f"  Fidelity:  {fidelity.overall_score:.4f}  (passed={fidelity.passed})")
    print(f"  Privacy:   {privacy.overall_score:.4f}  (passed={privacy.passed})")
    print(f"  Utility:   gap={utility.transfer_gap:.4f}  (passed={utility.passed})")
    all_passed = fidelity.passed and privacy.passed and utility.passed
    print(f"  Overall:   {'PASS' if all_passed else 'FAIL'}")


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------

def main() -> None:
    print("Synthetic Copies v2 — Generator Comparison Demo")
    print("-" * 50)

    real = load_real()
    print(f"Loaded real data: {SAMPLE_CSV} ({len(real.data)} rows)")

    # Collect results from each generator for comparison.
    results: dict[str, dict[str, Any]] = {}

    # --- Generator 1: Block Bootstrap (always available) ---
    print("\nRunning block_bootstrap generator...")
    bb_gen = BlockBootstrapGenerator(block_len=10)
    bb_gen.fit(real)
    bb_synth = bb_gen.sample(n=200, seed=42)
    bb_fidelity, bb_privacy, bb_utility = score(real, bb_synth)
    print_report("block_bootstrap", bb_fidelity, bb_privacy, bb_utility)
    results["block_bootstrap"] = {
        "fidelity": bb_fidelity.overall_score,
        "privacy": bb_privacy.overall_score,
        "utility_gap": bb_utility.transfer_gap,
        "all_passed": bb_fidelity.passed and bb_privacy.passed and bb_utility.passed,
    }

    # --- Generator 2: Gaussian Copula (conditional on Agent 1's PR) ---
    if _GaussianCopulaGenerator is not None:
        print("\nRunning gaussian_copula generator...")
        gc_gen = _GaussianCopulaGenerator()
        gc_gen.fit(real)
        gc_synth = gc_gen.sample(n=200, seed=42)
        gc_fidelity, gc_privacy, gc_utility = score(real, gc_synth)
        print_report("gaussian_copula", gc_fidelity, gc_privacy, gc_utility)
        results["gaussian_copula"] = {
            "fidelity": gc_fidelity.overall_score,
            "privacy": gc_privacy.overall_score,
            "utility_gap": gc_utility.transfer_gap,
            "all_passed": gc_fidelity.passed and gc_privacy.passed and gc_utility.passed,
        }
    else:
        print("\n[SKIP] gaussian_copula not available (Agent 1 PR not merged)")

    # --- Comparison and promotion ---
    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")

    if len(results) == 1:
        # Only one generator available — it wins by default.
        winner = list(results.keys())[0]
        print(f"Only one generator available: {winner}")
        print(f"Promoted by default.")
    else:
        # Compare: higher fidelity is better, lower utility gap is better,
        # higher privacy is better. We use a simple composite ranking:
        #   composite = fidelity + privacy - abs(utility_gap)
        # This is a heuristic; a production system would use the
        # ComparisonRunner from Agent 2.
        for name, r in results.items():
            r["composite"] = r["fidelity"] + r["privacy"] - abs(r["utility_gap"])
            print(f"  {name}: composite={r['composite']:.4f} "
                  f"(fid={r['fidelity']:.3f}, priv={r['privacy']:.3f}, "
                  f"gap={r['utility_gap']:.3f})")

        winner = max(results, key=lambda k: results[k]["composite"])
        print(f"\nPromoted generator: {winner}")

    print(f"\nDone. Winner: {winner}")


if __name__ == "__main__":
    main()
