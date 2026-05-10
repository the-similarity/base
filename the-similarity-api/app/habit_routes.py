"""Habit forecast routes for the Habitpulse iOS app.

Exposes a single stateless endpoint, ``POST /habit/forecast``, that wraps the
engine's :func:`the_similarity.search` + :func:`the_similarity.project` over a
user's own habit time series.

Lifecycle / invariants:
    * Stateless — no habit data is persisted server-side. Each request carries
      the full series and the server returns analogues + cone in one shot.
    * Series values are floats in ``[0, 1]`` by convention (1.0 = did the
      habit, 0.0 = skipped) but the math is dimensionless; any numeric scale
      works.
    * Self-exclusion is on by default in the engine, so the most-recent
      window cannot match itself.

Design rationale:
    The mobile client owns the data (SwiftData on-device). This endpoint is a
    pure compute surface so the server never accumulates personal habit
    history. Keep it that way — do not add storage or auth here without
    threading it through the platform's existing auth_routes.
"""

from __future__ import annotations

from typing import Annotated

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import the_similarity

router = APIRouter(prefix="/habit", tags=["habit"])


class HabitForecastRequest(BaseModel):
    """Body for ``POST /habit/forecast``.

    The query window is taken as the **last** ``window`` samples of ``series``;
    the rest is the search history. We require at least ``2 * window +
    forward_bars`` samples so there is enough history to find analogues that
    also have a forward trajectory.
    """

    series: Annotated[list[float], Field(min_length=14)]
    window: int = Field(default=7, ge=3, le=60)
    forward_bars: int = Field(default=7, ge=1, le=30)
    top_k: int = Field(default=3, ge=1, le=10)


class Analogue(BaseModel):
    """One historical analogue to the user's recent window."""

    start_idx: int
    end_idx: int
    score: float
    forward: list[float]  # The actual forward values that followed this analogue


class Cone(BaseModel):
    """Forecast cone — three percentiles of the projected habit value."""

    p10: list[float]
    p50: list[float]
    p75: list[float]


class HabitForecastResponse(BaseModel):
    analogues: list[Analogue]
    cone: Cone
    relapse_risk: float = Field(ge=0.0, le=1.0)


@router.post("/forecast", response_model=HabitForecastResponse)
def habit_forecast(request: HabitForecastRequest) -> HabitForecastResponse:
    arr = np.asarray(request.series, dtype=np.float64)
    n = len(arr)
    min_required = 2 * request.window + request.forward_bars
    if n < min_required:
        raise HTTPException(
            status_code=422,
            detail=(
                f"series length {n} is too short; need at least "
                f"{min_required} samples (2*window + forward_bars)."
            ),
        )

    # Degenerate series: zero variance breaks correlation-based methods. Bail
    # early with a flat cone instead of returning NaNs.
    if float(np.std(arr)) == 0.0:
        flat = [float(arr[-1])] * request.forward_bars
        return HabitForecastResponse(
            analogues=[],
            cone=Cone(p10=flat, p50=flat, p75=flat),
            relapse_risk=1.0 - float(arr[-1]),
        )

    query = arr[-request.window :]

    results = the_similarity.search(
        query=query,
        history=arr,
        top_k=request.top_k,
    )

    analogues: list[Analogue] = []
    for match in results.matches:
        # Snip the days that actually followed each analogue window. Cap at
        # forward_bars even if more data is available so the iOS chart can
        # render a fixed-width series.
        fwd_start = match.end_idx
        fwd_end = min(fwd_start + request.forward_bars, n)
        analogues.append(
            Analogue(
                start_idx=int(match.start_idx),
                end_idx=int(match.end_idx),
                score=float(match.confidence_score),
                forward=arr[fwd_start:fwd_end].tolist(),
            )
        )

    forecast = the_similarity.project(
        matches=results,
        history=arr,
        forward_bars=request.forward_bars,
        percentiles=[10, 50, 75],
        query=query,
    )

    p10 = forecast.curves.get(10, np.zeros(request.forward_bars))
    p50 = forecast.curves.get(50, np.zeros(request.forward_bars))
    p75 = forecast.curves.get(75, np.zeros(request.forward_bars))

    # Relapse risk = 1 - mean(P50). For a habit-completion series in [0, 1],
    # this collapses the cone into a single 0-1 number the UI can show as a
    # ring or color. Clamp because the projector returns cumulative returns
    # that can drift slightly outside [0, 1] for short series.
    relapse_risk = float(np.clip(1.0 - float(np.mean(p50)), 0.0, 1.0))

    return HabitForecastResponse(
        analogues=analogues,
        cone=Cone(p10=p10.tolist(), p50=p50.tolist(), p75=p75.tolist()),
        relapse_risk=relapse_risk,
    )
