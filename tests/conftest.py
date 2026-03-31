"""
tests/conftest.py — Fixtures for auth API tests.

Environment variables are set at the very top of this file, before any
application imports, so the app sees the test secret and the test database.

Design notes
────────────
• database.py creates a global SQLAlchemy engine at module load time using
  `_build_engine_args`, which corrupts SQLite URLs (strips netloc `//`).
  To avoid this, we mock `create_async_engine` BEFORE importing database.py
  so that `database.engine` and `database.SessionLocal` transparently use
  the test engine (file-based SQLite with NullPool).

• httpx ASGITransport does NOT trigger FastAPI startup/shutdown lifespan
  events.  Tables are therefore created and the admin is seeded manually
  once in a session-scoped autouse fixture.

• Sessions (JWT refresh tokens) are deleted after each test so no session
  state leaks between tests.
"""
from __future__ import annotations

import os

# ── Set ALL test env vars FIRST — before any app code is imported ─────────────
_TEST_JWT_SECRET = "test-jwt-secret-for-pytest-only-not-for-production-use"
os.environ["JWT_SECRET_KEY"]         = _TEST_JWT_SECRET
os.environ["ADMIN_DEFAULT_PASSWORD"] = "TestAdmin123!"
# DATABASE_URL is intentionally left unset here; database.py's engine is
# intercepted by the mock below so the URL value it reads doesn't matter.

import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# ── sys.path: make all app packages importable ────────────────────────────────
_root = Path(__file__).resolve().parent.parent
for _p in [
    str(_root),
    str(_root / "app"),
    str(_root / "app" / "api"),
    str(_root / "app" / "core"),
    str(_root / "app" / "auth"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Test engine: file-based SQLite with no connection pooling ─────────────────
# NullPool creates a fresh connection per request, allowing concurrent tests.
_TEST_DB_FILE = Path(__file__).parent / "test_auth.db"
_TEST_DB_URL  = f"sqlite+aiosqlite:///{_TEST_DB_FILE.as_posix()}"

_test_engine  = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
_TestSession  = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)

# ── Inject test engine into database.py BEFORE importing it ───────────────────
# database.py calls create_async_engine at module level; the corrupted URL it
# builds for SQLite would fail.  We mock that call so database.engine becomes
# _test_engine and database.SessionLocal binds to it automatically.
with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=_test_engine):
    from database import Base, get_db, User, Organization  # noqa: E402
    from auth_api import app, _seed_admin                   # noqa: E402

# ── Public constants (imported by test modules) ───────────────────────────────
TEST_JWT_SECRET = _TEST_JWT_SECRET
ADMIN_EMAIL     = "admin@company.local"
ADMIN_PASSWORD  = "TestAdmin123!"


# ── Session-wide DB setup / teardown ──────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_database():
    """
    Run once per test session:
      1. Create all tables in the test SQLite file.
      2. Seed the default admin user (via auth_api._seed_admin).
    Drop everything and delete the file on teardown.
    """
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # _seed_admin uses database.SessionLocal, which now binds to _test_engine.
    await _seed_admin()

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()
    _TEST_DB_FILE.unlink(missing_ok=True)


# ── Per-test session wipe ─────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def _wipe_sessions():
    """Delete all user_sessions rows and reset lockout state after every test."""
    yield
    from sqlalchemy import text
    async with _test_engine.begin() as conn:
        await conn.execute(text("DELETE FROM user_sessions"))
        await conn.execute(text("UPDATE users SET failed_attempts = 0, locked_until = NULL"))


# ── Reusable test fixtures ────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client() -> AsyncClient:
    """Async test client wired directly to the FastAPI ASGI app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def admin_creds() -> dict:
    return {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}


@pytest_asyncio.fixture
async def logged_in(client: AsyncClient, admin_creds: dict) -> dict:
    """Return the JSON body of a successful admin login."""
    resp = await client.post("/auth/login", json=admin_creds)
    assert resp.status_code == 200, f"Login fixture failed: {resp.text}"
    return resp.json()
