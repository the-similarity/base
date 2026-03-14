from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from the_similarity.contracts.api import DashboardDataResponse, SearchRequest, SearchResponse

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


@app.post("/search", response_model=SearchResponse)
def search(request: SearchRequest) -> SearchResponse:
    return execute_search(request)
