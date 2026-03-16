"""Alert system for pattern match notifications.

Provides persistent watchlists with confidence threshold triggers,
deduplication, and pluggable notification channels (webhook, log).

Architecture:
    ┌──────────────────────────────────────────────┐
    │              AlertManager                      │
    │                                                │
    │  Watchlist CRUD:                               │
    │    create / get / list / delete / update        │
    │                                                │
    │  Evaluation:                                   │
    │    evaluate(watchlist_id, search_results)       │
    │    → fires alerts when threshold exceeded      │
    │    → deduplicates via cooldown window           │
    │                                                │
    │  Alert history:                                │
    │    list_alerts(watchlist_id, limit)             │
    │                                                │
    │  Backend: SQLite (process-safe, WAL mode)      │
    └──────────────────────────────────────────────┘
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class NotificationChannel(str, Enum):
    LOG = "log"
    WEBHOOK = "webhook"


@dataclass
class Watchlist:
    """A user-defined pattern watch configuration."""
    id: str
    user_id: str
    name: str
    # Pattern definition
    query_values: list[float]
    dataset_id: str | None = None
    symbol: str | None = None
    timeframe: str | None = None
    # Trigger config
    threshold: float = 70.0
    cooldown_seconds: float = 3600.0  # 1 hour dedup window
    # Notification
    channels: list[str] = field(default_factory=lambda: ["log"])
    webhook_url: str | None = None
    # Search config overrides
    top_k: int = 5
    stride: int | None = None
    active_methods: list[str] | None = None
    # State
    enabled: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class Alert:
    """A fired alert record."""
    id: str
    watchlist_id: str
    user_id: str
    confidence_score: float
    match_start_idx: int
    match_end_idx: int
    match_regime: str | None = None
    message: str = ""
    fired_at: float = 0.0
    acknowledged: bool = False


# Type for notification dispatch functions
NotifyFn = Callable[[Alert, Watchlist], None]


def _default_log_notify(alert: Alert, watchlist: Watchlist) -> None:
    """Default notification: log the alert."""
    logger.info(
        "ALERT [%s] watchlist=%s score=%.1f — %s",
        alert.id[:8], watchlist.name, alert.confidence_score, alert.message,
    )


def _webhook_notify(alert: Alert, watchlist: Watchlist) -> None:
    """Send alert to a webhook URL."""
    if not watchlist.webhook_url:
        return
    import urllib.request
    payload = json.dumps({
        "alert_id": alert.id,
        "watchlist_id": watchlist.id,
        "watchlist_name": watchlist.name,
        "confidence_score": alert.confidence_score,
        "match_start_idx": alert.match_start_idx,
        "match_end_idx": alert.match_end_idx,
        "match_regime": alert.match_regime,
        "message": alert.message,
        "fired_at": alert.fired_at,
    }).encode("utf-8")
    req = urllib.request.Request(
        watchlist.webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.warning("Webhook delivery failed for alert %s: %s", alert.id[:8], exc)


class AlertManager:
    """SQLite-backed alert manager with watchlist CRUD and evaluation."""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._notifiers: dict[str, NotifyFn] = {
            "log": _default_log_notify,
            "webhook": _webhook_notify,
        }
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS watchlists (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    query_values TEXT NOT NULL,
                    dataset_id TEXT,
                    symbol TEXT,
                    timeframe TEXT,
                    threshold REAL NOT NULL DEFAULT 70.0,
                    cooldown_seconds REAL NOT NULL DEFAULT 3600.0,
                    channels TEXT NOT NULL DEFAULT '["log"]',
                    webhook_url TEXT,
                    top_k INTEGER NOT NULL DEFAULT 5,
                    stride INTEGER,
                    active_methods TEXT,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    watchlist_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    match_start_idx INTEGER NOT NULL,
                    match_end_idx INTEGER NOT NULL,
                    match_regime TEXT,
                    message TEXT NOT NULL DEFAULT '',
                    fired_at REAL NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (watchlist_id) REFERENCES watchlists(id)
                );

                CREATE INDEX IF NOT EXISTS idx_watchlists_user
                    ON watchlists(user_id);
                CREATE INDEX IF NOT EXISTS idx_alerts_watchlist
                    ON alerts(watchlist_id, fired_at DESC);
                CREATE INDEX IF NOT EXISTS idx_alerts_user
                    ON alerts(user_id, fired_at DESC);
            """)
        finally:
            conn.close()

    def register_notifier(self, channel: str, fn: NotifyFn) -> None:
        """Register a custom notification channel."""
        self._notifiers[channel] = fn

    # ---- Watchlist CRUD ----

    def create_watchlist(
        self,
        user_id: str,
        name: str,
        query_values: list[float],
        **kwargs,
    ) -> Watchlist:
        now = time.time()
        wl = Watchlist(
            id=uuid.uuid4().hex,
            user_id=user_id,
            name=name,
            query_values=query_values,
            created_at=now,
            updated_at=now,
            **kwargs,
        )
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO watchlists
                   (id, user_id, name, query_values, dataset_id, symbol, timeframe,
                    threshold, cooldown_seconds, channels, webhook_url,
                    top_k, stride, active_methods, enabled, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    wl.id, wl.user_id, wl.name, json.dumps(wl.query_values),
                    wl.dataset_id, wl.symbol, wl.timeframe,
                    wl.threshold, wl.cooldown_seconds,
                    json.dumps(wl.channels), wl.webhook_url,
                    wl.top_k, wl.stride,
                    json.dumps(wl.active_methods) if wl.active_methods else None,
                    int(wl.enabled), wl.created_at, wl.updated_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return wl

    def get_watchlist(self, watchlist_id: str) -> Watchlist | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM watchlists WHERE id = ?", (watchlist_id,)
            ).fetchone()
            return self._row_to_watchlist(row) if row else None
        finally:
            conn.close()

    def list_watchlists(self, user_id: str) -> list[Watchlist]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM watchlists WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [self._row_to_watchlist(r) for r in rows]
        finally:
            conn.close()

    def update_watchlist(self, watchlist_id: str, **kwargs) -> Watchlist | None:
        wl = self.get_watchlist(watchlist_id)
        if wl is None:
            return None
        conn = self._connect()
        try:
            updates = []
            params = []
            for key, val in kwargs.items():
                if key in ("query_values", "channels", "active_methods"):
                    updates.append(f"{key} = ?")
                    params.append(json.dumps(val))
                elif key == "enabled":
                    updates.append(f"{key} = ?")
                    params.append(int(val))
                elif hasattr(wl, key):
                    updates.append(f"{key} = ?")
                    params.append(val)
            if not updates:
                return wl
            updates.append("updated_at = ?")
            params.append(time.time())
            params.append(watchlist_id)
            conn.execute(
                f"UPDATE watchlists SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
        finally:
            conn.close()
        return self.get_watchlist(watchlist_id)

    def delete_watchlist(self, watchlist_id: str) -> bool:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM alerts WHERE watchlist_id = ?", (watchlist_id,))
            cursor = conn.execute("DELETE FROM watchlists WHERE id = ?", (watchlist_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ---- Evaluation ----

    def evaluate(
        self,
        watchlist_id: str,
        matches: list,
    ) -> Alert | None:
        """Evaluate search results against a watchlist's threshold.

        Args:
            watchlist_id: The watchlist to evaluate.
            matches: List of MatchResult objects from a search.

        Returns:
            An Alert if threshold was exceeded and cooldown passed, else None.
        """
        wl = self.get_watchlist(watchlist_id)
        if wl is None or not wl.enabled or not matches:
            return None

        best = max(matches, key=lambda m: m.confidence_score)
        if best.confidence_score < wl.threshold:
            return None

        # Deduplication: check cooldown
        if not self._cooldown_passed(watchlist_id, wl.cooldown_seconds):
            return None

        now = time.time()
        alert = Alert(
            id=uuid.uuid4().hex,
            watchlist_id=watchlist_id,
            user_id=wl.user_id,
            confidence_score=best.confidence_score,
            match_start_idx=best.start_idx,
            match_end_idx=best.end_idx,
            match_regime=best.regime,
            message=(
                f"Pattern match on {wl.name}: score {best.confidence_score:.1f} "
                f"exceeds threshold {wl.threshold:.1f}"
            ),
            fired_at=now,
        )

        # Persist alert
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO alerts
                   (id, watchlist_id, user_id, confidence_score,
                    match_start_idx, match_end_idx, match_regime,
                    message, fired_at, acknowledged)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    alert.id, alert.watchlist_id, alert.user_id,
                    alert.confidence_score, alert.match_start_idx,
                    alert.match_end_idx, alert.match_regime,
                    alert.message, alert.fired_at, 0,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        # Dispatch notifications
        for channel in wl.channels:
            notifier = self._notifiers.get(channel)
            if notifier:
                try:
                    notifier(alert, wl)
                except Exception as exc:
                    logger.warning("Notification %s failed: %s", channel, exc)

        return alert

    def _cooldown_passed(self, watchlist_id: str, cooldown_seconds: float) -> bool:
        """Check if enough time has passed since the last alert."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT fired_at FROM alerts WHERE watchlist_id = ? ORDER BY fired_at DESC LIMIT 1",
                (watchlist_id,),
            ).fetchone()
            if row is None:
                return True
            return (time.time() - row["fired_at"]) >= cooldown_seconds
        finally:
            conn.close()

    # ---- Alert history ----

    def list_alerts(
        self,
        user_id: str,
        watchlist_id: str | None = None,
        limit: int = 50,
    ) -> list[Alert]:
        conn = self._connect()
        try:
            if watchlist_id:
                rows = conn.execute(
                    "SELECT * FROM alerts WHERE user_id = ? AND watchlist_id = ? ORDER BY fired_at DESC LIMIT ?",
                    (user_id, watchlist_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM alerts WHERE user_id = ? ORDER BY fired_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
            return [self._row_to_alert(r) for r in rows]
        finally:
            conn.close()

    def acknowledge_alert(self, alert_id: str) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def count_alerts(self, user_id: str, unacknowledged_only: bool = False) -> int:
        conn = self._connect()
        try:
            if unacknowledged_only:
                row = conn.execute(
                    "SELECT COUNT(*) FROM alerts WHERE user_id = ? AND acknowledged = 0",
                    (user_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM alerts WHERE user_id = ?", (user_id,),
                ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    # ---- Helpers ----

    @staticmethod
    def _row_to_watchlist(row: sqlite3.Row) -> Watchlist:
        return Watchlist(
            id=row["id"],
            user_id=row["user_id"],
            name=row["name"],
            query_values=json.loads(row["query_values"]),
            dataset_id=row["dataset_id"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            threshold=row["threshold"],
            cooldown_seconds=row["cooldown_seconds"],
            channels=json.loads(row["channels"]),
            webhook_url=row["webhook_url"],
            top_k=row["top_k"],
            stride=row["stride"],
            active_methods=json.loads(row["active_methods"]) if row["active_methods"] else None,
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_alert(row: sqlite3.Row) -> Alert:
        return Alert(
            id=row["id"],
            watchlist_id=row["watchlist_id"],
            user_id=row["user_id"],
            confidence_score=row["confidence_score"],
            match_start_idx=row["match_start_idx"],
            match_end_idx=row["match_end_idx"],
            match_regime=row["match_regime"],
            message=row["message"],
            fired_at=row["fired_at"],
            acknowledged=bool(row["acknowledged"]),
        )
