from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from the_similarity.contracts.api import DashboardDataResponse, SearchRequest, SearchResponse

from app.data_service import load_catalog, load_ohlc, load_series
from app.models import CatalogItem, CatalogResponse, DatasetSeriesResponse, OhlcResponse
from app.services import execute_search, get_dashboard_payload
from app.settings import settings

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
