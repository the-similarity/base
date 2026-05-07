"""Tests for the auth & multi-tenancy system (6c).

Covers:
- User registration and authentication
- JWT token issuance and verification
- Token refresh with rotation
- API key CRUD and verification
- Rate limiting per tier
- Edge cases (duplicate email, bad password, disabled user, revoked key)
"""

from __future__ import annotations


import pytest

from the_similarity.core.auth import (
    AuthManager,
    RateLimiter,
    Tier,
)


@pytest.fixture
def auth_mgr(tmp_path):
    return AuthManager(
        db_path=tmp_path / "auth_test.db",
        jwt_secret="test-secret-key",
        token_expiry=60,  # 1 minute for tests
        refresh_expiry=300,  # 5 minutes for tests
    )


class TestUserManagement:
    def test_create_user(self, auth_mgr):
        user = auth_mgr.create_user("alice@example.com", "password123")
        assert user.id
        assert user.email == "alice@example.com"
        assert user.tier == Tier.FREE
        assert user.enabled is True

    def test_create_user_custom_tier(self, auth_mgr):
        user = auth_mgr.create_user("bob@example.com", "password123", tier=Tier.PRO)
        assert user.tier == Tier.PRO

    def test_duplicate_email_raises(self, auth_mgr):
        auth_mgr.create_user("alice@example.com", "password123")
        with pytest.raises(ValueError, match="already registered"):
            auth_mgr.create_user("alice@example.com", "otherpass")

    def test_authenticate_success(self, auth_mgr):
        auth_mgr.create_user("alice@example.com", "password123")
        user = auth_mgr.authenticate("alice@example.com", "password123")
        assert user is not None
        assert user.email == "alice@example.com"

    def test_authenticate_wrong_password(self, auth_mgr):
        auth_mgr.create_user("alice@example.com", "password123")
        assert auth_mgr.authenticate("alice@example.com", "wrong") is None

    def test_authenticate_unknown_email(self, auth_mgr):
        assert auth_mgr.authenticate("nobody@example.com", "pass") is None

    def test_get_user(self, auth_mgr):
        user = auth_mgr.create_user("alice@example.com", "password123")
        fetched = auth_mgr.get_user(user.id)
        assert fetched is not None
        assert fetched.email == "alice@example.com"

    def test_get_user_nonexistent(self, auth_mgr):
        assert auth_mgr.get_user("nonexistent") is None

    def test_update_tier(self, auth_mgr):
        user = auth_mgr.create_user("alice@example.com", "password123")
        assert auth_mgr.update_user_tier(user.id, Tier.ENTERPRISE) is True
        fetched = auth_mgr.get_user(user.id)
        assert fetched.tier == Tier.ENTERPRISE


class TestJWTTokens:
    def test_issue_and_verify(self, auth_mgr):
        user = auth_mgr.create_user("alice@example.com", "password123")
        tokens = auth_mgr.issue_tokens(user)

        assert tokens.access_token
        assert tokens.refresh_token
        assert tokens.expires_in == 60
        assert tokens.token_type == "bearer"

        payload = auth_mgr.verify_token(tokens.access_token)
        assert payload is not None
        assert payload["sub"] == user.id
        assert payload["email"] == "alice@example.com"
        assert payload["tier"] == Tier.FREE

    def test_verify_invalid_token(self, auth_mgr):
        assert auth_mgr.verify_token("garbage.token.here") is None

    def test_verify_wrong_secret(self, tmp_path):
        mgr1 = AuthManager(db_path=tmp_path / "a.db", jwt_secret="secret1")
        mgr2 = AuthManager(db_path=tmp_path / "b.db", jwt_secret="secret2")

        user = mgr1.create_user("alice@example.com", "password123")
        tokens = mgr1.issue_tokens(user)
        assert mgr2.verify_token(tokens.access_token) is None

    def test_refresh_token_rotation(self, auth_mgr):
        user = auth_mgr.create_user("alice@example.com", "password123")
        tokens1 = auth_mgr.issue_tokens(user)

        # Refresh
        tokens2 = auth_mgr.refresh_tokens(tokens1.refresh_token)
        assert tokens2 is not None
        assert tokens2.access_token != tokens1.access_token

        # Old refresh token should be revoked
        tokens3 = auth_mgr.refresh_tokens(tokens1.refresh_token)
        assert tokens3 is None

    def test_refresh_invalid_token(self, auth_mgr):
        assert auth_mgr.refresh_tokens("invalid.token") is None


class TestAPIKeys:
    def test_create_and_verify(self, auth_mgr):
        user = auth_mgr.create_user("alice@example.com", "password123")
        api_key, raw_key = auth_mgr.create_api_key(user.id, "My Key")

        assert api_key.name == "My Key"
        assert raw_key.startswith("sim_")
        assert api_key.key_prefix == raw_key[:12]

        verified_user = auth_mgr.verify_api_key(raw_key)
        assert verified_user is not None
        assert verified_user.id == user.id

    def test_verify_invalid_key(self, auth_mgr):
        assert auth_mgr.verify_api_key("sim_invalid_key") is None

    def test_list_api_keys(self, auth_mgr):
        user = auth_mgr.create_user("alice@example.com", "password123")
        auth_mgr.create_api_key(user.id, "Key 1")
        auth_mgr.create_api_key(user.id, "Key 2")

        keys = auth_mgr.list_api_keys(user.id)
        assert len(keys) == 2
        names = {k.name for k in keys}
        assert names == {"Key 1", "Key 2"}

    def test_revoke_api_key(self, auth_mgr):
        user = auth_mgr.create_user("alice@example.com", "password123")
        api_key, raw_key = auth_mgr.create_api_key(user.id, "Revoke Me")

        assert auth_mgr.verify_api_key(raw_key) is not None
        assert auth_mgr.revoke_api_key(user.id, api_key.id) is True
        assert auth_mgr.verify_api_key(raw_key) is None

    def test_revoke_api_key_cross_tenant_blocked(self, auth_mgr):
        # Row-level scoping: user B cannot revoke user A's key, even if B
        # somehow learns A's key_id. The DB-layer WHERE clause is the
        # second line of defense behind the route-layer ownership check.
        alice = auth_mgr.create_user("alice@example.com", "password123")
        bob = auth_mgr.create_user("bob@example.com", "password456")
        alice_key, raw_key = auth_mgr.create_api_key(alice.id, "Alice's key")

        assert auth_mgr.revoke_api_key(bob.id, alice_key.id) is False
        # Alice's key should still work
        assert auth_mgr.verify_api_key(raw_key) is not None
        # Alice can revoke her own key
        assert auth_mgr.revoke_api_key(alice.id, alice_key.id) is True
        assert auth_mgr.verify_api_key(raw_key) is None

    def test_api_key_updates_last_used(self, auth_mgr):
        user = auth_mgr.create_user("alice@example.com", "password123")
        api_key, raw_key = auth_mgr.create_api_key(user.id, "Usage Key")

        assert api_key.last_used_at is None
        auth_mgr.verify_api_key(raw_key)

        keys = auth_mgr.list_api_keys(user.id)
        assert keys[0].last_used_at is not None


class TestRateLimiting:
    def test_basic_rate_limit(self):
        limiter = RateLimiter()
        # Free tier: 10 req/min
        for i in range(10):
            allowed, remaining = limiter.check("user1", Tier.FREE)
            assert allowed is True

        # 11th request should be blocked
        allowed, remaining = limiter.check("user1", Tier.FREE)
        assert allowed is False
        assert remaining == 0

    def test_different_tiers(self):
        limiter = RateLimiter()
        # Pro tier: 60 req/min
        for i in range(60):
            allowed, _ = limiter.check("pro_user", Tier.PRO)
            assert allowed is True

        allowed, _ = limiter.check("pro_user", Tier.PRO)
        assert allowed is False

    def test_different_users_independent(self):
        limiter = RateLimiter()
        for i in range(10):
            limiter.check("user1", Tier.FREE)

        # user2 should still have full quota
        allowed, remaining = limiter.check("user2", Tier.FREE)
        assert allowed is True
        assert remaining == 9  # 10 - 1 (just used one)

    def test_reset(self):
        limiter = RateLimiter()
        for i in range(10):
            limiter.check("user1", Tier.FREE)

        limiter.reset("user1")
        allowed, _ = limiter.check("user1", Tier.FREE)
        assert allowed is True

    def test_auth_manager_rate_limit(self, auth_mgr):
        allowed, remaining = auth_mgr.check_rate_limit("user1", Tier.FREE)
        assert allowed is True
        assert remaining == 9  # 10 - 1
