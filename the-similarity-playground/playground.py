from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
ENGINE_ROOT = ROOT / "the_similarity"
DATA_ROOT = ROOT / "the-similarity-data"
API_ROOT = ROOT / "the-similarity-api"
APP_ROOT = ROOT / "the-similarity-app"
MANIFEST_PATH = DATA_ROOT / "manifests" / "catalog.json"


def bootstrap_imports() -> None:
    import sys

    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def load_manifest() -> pd.DataFrame:
    payload = json.loads(MANIFEST_PATH.read_text())
    return pd.DataFrame(payload["datasets"]).sort_values(
        ["asset_class", "symbol", "timeframe", "source"]
    )


def dataset_path(asset_class: str, symbol: str, timeframe: str) -> Path:
    manifest = load_manifest()
    rows = manifest[
        (manifest["asset_class"] == asset_class)
        & (manifest["symbol"] == symbol)
        & (manifest["timeframe"] == timeframe)
    ]
    if rows.empty:
        raise KeyError(f"No dataset found for {asset_class}/{symbol}/{timeframe}")
    relative_path = rows.iloc[0]["path"]
    return DATA_ROOT / relative_path


def read_candles(asset_class: str, symbol: str, timeframe: str) -> pd.DataFrame:
    path = dataset_path(asset_class, symbol, timeframe)
    frame = pd.read_parquet(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame


def build_query_slice(frame: pd.DataFrame, window_size: int, end_offset: int = 0) -> pd.DataFrame:
    if window_size <= 1:
        raise ValueError("window_size must be greater than 1")
    if len(frame) <= window_size + end_offset:
        raise ValueError("frame is too short for the requested query window")
    end_index = len(frame) - end_offset
    start_index = end_index - window_size
    return frame.iloc[start_index:end_index].copy()


def run_local_search(
    asset_class: str,
    symbol: str,
    timeframe: str,
    *,
    window_size: int = 100,
    top_k: int = 10,
    stride: int = 5,
    end_offset: int = 0,
    forward_bars: int = 30,
    active_methods: list[str] | None = None,
    tier1_candidates: int | None = 250,
    tier2_candidates: int | None = 40,
    percentiles: list[int] | None = None,
):
    bootstrap_imports()
    import the_similarity

    history_frame = read_candles(asset_class, symbol, timeframe)
    query_frame = build_query_slice(history_frame, window_size=window_size, end_offset=end_offset)

    history = the_similarity.load(
        history_frame,
        column="close",
        date_column="timestamp",
    )
    query = the_similarity.load(
        query_frame,
        column="close",
        date_column="timestamp",
    )

    results = the_similarity.search(
        query=query,
        history=history,
        top_k=top_k,
        stride=stride,
        active_methods=active_methods or ["dtw", "pearson_warped", "bempedelis_r2", "bempedelis_smoothness"],
        tier1_candidates=tier1_candidates,
        tier2_candidates=tier2_candidates,
    )
    forecast = the_similarity.project(
        results,
        history,
        forward_bars=forward_bars,
        percentiles=percentiles,
    )

    return {
        "history_frame": history_frame,
        "query_frame": query_frame,
        "results": results,
        "forecast": forecast,
    }


def top_matches_frame(results) -> pd.DataFrame:
    rows = []
    for match in results.matches:
        rows.append(
            {
                "start_idx": match.start_idx,
                "end_idx": match.end_idx,
                "start_date": match.start_date,
                "end_date": match.end_date,
                "confidence_score": match.confidence_score,
                "dtw": match.score_breakdown.dtw,
                "pearson": match.score_breakdown.pearson_warped,
                "bempedelis_r2": match.score_breakdown.bempedelis_r2,
                "bempedelis_smoothness": match.score_breakdown.bempedelis_smoothness,
                "transform_r2": match.transform_r2,
            }
        )
    return pd.DataFrame(rows)


def forecast_summary_frame(forecast) -> pd.DataFrame:
    rows = []
    for percentile, curve in forecast.curves.items():
        rows.append(
            {
                "percentile": percentile,
                "terminal_return": float(curve[-1]) if len(curve) else 0.0,
                "bars": forecast.bars,
            }
        )
    return pd.DataFrame(rows).sort_values("percentile")


def theory_scorecard(results, forecast) -> dict[str, float]:
    best = results.best
    return {
        "match_count": float(len(results.matches)),
        "best_confidence": float(best.confidence_score if best else 0.0),
        "best_dtw": float(best.score_breakdown.dtw if best else 0.0),
        "best_pearson": float(best.score_breakdown.pearson_warped if best else 0.0),
        "best_bempedelis_r2": float(best.score_breakdown.bempedelis_r2 if best else 0.0),
        "best_bempedelis_smoothness": float(best.score_breakdown.bempedelis_smoothness if best else 0.0),
        "forecast_p10_terminal": float(forecast.curves[10][-1]) if 10 in forecast.curves else 0.0,
        "forecast_p25_terminal": float(forecast.curves[25][-1]) if 25 in forecast.curves else 0.0,
        "forecast_p50_terminal": float(forecast.curves[50][-1]) if 50 in forecast.curves else 0.0,
        "forecast_p75_terminal": float(forecast.curves[75][-1]) if 75 in forecast.curves else 0.0,
        "forecast_p90_terminal": float(forecast.curves[90][-1]) if 90 in forecast.curves else 0.0,
    }


def run_api_search(
    payload: dict,
    *,
    base_url: str = "http://127.0.0.1:8000",
    timeout: int = 60,
) -> dict:
    response = requests.post(
        f"{base_url.rstrip('/')}/search",
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def make_api_payload_from_dataset(
    asset_class: str,
    symbol: str,
    timeframe: str,
    *,
    window_size: int = 100,
    top_k: int = 10,
    stride: int = 5,
    end_offset: int = 0,
    forward_bars: int = 30,
    active_methods: list[str] | None = None,
    tier1_candidates: int | None = 250,
    tier2_candidates: int | None = 40,
    percentiles: list[int] | None = None,
) -> dict:
    history_frame = read_candles(asset_class, symbol, timeframe)
    query_frame = build_query_slice(history_frame, window_size=window_size, end_offset=end_offset)
    return {
        "queryValues": query_frame["close"].tolist(),
        "historyValues": history_frame["close"].tolist(),
        "topK": top_k,
        "forwardBars": forward_bars,
        "excludeSelf": True,
        "stride": stride,
        "activeMethods": active_methods or ["dtw", "pearson_warped", "bempedelis_r2", "bempedelis_smoothness"],
        "tier1Candidates": tier1_candidates,
        "tier2Candidates": tier2_candidates,
        "percentiles": percentiles or [10, 25, 50, 75, 90],
    }
