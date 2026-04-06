"""
tests/conftest.py â€” Fixtures for auth API tests.

Environment variables are set at the very top of this file, before any
application imports, so the app sees the test secret and the test database.

Design notes
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
â€¢ database.py creates a global SQLAlchemy engine at module load time using
    `_build_engine_args`, which can rewrite async database URLs. To avoid this,
    we mock `create_async_engine` BEFORE importing database.py so that
    `database.engine` and `database.SessionLocal` transparently use the test
    engine with `NullPool`.

â€¢ httpx ASGITransport does NOT trigger FastAPI startup/shutdown lifespan
  events.  Tables are therefore created and the admin is seeded manually
  once in a session-scoped autouse fixture.

â€¢ Sessions (JWT refresh tokens) are deleted after each test so no session
  state leaks between tests.
"""
from __future__ import annotations

import os

# â”€â”€ Set ALL test env vars FIRST â€” before any app code is imported â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_TEST_SIGNING_SEED = "pytest-signing-seed-not-prod"
os.environ["JWT_SECRET_KEY"]         = _TEST_SIGNING_SEED
os.environ["ADMIN_DEFAULT_PASSWORD"] = "TestAdmin123!"
os.environ["ADMIN_DEFAULT_EMAIL"]    = "admin@company.local"
os.environ["DATABASE_URL"]          = "postgresql+asyncpg://test_user:test_pass@localhost:5433/resilo_test"
os.environ["ALLOWED_ORIGINS"]       = "http://localhost:3000"
os.environ["BACKUP_DIR"]            = "./backups"
os.environ["DEPLOY_HOST"]           = "http://localhost:8000"
# DATABASE_URL points to the isolated test DB (port 5433). Start it with:
#   docker-compose -f docker-compose.test.yml up -d

import hashlib
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

# â”€â”€ sys.path: make all app packages importable â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_tests = Path(__file__).resolve().parent
_root  = _tests.parent
for _p in [
    str(_tests),                              # tests/ â€” for helpers.py
    str(_root),
    str(_root / "app"),
    str(_root / "app" / "api"),
    str(_root / "app" / "core"),
    str(_root / "app" / "auth"),
    str(_root / "app" / "analytics"),
    str(_root / "app" / "integrations"),
]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest
import pytest_asyncio
from helpers import make_jwt as _make_jwt_helper
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.pool import NullPool

# â”€â”€ Test engine: PostgreSQL with NullPool (one connection per request) â”€â”€â”€â”€â”€â”€â”€
_TEST_DB_URL = os.environ["DATABASE_URL"]

_test_engine  = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
_TestSession  = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)

# â”€â”€ Inject test engine into database.py BEFORE importing it â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# database.py calls create_async_engine at module level; we mock that call so
# database.engine becomes _test_engine and database.SessionLocal binds to it
# automatically.
with patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=_test_engine):
    from auth_api import _seed_admin, app  # noqa: E402
    from database import Base, Organization, User, get_db  # noqa: E402

# â”€â”€ Import additional DB models (database already in sys.modules) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# â”€â”€ Import core_api app (database already mocked in sys.modules) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
from core_api import app as core_app  # noqa: E402
from database import Agent, AlertRecord, MetricSnapshot  # noqa: E402

# â”€â”€ Public constants (imported by test modules) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TEST_SIGNING_SEED = _TEST_SIGNING_SEED
ADMIN_EMAIL     = "admin@company.local"
ADMIN_PASSWORD  = "TestAdmin123!"


make_jwt = _make_jwt_helper  # re-export for backward compat within this module


# â”€â”€ Session-wide DB setup / teardown â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_database():
    """
        Run once per test session:
            1. Create all tables in the test database.
      2. Seed the default admin user (via auth_api._seed_admin).
    Drop everything and delete the file on teardown.
    """
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # _seed_admin uses database.SessionLocal, which now binds to _test_engine.
    await _seed_admin()

    # Wire the real admin user ID into helpers so admin_jwt() tokens pass the
    # DB user-existence check in _require_valid_access_payload.
    import helpers as _helpers_mod
    from sqlalchemy import select as _sa_select
    async with _TestSession() as _s:
        _result = await _s.execute(_sa_select(User).where(User.email == ADMIN_EMAIL))
        _admin = _result.scalar_one()
        _helpers_mod._TEST_ADMIN_ID = _admin.id

    yield

    async with _test_engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await _test_engine.dispose()


# â”€â”€ Per-test session wipe â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest_asyncio.fixture(autouse=True)
async def _wipe_sessions():
    """Delete session rows and reset lockout state after every test when tables exist."""
    yield
    from sqlalchemy import text
    async with _test_engine.begin() as conn:
        user_sessions_exists = (
            await conn.execute(text("SELECT to_regclass('public.user_sessions')"))
        ).scalar_one()
        if user_sessions_exists is not None:
            await conn.execute(text("DELETE FROM user_sessions"))

        users_exists = (
            await conn.execute(text("SELECT to_regclass('public.users')"))
        ).scalar_one()
        if users_exists is not None:
            await conn.execute(text("UPDATE users SET failed_attempts = 0, locked_until = NULL"))

# â”€â”€ Reusable test fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Core API fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@pytest_asyncio.fixture
async def core_client() -> AsyncClient:
    """Async test client wired to the core_api FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=core_app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def sample_org() -> Organization:
    """Create a test organization and clean it up after the test."""
    suffix = str(uuid.uuid4())[:8]
    org = Organization(
        id=str(uuid.uuid4()),
        name=f"Test Org {suffix}",
        slug=f"test-org-{suffix}",
        plan="free",
        is_active=True,
    )
    async with _TestSession() as session:
        session.add(org)
        await session.commit()
        await session.refresh(org)
    yield org
    # Delete child records in FK order before removing the org.
    async with _test_engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text(f"DELETE FROM alert_records WHERE org_id = '{org.id}'"))
        await conn.execute(text(f"DELETE FROM metric_snapshots WHERE org_id = '{org.id}'"))
        await conn.execute(text(f"DELETE FROM agents WHERE org_id = '{org.id}'"))
        await conn.execute(text(f"DELETE FROM organizations WHERE id = '{org.id}'"))


@pytest_asyncio.fixture
async def sample_agent(sample_org: Organization) -> tuple[Agent, str]:
    """
    Create a test agent in sample_org.
    Yields (agent, raw_key) â€” raw_key for use in X-Agent-Key header.
    """
    raw_key = "test-agent-key-for-pytest-only-do-not-use-in-prod"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    agent = Agent(
        id=str(uuid.uuid4()),
        org_id=sample_org.id,
        label="pytest-agent",
        key_hash=key_hash,
        status="online",
        is_active=True,
    )
    async with _TestSession() as session:
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
    yield agent, raw_key
    # Delete metric_snapshots referencing this agent before removing the agent.
    async with _test_engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text(f"DELETE FROM metric_snapshots WHERE agent_id = '{agent.id}'"))
        await conn.execute(text(f"DELETE FROM agents WHERE id = '{agent.id}'"))


@pytest_asyncio.fixture
async def sample_metric(
    core_client: AsyncClient,
    sample_org: Organization,
    sample_agent: tuple[Agent, str],
) -> dict:
    """
    Post one heartbeat to /ingest/heartbeat and return the stored metric.
    Uses X-Agent-Key authentication.
    """
    agent, raw_key = sample_agent
    resp = await core_client.post(
        "/ingest/heartbeat",
        headers={"X-Agent-Key": raw_key},
        json={
            "org_id": sample_org.id,
            "metrics": {
                "cpu": 42.5,
                "memory": 61.0,
                "disk": 75.0,
                "network_in": 1024,
                "network_out": 512,
            },
        },
    )
    assert resp.status_code == 200, f"Heartbeat fixture failed: {resp.text}"
    # Return the stored snapshot via the metrics API
    import helpers as _helpers_mod
    token = make_jwt(
        sub=_helpers_mod._TEST_ADMIN_ID or str(uuid.uuid4()), role="admin", org_id=sample_org.id
    )
    list_resp = await core_client.get(
        f"/api/orgs/{sample_org.id}/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200
    snapshots = list_resp.json()
    assert snapshots, "No metrics returned after heartbeat"
    return snapshots[0]


@pytest_asyncio.fixture
async def sample_alert(
    core_client: AsyncClient,
    sample_org: Organization,
) -> dict:
    """Create one alert via the API and return the response body."""
    import helpers as _helpers_mod
    token = make_jwt(
        sub=_helpers_mod._TEST_ADMIN_ID or str(uuid.uuid4()), role="admin", org_id=sample_org.id
    )
    resp = await core_client.post(
        f"/api/orgs/{sample_org.id}/alerts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "severity": "high",
            "category": "cpu",
            "title": "CPU threshold exceeded",
            "detail": "CPU at 92%, threshold 80%",
            "metric_value": 92.0,
            "threshold": 80.0,
        },
    )
    assert resp.status_code == 201, f"Alert fixture failed: {resp.text}"
    return resp.json()







