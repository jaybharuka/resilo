"""Integration tests for auth API request -> database -> response flow."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import SessionLocal


@pytest.mark.asyncio
async def test_login_persists_refresh_session(client: AsyncClient, admin_creds: dict):
    response = await client.post("/auth/login", json=admin_creds)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["token"]
    assert body["refresh_token"]

    async with SessionLocal() as db:
        result = await db.execute(text("SELECT COUNT(*) FROM user_sessions WHERE is_revoked = false"))
        active_sessions = result.scalar_one()
    assert active_sessions >= 1


@pytest.mark.asyncio
async def test_invalid_login_returns_401(client: AsyncClient):
    response = await client.post(
        "/auth/login",
        json={"email": "missing@company.local", "password": "does-not-exist"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_refresh_rotates_session_token(client: AsyncClient, logged_in: dict):
    first_refresh = logged_in["refresh_token"]

    refresh_response = await client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert refresh_response.status_code == 200

    rotated = refresh_response.json()["refresh_token"]
    assert rotated != first_refresh

    replay_response = await client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert replay_response.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_session(client: AsyncClient, logged_in: dict):
    refresh_token = logged_in["refresh_token"]

    logout_response = await client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout_response.status_code == 200
    assert logout_response.json()["ok"] is True

    refresh_response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 401


@pytest.mark.asyncio
async def test_auth_health_endpoint(client: AsyncClient):
    response = await client.get("/auth/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "auth"}


@pytest.mark.asyncio
async def test_db_health_endpoint(core_client: AsyncClient):
    response = await core_client.get("/health/db")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert isinstance(payload["latency_ms"], int)
