from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from the_similarity.contracts.api import DashboardDataResponse, SearchRequest, SearchResponse

from app.data_service import load_catalog, load_ohlc, load_series
from app.models import CatalogItem, CatalogResponse, DatasetSeriesResponse, OhlcResponse
from app.services import execute_search, get_dashboard_payload
from app.settings import settings
from app.streaming import handle_search_stream, handle_watch_stream
from app.auth_routes import router as auth_router
from app.alert_routes import router as alert_router
from app.auth_deps import get_current_user
from app.platform_routes import router as platform_router
from app.finance_routes import router as finance_router
from app.state_routes import router as state_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(alert_router)
# Platform registry surface — read/write access to runs, artifacts,
# scorecards, scenarios, and datasets. See ``app/platform_routes.py`` for
# the full contract. Mounted under the ``/platform`` prefix (declared on
# the router itself, not re-prefixed here).
app.include_router(platform_router)
# Finance review surface — review artifacts for finance runs.
# Mounted under the ``/platform`` prefix (declared on the router itself).
app.include_router(finance_router)
# State-space query surface — 3D projection, nearest neighbors, clusters,
# transitions, and cross-domain correspondences. See ``app/state_routes.py``.
app.include_router(state_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/dashboard", response_model=DashboardDataResponse)
def get_dashboard() -> DashboardDataResponse:
    return get_dashboard_payload()


@app.get("/catalog", response_model=CatalogResponse)
def get_catalog() -> CatalogResponse:
    datasets = load_catalog()
    items = [CatalogItem(**d) for d in datasets]
    return CatalogResponse(datasets=items)


@app.get(
    "/datasets/{asset_class}/{symbol}/{timeframe}/series",
    response_model=DatasetSeriesResponse,
)
def get_dataset_series(
    asset_class: str,
    symbol: str,
    timeframe: str,
    column: str = "close",
    start: str | None = None,
    end: str | None = None,
) -> DatasetSeriesResponse:
    dataset_id = f"{asset_class}/{symbol}/{timeframe}"
    try:
        values, dates = load_series(
            dataset_id, column=column, start_date=start, end_date=end
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return DatasetSeriesResponse(
        dataset_id=dataset_id,
        column=column,
        values=values,
        dates=dates,
        row_count=len(values),
    )


@app.get(
    "/datasets/{asset_class}/{symbol}/{timeframe}/ohlc",
    response_model=OhlcResponse,
)
def get_dataset_ohlc(
    asset_class: str,
    symbol: str,
    timeframe: str,
    start: str | None = None,
    end: str | None = None,
) -> OhlcResponse:
    dataset_id = f"{asset_class}/{symbol}/{timeframe}"
    try:
        data = load_ohlc(dataset_id, start_date=start, end_date=end)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return OhlcResponse(
        dataset_id=dataset_id,
        open=data["open"],
        high=data["high"],
        low=data["low"],
        close=data["close"],
        volume=data.get("volume", []),
        dates=data.get("dates", []),
        row_count=len(data["close"]),
    )


@app.post("/search", response_model=SearchResponse)
def search(request: SearchRequest) -> SearchResponse:
    return execute_search(request)


@app.websocket("/ws/search")
async def ws_search(websocket: WebSocket) -> None:
    """Stream search progress and results over WebSocket."""
    await handle_search_stream(websocket)


@app.websocket("/ws/watch")
async def ws_watch(websocket: WebSocket) -> None:
    """Watch for pattern matches on a live candle stream."""
    await handle_watch_stream(websocket)


# ---------------------------------------------------------------------------
# Data warehouse endpoints
# ---------------------------------------------------------------------------

def _get_warehouse():
    """Lazy-init warehouse singleton."""
    from app.data_service import _data_root
    from the_similarity_data.warehouse import Warehouse

    return Warehouse(_data_root())


@app.get("/warehouse/coverage")
def warehouse_coverage() -> dict:
    """Coverage statistics: asset classes, symbols, row counts, date ranges."""
    try:
        wh = _get_warehouse()
        stats = wh.coverage()
        return {
            "totalDatasets": stats.total_datasets,
            "totalRows": stats.total_rows,
            "byAssetClass": stats.by_asset_class,
            "byTimeframe": stats.by_timeframe,
            "bySource": stats.by_source,
            "uniqueSymbols": len(stats.symbols),
            "symbols": stats.symbols,
            "oldestTimestamp": stats.oldest_timestamp,
            "newestTimestamp": stats.newest_timestamp,
        }
    except Exception as exc:
        logger.exception("warehouse coverage error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/warehouse/quality")
def warehouse_quality(
    max_gap_multiplier: float = Query(3.0, ge=1.0),
    stale_hours: float = Query(48.0, ge=1.0),
) -> dict:
    """Run data quality checks across all datasets."""
    try:
        wh = _get_warehouse()
        issues = wh.check_quality(
            max_gap_multiplier=max_gap_multiplier,
            stale_hours=stale_hours,
        )
        return {
            "totalIssues": len(issues),
            "errors": len([i for i in issues if i.severity == "error"]),
            "warnings": len([i for i in issues if i.severity == "warning"]),
            "issues": [
                {
                    "datasetId": i.dataset_id,
                    "issueType": i.issue_type,
                    "severity": i.severity,
                    "message": i.message,
                    "details": i.details,
                }
                for i in issues
            ],
        }
    except Exception as exc:
        logger.exception("warehouse quality error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/warehouse/freshness")
def warehouse_freshness() -> list[dict]:
    """Freshness report for all datasets, sorted by staleness."""
    try:
        wh = _get_warehouse()
        return wh.freshness_report()
    except Exception as exc:
        logger.exception("warehouse freshness error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc



@app.post("/warehouse/refresh")
def warehouse_refresh(
    asset_class: str | None = Query(None),
    symbol: str | None = Query(None),
    timeframe: str | None = Query(None),
    _user=Depends(get_current_user),
) -> dict:
    """Trigger a data refresh for matching datasets.

    Refreshes parquet files from external sources and updates the catalog.
    Filter by asset_class, symbol, and/or timeframe. With no filters,
    refreshes all enabled datasets.
    """
    try:
        import sys
        from pathlib import Path

        data_root = _data_root()
        sys.path.insert(0, str(data_root))

        from the_similarity_data.config import load_dataset_specs
        from the_similarity_data.refresh import refresh_all_datasets
        
        
        specs = load_dataset_specs()
        results = refresh_all_datasets(
            specs,
            asset_class=asset_class,
            symbol=symbol,
            timeframe=timeframe,
        )
        return {
            "refreshed": len(results),
            "datasets": [
                {
                    "datasetId": f"{r.asset_class}/{r.symbol}/{r.timeframe}",
                    "rows": r.row_count,
                    "start": r.start_timestamp,
                    "end": r.end_timestamp,
                }
                for r in results
            ],
        }
    except Exception as exc:
        logger.exception("warehouse refresh error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/warehouse/search")
def warehouse_search(
    asset_class: str | None = Query(None),
    source: str | None = Query(None),
    min_rows: int = Query(0, ge=0),
) -> list[dict]:
    """Search the catalog for datasets matching filters."""
    try:
        wh = _get_warehouse()
        return wh.search_assets(
            asset_class=asset_class,
            source=source,
            min_rows=min_rows,
        )
    except Exception as exc:
        logger.exception("warehouse search error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Terrain generation endpoints
# ---------------------------------------------------------------------------


@app.get("/terrain/presets")
def terrain_presets() -> list[dict]:
    """List available terrain presets."""
    from the_similarity.core.terrain_params import list_presets, get_preset, params_to_dict

    return [
        {"name": name, **params_to_dict(get_preset(name))}
        for name in list_presets()
    ]


@app.get("/terrain/presets/{name}")
def terrain_preset(name: str) -> dict:
    """Get a specific terrain preset."""
    from the_similarity.core.terrain_params import get_preset, params_to_dict

    try:
        return params_to_dict(get_preset(name))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/terrain/generate")
def generate_terrain_endpoint(
    preset: str = Query("alpine"),
    size: int = Query(256, ge=32, le=512),
    seed: int = Query(42),
) -> dict:
    """Generate terrain from a preset.

    Returns heightmap, moisture, flow, biome maps as flat lists,
    plus features for object placement.
    """
    try:
        from the_similarity.core.terrain_generator import TerrainGenerator

        gen = TerrainGenerator(preset)
        result = gen.generate(size=size, seed=seed)

        return {
            "size": size,
            "seed": seed,
            "preset": preset,
            "heightmap": result.heightmap.ravel().tolist(),
            "moisture": result.moisture_map.ravel().tolist(),
            "flow": result.flow_map.ravel().tolist(),
            "biome": result.biome_map.ravel().tolist(),
            "features": result.features,
            "params": {
                "water_level": result.params.water_level if result.params else 0.2,
                "snow_line": result.params.snow_line if result.params else 0.8,
                "elevation_range": result.params.elevation_range if result.params else 1.0,
            },
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("terrain generation error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
