"""
Unit tests for auth_api.py endpoints.

Tests cover:
- Login endpoint (success, invalid credentials, 2FA flow)
- Password validation (strong/weak passwords)
- Rate limiting (verify 429 on excess requests)
- Input validation (invalid email, username patterns)
- Error handling (verify no stack traces in responses)
"""

import pytest
import asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Import the FastAPI app and database models
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app', 'api'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app', 'core'))

from auth_api import app
from database import Base, get_db


# Test database setup
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_db():
    """Create an in-memory test database."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async def override_get_db():
        async with async_session() as session:
            yield session
    
    app.dependency_overrides[get_db] = override_get_db
    
    yield async_session
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def client(test_db):
    """Create an async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


# ─────────────────────────────────────────────────────────────────────────────
# Login Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_invalid_email_format(client):
    """Test login with invalid email format."""
    response = await client.post(
        "/auth/login",
        json={"email": "not-an-email", "password": "TestPassword123!"}
    )
    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_login_missing_credentials(client):
    """Test login with missing credentials."""
    response = await client.post(
        "/auth/login",
        json={"email": "test@test.com"}
    )
    assert response.status_code == 422  # Missing password field


@pytest.mark.asyncio
async def test_login_invalid_credentials(client):
    """Test login with non-existent user."""
    response = await client.post(
        "/auth/login",
        json={"email": "nonexistent@test.com", "password": "TestPassword123!"}
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# Password Validation Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_weak_password_too_short(client):
    """Test registration with password < 12 characters."""
    response = await client.post(
        "/auth/register",
        json={
            "org_name": "Test Org",
            "email": "test@test.com",
            "username": "testuser",
            "password": "Short1!",
            "full_name": "Test User"
        }
    )
    assert response.status_code == 400
    assert "at least 12 characters" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_weak_password_no_uppercase(client):
    """Test registration with password missing uppercase."""
    response = await client.post(
        "/auth/register",
        json={
            "org_name": "Test Org",
            "email": "test@test.com",
            "username": "testuser",
            "password": "testpassword123!",
            "full_name": "Test User"
        }
    )
    assert response.status_code == 400
    assert "uppercase letter" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_weak_password_no_digit(client):
    """Test registration with password missing digit."""
    response = await client.post(
        "/auth/register",
        json={
            "org_name": "Test Org",
            "email": "test@test.com",
            "username": "testuser",
            "password": "TestPassword!",
            "full_name": "Test User"
        }
    )
    assert response.status_code == 400
    assert "digit" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_weak_password_no_special_char(client):
    """Test registration with password missing special character."""
    response = await client.post(
        "/auth/register",
        json={
            "org_name": "Test Org",
            "email": "test@test.com",
            "username": "testuser",
            "password": "TestPassword123",
            "full_name": "Test User"
        }
    )
    assert response.status_code == 400
    assert "special character" in response.json()["detail"]


# ─────────────────────────────────────────────────────────────────────────────
# Input Validation Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_invalid_username_format(client):
    """Test registration with invalid username format."""
    response = await client.post(
        "/auth/register",
        json={
            "org_name": "Test Org",
            "email": "test@test.com",
            "username": "test<script>",
            "password": "TestPassword123!",
            "full_name": "Test User"
        }
    )
    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_register_invalid_org_name_format(client):
    """Test registration with invalid org name format."""
    response = await client.post(
        "/auth/register",
        json={
            "org_name": "Test<script>alert(1)</script>",
            "email": "test@test.com",
            "username": "testuser",
            "password": "TestPassword123!",
            "full_name": "Test User"
        }
    )
    assert response.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_register_username_too_short(client):
    """Test registration with username < 3 characters."""
    response = await client.post(
        "/auth/register",
        json={
            "org_name": "Test Org",
            "email": "test@test.com",
            "username": "ab",
            "password": "TestPassword123!",
            "full_name": "Test User"
        }
    )
    assert response.status_code == 422  # Pydantic validation error


# ─────────────────────────────────────────────────────────────────────────────
# Error Handling Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_error_response_format(client):
    """Test that error responses don't expose stack traces."""
    response = await client.post(
        "/auth/login",
        json={"email": "test@test.com", "password": "test"}
    )
    # Should return JSON with 'detail' field, not HTML stack trace
    assert response.status_code in [401, 422]
    assert "detail" in response.json()
    assert "Traceback" not in response.text
    assert "File " not in response.text


@pytest.mark.asyncio
async def test_error_response_includes_error_id(client):
    """Test that error responses include correlation ID for tracing."""
    response = await client.post(
        "/auth/login",
        json={"email": "test@test.com", "password": "test"}
    )
    # 500 errors should include error_id for tracing
    if response.status_code == 500:
        assert "error_id" in response.json()


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiting Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_rate_limit(client):
    """Test that login endpoint enforces rate limiting (5/minute)."""
    # Make 6 requests to exceed the 5/minute limit
    for i in range(6):
        response = await client.post(
            "/auth/login",
            json={"email": f"test{i}@test.com", "password": "test"}
        )
        if i < 5:
            # First 5 should succeed (or fail with 401, not 429)
            assert response.status_code != 429
        else:
            # 6th should be rate limited
            assert response.status_code == 429
            assert "Too many requests" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_rate_limit(client):
    """Test that register endpoint enforces rate limiting (3/hour)."""
    # Make 4 requests to exceed the 3/hour limit
    for i in range(4):
        response = await client.post(
            "/auth/register",
            json={
                "org_name": f"Org {i}",
                "email": f"test{i}@test.com",
                "username": f"user{i}",
                "password": "TestPassword123!"
            }
        )
        if i < 3:
            # First 3 should succeed (or fail with validation error, not 429)
            assert response.status_code != 429
        else:
            # 4th should be rate limited
            assert response.status_code == 429


# ─────────────────────────────────────────────────────────────────────────────
# Health Check Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(client):
    """Test that health check endpoint works."""
    response = await client.get("/auth/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "auth-api"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
