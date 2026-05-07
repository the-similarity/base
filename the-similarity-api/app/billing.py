"""Stripe Checkout billing surface for the personalized setup scanner."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from the_similarity.core.auth import User

from app.auth_deps import get_current_user

logger = logging.getLogger(__name__)

MONTHLY_PRICE_CENTS = 2900
MONEY_BACK_GUARANTEE = "Month-1 money-back guarantee. No free trial."

router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    success_url: str = Field(..., min_length=8, max_length=2048)
    cancel_url: str = Field(..., min_length=8, max_length=2048)
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)


class CheckoutResponse(BaseModel):
    checkout_session_id: str
    checkout_url: str
    idempotency_key: str


class BillingStatusResponse(BaseModel):
    user_id: str
    stripe_customer_id: str | None = None
    subscription_id: str | None = None
    status: str | None = None
    current_period_end: float | None = None
    guarantee: str = MONEY_BACK_GUARANTEE


class StripeWebhookResponse(BaseModel):
    status: Literal["processed", "duplicate", "ignored"]
    event_id: str | None = None


class BillingStore:
    """SQLite state with idempotency keys on every billing write."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stripe_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    processed_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS checkout_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    stripe_customer_id TEXT,
                    checkout_url TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS billing_subscriptions (
                    user_id TEXT PRIMARY KEY,
                    stripe_customer_id TEXT,
                    subscription_id TEXT,
                    status TEXT NOT NULL,
                    current_period_end REAL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS billing_writes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    write_kind TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL
                );
                """
            )

    def get_checkout_by_key(self, idempotency_key: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM checkout_sessions WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()

    def record_checkout_session(
        self,
        *,
        session_id: str,
        user_id: str,
        stripe_customer_id: str | None,
        checkout_url: str,
        idempotency_key: str,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO checkout_sessions (
                    session_id, user_id, stripe_customer_id, checkout_url,
                    idempotency_key, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    stripe_customer_id,
                    checkout_url,
                    idempotency_key,
                    now,
                ),
            )
            self._record_write(
                conn,
                user_id=user_id,
                write_kind="checkout_session.created",
                idempotency_key=f"checkout-write:{idempotency_key}",
            )

    def has_event(self, event_id: str) -> bool:
        with self._connect() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM stripe_events WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
                is not None
            )

    def record_event(
        self,
        *,
        event_id: str,
        event_type: str,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO stripe_events (
                    event_id, event_type, idempotency_key, payload_json, processed_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event_type,
                    idempotency_key,
                    json.dumps(payload, sort_keys=True),
                    time.time(),
                ),
            )

    def upsert_subscription(
        self,
        *,
        user_id: str,
        stripe_customer_id: str | None,
        subscription_id: str | None,
        status: str,
        current_period_end: float | None,
        idempotency_key: str,
    ) -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO billing_subscriptions (
                    user_id, stripe_customer_id, subscription_id, status,
                    current_period_end, idempotency_key, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    stripe_customer_id = excluded.stripe_customer_id,
                    subscription_id = excluded.subscription_id,
                    status = excluded.status,
                    current_period_end = excluded.current_period_end,
                    idempotency_key = excluded.idempotency_key,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    stripe_customer_id,
                    subscription_id,
                    status,
                    current_period_end,
                    idempotency_key,
                    now,
                ),
            )
            self._record_write(
                conn,
                user_id=user_id,
                write_kind="subscription.upsert",
                idempotency_key=f"subscription-write:{idempotency_key}",
            )

    def get_status(self, user_id: str) -> BillingStatusResponse:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM billing_subscriptions WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return BillingStatusResponse(user_id=user_id)
        return BillingStatusResponse(
            user_id=user_id,
            stripe_customer_id=row["stripe_customer_id"],
            subscription_id=row["subscription_id"],
            status=row["status"],
            current_period_end=row["current_period_end"],
        )

    def _record_write(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str,
        write_kind: str,
        idempotency_key: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO billing_writes (id, user_id, write_kind, idempotency_key, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (str(uuid.uuid4()), user_id, write_kind, idempotency_key, time.time()),
        )


_billing_store: BillingStore | None = None


def get_billing_store() -> BillingStore:
    global _billing_store
    if _billing_store is None:
        data_dir = Path(os.getenv("THE_SIMILARITY_DATA_DIR", "/tmp/the_similarity"))
        _billing_store = BillingStore(data_dir / "setup_scanner_billing.db")
    return _billing_store


def _stripe_secret_key() -> str:
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe secret key is not configured",
        )
    return key


def _stripe_webhook_secret() -> str:
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stripe webhook secret is not configured",
        )
    return secret


def _price_id() -> str | None:
    return os.getenv("STRIPE_SETUP_SCANNER_PRICE_ID")


def _create_checkout_session(
    *,
    user: User,
    success_url: str,
    cancel_url: str,
    idempotency_key: str,
) -> dict[str, Any]:
    form: list[tuple[str, str]] = [
        ("mode", "subscription"),
        ("success_url", success_url),
        ("cancel_url", cancel_url),
        ("customer_email", user.email),
        ("client_reference_id", user.id),
        ("metadata[user_id]", user.id),
        ("metadata[product]", "personalized_setup_scanner"),
        ("metadata[guarantee]", MONEY_BACK_GUARANTEE),
        ("subscription_data[metadata][user_id]", user.id),
        ("subscription_data[metadata][product]", "personalized_setup_scanner"),
        ("subscription_data[metadata][guarantee]", MONEY_BACK_GUARANTEE),
        ("allow_promotion_codes", "true"),
    ]
    price_id = _price_id()
    if price_id:
        form.extend(
            [
                ("line_items[0][price]", price_id),
                ("line_items[0][quantity]", "1"),
            ]
        )
    else:
        form.extend(
            [
                ("line_items[0][price_data][currency]", "usd"),
                ("line_items[0][price_data][unit_amount]", str(MONTHLY_PRICE_CENTS)),
                ("line_items[0][price_data][recurring][interval]", "month"),
                (
                    "line_items[0][price_data][product_data][name]",
                    "Personalized Setup Scanner",
                ),
                (
                    "line_items[0][price_data][product_data][description]",
                    "$29/mo recurring research subscription. "
                    "Month-1 money-back guarantee. No free trial.",
                ),
                ("line_items[0][quantity]", "1"),
            ]
        )

    headers = {
        "Authorization": f"Bearer {_stripe_secret_key()}",
        "Idempotency-Key": idempotency_key,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    with httpx.Client(timeout=20) as client:
        response = client.post(
            "https://api.stripe.com/v1/checkout/sessions",
            content=urlencode(form),
            headers=headers,
        )
    if response.status_code >= 400:
        logger.warning(
            "stripe checkout session creation failed",
            extra={"status": response.status_code},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Stripe Checkout session could not be created",
        )
    return response.json()


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout_session(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    store: BillingStore = Depends(get_billing_store),
) -> CheckoutResponse:
    existing = store.get_checkout_by_key(body.idempotency_key)
    if existing is not None:
        return CheckoutResponse(
            checkout_session_id=existing["session_id"],
            checkout_url=existing["checkout_url"],
            idempotency_key=body.idempotency_key,
        )

    session = _create_checkout_session(
        user=user,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
        idempotency_key=body.idempotency_key,
    )
    session_id = str(session["id"])
    checkout_url = str(session["url"])
    store.record_checkout_session(
        session_id=session_id,
        user_id=user.id,
        stripe_customer_id=session.get("customer"),
        checkout_url=checkout_url,
        idempotency_key=body.idempotency_key,
    )
    return CheckoutResponse(
        checkout_session_id=session_id,
        checkout_url=checkout_url,
        idempotency_key=body.idempotency_key,
    )


@router.get("/status", response_model=BillingStatusResponse)
def billing_status(
    user: User = Depends(get_current_user),
    store: BillingStore = Depends(get_billing_store),
) -> BillingStatusResponse:
    return store.get_status(user.id)


@router.post("/webhooks/stripe", response_model=StripeWebhookResponse)
async def handle_stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    store: BillingStore = Depends(get_billing_store),
) -> StripeWebhookResponse:
    payload_bytes = await request.body()
    _verify_stripe_signature(payload_bytes, stripe_signature)
    try:
        event = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe payload") from exc

    event_id = str(event.get("id", ""))
    event_type = str(event.get("type", ""))
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Invalid Stripe event")
    if store.has_event(event_id):
        return StripeWebhookResponse(status="duplicate", event_id=event_id)

    idempotency_key = f"stripe-event:{event_id}"
    data_object = event.get("data", {}).get("object", {})
    processed = _apply_stripe_event(
        event_id=event_id,
        event_type=event_type,
        data_object=data_object,
        store=store,
    )
    store.record_event(
        event_id=event_id,
        event_type=event_type,
        idempotency_key=idempotency_key,
        payload=event,
    )
    return StripeWebhookResponse(
        status="processed" if processed else "ignored",
        event_id=event_id,
    )


def _verify_stripe_signature(payload: bytes, signature_header: str | None) -> None:
    if not signature_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")
    values: dict[str, str] = {}
    for item in signature_header.split(","):
        if "=" in item:
            key, value = item.split("=", 1)
            values[key] = value
    timestamp = values.get("t")
    signature = values.get("v1")
    if not timestamp or not signature:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    signed_payload = timestamp.encode() + b"." + payload
    expected = hmac.new(
        _stripe_webhook_secret().encode(),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")


def _apply_stripe_event(
    *,
    event_id: str,
    event_type: str,
    data_object: dict[str, Any],
    store: BillingStore,
) -> bool:
    if event_type == "checkout.session.completed":
        user_id = _metadata_user_id(data_object)
        if not user_id:
            return False
        store.upsert_subscription(
            user_id=user_id,
            stripe_customer_id=_string_or_none(data_object.get("customer")),
            subscription_id=_string_or_none(data_object.get("subscription")),
            status="checkout_completed",
            current_period_end=None,
            idempotency_key=f"{event_id}:checkout.session.completed",
        )
        return True

    if event_type in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        user_id = _metadata_user_id(data_object)
        if not user_id:
            return False
        store.upsert_subscription(
            user_id=user_id,
            stripe_customer_id=_string_or_none(data_object.get("customer")),
            subscription_id=_string_or_none(data_object.get("id")),
            status=str(data_object.get("status", "unknown")),
            current_period_end=_float_or_none(data_object.get("current_period_end")),
            idempotency_key=f"{event_id}:{event_type}",
        )
        return True

    if event_type in {"invoice.payment_failed", "invoice.paid"}:
        subscription_id = _string_or_none(data_object.get("subscription"))
        user_id = _metadata_user_id(data_object)
        if not user_id:
            return False
        status_value = "past_due" if event_type == "invoice.payment_failed" else "active"
        store.upsert_subscription(
            user_id=user_id,
            stripe_customer_id=_string_or_none(data_object.get("customer")),
            subscription_id=subscription_id,
            status=status_value,
            current_period_end=None,
            idempotency_key=f"{event_id}:{event_type}",
        )
        return True

    return False


def _metadata_user_id(data_object: dict[str, Any]) -> str | None:
    metadata = data_object.get("metadata") or {}
    if isinstance(metadata, dict):
        user_id = metadata.get("user_id")
        if user_id:
            return str(user_id)
    client_reference_id = data_object.get("client_reference_id")
    if client_reference_id:
        return str(client_reference_id)
    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
