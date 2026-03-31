"""
tests/test_auth.py — 10 authentication flow tests for auth_api.py.

Covers: login success/failure, JWT validation, protected routes,
token expiry, tampering, logout, refresh, and concurrent sessions.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

import pytest
from httpx import AsyncClient
from jose import jwt

# Must match conftest.py — both define these so test_auth.py can be self-contained
ADMIN_EMAIL     = "admin@company.local"
ADMIN_PASSWORD  = "TestAdmin123!"
TEST_JWT_SECRET = "test-jwt-secret-for-pytest-only-not-for-production-use"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Successful login returns a valid JWT
# ─────────────────────────────────────────────────────────────────────────────

async def test_login_returns_valid_jwt(client: AsyncClient, admin_creds: dict):
    """POST /auth/login with correct credentials returns a decodable JWT."""
    resp = await client.post("/auth/login", json=admin_creds)

    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data, "Response must contain 'token'"
    assert "refresh_token" in data, "Response must contain 'refresh_token'"

    # Decode and verify JWT claims without validation (already verified by server)
    payload = jwt.decode(data["token"], TEST_JWT_SECRET, algorithms=["HS256"])
    assert payload["email"] == ADMIN_EMAIL
    assert payload["type"] == "access"
    assert "sub" in payload
    assert "exp" in payload


# ─────────────────────────────────────────────────────────────────────────────
# 2. Login with wrong password returns 401
# ─────────────────────────────────────────────────────────────────────────────

async def test_wrong_password_returns_401(client: AsyncClient):
    """POST /auth/login with the wrong password must return HTTP 401."""
    resp = await client.post(
        "/auth/login",
        json={"email": ADMIN_EMAIL, "password": "definitely-wrong-password"},
    )
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 3. Login with missing fields returns 422
# ─────────────────────────────────────────────────────────────────────────────

async def test_missing_fields_returns_422(client: AsyncClient):
    """POST /auth/login without the password field must return HTTP 422."""
    resp = await client.post("/auth/login", json={"email": ADMIN_EMAIL})
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 4. Valid JWT grants access to a protected route
# ─────────────────────────────────────────────────────────────────────────────

async def test_valid_jwt_accesses_protected_route(
    client: AsyncClient, logged_in: dict
):
    """GET /auth/me with a fresh JWT must return the authenticated user's profile."""
    resp = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {logged_in['token']}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == ADMIN_EMAIL
    assert data["role"] == "admin"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Expired JWT is rejected
# ─────────────────────────────────────────────────────────────────────────────

async def test_expired_jwt_is_rejected(client: AsyncClient):
    """GET /auth/me with an expired JWT must return HTTP 401."""
    now = datetime.now(timezone.utc)
    expired_token = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "email": ADMIN_EMAIL,
            "role": "admin",
            "username": "admin",
            "org_id": "test-org-id",
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),   # already expired
        },
        TEST_JWT_SECRET,
        algorithm="HS256",
    )

    resp = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 6. Missing JWT on a protected route returns 401
# ─────────────────────────────────────────────────────────────────────────────

async def test_missing_jwt_returns_401(client: AsyncClient):
    """GET /auth/me with no Authorization header must return HTTP 401."""
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 7. Tampered JWT is rejected
# ─────────────────────────────────────────────────────────────────────────────

async def test_tampered_jwt_is_rejected(client: AsyncClient, logged_in: dict):
    """
    GET /auth/me with a structurally valid JWT whose signature has been
    modified must return HTTP 401.
    """
    token = logged_in["token"]
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.INVALIDSIGNATUREXXXXXXXXXXXXXXXX"

    resp = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 8. Logout invalidates the session
# ─────────────────────────────────────────────────────────────────────────────

async def test_logout_invalidates_session(client: AsyncClient, logged_in: dict):
    """
    After a successful logout, using the same refresh token to request a
    new access token must fail with HTTP 401.
    """
    refresh_token = logged_in["refresh_token"]

    # Logout — should succeed
    logout_resp = await client.post(
        "/auth/logout", json={"refresh_token": refresh_token}
    )
    assert logout_resp.status_code == 200
    assert logout_resp.json().get("ok") is True

    # Attempt to refresh the revoked session — must be rejected
    refresh_resp = await client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 9. Token refresh works correctly (and old token is rotated out)
# ─────────────────────────────────────────────────────────────────────────────

async def test_token_refresh_works_and_rotates(
    client: AsyncClient, logged_in: dict
):
    """
    POST /auth/refresh with a valid refresh token must return a new access
    token and a new refresh token.  Re-using the consumed refresh token
    afterwards must return HTTP 401 (rotation prevents replay).
    """
    old_refresh = logged_in["refresh_token"]

    # First refresh — must succeed
    resp1 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert resp1.status_code == 200
    new_data = resp1.json()
    assert "token" in new_data
    assert "refresh_token" in new_data
    assert new_data["refresh_token"] != old_refresh, "Refresh token must be rotated"

    # Replaying the old refresh token — must be rejected
    resp2 = await client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert resp2.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 10. Concurrent logins from the same user work without conflict
# ─────────────────────────────────────────────────────────────────────────────

async def test_concurrent_logins_do_not_conflict(
    client: AsyncClient, admin_creds: dict
):
    """
    Five simultaneous login requests from the same user must all succeed
    independently — each gets its own access token and refresh token.
    """
    tasks = [
        client.post("/auth/login", json=admin_creds)
        for _ in range(5)
    ]
    responses = await asyncio.gather(*tasks)

    tokens = set()
    for resp in responses:
        assert resp.status_code == 200, f"Concurrent login failed: {resp.text}"
        data = resp.json()
        assert "token" in data
        tokens.add(data["token"])

    # Each concurrent login should produce a unique access token
    assert len(tokens) == 5, "Each concurrent login must produce a distinct token"


# ─────────────────────────────────────────────────────────────────────────────
# 11. Account locks after MAX_FAILED_ATTEMPTS consecutive bad passwords
# ─────────────────────────────────────────────────────────────────────────────

async def test_account_locks_after_max_failed_attempts(client: AsyncClient):
    """5 wrong passwords must lock the account; 6th attempt returns 403."""
    bad = {"email": ADMIN_EMAIL, "password": "wrong-password-xxxx"}

    for i in range(4):
        resp = await client.post("/auth/login", json=bad)
        assert resp.status_code == 401, f"Attempt {i+1} should be 401, got {resp.status_code}"

    # 5th attempt triggers the lock — must return 403
    resp = await client.post("/auth/login", json=bad)
    assert resp.status_code == 403
    assert "locked" in resp.json()["detail"].lower()

    # 6th attempt on a now-locked account — still 403
    resp = await client.post("/auth/login", json=bad)
    assert resp.status_code == 403
    assert "locked" in resp.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# 12. Successful login resets the failure counter
# ─────────────────────────────────────────────────────────────────────────────

async def test_successful_login_resets_failure_counter(
    client: AsyncClient, admin_creds: dict
):
    """4 wrong attempts followed by a correct login must not lock the account."""
    bad = {"email": ADMIN_EMAIL, "password": "wrong-password-xxxx"}

    for _ in range(4):
        await client.post("/auth/login", json=bad)

    # Correct login resets the counter
    resp = await client.post("/auth/login", json=admin_creds)
    assert resp.status_code == 200, f"Good login after 4 failures should succeed: {resp.text}"

    # Another bad attempt should NOT immediately lock (counter was reset to 0)
    resp = await client.post("/auth/login", json=bad)
    assert resp.status_code == 401
