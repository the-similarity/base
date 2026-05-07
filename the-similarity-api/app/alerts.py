"""Delivery adapters for personalized setup scanner alerts.

This module is intentionally self-contained while Worktree A's scanner schema
is still in flight. The placeholder dataclasses below mirror the delivery
surface expected from ``vision/setup_scanner_schema_contract.md``: a scanner
event is rendered into one or more outbound alert messages, each with a stable
``alert_id`` and channel-specific recipient.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import smtplib
import sqlite3
import ssl
import time
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, HttpUrl

from the_similarity.core.auth import User

from app.auth_deps import get_current_user

logger = logging.getLogger(__name__)

DISCLAIMER = "Not financial advice. Past performance does not guarantee future results."
MAX_ATTEMPTS = 3
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 4.0
Channel = Literal["email", "discord"]

router = APIRouter(prefix="/setup-scanner/alerts", tags=["setup-scanner-alerts"])


@dataclass(frozen=True)
class SetupScannerAlert:
    """Placeholder scanner event contract until Worktree A lands the schema."""

    alert_id: str
    user_id: str
    setup_id: str
    instrument: str
    timeframe: str
    confidence: float
    match_summary: str
    analog_count: int | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class AlertDeliveryMessage:
    """Channel-neutral rendered delivery payload."""

    alert: SetupScannerAlert
    title: str
    body: str
    action_url: str | None = None


class EmailAlertRequest(BaseModel):
    recipient_email: str = Field(..., min_length=3, max_length=320)
    subject: str = Field(..., min_length=1, max_length=200)
    body: str = Field(..., min_length=1, max_length=8000)
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)


class DiscordWebhookCreateRequest(BaseModel):
    webhook_url: HttpUrl
    label: str = Field(default="Discord", min_length=1, max_length=120)


class DiscordWebhookResponse(BaseModel):
    id: str
    label: str
    url_fingerprint: str
    created_at: float
    updated_at: float


class DiscordAlertRequest(BaseModel):
    webhook_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1, max_length=1800)
    username: str | None = Field(default="The Similarity", max_length=80)
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)


class DeliveryResponse(BaseModel):
    status: Literal["delivered", "duplicate", "dead_lettered"]
    delivery_id: str
    attempts: int


class DeadLetterResponse(BaseModel):
    id: str
    channel: str
    user_id: str
    alert_id: str
    reason: str
    attempts: int
    payload: dict[str, Any]
    created_at: float


class DeliveryStore:
    """SQLite-backed delivery state and manual-review queue."""

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
                CREATE TABLE IF NOT EXISTS deliveries (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    channel TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    alert_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alert_dead_letters (
                    id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    alert_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS discord_webhooks (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    encrypted_url TEXT NOT NULL,
                    url_fingerprint TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )

    def get_delivery_by_key(self, idempotency_key: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM deliveries WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()

    def record_delivery(
        self,
        *,
        idempotency_key: str,
        channel: Channel,
        user_id: str,
        alert_id: str,
        status: str,
        attempts: int,
    ) -> str:
        delivery_id = str(uuid.uuid4())
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO deliveries (
                    id, idempotency_key, channel, user_id, alert_id, status,
                    attempts, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    delivery_id,
                    idempotency_key,
                    channel,
                    user_id,
                    alert_id,
                    status,
                    attempts,
                    now,
                    now,
                ),
            )
        return delivery_id

    def dead_letter(
        self,
        *,
        channel: Channel,
        user_id: str,
        alert_id: str,
        reason: str,
        attempts: int,
        payload: dict[str, Any],
    ) -> str:
        dead_letter_id = str(uuid.uuid4())
        now = time.time()
        safe_payload = _strip_sensitive_payload(payload)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO alert_dead_letters (
                    id, channel, user_id, alert_id, reason, attempts,
                    payload_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dead_letter_id,
                    channel,
                    user_id,
                    alert_id,
                    reason,
                    attempts,
                    json.dumps(safe_payload, sort_keys=True),
                    now,
                ),
            )
        logger.warning(
            "alert delivery dead-lettered",
            extra={"channel": channel, "user_id": user_id, "alert_id": alert_id},
        )
        return dead_letter_id

    def list_dead_letters(self, user_id: str, limit: int = 50) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM alert_dead_letters
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

    def create_discord_webhook(
        self,
        *,
        user_id: str,
        label: str,
        webhook_url: str,
        encryption_key: str,
    ) -> DiscordWebhookResponse:
        now = time.time()
        webhook_id = str(uuid.uuid4())
        encrypted_url = encrypt_secret(webhook_url, encryption_key)
        fingerprint = _secret_fingerprint(webhook_url)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO discord_webhooks (
                    id, user_id, label, encrypted_url, url_fingerprint,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (webhook_id, user_id, label, encrypted_url, fingerprint, now, now),
            )
        return DiscordWebhookResponse(
            id=webhook_id,
            label=label,
            url_fingerprint=fingerprint,
            created_at=now,
            updated_at=now,
        )

    def get_discord_webhook(
        self, *, user_id: str, webhook_id: str
    ) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM discord_webhooks
                WHERE id = ? AND user_id = ?
                """,
                (webhook_id, user_id),
            ).fetchone()


_delivery_store: DeliveryStore | None = None


def get_delivery_store() -> DeliveryStore:
    global _delivery_store
    if _delivery_store is None:
        data_dir = Path(os.getenv("THE_SIMILARITY_DATA_DIR", "/tmp/the_similarity"))
        _delivery_store = DeliveryStore(data_dir / "setup_scanner_delivery.db")
    return _delivery_store


def _discord_secret() -> str:
    secret = os.getenv("THE_SIMILARITY_DISCORD_WEBHOOK_SECRET")
    if secret:
        return secret
    fallback = os.getenv("THE_SIMILARITY_JWT_SECRET")
    if fallback and fallback != "dev-secret-change-in-prod":
        return fallback
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Discord webhook encryption secret is not configured",
    )


def encrypt_secret(value: str, key: str) -> str:
    """Encrypt a short secret using a keyed stream plus integrity tag.

    The project currently avoids a cryptography dependency in this API package.
    This keeps webhook URLs out of plaintext at rest and authenticates the
    ciphertext with HMAC-SHA256. Production deployments should pin a strong
    ``THE_SIMILARITY_DISCORD_WEBHOOK_SECRET``.
    """

    nonce = secrets.token_bytes(16)
    plaintext = value.encode()
    keystream = _derive_stream(key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream))
    tag = hmac.new(
        _key_bytes(key), nonce + ciphertext, hashlib.sha256
    ).digest()
    token = base64.urlsafe_b64encode(nonce + tag + ciphertext).decode()
    return token


def decrypt_secret(token: str, key: str) -> str:
    raw = base64.urlsafe_b64decode(token.encode())
    nonce = raw[:16]
    tag = raw[16:48]
    ciphertext = raw[48:]
    expected = hmac.new(
        _key_bytes(key), nonce + ciphertext, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("encrypted secret failed integrity check")
    keystream = _derive_stream(key, nonce, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, keystream))
    return plaintext.decode()


def _derive_stream(key: str, nonce: bytes, length: int) -> bytes:
    output = bytearray()
    counter = 0
    key_bytes = _key_bytes(key)
    while len(output) < length:
        output.extend(
            hmac.new(
                key_bytes,
                nonce + counter.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
        )
        counter += 1
    return bytes(output[:length])


def _key_bytes(key: str) -> bytes:
    return hashlib.sha256(key.encode()).digest()


def _secret_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _strip_sensitive_payload(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = {"webhook_url", "encrypted_url", "authorization", "token", "secret"}
    return {k: v for k, v in payload.items() if k.lower() not in blocked}


def with_disclaimer(text: str) -> str:
    return f"{text.rstrip()}\n\n{DISCLAIMER}"


def render_scanner_message(
    alert: SetupScannerAlert,
    action_url: str | None = None,
) -> AlertDeliveryMessage:
    analog_text = (
        f" {alert.analog_count} historical analogs found."
        if alert.analog_count is not None
        else ""
    )
    title = f"Setup active on {alert.instrument} {alert.timeframe}"
    body = (
        f"{alert.match_summary}\n"
        f"Confidence: {alert.confidence:.1f}%.{analog_text}"
    )
    return AlertDeliveryMessage(alert=alert, title=title, body=body, action_url=action_url)


def _smtp_config() -> dict[str, Any]:
    return {
        "host": os.getenv("THE_SIMILARITY_SMTP_HOST", ""),
        "port": int(os.getenv("THE_SIMILARITY_SMTP_PORT", "587")),
        "username": os.getenv("THE_SIMILARITY_SMTP_USERNAME", ""),
        "password": os.getenv("THE_SIMILARITY_SMTP_PASSWORD", ""),
        "from_email": os.getenv(
            "THE_SIMILARITY_ALERT_FROM_EMAIL", "alerts@thesimilarity.tech"
        ),
        "use_tls": os.getenv("THE_SIMILARITY_SMTP_USE_TLS", "1") != "0",
    }


def _sleep_for_retry(attempt: int) -> None:
    delay = min(INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)
    time.sleep(delay)


def _send_email_once(recipient: str, subject: str, body: str) -> None:
    cfg = _smtp_config()
    if not cfg["host"]:
        raise RuntimeError("SMTP host is not configured")

    message = EmailMessage()
    message["From"] = cfg["from_email"]
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(with_disclaimer(body))

    context = ssl.create_default_context()
    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as smtp:
        if cfg["use_tls"]:
            smtp.starttls(context=context)
        if cfg["username"]:
            smtp.login(cfg["username"], cfg["password"])
        smtp.send_message(message)


def _post_discord_once(webhook_url: str, payload: dict[str, Any]) -> None:
    safe_payload = {
        "content": with_disclaimer(str(payload["content"])),
        "username": payload.get("username") or "The Similarity",
        "allowed_mentions": {"parse": []},
    }
    with httpx.Client(timeout=15) as client:
        response = client.post(webhook_url, json=safe_payload)
        response.raise_for_status()


def _deliver_with_retry(send_once) -> tuple[bool, int, str | None]:
    last_error: str | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            send_once()
            return True, attempt, None
        except Exception as exc:  # noqa: BLE001 - adapters normalize failure.
            last_error = exc.__class__.__name__
            if attempt < MAX_ATTEMPTS:
                _sleep_for_retry(attempt)
    return False, MAX_ATTEMPTS, last_error or "delivery_failed"


@router.post("/email", response_model=DeliveryResponse)
def deliver_email_alert(
    body: EmailAlertRequest,
    user: User = Depends(get_current_user),
    store: DeliveryStore = Depends(get_delivery_store),
) -> DeliveryResponse:
    existing = store.get_delivery_by_key(body.idempotency_key)
    if existing is not None:
        return DeliveryResponse(
            status="duplicate",
            delivery_id=existing["id"],
            attempts=existing["attempts"],
        )

    sent, attempts, reason = _deliver_with_retry(
        lambda: _send_email_once(body.recipient_email, body.subject, body.body)
    )
    delivery_status = "delivered" if sent else "dead_lettered"
    delivery_id = store.record_delivery(
        idempotency_key=body.idempotency_key,
        channel="email",
        user_id=user.id,
        alert_id=body.alert_id,
        status=delivery_status,
        attempts=attempts,
    )
    if not sent:
        store.dead_letter(
            channel="email",
            user_id=user.id,
            alert_id=body.alert_id,
            reason=reason or "email_delivery_failed",
            attempts=attempts,
            payload=body.model_dump(),
        )
    return DeliveryResponse(status=delivery_status, delivery_id=delivery_id, attempts=attempts)


@router.post("/discord/webhooks", response_model=DiscordWebhookResponse, status_code=201)
def create_discord_webhook(
    body: DiscordWebhookCreateRequest,
    user: User = Depends(get_current_user),
    store: DeliveryStore = Depends(get_delivery_store),
) -> DiscordWebhookResponse:
    return store.create_discord_webhook(
        user_id=user.id,
        label=body.label,
        webhook_url=str(body.webhook_url),
        encryption_key=_discord_secret(),
    )


@router.post("/discord", response_model=DeliveryResponse)
def deliver_discord_alert(
    body: DiscordAlertRequest,
    user: User = Depends(get_current_user),
    store: DeliveryStore = Depends(get_delivery_store),
) -> DeliveryResponse:
    existing = store.get_delivery_by_key(body.idempotency_key)
    if existing is not None:
        return DeliveryResponse(
            status="duplicate",
            delivery_id=existing["id"],
            attempts=existing["attempts"],
        )

    webhook = store.get_discord_webhook(user_id=user.id, webhook_id=body.webhook_id)
    if webhook is None:
        raise HTTPException(status_code=404, detail="Discord webhook not found")
    try:
        webhook_url = decrypt_secret(webhook["encrypted_url"], _discord_secret())
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Discord webhook is unreadable") from exc

    payload = body.model_dump()
    sent, attempts, reason = _deliver_with_retry(
        lambda: _post_discord_once(webhook_url, payload)
    )
    delivery_status = "delivered" if sent else "dead_lettered"
    delivery_id = store.record_delivery(
        idempotency_key=body.idempotency_key,
        channel="discord",
        user_id=user.id,
        alert_id=body.alert_id,
        status=delivery_status,
        attempts=attempts,
    )
    if not sent:
        safe_payload = payload | {
            "webhook_id": body.webhook_id,
            "url_fingerprint": webhook["url_fingerprint"],
        }
        store.dead_letter(
            channel="discord",
            user_id=user.id,
            alert_id=body.alert_id,
            reason=reason or "discord_delivery_failed",
            attempts=attempts,
            payload=safe_payload,
        )
    return DeliveryResponse(status=delivery_status, delivery_id=delivery_id, attempts=attempts)


@router.get("/dead-letters", response_model=list[DeadLetterResponse])
def list_dead_letters(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    store: DeliveryStore = Depends(get_delivery_store),
) -> list[DeadLetterResponse]:
    rows = store.list_dead_letters(user.id, limit=limit)
    return [
        DeadLetterResponse(
            id=row["id"],
            channel=row["channel"],
            user_id=row["user_id"],
            alert_id=row["alert_id"],
            reason=row["reason"],
            attempts=row["attempts"],
            payload=json.loads(row["payload_json"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.post("/preview-disclaimer", response_class=Response)
def preview_disclaimer(body: dict[str, str]) -> Response:
    text = body.get("text", "")
    return Response(content=with_disclaimer(text), media_type="text/plain")


def scanner_message_to_email(message: AlertDeliveryMessage) -> EmailAlertRequest:
    return EmailAlertRequest(
        recipient_email="placeholder@example.com",
        subject=message.title,
        body=message.body,
        alert_id=message.alert.alert_id,
    )


def scanner_message_to_discord(
    message: AlertDeliveryMessage,
    webhook_id: str,
) -> DiscordAlertRequest:
    content = message.body
    if message.action_url:
        content = f"{content}\n{message.action_url}"
    return DiscordAlertRequest(
        webhook_id=webhook_id,
        content=content,
        alert_id=message.alert.alert_id,
    )
