from __future__ import annotations

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from the_similarity.contracts.api import DashboardDataResponse, SearchRequest, SearchResponse

from app.data_service import load_catalog, load_series
from app.models import CatalogItem, CatalogResponse, DatasetSeriesResponse
from app.services import execute_search, get_dashboard_payload
from app.settings import settings
from app.streaming import handle_search_stream, handle_watch_stream

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
