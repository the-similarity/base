"""Authentication and multi-tenancy for The Similarity API.

Provides JWT-based auth, user accounts, API key management,
and per-tier rate limiting — all backed by SQLite.

Architecture:
    ┌──────────────────────────────────────────────┐
    │              AuthManager                       │
    │                                                │
    │  User accounts:                                │
    │    create_user / authenticate / get_user        │
    │                                                │
    │  JWT tokens:                                   │
    │    issue_token / refresh_token / verify_token   │
    │                                                │
    │  API keys:                                     │
    │    create_api_key / verify_api_key / revoke      │
    │                                                │
    │  Rate limiting:                                │
    │    check_rate_limit (in-memory sliding window)  │
    │                                                │
    │  Backend: SQLite (WAL) + in-memory rate state  │
    └──────────────────────────────────────────────┘
"""
from __future__ import annotations

import base64
import hashlib
import hmac as _hmac
import json
import logging
import secrets
import sqlite3
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default JWT settings
DEFAULT_TOKEN_EXPIRY = 3600       # 1 hour
DEFAULT_REFRESH_EXPIRY = 604800   # 7 days


# ---------------------------------------------------------------------------
# Minimal HS256 JWT (pure stdlib — no PyJWT / cryptography dependency)
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _jwt_encode(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = f"{segments[0]}.{segments[1]}"
    sig = _hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    segments.append(_b64url_encode(sig))
    return ".".join(segments)


def _jwt_decode(token: str, secret: str) -> dict | None:
    """Decode and verify an HS256 JWT. Returns payload dict or None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        signing_input = f"{parts[0]}.{parts[1]}"
        expected_sig = _hmac.new(
            secret.encode(), signing_input.encode(), hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(parts[2])
        if not _hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(parts[1]))
        # Check expiry
        if "exp" in payload and payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None


class Tier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


# Requests per minute per tier
TIER_RATE_LIMITS: dict[str, int] = {
    Tier.FREE: 10,
    Tier.PRO: 60,
    Tier.ENTERPRISE: 300,
}


@dataclass
class User:
    """A registered user account."""
    id: str
    email: str
    tier: str = Tier.FREE
    enabled: bool = True
    created_at: float = 0.0


@dataclass
class APIKey:
    """An API key for programmatic access."""
    id: str
    user_id: str
    name: str
    key_prefix: str  # first 8 chars, for display
    enabled: bool = True
    created_at: float = 0.0
    last_used_at: float | None = None


@dataclass
class TokenPair:
    """JWT access + refresh token pair."""
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"


def _hash_password(password: str, salt: str) -> str:
    """Hash password with PBKDF2-SHA256."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), iterations=100_000
    ).hex()


def _hash_key(key: str) -> str:
    """Hash an API key or refresh token for storage."""
    return hashlib.sha256(key.encode()).hexdigest()


class RateLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self) -> None:
        # user_id -> list of request timestamps
        self._windows: dict[str, list[float]] = defaultdict(list)

    def check(self, user_id: str, tier: str) -> tuple[bool, int]:
        """Check if a request is allowed.

        Returns:
            (allowed, remaining) — whether the request is allowed and
            how many requests remain in the current window.
        """
        limit = TIER_RATE_LIMITS.get(tier, TIER_RATE_LIMITS[Tier.FREE])
        now = time.time()
        window_start = now - 60.0  # 1-minute window

        # Prune old entries
        timestamps = self._windows[user_id]
        self._windows[user_id] = [t for t in timestamps if t > window_start]
        timestamps = self._windows[user_id]

        remaining = max(0, limit - len(timestamps))
        if len(timestamps) >= limit:
            return False, 0

        self._windows[user_id].append(now)
        return True, remaining - 1

    def reset(self, user_id: str) -> None:
        """Reset rate limit state for a user."""
        self._windows.pop(user_id, None)


class AuthManager:
    """SQLite-backed auth manager with JWT, API keys, and rate limiting."""

    def __init__(
        self,
        db_path: str | Path,
        jwt_secret: str = "change-me-in-production",
        token_expiry: int = DEFAULT_TOKEN_EXPIRY,
        refresh_expiry: int = DEFAULT_REFRESH_EXPIRY,
    ):
        self._db_path = str(db_path)
        self._jwt_secret = jwt_secret
        self._token_expiry = token_expiry
        self._refresh_expiry = refresh_expiry
        self._rate_limiter = RateLimiter()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    tier TEXT NOT NULL DEFAULT 'free',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    key_hash TEXT UNIQUE NOT NULL,
                    key_prefix TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    last_used_at REAL,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                );

                CREATE INDEX IF NOT EXISTS idx_api_keys_user
                    ON api_keys(user_id);
                CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user
                    ON refresh_tokens(user_id);
            """)
        finally:
            conn.close()

    # ---- User management ----

    def create_user(self, email: str, password: str, tier: str = Tier.FREE) -> User:
        """Create a new user account.

        Raises:
            ValueError: If email already exists.
        """
        email = email.strip().lower()
        salt = secrets.token_hex(16)
        pw_hash = _hash_password(password, salt)
        now = time.time()
        user_id = uuid.uuid4().hex

        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO users (id, email, password_hash, salt, tier, enabled, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (user_id, email, pw_hash, salt, tier, now),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Email already registered: {email}") from exc
        finally:
            conn.close()

        return User(id=user_id, email=email, tier=tier, enabled=True, created_at=now)

    def authenticate(self, email: str, password: str) -> User | None:
        """Authenticate by email + password. Returns User or None."""
        email = email.strip().lower()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ? AND enabled = 1", (email,)
            ).fetchone()
            if row is None:
                return None
            expected = _hash_password(password, row["salt"])
            if not _hmac.compare_digest(expected, row["password_hash"]):
                return None
            return self._row_to_user(row)
        finally:
            conn.close()

    def get_user(self, user_id: str) -> User | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return self._row_to_user(row) if row else None
        finally:
            conn.close()

    def update_user_tier(self, user_id: str, tier: str) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE users SET tier = ? WHERE id = ?", (tier, user_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ---- JWT tokens ----

    def issue_tokens(self, user: User) -> TokenPair:
        """Issue access + refresh token pair."""
        now = time.time()

        access_payload = {
            "sub": user.id,
            "email": user.email,
            "tier": user.tier,
            "iat": now,
            "exp": now + self._token_expiry,
            "type": "access",
        }
        access_token = _jwt_encode(access_payload, self._jwt_secret)

        refresh_payload = {
            "sub": user.id,
            "iat": now,
            "exp": now + self._refresh_expiry,
            "type": "refresh",
            "jti": uuid.uuid4().hex,
        }
        refresh_token = _jwt_encode(refresh_payload, self._jwt_secret)

        # Store refresh token hash
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO refresh_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (_hash_key(refresh_token), user.id, now + self._refresh_expiry),
            )
            conn.commit()
        finally:
            conn.close()

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._token_expiry,
        )

    def verify_token(self, token: str) -> dict[str, Any] | None:
        """Verify and decode a JWT access token.

        Returns decoded payload or None if invalid/expired.
        """
        payload = _jwt_decode(token, self._jwt_secret)
        if payload is None or payload.get("type") != "access":
            return None
        return payload

    def refresh_tokens(self, refresh_token: str) -> TokenPair | None:
        """Use a refresh token to get a new token pair.

        The old refresh token is revoked (rotation).
        Returns None if the refresh token is invalid or revoked.
        """
        payload = _jwt_decode(refresh_token, self._jwt_secret)
        if payload is None or payload.get("type") != "refresh":
            return None

        token_hash = _hash_key(refresh_token)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM refresh_tokens WHERE token_hash = ? AND revoked = 0",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None

            # Revoke the old refresh token
            conn.execute(
                "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ?",
                (token_hash,),
            )
            conn.commit()
        finally:
            conn.close()

        user = self.get_user(payload["sub"])
        if user is None or not user.enabled:
            return None

        return self.issue_tokens(user)

    # ---- API keys ----

    def create_api_key(self, user_id: str, name: str) -> tuple[APIKey, str]:
        """Create a new API key.

        Returns (APIKey metadata, raw key string).
        The raw key is only returned once — store it securely.
        """
        raw_key = f"sim_{secrets.token_urlsafe(32)}"
        key_hash = _hash_key(raw_key)
        key_prefix = raw_key[:12]
        now = time.time()
        key_id = uuid.uuid4().hex

        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO api_keys (id, user_id, name, key_hash, key_prefix, enabled, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (key_id, user_id, name, key_hash, key_prefix, now),
            )
            conn.commit()
        finally:
            conn.close()

        api_key = APIKey(
            id=key_id, user_id=user_id, name=name,
            key_prefix=key_prefix, enabled=True, created_at=now,
        )
        return api_key, raw_key

    def verify_api_key(self, raw_key: str) -> User | None:
        """Verify an API key and return the associated user.

        Also updates last_used_at timestamp.
        """
        key_hash = _hash_key(raw_key)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT ak.*, u.email, u.tier, u.enabled as user_enabled "
                "FROM api_keys ak JOIN users u ON ak.user_id = u.id "
                "WHERE ak.key_hash = ? AND ak.enabled = 1",
                (key_hash,),
            ).fetchone()
            if row is None or not row["user_enabled"]:
                return None

            # Update last_used_at
            conn.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (time.time(), row["id"]),
            )
            conn.commit()

            return User(
                id=row["user_id"],
                email=row["email"],
                tier=row["tier"],
                enabled=bool(row["user_enabled"]),
            )
        finally:
            conn.close()

    def list_api_keys(self, user_id: str) -> list[APIKey]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM api_keys WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [
                APIKey(
                    id=r["id"], user_id=r["user_id"], name=r["name"],
                    key_prefix=r["key_prefix"], enabled=bool(r["enabled"]),
                    created_at=r["created_at"], last_used_at=r["last_used_at"],
                )
                for r in rows
            ]
        finally:
            conn.close()

    def revoke_api_key(self, key_id: str) -> bool:
        conn = self._connect()
        try:
            cursor = conn.execute(
                "UPDATE api_keys SET enabled = 0 WHERE id = ?", (key_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # ---- Rate limiting ----

    def check_rate_limit(self, user_id: str, tier: str) -> tuple[bool, int]:
        """Check rate limit for a user. Returns (allowed, remaining)."""
        return self._rate_limiter.check(user_id, tier)

    # ---- Helpers ----

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> User:
        return User(
            id=row["id"],
            email=row["email"],
            tier=row["tier"],
            enabled=bool(row["enabled"]),
            created_at=row["created_at"],
        )
