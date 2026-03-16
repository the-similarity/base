"""Auth API routes: register, login, refresh, API keys."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from the_similarity.core.auth import AuthManager, Tier, User

from app.auth_deps import enforce_rate_limit, get_auth_manager, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


# ---- Request / Response models ----

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)

class LoginRequest(BaseModel):
    email: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: str
    email: str
    tier: str
    enabled: bool

class CreateAPIKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: float
    last_used_at: float | None = None

class APIKeyCreatedResponse(APIKeyResponse):
    raw_key: str  # only returned once


# ---- Endpoints ----

@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    body: RegisterRequest,
    auth: AuthManager = Depends(get_auth_manager),
) -> TokenResponse:
    """Register a new user account and return tokens."""
    try:
        user = auth.create_user(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    tokens = auth.issue_tokens(user)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    auth: AuthManager = Depends(get_auth_manager),
) -> TokenResponse:
    """Authenticate and return tokens."""
    user = auth.authenticate(body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    tokens = auth.issue_tokens(user)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    body: RefreshRequest,
    auth: AuthManager = Depends(get_auth_manager),
) -> TokenResponse:
    """Refresh an access token using a refresh token."""
    tokens = auth.refresh_tokens(body.refresh_token)
    if tokens is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)) -> UserResponse:
    """Get current user profile."""
    return UserResponse(id=user.id, email=user.email, tier=user.tier, enabled=user.enabled)


# ---- API Keys ----

@router.post("/api-keys", response_model=APIKeyCreatedResponse, status_code=201)
def create_api_key(
    body: CreateAPIKeyRequest,
    user: User = Depends(get_current_user),
    auth: AuthManager = Depends(get_auth_manager),
) -> APIKeyCreatedResponse:
    """Create a new API key. The raw key is only shown once."""
    api_key, raw_key = auth.create_api_key(user.id, body.name)
    return APIKeyCreatedResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        created_at=api_key.created_at,
        raw_key=raw_key,
    )


@router.get("/api-keys", response_model=list[APIKeyResponse])
def list_api_keys(
    user: User = Depends(get_current_user),
    auth: AuthManager = Depends(get_auth_manager),
) -> list[APIKeyResponse]:
    """List all API keys for the current user."""
    keys = auth.list_api_keys(user.id)
    return [
        APIKeyResponse(
            id=k.id, name=k.name, key_prefix=k.key_prefix,
            created_at=k.created_at, last_used_at=k.last_used_at,
        )
        for k in keys
    ]


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_api_key(
    key_id: str,
    user: User = Depends(get_current_user),
    auth: AuthManager = Depends(get_auth_manager),
) -> None:
    """Revoke an API key."""
    # Verify the key belongs to the user
    keys = auth.list_api_keys(user.id)
    if not any(k.id == key_id for k in keys):
        raise HTTPException(status_code=404, detail="API key not found")
    auth.revoke_api_key(key_id)
