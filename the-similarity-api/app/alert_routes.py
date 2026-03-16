"""Alert system API routes: watchlists + alert history."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from the_similarity.core.alerts import AlertManager, Watchlist
from the_similarity.core.auth import User

from app.auth_deps import get_current_user

router = APIRouter(prefix="/alerts", tags=["alerts"])

# Singleton alert manager
_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    global _alert_manager
    if _alert_manager is None:
        data_dir = Path(os.getenv("THE_SIMILARITY_DATA_DIR", "/tmp/the_similarity"))
        data_dir.mkdir(parents=True, exist_ok=True)
        _alert_manager = AlertManager(db_path=data_dir / "alerts.db")
    return _alert_manager


# ---- Request / Response models ----

class CreateWatchlistRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    query_values: list[float] = Field(..., min_length=2)
    dataset_id: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    threshold: float = Field(default=70.0, ge=0.0, le=100.0)
    cooldown_seconds: float = Field(default=3600.0, ge=0.0)
    channels: list[str] = Field(default_factory=lambda: ["log"])
    webhook_url: str | None = None
    top_k: int = Field(default=5, ge=1, le=100)
    stride: int | None = None
    active_methods: list[str] | None = None


class UpdateWatchlistRequest(BaseModel):
    name: str | None = None
    threshold: float | None = Field(default=None, ge=0.0, le=100.0)
    cooldown_seconds: float | None = Field(default=None, ge=0.0)
    channels: list[str] | None = None
    webhook_url: str | None = None
    enabled: bool | None = None
    top_k: int | None = Field(default=None, ge=1, le=100)


class WatchlistResponse(BaseModel):
    id: str
    name: str
    dataset_id: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    threshold: float
    cooldown_seconds: float
    channels: list[str]
    webhook_url: str | None = None
    top_k: int
    enabled: bool
    created_at: float
    updated_at: float


class AlertResponse(BaseModel):
    id: str
    watchlist_id: str
    confidence_score: float
    match_start_idx: int
    match_end_idx: int
    match_regime: str | None = None
    message: str
    fired_at: float
    acknowledged: bool


class AlertCountResponse(BaseModel):
    total: int
    unacknowledged: int


# ---- Watchlist endpoints ----

@router.post("/watchlists", response_model=WatchlistResponse, status_code=201)
def create_watchlist(
    body: CreateWatchlistRequest,
    user: User = Depends(get_current_user),
    mgr: AlertManager = Depends(get_alert_manager),
) -> WatchlistResponse:
    """Create a new pattern watchlist."""
    wl = mgr.create_watchlist(
        user_id=user.id,
        name=body.name,
        query_values=body.query_values,
        dataset_id=body.dataset_id,
        symbol=body.symbol,
        timeframe=body.timeframe,
        threshold=body.threshold,
        cooldown_seconds=body.cooldown_seconds,
        channels=body.channels,
        webhook_url=body.webhook_url,
        top_k=body.top_k,
        stride=body.stride,
        active_methods=body.active_methods,
    )
    return _watchlist_to_response(wl)


@router.get("/watchlists", response_model=list[WatchlistResponse])
def list_watchlists(
    user: User = Depends(get_current_user),
    mgr: AlertManager = Depends(get_alert_manager),
) -> list[WatchlistResponse]:
    """List all watchlists for the current user."""
    return [_watchlist_to_response(wl) for wl in mgr.list_watchlists(user.id)]


@router.get("/watchlists/{watchlist_id}", response_model=WatchlistResponse)
def get_watchlist(
    watchlist_id: str,
    user: User = Depends(get_current_user),
    mgr: AlertManager = Depends(get_alert_manager),
) -> WatchlistResponse:
    """Get a specific watchlist."""
    wl = mgr.get_watchlist(watchlist_id)
    if wl is None or wl.user_id != user.id:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return _watchlist_to_response(wl)


@router.patch("/watchlists/{watchlist_id}", response_model=WatchlistResponse)
def update_watchlist(
    watchlist_id: str,
    body: UpdateWatchlistRequest,
    user: User = Depends(get_current_user),
    mgr: AlertManager = Depends(get_alert_manager),
) -> WatchlistResponse:
    """Update a watchlist's configuration."""
    wl = mgr.get_watchlist(watchlist_id)
    if wl is None or wl.user_id != user.id:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = mgr.update_watchlist(watchlist_id, **updates)
    if updated is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    return _watchlist_to_response(updated)


@router.delete("/watchlists/{watchlist_id}", status_code=204)
def delete_watchlist(
    watchlist_id: str,
    user: User = Depends(get_current_user),
    mgr: AlertManager = Depends(get_alert_manager),
) -> None:
    """Delete a watchlist and all its alerts."""
    wl = mgr.get_watchlist(watchlist_id)
    if wl is None or wl.user_id != user.id:
        raise HTTPException(status_code=404, detail="Watchlist not found")
    mgr.delete_watchlist(watchlist_id)


# ---- Alert endpoints ----

@router.get("/history", response_model=list[AlertResponse])
def list_alerts(
    watchlist_id: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    mgr: AlertManager = Depends(get_alert_manager),
) -> list[AlertResponse]:
    """List alert history, optionally filtered by watchlist."""
    alerts = mgr.list_alerts(user.id, watchlist_id=watchlist_id, limit=limit)
    return [_alert_to_response(a) for a in alerts]


@router.get("/count", response_model=AlertCountResponse)
def alert_count(
    user: User = Depends(get_current_user),
    mgr: AlertManager = Depends(get_alert_manager),
) -> AlertCountResponse:
    """Get alert counts."""
    total = mgr.count_alerts(user.id)
    unack = mgr.count_alerts(user.id, unacknowledged_only=True)
    return AlertCountResponse(total=total, unacknowledged=unack)


@router.post("/{alert_id}/ack", status_code=204)
def acknowledge_alert(
    alert_id: str,
    user: User = Depends(get_current_user),
    mgr: AlertManager = Depends(get_alert_manager),
) -> None:
    """Acknowledge an alert."""
    # Verify alert belongs to user
    alerts = mgr.list_alerts(user.id, limit=1000)
    if not any(a.id == alert_id for a in alerts):
        raise HTTPException(status_code=404, detail="Alert not found")
    mgr.acknowledge_alert(alert_id)


# ---- Helpers ----

def _watchlist_to_response(wl: Watchlist) -> WatchlistResponse:
    return WatchlistResponse(
        id=wl.id,
        name=wl.name,
        dataset_id=wl.dataset_id,
        symbol=wl.symbol,
        timeframe=wl.timeframe,
        threshold=wl.threshold,
        cooldown_seconds=wl.cooldown_seconds,
        channels=wl.channels,
        webhook_url=wl.webhook_url,
        top_k=wl.top_k,
        enabled=wl.enabled,
        created_at=wl.created_at,
        updated_at=wl.updated_at,
    )


def _alert_to_response(a) -> AlertResponse:
    return AlertResponse(
        id=a.id,
        watchlist_id=a.watchlist_id,
        confidence_score=a.confidence_score,
        match_start_idx=a.match_start_idx,
        match_end_idx=a.match_end_idx,
        match_regime=a.match_regime,
        message=a.message,
        fired_at=a.fired_at,
        acknowledged=a.acknowledged,
    )
