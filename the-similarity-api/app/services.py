from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

import numpy as np

import the_similarity
from the_similarity.contracts.api import (
    CalibrationMetricsResponse,
    ConfidenceBreakdownItem,
    DashboardDataResponse,
    ForecastBands,
    ForecastResponse,
    HeroContent,
    MatchCard,
    MatchResultResponse,
    ModuleCard,
    RangeView,
    ReliabilityBucketResponse,
    ScoreBreakdownResponse,
    SearchRequest,
    SearchResponse,
)


def create_series(
    length: int,
    start: float,
    slope: float,
    amplitude: float,
    frequency: float,
    phase: float,
) -> list[float]:
    values = []
    for index in range(length):
        wave = np.sin(index * frequency + phase) * amplitude
        harmonic = np.cos(index * frequency * 0.55 + phase * 0.5) * amplitude * 0.32
        values.append(round(start + index * slope + wave + harmonic, 2))
    return values


def build_forecast(
    anchor: float,
    length: int,
    slope: float,
    amplitude: float,
    phase: float,
) -> ForecastBands:
    median = []
    for index in range(length):
        point = index + 1
        value = (
            anchor
            + point * slope
            + np.sin(point * 0.48 + phase) * amplitude
            + np.cos(point * 0.24 + phase) * amplitude * 0.35
        )
        median.append(round(value, 2))

    p10 = [round(value - 2.4 - index * 0.18, 2) for index, value in enumerate(median)]
    p90 = [round(value + 2.4 + index * 0.22, 2) for index, value in enumerate(median)]
    return ForecastBands(p10=p10, p50=median, p90=p90)


def build_range_view(
    label: str,
    query_config: tuple[int, float, float, float, float, float],
    match_config: tuple[int, float, float, float, float, float],
    forecast_config: tuple[int, float, float, float],
) -> RangeView:
    query = create_series(*query_config)
    best_match = create_series(*match_config)
    anchor = query[-1]
    forecast = build_forecast(anchor, *forecast_config)
    return RangeView(label=label, query=query, best_match=best_match, forecast=forecast)


def get_dashboard_payload() -> DashboardDataResponse:
    return DashboardDataResponse(
        data_source="api",
        hero=HeroContent(
            eyebrow="The Similarity dashboard",
            title="Pattern search, confidence scoring, and forecast cones in one research desk.",
            description=(
                "This backend payload mirrors the future split-repo contract and is served "
                "from FastAPI instead of local mock modules."
            ),
            badges=["FastAPI", "Pydantic", "Contract-first"],
        ),
        ranges=["1D", "1W", "1M", "3M", "1Y", "ALL"],
        default_range="3M",
        views={
            "1D": build_range_view(
                "Intraday scan",
                (24, 101.6, 0.28, 1.25, 0.54, 0.6),
                (24, 100.9, 0.26, 1.1, 0.56, 0.75),
                (8, 0.21, 0.7, 0.8),
            ),
            "1W": build_range_view(
                "Weekly shape",
                (26, 98.8, 0.42, 1.6, 0.42, 0.25),
                (26, 98.1, 0.39, 1.44, 0.44, 0.36),
                (8, 0.34, 0.86, 0.55),
            ),
            "1M": build_range_view(
                "Monthly analog",
                (28, 96.3, 0.55, 2.1, 0.33, 0.2),
                (28, 95.6, 0.5, 1.9, 0.34, 0.28),
                (10, 0.46, 1.05, 0.45),
            ),
            "3M": build_range_view(
                "Quarterly setup",
                (30, 92.4, 0.66, 2.45, 0.26, 0.18),
                (30, 91.7, 0.62, 2.2, 0.25, 0.26),
                (12, 0.59, 1.18, 0.38),
            ),
            "1Y": build_range_view(
                "Annual structure",
                (32, 84.2, 0.94, 3.3, 0.19, 0.18),
                (32, 83.5, 0.9, 2.95, 0.18, 0.26),
                (12, 0.84, 1.45, 0.34),
            ),
            "ALL": build_range_view(
                "Full history",
                (34, 76.8, 1.12, 4.2, 0.14, 0.16),
                (34, 75.9, 1.08, 3.8, 0.13, 0.24),
                (14, 1.06, 1.72, 0.28),
            ),
        },
        top_matches=[
            MatchCard(
                label="Primary analog",
                window="2019-05-03 -> 2019-08-14",
                score=86.4,
                delta=5.8,
                method="DTW + Pearson",
                regime="trending_up",
            ),
            MatchCard(
                label="Volatility twin",
                window="2020-10-19 -> 2021-01-28",
                score=82.1,
                delta=3.2,
                method="Wavelet",
                regime="high_vol",
            ),
            MatchCard(
                label="Compression setup",
                window="2018-02-12 -> 2018-05-25",
                score=78.7,
                delta=-1.4,
                method="Bempedelis",
                regime="mean_reverting",
            ),
            MatchCard(
                label="Late cycle echo",
                window="2023-03-11 -> 2023-06-20",
                score=74.2,
                delta=6.9,
                method="Koopman",
                regime="trending_up",
            ),
        ],
        architecture_cards=[
            ModuleCard(
                module="io/loader.py",
                responsibility="Data ingestion from CSV, parquet, DataFrame, dict, and array inputs.",
                scale="Swap for streaming loader later",
            ),
            ModuleCard(
                module="core/windower.py",
                responsibility="Sliding window generation and multi-scale candidate indexing.",
                scale="Chunkable and memory-bound",
            ),
            ModuleCard(
                module="core/matcher.py",
                responsibility="Pipeline orchestration from query normalization to ranked candidates.",
                scale="Delegates to independent methods",
            ),
            ModuleCard(
                module="core/scorer.py",
                responsibility="Confidence aggregation and method score normalization into a 0-100 rank.",
                scale="Pure math, easy to parallelize",
            ),
            ModuleCard(
                module="core/projector.py",
                responsibility="Weighted percentile forecast cone from post-match forward paths.",
                scale="Stateless projection surface",
            ),
            ModuleCard(
                module="methods/",
                responsibility="Independent scoring engines like DTW, Bempedelis, Wavelet, and Koopman.",
                scale="Worker-friendly extraction path",
            ),
        ],
        pipeline_steps=[
            "load() -> TimeSeries",
            "normalize(query)",
            "sliding_windows(history)",
            "tier 1 pre-filters",
            "tier 2 method scoring",
            "compute_confidence()",
            "project(matches, history)",
        ],
        base_breakdown=[
            ConfidenceBreakdownItem(label="DTW", value=0.91),
            ConfidenceBreakdownItem(label="Pearson", value=0.84),
            ConfidenceBreakdownItem(label="Bempedelis", value=0.71),
            ConfidenceBreakdownItem(label="Wavelet", value=0.66),
            ConfidenceBreakdownItem(label="Koopman", value=0.58),
            ConfidenceBreakdownItem(label="EMD", value=0.42),
        ],
    )


def _to_list(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.ndarray):
        return value.tolist()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (list, tuple)):
        return [_to_list(item) for item in value]
    return value


def build_score_breakdown_response(match) -> ScoreBreakdownResponse:
    breakdown = match.score_breakdown
    return ScoreBreakdownResponse(
        bempedelis_r2=breakdown.bempedelis_r2,
        bempedelis_smoothness=breakdown.bempedelis_smoothness,
        koopman=breakdown.koopman,
        wavelet_spectrum=breakdown.wavelet_spectrum,
        emd=breakdown.emd,
        tda=breakdown.tda,
        dtw=breakdown.dtw,
        pearson_warped=breakdown.pearson_warped,
        transfer_entropy=breakdown.transfer_entropy,
    )


def build_match_result_response(match) -> MatchResultResponse:
    return MatchResultResponse(
        start_idx=match.start_idx,
        end_idx=match.end_idx,
        start_date=match.start_date,
        end_date=match.end_date,
        confidence_score=match.confidence_score,
        score_breakdown=build_score_breakdown_response(match),
        matched_series=_to_list(match.matched_series),
        transform_alpha=_to_list(match.transform_alpha),
        transform_beta=_to_list(match.transform_beta),
        transform_r2=match.transform_r2,
        koopman_eigenvalues=_to_list(match.koopman_eigenvalues),
        fractal_spectrum=_to_list(match.fractal_spectrum),
        persistence_diagram=_to_list(match.persistence_diagram),
        forward_window=_to_list(match.forward_window),
    )


def build_forecast_response(forecast) -> ForecastResponse:
    return ForecastResponse(
        bars=forecast.bars,
        percentiles=forecast.percentiles,
        curves={key: _to_list(value) for key, value in forecast.curves.items()},
        all_paths=_to_list(forecast.all_paths),
        weights=_to_list(forecast.weights),
    )


def _grade_from_metrics(
    coverage_gap: float,
    crps_value: float,
    hit_rate_value: float,
) -> str:
    """Derive a discrete quality grade from three continuous metrics.

    Grading bands (sequential, first match wins):
        A  — coverage within 5pp of the 80% target AND crps <= 0.05 AND hit >= 0.58
        B  — within 10pp, crps <= 0.08, hit >= 0.54
        C  — within 15pp, crps <= 0.12, hit >= 0.52
        D  — within 20pp OR crps <= 0.20
        F  — everything else

    coverage_gap is the absolute distance from the 80% target, i.e.
    ``abs(coverage - 0.80)``. Positive values mean the cone is mis-sized in
    either direction (too wide OR too narrow — the sign-neutral distance is
    what graders care about).

    NOTE: The numeric thresholds are the same ones used in the TS fallback
    (``the-similarity-app/lib/data.ts::computeCalibrationMetrics``). If you
    change them here, change them there too or the live and synthetic UIs
    will disagree on the grade badge color.
    """
    if coverage_gap <= 0.05 and crps_value <= 0.05 and hit_rate_value >= 0.58:
        return "A"
    if coverage_gap <= 0.10 and crps_value <= 0.08 and hit_rate_value >= 0.54:
        return "B"
    if coverage_gap <= 0.15 and crps_value <= 0.12 and hit_rate_value >= 0.52:
        return "C"
    if coverage_gap <= 0.20 or crps_value <= 0.20:
        return "D"
    return "F"


def _regime_drift_from_dispersion(dispersion: float) -> str:
    """Classify regime drift from cross-analog terminal-return dispersion.

    dispersion is the population standard deviation of terminal returns
    across the top-K analogs. Higher dispersion → the analog set disagrees
    about what happens next → drift is elevated.

    Thresholds were picked to roughly match the old hardcoded UI label's
    "elevated" reading at ~2% daily-return dispersion. The bands are:
        dispersion < 0.03 → "low"
        0.03 <= dispersion < 0.07 → "elevated"
        dispersion >= 0.07 → "high"
    """
    if dispersion < 0.03:
        return "low"
    if dispersion < 0.07:
        return "elevated"
    return "high"


def build_calibration_metrics_response(
    results,
    forecast,
    forward_bars: int,
) -> CalibrationMetricsResponse:
    """Compute trust + calibration metrics from the analog forward windows.

    This is an *in-sample* diagnostic: we treat each analog's forward window
    as one realized outcome against the engine's own forecast cone. That
    gives the UI numbers that (a) change with every query and (b) are
    derived from this query's actual analog set, not a stale global eval.

    When the engine has too few analogs (< 3), or when the forward windows
    are incomplete, the function returns a fail-closed "unknown" block with
    zero numeric values — the UI renders em-dashes for those.

    Mathematical specification:
        coverage = fraction of analog terminal returns that fall inside
                   their own P10–P90 cone at the terminal bar.
        hit_rate = fraction of analogs whose terminal return sign matches
                   the P50 forecast terminal sign.
        crps     = mean discrete CRPS across analogs at the terminal bar,
                   using the available percentile curves as the empirical
                   forecast CDF.
        reliability[i] = (percentile_i/100, empirical_below_rate_i) for the
                         forecast's native percentile grid.

    Args:
        results: SearchResult with .matches[] (each has .forward_window).
        forecast: Forecast object with .curves (percentile → per-bar array)
            and .percentiles. Must already be projected over forward_bars.
        forward_bars: The requested forecast horizon; used to truncate any
            analog forward windows that are longer than the cone itself.

    Returns:
        CalibrationMetricsResponse — always a concrete object. "unknown"
        grade signals the UI to render em-dashes rather than scores.
    """
    import math

    # Collect analog terminal *cumulative returns*. The projector stores
    # ``forward_window`` as ``(future_price - anchor) / anchor``, i.e. a
    # cumulative return (0.05 == 5% above anchor). The forecast curves
    # live in the same space, so no rescaling is needed — we compare
    # realized cumulative return at the terminal bar directly against the
    # forecast curve at that bar.
    realized_terminals: list[float] = []
    for match in results.matches:
        forward = getattr(match, "forward_window", None)
        if forward is None:
            continue
        forward_arr = np.asarray(forward, dtype=np.float64)
        if forward_arr.size == 0:
            continue
        # Trim the analog forward window to at most ``forward_bars`` so
        # longer analog histories don't skew the terminal comparison.
        terminal_idx = min(forward_arr.size, forward_bars) - 1
        if terminal_idx < 0:
            continue
        realized = float(forward_arr[terminal_idx])
        if not math.isfinite(realized):
            continue
        realized_terminals.append(realized)

    n_analogs = len(realized_terminals)

    # Extract forecast terminal values per percentile for the realized-bar
    # comparison. The projector returns curves keyed by integer percentiles
    # (10, 25, 50, 75, 90 by default).
    curves = getattr(forecast, "curves", {}) or {}
    percentiles = sorted(int(p) for p in curves.keys())
    if not percentiles or n_analogs < 3:
        # Fail-closed: not enough data to grade. The UI renders em-dashes
        # when grade == "unknown", so we don't need to fabricate scores.
        return CalibrationMetricsResponse(
            coverage=0.0,
            crps=0.0,
            hit_rate=0.0,
            grade="unknown",
            regime_drift="unknown",
            reliability=[],
            n_analogs=n_analogs,
        )

    def _terminal(p: int) -> float:
        curve = curves.get(p)
        if curve is None or len(curve) == 0:
            return float("nan")
        return float(curve[-1])

    p10_term = _terminal(10) if 10 in percentiles else float("nan")
    p50_term = _terminal(50) if 50 in percentiles else float("nan")
    p90_term = _terminal(90) if 90 in percentiles else float("nan")

    # ── Coverage ───────────────────────────────────────────────────────
    # Fraction of analog terminals inside the P10-P90 envelope. Only
    # counted when both bounds are finite (fail-closed otherwise).
    coverage_value = 0.0
    if math.isfinite(p10_term) and math.isfinite(p90_term):
        inside = sum(
            1 for r in realized_terminals if p10_term <= r <= p90_term
        )
        coverage_value = inside / n_analogs

    # ── Hit rate ───────────────────────────────────────────────────────
    # Forecast curves are cumulative returns (0.05 == 5%), so the predicted
    # direction is sign(P50_terminal) and the realized direction is sign(r).
    # A "hit" requires matching non-zero signs; zero-valued forecasts count
    # as non-directional and never count as a hit.
    hit_rate_value = 0.0
    if math.isfinite(p50_term):
        p50_dir = 1 if p50_term > 0.0 else (-1 if p50_term < 0.0 else 0)
        hits = 0
        for r in realized_terminals:
            real_dir = 1 if r > 0.0 else (-1 if r < 0.0 else 0)
            if p50_dir != 0 and p50_dir == real_dir:
                hits += 1
        hit_rate_value = hits / n_analogs

    # ── CRPS (discrete approximation, per-analog, averaged) ────────────
    # For each analog, compare indicator(realized <= F_p) to the nominal
    # CDF level p/100 at every percentile, then average squared diffs.
    forecast_terminals = np.array(
        [_terminal(p) for p in percentiles], dtype=np.float64
    )
    cdf_levels = np.array(percentiles, dtype=np.float64) / 100.0
    crps_per = []
    for r in realized_terminals:
        if not math.isfinite(r):
            continue
        # Skip percentiles whose terminal is NaN so we don't poison the mean.
        valid = np.isfinite(forecast_terminals)
        if not valid.any():
            continue
        indicators = (r <= forecast_terminals[valid]).astype(np.float64)
        diffs = (indicators - cdf_levels[valid]) ** 2
        crps_per.append(float(np.mean(diffs)))
    crps_value = float(np.mean(crps_per)) if crps_per else 0.0

    # ── Reliability diagram ────────────────────────────────────────────
    # For each percentile, the empirical "observed" level is the fraction
    # of realized terminals at or below that percentile's forecast. This
    # is the standard reliability-diagram construction.
    reliability_buckets: list[ReliabilityBucketResponse] = []
    for pct, f_t in zip(percentiles, forecast_terminals):
        if not math.isfinite(f_t):
            continue
        observed = sum(1 for r in realized_terminals if r <= f_t) / n_analogs
        reliability_buckets.append(
            ReliabilityBucketResponse(
                predicted=float(pct) / 100.0,
                observed=float(max(0.0, min(1.0, observed))),
            )
        )

    # ── Regime drift from terminal-return dispersion ───────────────────
    dispersion = float(np.std(np.asarray(realized_terminals, dtype=np.float64), ddof=0))
    regime_drift_value = _regime_drift_from_dispersion(dispersion)

    # ── Grade ──────────────────────────────────────────────────────────
    coverage_gap = abs(coverage_value - 0.80)
    grade_value = _grade_from_metrics(coverage_gap, crps_value, hit_rate_value)

    return CalibrationMetricsResponse(
        coverage=float(max(0.0, min(1.0, coverage_value))),
        crps=float(max(0.0, crps_value)),
        hit_rate=float(max(0.0, min(1.0, hit_rate_value))),
        grade=grade_value,
        regime_drift=regime_drift_value,
        reliability=reliability_buckets,
        n_analogs=n_analogs,
    )


def _resolve_series(
    raw_values: list[float] | None,
    dataset_id: str | None,
    start_date: str | None,
    end_date: str | None,
    label: str,
) -> np.ndarray:
    """Resolve either raw values or a dataset reference to a numpy array."""
    if raw_values is not None:
        return np.asarray(raw_values, dtype=np.float64)

    if dataset_id is not None:
        from app.data_service import load_series

        values, _dates = load_series(
            dataset_id, start_date=start_date, end_date=end_date
        )
        if len(values) < 2:
            raise ValueError(
                f"{label} resolved to {len(values)} values (need at least 2)"
            )
        return np.asarray(values, dtype=np.float64)

    raise ValueError(f"Either {label}_values or {label}_dataset_id must be provided")


def execute_search(request: SearchRequest) -> SearchResponse:
    from fastapi import HTTPException

    try:
        query_values = _resolve_series(
            getattr(request, "query_values", None),
            getattr(request, "query_dataset_id", None),
            getattr(request, "query_start", None),
            getattr(request, "query_end", None),
            "query",
        )
        history_values = _resolve_series(
            getattr(request, "history_values", None),
            getattr(request, "history_dataset_id", None),
            getattr(request, "history_start", None),
            getattr(request, "history_end", None),
            "history",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    search_kwargs: dict[str, Any] = {}
    if request.normalization is not None:
        search_kwargs["normalization"] = request.normalization
    if request.stride is not None:
        search_kwargs["stride"] = request.stride
    if request.tier1_candidates is not None:
        search_kwargs["tier1_candidates"] = request.tier1_candidates
    if request.tier2_candidates is not None:
        search_kwargs["tier2_candidates"] = request.tier2_candidates
    if request.active_methods:
        search_kwargs["active_methods"] = request.active_methods

    # ── Cross-timeframe branch ─────────────────────────────────────────
    # When the caller supplies a non-empty timeframes list, we need a
    # DatetimeIndex on the history so the engine can resample. The dates
    # come from request.history_dates (1:1 with history_values) and must
    # be present + the same length as the values array.
    if request.timeframes:
        if not request.history_dates:
            raise HTTPException(
                status_code=400,
                detail=(
                    "history_dates is required when timeframes is set "
                    "(cross-timeframe search needs a DatetimeIndex to resample)"
                ),
            )
        if len(request.history_dates) != len(history_values):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"history_dates length ({len(request.history_dates)}) "
                    f"must equal history_values length ({len(history_values)})"
                ),
            )

        try:
            history_dates_np = np.array(request.history_dates, dtype="datetime64[ns]")
        except (ValueError, TypeError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to parse history_dates as ISO timestamps: {exc}",
            ) from exc

        # cross_timeframe_search resamples history per-timeframe, scales
        # the query window proportionally via np.interp, and merges +
        # dedupes matches across the union. Each match carries a
        # source_timeframe tag we ignore at the API surface today.
        from the_similarity.io.loader import TimeSeries

        history_ts = TimeSeries(values=history_values, dates=history_dates_np)
        results = the_similarity.cross_timeframe_search(
            query=query_values,
            history=history_ts,
            timeframes=request.timeframes,
            top_k=request.top_k,
            forward_bars=request.forward_bars,
            **search_kwargs,
        )
    else:
        results = the_similarity.search(
            query=query_values,
            history=history_values,
            top_k=request.top_k,
            weights=request.weights or None,
            exclude_self=request.exclude_self,
            **search_kwargs,
        )

    forecast = the_similarity.project(
        matches=results,
        history=history_values,
        forward_bars=request.forward_bars,
        percentiles=request.percentiles or None,
    )

    # Calibration / trust metrics are derived from the analog forward windows
    # vs this query's own forecast cone. When insufficient analogs exist,
    # build_calibration_metrics_response returns an "unknown" block — the
    # frontend renders em-dashes rather than fabricating scores.
    metrics = build_calibration_metrics_response(
        results=results,
        forecast=forecast,
        forward_bars=request.forward_bars,
    )

    return SearchResponse(
        query_values=_to_list(query_values),
        matches=[build_match_result_response(match) for match in results.matches],
        forecast=build_forecast_response(forecast),
        metrics=metrics,
    )
