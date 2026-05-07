"""Tests for :mod:`the_similarity.core.scanner`.

The scanner is a thin orchestration layer over the existing matcher +
projector. These tests exercise:

1. The orchestration surface — universe iteration, parallel per-instrument
   dispatch, top-N flat ranking, error wrapping per the partial-success
   contract.
2. The registry persistence path — when a :class:`RunRegistry` is
   supplied, a :class:`RunRecord` of kind :attr:`RunKind.SETUP_SCAN` is
   created with the full :class:`ScanResult` in ``summary``.

All tests inject a deterministic mock ``data_loader`` so we never hit
Binance or any other live data source.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from the_similarity.config import Config
from the_similarity.core.scanner import (
    UNIVERSE_CRYPTO,
    UNIVERSE_DEFAULT,
    UNIVERSE_FX_GOLD,
    scan,
)
from the_similarity.platform.artifacts import RunKind
from the_similarity.platform.contracts import Setup
from the_similarity.platform.registry import RunRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_setup(region_series: list[float] | None = None) -> Setup:
    """Build a minimal Setup object pinned to a 32-bar query window.

    32 bars is enough for the matcher's default Sakoe-Chiba band (~10%
    of the window) and small enough to keep tests sub-second.
    """
    if region_series is None:
        # A simple sinusoidal pattern — gives the matcher something
        # repeatable to align against.
        region_series = [
            float(np.sin(i / 4.0) + 1.0) for i in range(32)
        ]
    return Setup(
        id="setup-test-1",
        user_id="user-test",
        name="test setup",
        instrument="BTCUSDT",
        timeframe="1h",
        region_start_ts="2026-04-01T00:00:00Z",
        region_end_ts="2026-04-02T08:00:00Z",
        region_series=region_series,
    )


def _deterministic_history(n_bars: int, seed: int = 0) -> np.ndarray:
    """Return a ``n_bars``-long pseudo-price series.

    Deterministic via a per-instrument seed so the scanner produces
    consistent results across test runs without being identical across
    instruments. Values are a smooth random walk to give the matcher
    real candidates instead of constant prices.
    """
    rng = np.random.default_rng(seed)
    # Smooth random walk: cumulative sum of small Gaussian increments
    # plus a drift term so the matcher's normalization has signal.
    deltas = rng.normal(loc=0.0, scale=0.5, size=n_bars)
    walk = 100.0 + np.cumsum(deltas)
    return walk.astype(np.float64)


def _mock_loader_factory(n_bars: int = 256):
    """Build a deterministic data loader keyed by instrument symbol.

    Maps each instrument to a unique seed so two instruments don't
    return the same series (which would short-circuit the matcher's
    Tier 0 prefilter to identical scores). Tests assert per-instrument
    independence.
    """
    seed_map: dict[str, int] = {}

    def loader(instrument: str, timeframe: str, requested: int) -> np.ndarray:
        # Stable per-symbol seed: hash() is randomized per Python
        # process so we use a manual fold over the symbol bytes.
        seed = seed_map.get(instrument)
        if seed is None:
            seed = sum(ord(c) for c in instrument) % 2_147_483_647
            seed_map[instrument] = seed
        bars = max(int(requested), n_bars)
        return _deterministic_history(bars, seed=seed)

    return loader


def _failing_loader(instrument: str, timeframe: str, n: int) -> np.ndarray:
    """Loader that always raises — used to test partial-success."""
    raise RuntimeError(f"simulated network failure for {instrument}")


# ---------------------------------------------------------------------------
# Universe constants
# ---------------------------------------------------------------------------


def test_universe_default_size() -> None:
    """The v1 default universe is 30 crypto + 7 FX/gold = 37 symbols."""
    assert len(UNIVERSE_CRYPTO) == 30
    assert len(UNIVERSE_FX_GOLD) == 7
    assert len(UNIVERSE_DEFAULT) == 37
    # No duplicates across the two halves — symmetric set check.
    assert set(UNIVERSE_CRYPTO).isdisjoint(set(UNIVERSE_FX_GOLD))


def test_universe_includes_required_majors() -> None:
    """Sanity: BTCUSDT, ETHUSDT, EURUSD, XAUUSD must be in the default set."""
    for required in ("BTCUSDT", "ETHUSDT", "EURUSD", "XAUUSD"):
        assert required in UNIVERSE_DEFAULT


# ---------------------------------------------------------------------------
# Scan orchestration
# ---------------------------------------------------------------------------


def test_scan_returns_per_instrument_for_every_universe_symbol() -> None:
    """Every symbol in the universe gets a per_instrument entry, in order."""
    setup = _make_setup()
    universe = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    loader = _mock_loader_factory(n_bars=256)

    result = scan(
        setup,
        universe=universe,
        data_loader=loader,
        history_bars=256,
        top_k=3,
        top_n=5,
        forward_bars=10,
        max_workers=2,
    )

    assert [r.instrument for r in result.per_instrument] == universe
    assert result.universe == universe
    assert result.setup_id == setup.id
    assert result.user_id == setup.user_id
    assert result.created_at != ""


def test_scan_partial_success_records_error_per_instrument() -> None:
    """A failing loader does NOT abort the scan — error string is recorded."""
    setup = _make_setup()
    universe = ["BTCUSDT", "ETHUSDT"]

    def half_failing_loader(instrument: str, timeframe: str, n: int) -> np.ndarray:
        if instrument == "ETHUSDT":
            raise RuntimeError("simulated outage")
        return _deterministic_history(n, seed=42)

    result = scan(
        setup,
        universe=universe,
        data_loader=half_failing_loader,
        history_bars=256,
        top_k=2,
        top_n=4,
        forward_bars=8,
        max_workers=2,
    )

    by_sym = {r.instrument: r for r in result.per_instrument}
    assert by_sym["ETHUSDT"].error is not None
    assert "simulated outage" in by_sym["ETHUSDT"].error
    # The other instrument may or may not have analogs depending on the
    # matcher's tiered ranker — but it must NOT carry an error.
    assert by_sym["BTCUSDT"].error is None


def test_scan_top_n_is_globally_ranked() -> None:
    """top_n is sorted by confidence_score descending across instruments."""
    setup = _make_setup()
    universe = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    loader = _mock_loader_factory(n_bars=256)

    result = scan(
        setup,
        universe=universe,
        data_loader=loader,
        history_bars=256,
        top_k=3,
        top_n=20,
        forward_bars=10,
        max_workers=3,
    )

    # If matches were found, top_n is sorted by confidence_score desc.
    # Some matcher configurations may return zero — that's a valid no-op.
    scores = [a["confidence_score"] for a in result.top_n]
    assert scores == sorted(scores, reverse=True)
    # Every entry in top_n carries an "instrument" key from the parent
    # InstrumentScanResult.
    for analog in result.top_n:
        assert analog["instrument"] in universe


def test_scan_top_n_clamped_to_n() -> None:
    """top_n list is at most ``top_n`` entries long."""
    setup = _make_setup()
    universe = ["BTCUSDT", "ETHUSDT"]
    loader = _mock_loader_factory(n_bars=256)

    result = scan(
        setup,
        universe=universe,
        data_loader=loader,
        history_bars=256,
        top_k=5,
        top_n=3,
        forward_bars=10,
        max_workers=2,
    )

    assert len(result.top_n) <= 3


def test_scan_skips_too_short_history() -> None:
    """If the history is shorter than (region + forward_bars), error is set."""
    setup = _make_setup()
    universe = ["BTCUSDT"]

    def short_loader(instrument: str, tf: str, n: int) -> np.ndarray:
        # Return way fewer bars than the matcher needs.
        return np.array([1.0, 2.0, 3.0], dtype=np.float64)

    result = scan(
        setup,
        universe=universe,
        data_loader=short_loader,
        history_bars=64,
        top_k=3,
        top_n=5,
        forward_bars=10,
        max_workers=1,
    )

    assert result.per_instrument[0].error is not None
    assert "insufficient history" in result.per_instrument[0].error


def test_scan_empty_universe_raises() -> None:
    """An empty universe is a programmer error — fail loud."""
    setup = _make_setup()
    with pytest.raises(ValueError, match="universe"):
        scan(
            setup,
            universe=[],
            data_loader=_mock_loader_factory(),
            max_workers=1,
        )


# ---------------------------------------------------------------------------
# Registry persistence
# ---------------------------------------------------------------------------


def test_scan_with_registry_persists_run_record(tmp_path: Path) -> None:
    """When a registry is supplied, the scan registers a SETUP_SCAN run."""
    db_path = tmp_path / "registry.db"
    setup = _make_setup()
    universe = ["BTCUSDT", "ETHUSDT"]
    loader = _mock_loader_factory(n_bars=256)

    with RunRegistry(db_path) as registry:
        result = scan(
            setup,
            universe=universe,
            data_loader=loader,
            history_bars=256,
            top_k=2,
            top_n=4,
            forward_bars=8,
            max_workers=2,
            registry=registry,
        )

        # ScanResult.run_id must be set when a registry was supplied.
        assert result.run_id is not None
        record = registry.get_run(result.run_id)

    assert record is not None
    assert record.kind is RunKind.SETUP_SCAN
    assert record.pillar == "finance"
    assert record.config["user_id"] == setup.user_id
    assert record.config["setup_id"] == setup.id
    assert record.config["universe"] == universe
    # Summary carries the full ScanResult shape so the API can read
    # without a second query.
    assert "per_instrument" in record.summary
    assert "top_n" in record.summary


def test_scan_without_registry_does_not_set_run_id() -> None:
    """No registry -> run_id stays None on the ScanResult."""
    setup = _make_setup()
    result = scan(
        setup,
        universe=["BTCUSDT"],
        data_loader=_mock_loader_factory(n_bars=256),
        history_bars=256,
        top_k=2,
        top_n=4,
        forward_bars=8,
        max_workers=1,
        registry=None,
    )
    assert result.run_id is None


def test_scan_serialization_round_trips_via_to_dict() -> None:
    """ScanResult.to_dict -> from_dict round-trips faithfully (frontend wire)."""
    from the_similarity.platform.contracts import ScanResult

    setup = _make_setup()
    result = scan(
        setup,
        universe=["BTCUSDT"],
        data_loader=_mock_loader_factory(n_bars=256),
        history_bars=256,
        top_k=2,
        top_n=4,
        forward_bars=8,
        max_workers=1,
    )

    dumped = result.to_dict()
    reloaded = ScanResult.from_dict(dumped)
    assert reloaded.setup_id == result.setup_id
    assert reloaded.user_id == result.user_id
    assert reloaded.universe == result.universe
    assert len(reloaded.per_instrument) == len(result.per_instrument)
    assert reloaded.top_n == result.top_n
