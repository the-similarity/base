"""Integration tests for Copies v2: multi-generator pipeline.

Exercises the end-to-end workflow that Copies v2 introduces:
  1. Load a real CSV dataset.
  2. Run both generators (block_bootstrap + gaussian_copula, falling back
     to block_bootstrap only when Agent 1's GaussianCopulaGenerator has
     not landed yet).
  3. Score each synthetic dataset with all three scorecards (fidelity,
     privacy, utility).
  4. Verify scores fall within valid contract ranges.
  5. Register both runs in a temp registry and verify listing.

Tests use ``try/except ImportError`` for GaussianCopulaGenerator so this
file passes regardless of merge order across parallel agent PRs.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import pytest

from the_similarity.synthetic.contracts import (
    FidelityReport,
    GeneratorProtocol,
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
# Optional GaussianCopulaGenerator import — Agent 1 may not have landed yet.
# ---------------------------------------------------------------------------

_GaussianCopulaGenerator: Optional[type] = None
try:
    # Agent 1 ships the copula in its own module (copula.py), not copies.py.
    from the_similarity.synthetic.copula import (  # type: ignore[import-not-found]
        GaussianCopulaGenerator,
    )

    _GaussianCopulaGenerator = GaussianCopulaGenerator
except (ImportError, AttributeError):
    # Agent 1's PR has not merged yet. Tests that need it will be skipped.
    pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Path to the demo CSV shipped with the synthetic module.
_SAMPLE_CSV = Path(__file__).resolve().parents[1] / "synthetic" / "demos" / "sample.csv"


def _load_real_csv() -> SyntheticDataset:
    """Load sample.csv into a SyntheticDataset with real provenance."""
    import pandas as pd

    df = pd.read_csv(_SAMPLE_CSV)
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


def _generate_synth(
    generator: GeneratorProtocol,
    real: SyntheticDataset,
    n: int = 200,
    seed: int = 42,
) -> SyntheticDataset:
    """Fit a generator on real data and sample n synthetic rows."""
    generator.fit(real)
    return generator.sample(n, seed=seed)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEndToEndScoring:
    """End-to-end: load CSV -> generate -> score -> validate ranges."""

    def test_block_bootstrap_all_scorecards(self) -> None:
        """Block bootstrap + all 3 scorecards produce valid-range scores."""
        real = _load_real_csv()
        gen = BlockBootstrapGenerator(block_len=10)
        synth = _generate_synth(gen, real, n=200, seed=42)

        # Fidelity: overall_score in [0, 1]
        fidelity = FidelityScorecard().evaluate(real, synth)
        assert isinstance(fidelity, FidelityReport)
        assert 0.0 <= fidelity.overall_score <= 1.0
        # Block bootstrap should produce reasonable fidelity on its own source
        # data -- not perfect but not catastrophic.
        assert fidelity.overall_score > 0.1, (
            f"Unexpectedly low fidelity: {fidelity.overall_score}"
        )

        # Privacy: overall_score in [0, 1]
        privacy = PrivacyScorecard().evaluate(real, synth)
        assert isinstance(privacy, PrivacyReport)
        assert 0.0 <= privacy.overall_score <= 1.0

        # Utility: transfer_gap is a real number (can be negative)
        utility = UtilityScorecard().evaluate(real, synth)
        assert isinstance(utility, UtilityReport)
        assert np.isfinite(utility.transfer_gap), (
            f"transfer_gap is not finite: {utility.transfer_gap}"
        )

    @pytest.mark.skipif(
        _GaussianCopulaGenerator is None,
        reason="GaussianCopulaGenerator not available (Agent 1 PR not merged)",
    )
    def test_gaussian_copula_all_scorecards(self) -> None:
        """Gaussian copula + all 3 scorecards produce valid-range scores."""
        real = _load_real_csv()
        gen = _GaussianCopulaGenerator()  # type: ignore[misc]
        synth = _generate_synth(gen, real, n=200, seed=42)

        fidelity = FidelityScorecard().evaluate(real, synth)
        assert 0.0 <= fidelity.overall_score <= 1.0

        privacy = PrivacyScorecard().evaluate(real, synth)
        assert 0.0 <= privacy.overall_score <= 1.0

        utility = UtilityScorecard().evaluate(real, synth)
        assert np.isfinite(utility.transfer_gap)


class TestScorecardComposition:
    """Verify Scorecard aggregation logic with real generator output."""

    def test_scorecard_passed_reflects_all_reports(self) -> None:
        """Scorecard.passed is True only if every present report passed."""
        real = _load_real_csv()
        gen = BlockBootstrapGenerator(block_len=10)
        synth = _generate_synth(gen, real, n=200, seed=42)

        fidelity = FidelityScorecard().evaluate(real, synth)
        privacy = PrivacyScorecard().evaluate(real, synth)
        utility = UtilityScorecard().evaluate(real, synth)

        scorecard = Scorecard(
            dataset=synth,
            fidelity=fidelity,
            privacy=privacy,
            utility=utility,
        )
        # The overall pass must equal the conjunction of individual passes.
        expected = fidelity.passed and privacy.passed and utility.passed
        assert scorecard.passed == expected


class TestRegistryIntegration:
    """Register generator runs in a temp registry and verify listing."""

    def test_register_and_list_block_bootstrap(self) -> None:
        """Register a block_bootstrap run and verify list_runs returns it."""
        # Import the platform registry and adapter.
        from the_similarity.platform.adapters.copies import register_copies_run
        from the_similarity.platform.artifacts import RunKind
        from the_similarity.platform.registry import RunRegistry

        real = _load_real_csv()
        gen = BlockBootstrapGenerator(block_len=10)
        synth = _generate_synth(gen, real, n=200, seed=42)

        # Write artifacts to a temp dir so register_copies_run can read them.
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "bb-run"
            run_dir.mkdir()

            # Write minimal artifacts the adapter expects.
            from the_similarity.synthetic.cli import (
                write_parquets,
                write_provenance,
                write_scorecard,
            )

            fidelity = FidelityScorecard().evaluate(real, synth)
            privacy = PrivacyScorecard().evaluate(real, synth)
            utility = UtilityScorecard().evaluate(real, synth)
            scorecard = Scorecard(
                dataset=synth,
                fidelity=fidelity,
                privacy=privacy,
                utility=utility,
            )
            write_parquets(run_dir, real, synth)
            write_scorecard(run_dir, scorecard)
            write_provenance(run_dir, synth.provenance)

            # Register into a temp DB.
            db_path = Path(tmpdir) / "test_registry.db"
            with RunRegistry(db_path) as reg:
                run_id = register_copies_run(
                    run_dir,
                    source_id="sample",
                    n=200,
                    seed=42,
                    generator="block_bootstrap",
                    registry=reg,
                )
                assert run_id  # non-empty string

                # Verify listing returns the run with kind=COPIES.
                # RunRegistry.list_runs returns RunRecord dataclass instances,
                # not dicts — access fields via attribute, not subscript.
                runs = reg.list_runs(kind=RunKind.COPIES)
                assert len(runs) >= 1
                found = [r for r in runs if r.run_id == run_id]
                assert len(found) == 1
                assert found[0].kind == RunKind.COPIES

    @pytest.mark.skipif(
        _GaussianCopulaGenerator is None,
        reason="GaussianCopulaGenerator not available (Agent 1 PR not merged)",
    )
    def test_register_both_generators(self) -> None:
        """Register both generators and verify list returns both."""
        from the_similarity.platform.adapters.copies import register_copies_run
        from the_similarity.platform.artifacts import RunKind
        from the_similarity.platform.registry import RunRegistry

        real = _load_real_csv()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_registry.db"

            run_ids = []
            for gen_cls, gen_name in [
                (BlockBootstrapGenerator, "block_bootstrap"),
                (_GaussianCopulaGenerator, "gaussian_copula"),
            ]:
                gen = gen_cls(block_len=10) if gen_name == "block_bootstrap" else gen_cls()  # type: ignore[misc]
                synth = _generate_synth(gen, real, n=200, seed=42)

                run_dir = Path(tmpdir) / f"{gen_name}-run"
                run_dir.mkdir()

                from the_similarity.synthetic.cli import (
                    write_parquets,
                    write_provenance,
                    write_scorecard,
                )

                fidelity = FidelityScorecard().evaluate(real, synth)
                privacy = PrivacyScorecard().evaluate(real, synth)
                utility = UtilityScorecard().evaluate(real, synth)
                sc = Scorecard(
                    dataset=synth,
                    fidelity=fidelity,
                    privacy=privacy,
                    utility=utility,
                )
                write_parquets(run_dir, real, synth)
                write_scorecard(run_dir, sc)
                write_provenance(run_dir, synth.provenance)

                with RunRegistry(db_path) as reg:
                    rid = register_copies_run(
                        run_dir,
                        source_id="sample",
                        n=200,
                        seed=42,
                        generator=gen_name,
                        registry=reg,
                    )
                    run_ids.append(rid)

            # Both runs should appear in the listing.
            with RunRegistry(db_path) as reg:
                runs = reg.list_runs(kind=RunKind.COPIES)
                listed_ids = {r.run_id for r in runs}
                for rid in run_ids:
                    assert rid in listed_ids
