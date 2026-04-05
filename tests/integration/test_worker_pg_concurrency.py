"""Integration tests for worker concurrency using real PostgreSQL."""
import asyncio
import os
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base, RemediationJob
from remediation.worker import claim_pending_jobs


@pytest_asyncio.fixture
async def integration_db_engine():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        pytest.skip("DATABASE_URL not configured")
    engine = create_async_engine(db_url, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory_independent(integration_db_engine):
    async_session_maker = async_sessionmaker(integration_db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _make_session():
        return async_session_maker()

    return _make_session


@pytest_asyncio.fixture
async def cleanup_jobs(integration_db_engine):
    yield
    async with integration_db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM remediation_jobs"))


@pytest.mark.asyncio
async def test_pg_skip_locked_prevents_double_claim(db_session_factory_independent, cleanup_jobs):
    """Prove FOR UPDATE SKIP LOCKED prevents double-claim."""
    session = await db_session_factory_independent()
    try:
        job = RemediationJob(
            alert_id=None,
            playbook_type="restart_service",
            status="pending",
            attempts=0,
            max_retries=3,
            payload={"org_id": "test-org"},
        )
        session.add(job)
        await session.commit()
        job_id = job.id
    finally:
        await session.close()

    session_a = await db_session_factory_independent()
    session_b = await db_session_factory_independent()
    claimed_a, claimed_b = [], []

    async def claim_a():
        jobs = await claim_pending_jobs(session_a, 10, 300)
        claimed_a.extend(jobs)

    async def claim_b():
        jobs = await claim_pending_jobs(session_b, 10, 300)
        claimed_b.extend(jobs)

    try:
        await asyncio.gather(claim_a(), claim_b())
        total = len(claimed_a) + len(claimed_b)
        assert total == 1, f"Double-claim! Got {total} claims"
        winner = claimed_a[0] if claimed_a else claimed_b[0]
        assert winner.id == job_id and winner.status == "running"
    finally:
        await session_a.close()
        await session_b.close()


@pytest.mark.asyncio
async def test_pg_stale_job_reclamation(db_session_factory_independent, cleanup_jobs):
    """Prove stale running jobs are reclaimed."""
    session = await db_session_factory_independent()
    try:
        stale_time = datetime.utcnow() - timedelta(seconds=400)
        job = RemediationJob(
            alert_id=None,
            playbook_type="restart_service",
            status="running",
            attempts=1,
            max_retries=3,
            updated_at=stale_time,
            payload={"org_id": "test-org"},
        )
        session.add(job)
        await session.commit()
        job_id = job.id
    finally:
        await session.close()

    session = await db_session_factory_independent()
    try:
        jobs = await claim_pending_jobs(session, 10, 300)
        assert len(jobs) == 1 and jobs[0].id == job_id and jobs[0].status == "running"
    finally:
        await session.close()
