"""Tests for the benchmark reporting layer.

Two surfaces under test, both small and pure:

1. ``benchmarks.chronos_published`` — declarative reference table.
   We assert the embedded MASE numbers match what we extracted from
   the paper PDF (so a typo during a future edit fails CI loud), and
   that unknown lookups return ``None`` instead of raising.

2. ``benchmarks.report.build_report`` — JSONL → Markdown renderer.
   We synthesise a tiny ``raw.jsonl`` (2 systems × 1 dataset × 1
   horizon × 3 series), invoke both the library function and the CLI
   (via ``main(argv)``), and assert specific structural + numerical
   facts about the output. The numbers are hand-computed in the test
   so a regression in the aggregator is immediately localised.

Why hand-computed values instead of golden-file diff?
    Golden files drift the moment a metric format changes (4dp ↔ 5dp)
    and force unrelated PRs to regen them. Hand-computing the few
    values we actually care about means tests fail for the RIGHT
    reasons.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks import chronos_published, report


# ---------------------------------------------------------------------------
# chronos_published — pure data, pure assertions.
# ---------------------------------------------------------------------------
class TestChronosPublished:
    """Pin the verbatim MASE table to the values extracted from arxiv."""

    def test_nn5_daily_small_matches_paper_table_10(self) -> None:
        # arxiv 2403.07815v3 Table 10 (Benchmark II MASE), page 37,
        # NN5 (Daily) row, Chronos-T5-Small column = 0.169.
        assert chronos_published.get_chronos_mase(
            "nn5_daily", "chronos-t5-small"
        ) == pytest.approx(0.169)

    def test_nn5_daily_large_matches_paper_table_10(self) -> None:
        # Same row, Chronos-T5-Large column = 0.156.
        assert chronos_published.get_chronos_mase(
            "nn5_daily", "chronos-t5-large"
        ) == pytest.approx(0.156)

    def test_m4_daily_small_matches_paper_table_8(self) -> None:
        # arxiv 2403.07815v3 Table 8 (Benchmark I MASE), page 36,
        # M4 (Daily) row, Chronos-T5-Small column = 3.148.
        assert chronos_published.get_chronos_mase(
            "m4_daily", "chronos-t5-small"
        ) == pytest.approx(3.148)

    def test_m4_hourly_base_matches_paper_table_8(self) -> None:
        # Table 8, M4 (Hourly) row, Chronos-T5-Base column = 0.694.
        assert chronos_published.get_chronos_mase(
            "m4_hourly", "chronos-t5-base"
        ) == pytest.approx(0.694)

    def test_default_model_is_chronos_t5_small(self) -> None:
        # The convenience default should hit the small model so callers
        # who omit the kwarg get a stable, cheapest-baseline number.
        explicit = chronos_published.get_chronos_mase("nn5_daily", "chronos-t5-small")
        default = chronos_published.get_chronos_mase("nn5_daily")
        assert explicit == default

    def test_unknown_dataset_returns_none(self) -> None:
        # Never raise on unknown lookups — the report layer relies on
        # this to render an empty cell instead of crashing.
        assert chronos_published.get_chronos_mase("not_a_real_dataset") is None

    def test_unknown_model_returns_none(self) -> None:
        assert chronos_published.get_chronos_mase("nn5_daily", "gpt-99-xxxl") is None

    def test_sentinel_keys_do_not_leak_through(self) -> None:
        # The internal _regime / _source_table sentinels are strings.
        # If a caller types model="_regime" we must still return None,
        # not the regime label.
        assert chronos_published.get_chronos_mase("nn5_daily", "_regime") is None

    def test_list_supported_datasets_is_alphabetical(self) -> None:
        ds = chronos_published.list_supported_datasets()
        assert ds == sorted(ds)
        # Lock the membership so an accidental deletion fails CI.
        assert set(ds) == {"m4_daily", "m4_hourly", "nn5_daily"}

    def test_regime_classification_matches_paper(self) -> None:
        # Per the paper M4 datasets are Benchmark I (in-domain),
        # NN5 is Benchmark II (zero-shot). Misrepresenting either
        # way would invalidate the report's "zero-shot" claim.
        assert chronos_published.get_chronos_regime("m4_daily") == "in_domain"
        assert chronos_published.get_chronos_regime("m4_hourly") == "in_domain"
        assert chronos_published.get_chronos_regime("nn5_daily") == "zero_shot"
        assert chronos_published.get_chronos_regime("not_real") is None

    def test_source_table_citations_present(self) -> None:
        # Each dataset must carry a non-empty source citation so the
        # report layer can emit auditable footnotes.
        for ds in chronos_published.list_supported_datasets():
            src = chronos_published.get_chronos_source(ds)
            assert isinstance(src, str)
            assert "Table" in src and "page" in src


# ---------------------------------------------------------------------------
# report — synthetic JSONL fixture + structural + numerical assertions.
# ---------------------------------------------------------------------------
def _write_synthetic_jsonl(path: Path) -> None:
    """Write 2 systems × 1 dataset × 1 horizon × 3 series.

    Hand-picked numbers below are designed so the per-column means /
    medians / maxes are easy to verify by inspection in the assertion
    block. The "fast_baseline" system wins latency + memory; the
    "the_similarity" system wins all error metrics; coverage is exactly
    0.80 for the_similarity (perfect) and 0.60 for fast_baseline.
    """
    # the_similarity per-series: MAE 0.40/0.60/0.50 → mean 0.50.
    sim_rows = [
        {
            "dataset": "nn5_daily",
            "series_id": "S1",
            "system": "the_similarity",
            "horizon": 7,
            "mae": 0.40,
            "smape": 10.0,
            "crps": 0.30,
            "mase": 0.18,
            "coverage_p10_p90": 0.80,
            "query_ms": 20.0,
            "peak_mb": 100.0,
        },
        {
            "dataset": "nn5_daily",
            "series_id": "S2",
            "system": "the_similarity",
            "horizon": 7,
            "mae": 0.60,
            "smape": 14.0,
            "crps": 0.50,
            "mase": 0.22,
            "coverage_p10_p90": 0.80,
            "query_ms": 25.0,
            "peak_mb": 110.0,
        },
        {
            "dataset": "nn5_daily",
            "series_id": "S3",
            "system": "the_similarity",
            "horizon": 7,
            "mae": 0.50,
            "smape": 12.0,
            "crps": 0.40,
            "mase": 0.20,
            "coverage_p10_p90": 0.80,
            "query_ms": 30.0,
            "peak_mb": 120.0,
        },
    ]
    # fast_baseline per-series: MAE 0.80/0.90/1.00 → mean 0.90.
    base_rows = [
        {
            "dataset": "nn5_daily",
            "series_id": "S1",
            "system": "fast_baseline",
            "horizon": 7,
            "mae": 0.80,
            "smape": 20.0,
            "crps": 0.70,
            "mase": 0.40,
            "coverage_p10_p90": 0.60,
            "query_ms": 0.5,
            "peak_mb": 5.0,
        },
        {
            "dataset": "nn5_daily",
            "series_id": "S2",
            "system": "fast_baseline",
            "horizon": 7,
            "mae": 0.90,
            "smape": 22.0,
            "crps": 0.80,
            "mase": 0.45,
            "coverage_p10_p90": 0.60,
            "query_ms": 1.0,
            "peak_mb": 6.0,
        },
        {
            "dataset": "nn5_daily",
            "series_id": "S3",
            "system": "fast_baseline",
            "horizon": 7,
            "mae": 1.00,
            "smape": 24.0,
            "crps": 0.90,
            "mase": 0.50,
            "coverage_p10_p90": 0.60,
            "query_ms": 1.5,
            "peak_mb": 7.0,
        },
    ]
    with path.open("w", encoding="utf-8") as fh:
        for row in sim_rows + base_rows:
            fh.write(json.dumps(row) + "\n")


class TestBuildReport:
    """Library + CLI report rendering."""

    def test_headers_present(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.jsonl"
        _write_synthetic_jsonl(raw)
        md = report.build_report(raw)
        # Title + section + caveats footer are non-negotiable.
        assert "# Benchmark report" in md
        assert "### nn5_daily — horizon 7" in md
        assert "## Caveats" in md

    def test_table_columns_in_spec_order(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.jsonl"
        _write_synthetic_jsonl(raw)
        md = report.build_report(raw)
        # The header row should list every metric column in the order
        # declared by benchmarks/report.py::_COLUMNS.
        expected_header = (
            "| System | MAE | sMAPE | CRPS | MASE | "
            "P10/P90 cov. | median query ms | peak MB |"
        )
        assert expected_header in md

    def test_both_system_names_appear(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.jsonl"
        _write_synthetic_jsonl(raw)
        md = report.build_report(raw)
        assert "the_similarity" in md
        assert "fast_baseline" in md

    def test_aggregated_mae_means_are_correct(self, tmp_path: Path) -> None:
        # Hand-computed:
        #   the_similarity MAE mean = (0.40 + 0.60 + 0.50) / 3 = 0.5000
        #   fast_baseline  MAE mean = (0.80 + 0.90 + 1.00) / 3 = 0.9000
        raw = tmp_path / "raw.jsonl"
        _write_synthetic_jsonl(raw)
        md = report.build_report(raw)
        assert "0.5000" in md  # the_similarity (and bolded as winner)
        assert "0.9000" in md  # fast_baseline

    def test_query_ms_is_median_not_mean(self, tmp_path: Path) -> None:
        # the_similarity query_ms = [20.0, 25.0, 30.0] → median 25.0.
        # If we accidentally took the mean we would get 25.0 too — so
        # we use fast_baseline where median (1.0) and mean (1.0) also
        # coincide. To actually distinguish median vs mean, we add a
        # skewed series and re-check.
        raw = tmp_path / "raw.jsonl"
        rows = [
            {
                "dataset": "tiny",
                "series_id": "A",
                "system": "skewed",
                "horizon": 1,
                "mae": 0.0,
                "smape": 0.0,
                "crps": 0.0,
                "mase": 0.0,
                "coverage_p10_p90": 0.8,
                "query_ms": 1.0,
                "peak_mb": 1.0,
            },
            {
                "dataset": "tiny",
                "series_id": "B",
                "system": "skewed",
                "horizon": 1,
                "mae": 0.0,
                "smape": 0.0,
                "crps": 0.0,
                "mase": 0.0,
                "coverage_p10_p90": 0.8,
                "query_ms": 2.0,
                "peak_mb": 1.0,
            },
            {
                "dataset": "tiny",
                "series_id": "C",
                "system": "skewed",
                "horizon": 1,
                "mae": 0.0,
                "smape": 0.0,
                "crps": 0.0,
                "mase": 0.0,
                "coverage_p10_p90": 0.8,
                "query_ms": 1000.0,  # cold-cache outlier
                "peak_mb": 1.0,
            },
        ]
        with raw.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        md = report.build_report(raw)
        # Median of [1, 2, 1000] is 2.0; mean would be ~334.3. The
        # report formatter prints 1 dp; with a single system every
        # cell is the column-winner and gets bolded as **2.0**.
        assert "**2.0**" in md  # median (bolded as winner)
        assert "334.3" not in md  # would imply mean
        assert "1000.0" not in md  # would imply max

    def test_peak_mb_is_max_across_series(self, tmp_path: Path) -> None:
        # the_similarity peak_mb = max(100, 110, 120) = 120.0.
        raw = tmp_path / "raw.jsonl"
        _write_synthetic_jsonl(raw)
        md = report.build_report(raw)
        # 120.0 should appear in the_similarity row; if we took mean we
        # would see 110.0 instead.
        assert "120.0" in md

    def test_chronos_row_appears_for_nn5_daily(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.jsonl"
        _write_synthetic_jsonl(raw)
        md = report.build_report(raw)
        # Label uses zero-shot for NN5 per paper categorisation.
        assert "Chronos-T5-small (published, zero-shot)" in md
        # Published MASE for nn5_daily/small = 0.169.
        assert "0.169" in md

    def test_chronos_row_omitted_for_unknown_dataset(self, tmp_path: Path) -> None:
        # SPY-style synthetic dataset not in the Chronos paper.
        raw = tmp_path / "raw.jsonl"
        with raw.open("w", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "dataset": "spy_daily",
                        "series_id": "SPY",
                        "system": "the_similarity",
                        "horizon": 5,
                        "mae": 1.0,
                        "smape": 5.0,
                        "crps": 0.5,
                        "mase": 0.9,
                        "coverage_p10_p90": 0.8,
                        "query_ms": 10.0,
                        "peak_mb": 50.0,
                    }
                )
                + "\n"
            )
        md = report.build_report(raw)
        assert "spy_daily" in md
        # No Chronos REFERENCE ROW for SPY (the intro paragraph
        # always mentions "Chronos" — that's not what we are guarding
        # against). The reference row label is unmistakable.
        assert "Chronos-T5-small (published," not in md

    def test_caveats_footer_is_present(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.jsonl"
        _write_synthetic_jsonl(raw)
        md = report.build_report(raw)
        # All four bullet anchors from _CAVEATS:
        assert "Chronos numbers are paper-aggregate" in md
        assert "default config, no tuning" in md
        assert "SPY / BTC have no Chronos comparison" in md
        assert "Pretraining contamination" in md

    def test_winning_cells_are_bolded(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.jsonl"
        _write_synthetic_jsonl(raw)
        md = report.build_report(raw)
        # the_similarity wins MAE (0.5000 < 0.9000) → must be bolded.
        assert "**0.5000**" in md
        # fast_baseline wins peak_mb (max 7.0 < the_similarity max 120.0)
        # → 7.0 must be bolded.
        assert "**7.0**" in md

    def test_empty_jsonl_renders_placeholder(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.jsonl"
        raw.write_text("", encoding="utf-8")
        md = report.build_report(raw)
        assert "_No results in raw.jsonl yet._" in md
        # Caveats still present so the artefact is well-formed.
        assert "## Caveats" in md

    def test_missing_jsonl_renders_placeholder(self, tmp_path: Path) -> None:
        # Path that does not exist → same as empty file.
        md = report.build_report(tmp_path / "missing.jsonl")
        assert "_No results in raw.jsonl yet._" in md

    def test_malformed_jsonl_raises_with_line_number(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.jsonl"
        raw.write_text("not json at all\n", encoding="utf-8")
        with pytest.raises(ValueError, match=r":1:"):
            report.build_report(raw)

    def test_missing_required_keys_raises(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.jsonl"
        # Missing 'mase' and 'peak_mb'.
        raw.write_text(
            json.dumps(
                {
                    "dataset": "x",
                    "series_id": "A",
                    "system": "y",
                    "horizon": 1,
                    "mae": 0.1,
                    "smape": 1.0,
                    "crps": 0.1,
                    "coverage_p10_p90": 0.8,
                    "query_ms": 1.0,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="missing required keys"):
            report.build_report(raw)

    def test_cli_writes_output_file(self, tmp_path: Path) -> None:
        raw = tmp_path / "raw.jsonl"
        out = tmp_path / "REPORT.md"
        _write_synthetic_jsonl(raw)
        rc = report.main(["--raw", str(raw), "--out", str(out)])
        assert rc == 0
        assert out.exists()
        body = out.read_text(encoding="utf-8")
        assert "# Benchmark report" in body
        assert "Chronos-T5-small (published, zero-shot)" in body
