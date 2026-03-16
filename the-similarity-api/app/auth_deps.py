"""FastAPI dependency injection for auth and rate limiting."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, Header, HTTPException, Request

from the_similarity.core.auth import AuthManager, RateLimiter, User

# Singleton instances — initialized lazily
_auth_manager: AuthManager | None = None
_data_dir: Path | None = None


def _get_data_dir() -> Path:
    global _data_dir
    if _data_dir is None:
        _data_dir = Path(os.getenv("THE_SIMILARITY_DATA_DIR", "/tmp/the_similarity"))
        _data_dir.mkdir(parents=True, exist_ok=True)
    return _data_dir


def get_auth_manager() -> AuthManager:
    """Get or create the singleton AuthManager."""
    global _auth_manager
    if _auth_manager is None:
        db_path = _get_data_dir() / "auth.db"
        jwt_secret = os.getenv("THE_SIMILARITY_JWT_SECRET", "dev-secret-change-in-prod")
        _auth_manager = AuthManager(db_path=db_path, jwt_secret=jwt_secret)
    return _auth_manager


def get_current_user(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    auth: AuthManager = Depends(get_auth_manager),
) -> User:
    """Extract and verify the current user from JWT or API key.

    Supports:
        - Bearer token: Authorization: Bearer <jwt>
        - API key: X-API-Key: sim_xxx
    """
    # Try API key first
    if x_api_key:
        user = auth.verify_api_key(x_api_key)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid API key")
        return user

    # Try Bearer token
    if authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            payload = auth.verify_token(parts[1])
            if payload is None:
                raise HTTPException(status_code=401, detail="Invalid or expired token")
            user = auth.get_user(payload["sub"])
            if user is None or not user.enabled:
                raise HTTPException(status_code=401, detail="User not found or disabled")
            return user

    raise HTTPException(
        status_code=401,
        detail="Authentication required. Use 'Authorization: Bearer <token>' or 'X-API-Key: <key>'",
    )


def get_optional_user(
    authorization: str | None = Header(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    auth: AuthManager = Depends(get_auth_manager),
) -> User | None:
    """Like get_current_user but returns None instead of 401."""
    try:
        return get_current_user(authorization, x_api_key, auth)
    except HTTPException:
        return None


def enforce_rate_limit(
    user: User = Depends(get_current_user),
    auth: AuthManager = Depends(get_auth_manager),
) -> User:
    """Check rate limit and return user if allowed."""
    allowed, remaining = auth.check_rate_limit(user.id, user.tier)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Upgrade your tier for higher limits.",
            headers={"Retry-After": "60"},
        )
    return user
