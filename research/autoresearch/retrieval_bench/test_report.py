"""Snapshot-style tests for the markdown report writer."""
from __future__ import annotations

from research.autoresearch.retrieval_bench.compare import (
    ComparisonRow,
    Verdict,
    build_comparison_rows,
    decide,
)
from research.autoresearch.retrieval_bench.report import (
    render_markdown,
    write_markdown_report,
)


def _demo_grouped():
    def _r(arm, slice_id, *, corr, crps, cal=0.1, hit=0.6, rt=1.0):
        return {
            "slice_id": slice_id,
            "arm_id": arm,
            "arm_label": arm,
            "n_trials": 10,
            "forward_return_correlation": corr,
            "crps": crps,
            "calibration_error_p10_p90": cal,
            "hit_rate": hit,
            "runtime_seconds": {"median": rt, "mean": rt, "p95": rt, "n": 10},
        }

    return {
        "s1": {
            "tier1_only": _r("tier1_only", "s1", corr=0.1, crps=0.02, rt=0.1),
            "tier1_plus_full": _r("tier1_plus_full", "s1", corr=0.2, crps=0.015, rt=5.0),
        },
        "s2": {
            "tier1_only": _r("tier1_only", "s2", corr=0.0, crps=0.03, rt=0.1),
            "tier1_plus_full": _r("tier1_plus_full", "s2", corr=0.1, crps=0.028, rt=5.0),
        },
    }


def test_render_markdown_includes_verdict_and_table_header():
    grouped = _demo_grouped()
    rows = build_comparison_rows(grouped)
    v = decide(rows, thresholds={"max_runtime_multiplier": 3.0, "min_slices_improved": 2})
    md = render_markdown(v, n_trials=10, seeds=[42])
    assert "Retrieval benchmark" in md
    assert f"Verdict: `{v.decision.upper()}`" in md
    # Table header contains all expected columns
    for col in ("T1 corr", "T1+2 corr", "Δcorr", "ΔCRPS", "rt×"):
        assert col in md


def test_render_markdown_keep_vs_discard_has_different_next_actions():
    grouped = _demo_grouped()
    rows = build_comparison_rows(grouped)
    v_keep = Verdict(
        decision="keep", rationale="test", slices_crps_improved=2, slices_corr_improved=2,
        mean_d_crps=-0.01, mean_d_corr=0.1, mean_runtime_ratio=5.0, rows=rows,
    )
    v_discard = Verdict(
        decision="discard", rationale="test", slices_crps_improved=0, slices_corr_improved=0,
        mean_d_crps=0.0, mean_d_corr=0.0, mean_runtime_ratio=50.0, rows=rows,
    )
    md_keep = render_markdown(v_keep)
    md_discard = render_markdown(v_discard)
    assert "Keep Tier 1+2" in md_keep
    assert "Do NOT change engine defaults" in md_discard


def test_write_markdown_report_roundtrip(tmp_path):
    grouped = _demo_grouped()
    rows = build_comparison_rows(grouped)
    v = decide(rows, thresholds={"max_runtime_multiplier": 3.0, "min_slices_improved": 2})
    path = write_markdown_report(v, tmp_path / "report.md", n_trials=10, seeds=[42])
    assert path.exists()
    text = path.read_text()
    assert "Retrieval benchmark" in text
    assert "`s1`" in text and "`s2`" in text
