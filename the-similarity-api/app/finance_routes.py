"""Finance review API routes — mounts at ``/platform/runs/{run_id}/review``.

Purpose
-------
Expose CRUD operations for :class:`ReviewArtifact` through the customer-facing
API. Reviews are stored in a companion SQLite table (``reviews``) in the same
registry DB file so they co-locate with runs, artifacts, and scorecards.

Endpoints
---------
- ``POST /platform/runs/{run_id}/review`` — create a review for a run.
- ``GET  /platform/runs/{run_id}/review`` — get the review for a run.
- ``PUT  /platform/runs/{run_id}/review`` — update review (e.g. realized_outcome).
- ``GET  /platform/reviews``              — list reviews by status.

Design invariants
-----------------
1. One review per run — the ``run_id`` column is UNIQUE in the reviews table.
   Creating a second review for the same run returns 409.
2. Reviews reference runs — the parent run must exist (checked via
   ``_require_run``).
3. The review table is created lazily via ``_ensure_reviews_table`` on first
   access, following the same pattern as the companion tables in
   ``platform_routes.py``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Iterator, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.platform_routes import get_registry, _require_run
from the_similarity.platform.registry import RunRegistry
from the_similarity.platform.artifacts import iso_now
from the_similarity.finance.review import ReviewArtifact, ReviewStatus


# ---------------------------------------------------------------------------
# Router — mounted on the platform router's prefix in main.py.
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/platform", tags=["finance-reviews"])


# ---------------------------------------------------------------------------
# Pydantic wire models
# ---------------------------------------------------------------------------


class ReviewCreateRequest(BaseModel):
    """POST body for creating a review."""

    reviewer: str = Field(..., description="Agent ID or human email.")
    status: str = Field(
        "pending",
        description="Review status: pending, approved, flagged, rejected.",
    )
    signal_summary: str = Field(
        "", description="1-3 sentence summary of what the run found."
    )
    trust_decision: str = Field(
        "REVIEW",
        description="Trust verdict: TRUSTED, REVIEW, or REJECTED.",
    )
    calibration_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of calibration metrics at review time.",
    )
    risk_flags: List[str] = Field(
        default_factory=list, description="List of risk flag constants."
    )
    notes: str = Field("", description="Free-form reviewer notes.")


class ReviewUpdateRequest(BaseModel):
    """PUT body for updating a review."""

    status: Optional[str] = Field(
        None, description="New status: pending, approved, flagged, rejected."
    )
    trust_decision: Optional[str] = Field(
        None, description="Updated trust verdict."
    )
    notes: Optional[str] = Field(None, description="Updated reviewer notes.")
    realized_outcome: Optional[Dict[str, Any]] = Field(
        None, description="Post-hoc realized outcome data."
    )
    risk_flags: Optional[List[str]] = Field(
        None, description="Updated risk flags."
    )


class ReviewResponse(BaseModel):
    """Wire shape for a review artifact."""

    review_id: str
    run_id: str
    reviewer: str
    status: str
    signal_summary: str
    trust_decision: str
    calibration_context: Dict[str, Any] = Field(default_factory=dict)
    risk_flags: List[str] = Field(default_factory=list)
    notes: str = ""
    realized_outcome: Optional[Dict[str, Any]] = None
    created_at: str = ""
    updated_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Reviews table DDL — companion to the runs table in the same DB.
# ---------------------------------------------------------------------------

_CREATE_REVIEWS_SQL = """
CREATE TABLE IF NOT EXISTS reviews (
    review_id            TEXT PRIMARY KEY,
    run_id               TEXT NOT NULL UNIQUE,
    reviewer             TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'pending',
    signal_summary       TEXT NOT NULL DEFAULT '',
    trust_decision       TEXT NOT NULL DEFAULT 'REVIEW',
    calibration_ctx_json TEXT NOT NULL DEFAULT '{}',
    risk_flags_json      TEXT NOT NULL DEFAULT '[]',
    notes                TEXT NOT NULL DEFAULT '',
    realized_outcome_json TEXT,
    created_at           TEXT NOT NULL,
    updated_at           TEXT
);
"""

_CREATE_IDX_REVIEWS_STATUS = (
    "CREATE INDEX IF NOT EXISTS idx_reviews_status ON reviews (status);"
)
_CREATE_IDX_REVIEWS_RUN_ID = (
    "CREATE INDEX IF NOT EXISTS idx_reviews_run_id ON reviews (run_id);"
)


def _ensure_reviews_table(conn: sqlite3.Connection) -> None:
    """Create the reviews table if missing. Idempotent."""
    with conn:
        conn.execute(_CREATE_REVIEWS_SQL)
        conn.execute(_CREATE_IDX_REVIEWS_STATUS)
        conn.execute(_CREATE_IDX_REVIEWS_RUN_ID)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/runs/{run_id}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {"description": "run_id not found."},
        409: {"description": "Review already exists for this run."},
    },
)
def create_review(
    run_id: str,
    body: ReviewCreateRequest,
    registry: RunRegistry = Depends(get_registry),
) -> ReviewResponse:
    """Create a review for a finance run.

    One review per run — duplicate creation returns 409.
    """
    _require_run(registry, run_id)
    _ensure_reviews_table(registry._conn)  # noqa: SLF001

    review = ReviewArtifact(
        review_id=ReviewArtifact.new_review_id(),
        run_id=run_id,
        reviewer=body.reviewer,
        status=ReviewStatus(body.status),
        signal_summary=body.signal_summary,
        trust_decision=body.trust_decision,
        calibration_context=body.calibration_context,
        risk_flags=body.risk_flags,
        notes=body.notes,
        created_at=iso_now(),
    )

    try:
        with registry._conn:  # noqa: SLF001
            registry._conn.execute(  # noqa: SLF001
                "INSERT INTO reviews "
                "(review_id, run_id, reviewer, status, signal_summary, "
                "trust_decision, calibration_ctx_json, risk_flags_json, "
                "notes, realized_outcome_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    review.review_id,
                    review.run_id,
                    review.reviewer,
                    review.status.value,
                    review.signal_summary,
                    review.trust_decision,
                    json.dumps(review.calibration_context, separators=(",", ":")),
                    json.dumps(review.risk_flags, separators=(",", ":")),
                    review.notes,
                    None,
                    review.created_at,
                    None,
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review already exists for run_id={run_id}",
        ) from exc

    return _review_to_response(review)


@router.get(
    "/runs/{run_id}/review",
    response_model=ReviewResponse,
    responses={
        404: {"description": "run_id or review not found."},
    },
)
def get_review(
    run_id: str,
    registry: RunRegistry = Depends(get_registry),
) -> ReviewResponse:
    """Get the review for a run. 404 if no review exists."""
    _require_run(registry, run_id)
    _ensure_reviews_table(registry._conn)  # noqa: SLF001

    row = registry._conn.execute(  # noqa: SLF001
        "SELECT review_id, run_id, reviewer, status, signal_summary, "
        "trust_decision, calibration_ctx_json, risk_flags_json, "
        "notes, realized_outcome_json, created_at, updated_at "
        "FROM reviews WHERE run_id = ?",
        (run_id,),
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No review found for run_id={run_id}",
        )

    return _row_to_response(row)


@router.put(
    "/runs/{run_id}/review",
    response_model=ReviewResponse,
    responses={
        404: {"description": "run_id or review not found."},
    },
)
def update_review(
    run_id: str,
    body: ReviewUpdateRequest,
    registry: RunRegistry = Depends(get_registry),
) -> ReviewResponse:
    """Update an existing review (e.g. add realized_outcome, change status).

    Only non-None fields in the body are updated. ``updated_at`` is
    automatically set to the current UTC timestamp.
    """
    _require_run(registry, run_id)
    _ensure_reviews_table(registry._conn)  # noqa: SLF001

    # Verify the review exists.
    existing = registry._conn.execute(  # noqa: SLF001
        "SELECT review_id FROM reviews WHERE run_id = ?", (run_id,)
    ).fetchone()
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No review found for run_id={run_id}",
        )

    # Build dynamic SET clause from non-None fields.
    updates: List[str] = []
    params: List[Any] = []

    if body.status is not None:
        # Validate the status value.
        ReviewStatus(body.status)  # raises ValueError if invalid
        updates.append("status = ?")
        params.append(body.status)

    if body.trust_decision is not None:
        updates.append("trust_decision = ?")
        params.append(body.trust_decision)

    if body.notes is not None:
        updates.append("notes = ?")
        params.append(body.notes)

    if body.realized_outcome is not None:
        updates.append("realized_outcome_json = ?")
        params.append(json.dumps(body.realized_outcome, separators=(",", ":")))

    if body.risk_flags is not None:
        updates.append("risk_flags_json = ?")
        params.append(json.dumps(body.risk_flags, separators=(",", ":")))

    # Always update updated_at.
    updates.append("updated_at = ?")
    params.append(iso_now())

    # Execute the update.
    params.append(run_id)
    with registry._conn:  # noqa: SLF001
        registry._conn.execute(  # noqa: SLF001
            f"UPDATE reviews SET {', '.join(updates)} WHERE run_id = ?",
            tuple(params),
        )

    # Return the updated review.
    row = registry._conn.execute(  # noqa: SLF001
        "SELECT review_id, run_id, reviewer, status, signal_summary, "
        "trust_decision, calibration_ctx_json, risk_flags_json, "
        "notes, realized_outcome_json, created_at, updated_at "
        "FROM reviews WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    return _row_to_response(row)


@router.get(
    "/reviews",
    response_model=List[ReviewResponse],
)
def list_reviews(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter by review status: pending, approved, flagged, rejected.",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    registry: RunRegistry = Depends(get_registry),
) -> List[ReviewResponse]:
    """List reviews, optionally filtered by status.

    Returns newest-first by created_at.
    """
    _ensure_reviews_table(registry._conn)  # noqa: SLF001

    if status_filter is not None:
        rows = registry._conn.execute(  # noqa: SLF001
            "SELECT review_id, run_id, reviewer, status, signal_summary, "
            "trust_decision, calibration_ctx_json, risk_flags_json, "
            "notes, realized_outcome_json, created_at, updated_at "
            "FROM reviews WHERE status = ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (status_filter, limit, offset),
        ).fetchall()
    else:
        rows = registry._conn.execute(  # noqa: SLF001
            "SELECT review_id, run_id, reviewer, status, signal_summary, "
            "trust_decision, calibration_ctx_json, risk_flags_json, "
            "notes, realized_outcome_json, created_at, updated_at "
            "FROM reviews ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()

    return [_row_to_response(row) for row in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _review_to_response(review: ReviewArtifact) -> ReviewResponse:
    """Convert a ReviewArtifact to the wire response model."""
    return ReviewResponse(
        review_id=review.review_id,
        run_id=review.run_id,
        reviewer=review.reviewer,
        status=review.status.value,
        signal_summary=review.signal_summary,
        trust_decision=review.trust_decision,
        calibration_context=review.calibration_context,
        risk_flags=review.risk_flags,
        notes=review.notes,
        realized_outcome=review.realized_outcome,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def _row_to_response(row: tuple) -> ReviewResponse:
    """Convert a raw SQLite row to the wire response model.

    Column order matches the SELECT statements above:
    (review_id, run_id, reviewer, status, signal_summary, trust_decision,
     calibration_ctx_json, risk_flags_json, notes, realized_outcome_json,
     created_at, updated_at)
    """
    return ReviewResponse(
        review_id=row[0],
        run_id=row[1],
        reviewer=row[2],
        status=row[3],
        signal_summary=row[4],
        trust_decision=row[5],
        calibration_context=json.loads(row[6]) if row[6] else {},
        risk_flags=json.loads(row[7]) if row[7] else [],
        notes=row[8] or "",
        realized_outcome=json.loads(row[9]) if row[9] else None,
        created_at=row[10] or "",
        updated_at=row[11],
    )


__all__ = [
    "ReviewCreateRequest",
    "ReviewResponse",
    "ReviewUpdateRequest",
    "router",
]
