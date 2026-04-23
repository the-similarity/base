"""
FastAPI dependency injection for authentication, authorization, and rate limiting.

This module provides four injectable dependencies:
- `get_auth_manager()` → singleton AuthManager (lazy-initialized)
- `get_current_user()` → extract + verify the authenticated user
- `get_optional_user()` → same as above but returns None instead of 401
- `enforce_rate_limit()` → verify rate limit + return user

AI AGENT NOTES:
- AuthManager is a singleton with lazy initialization. It persists across
  requests for the lifetime of the FastAPI process.
- JWT secret MUST be set via THE_SIMILARITY_JWT_SECRET env var in production.
  The "dev-secret-change-in-prod" default exists only for local development
  and emits a warning when used.
- Two authentication methods are supported (checked in this priority):
  1. API key: X-API-Key header (for programmatic/SDK access)
  2. Bearer token: Authorization header (for frontend/browser access)
- Rate limiting is tiered (free/pro/enterprise). The limit check is per-user
  and uses the AuthManager's internal sliding window counter.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, Header, HTTPException

from the_similarity.core.auth import AuthManager, User

# ---------------------------------------------------------------------------
# Singleton state
# ---------------------------------------------------------------------------
# Lazy-initialized at first request, persists for process lifetime.
# An alternative would be FastAPI lifespan events, but lazy init keeps
# the module import-safe and testable.
_auth_manager: AuthManager | None = None
_data_dir: Path | None = None


def _get_data_dir() -> Path:
    """Resolve and create the data directory for SQLite databases.

    Default: /tmp/the_similarity (safe for local dev, ephemeral in containers).
    Override: THE_SIMILARITY_DATA_DIR env var for persistent storage.
    """
    global _data_dir
    if _data_dir is None:
        _data_dir = Path(os.getenv("THE_SIMILARITY_DATA_DIR", "/tmp/the_similarity"))
        _data_dir.mkdir(parents=True, exist_ok=True)
    return _data_dir


def get_auth_manager() -> AuthManager:
    """Get or create the singleton AuthManager.

    The AuthManager owns the auth.db SQLite database and handles:
    - User creation and password hashing
    - JWT token issuance and verification
    - API key generation and verification
    - Per-user rate limit tracking

    Thread-safety: AuthManager uses SQLite WAL mode internally.
    """
    global _auth_manager
    if _auth_manager is None:
        db_path = _get_data_dir() / "auth.db"

        # JWT secret from environment — CRITICAL for production security.
        # Without a strong secret, tokens can be forged.
        jwt_secret = os.getenv("THE_SIMILARITY_JWT_SECRET", "")
        if not jwt_secret or jwt_secret == "dev-secret-change-in-prod":
            import warnings
            warnings.warn(
                "THE_SIMILARITY_JWT_SECRET is not set or using default. "
                "Set a secure secret in production via environment variable.",
                stacklevel=2,
            )
            if not jwt_secret:
                jwt_secret = "dev-secret-change-in-prod"

        _auth_manager = AuthManager(db_path=db_path, jwt_secret=jwt_secret)
    return _auth_manager


def get_current_user(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    auth: AuthManager = Depends(get_auth_manager),
) -> User:
    """Extract and verify the current user from request headers.

    Authentication cascade (checked in this order):
    1. X-API-Key header → API key verification
    2. Authorization: Bearer <jwt> → JWT verification

    Why API key first:
    - API keys are simpler (no expiration, no refresh dance).
    - SDK/CLI clients prefer them. If both headers are present,
      the API key takes precedence for predictability.

    Returns:
        Authenticated User object.

    Raises:
        HTTPException(401): If no valid credentials are provided,
                            or the user is disabled.
    """
    # --- Try API key first ---
    if x_api_key:
        user = auth.verify_api_key(x_api_key)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return user

    # --- Try Bearer token ---
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            payload = auth.verify_token(parts[1])
            if payload is None:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            # The JWT "sub" claim contains the user ID
            user = auth.get_user(payload["sub"])
            if user is None or not user.enabled:
                raise HTTPException(status_code=401, detail="User not found or disabled")
            return user

    # --- No credentials provided ---
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Use 'Authorization: Bearer <token>' or 'X-API-Key: <key>'",
    )


def get_optional_user(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    auth: AuthManager = Depends(get_auth_manager),
) -> User | None:
    """Like get_current_user but returns None instead of raising 401.

    Used for endpoints that work differently for authenticated vs.
    anonymous users (e.g., showing user-specific data when logged in,
    but still serving public data when not).
    """
    try:
        return get_current_user(authorization, x_api_key, auth)
    except HTTPException:
        return None


def enforce_rate_limit(
    user: User = Depends(get_current_user),
    auth: AuthManager = Depends(get_auth_manager),
) -> User:
    """Check rate limit before processing the request.

    Rate limits are tier-based:
    - free: low limits (e.g., 10 requests/minute)
    - pro: higher limits
    - enterprise: highest limits

    If the limit is exceeded, returns a 429 with a Retry-After header.
    The user object is returned on success for downstream DI consumers.
    """
    allowed, remaining = auth.check_rate_limit(user.id, user.tier)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Upgrade your tier for higher limits.",
            headers={"Retry-After": "60"},
        )
    return user
