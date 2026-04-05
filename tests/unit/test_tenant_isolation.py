from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.core.database import Base, Organization, SessionLocal, User, engine
from helpers import make_jwt


async def _create_org() -> Organization:
    suffix = str(uuid.uuid4())[:8]
    org = Organization(
        id=str(uuid.uuid4()),
        name=f"Tenant Test Org {suffix}",
        slug=f"tenant-test-{suffix}",
        plan="free",
        is_active=True,
    )
    async with SessionLocal() as session:
        session.add(org)
        await session.commit()
        await session.refresh(org)
    return org


async def _create_user(org_id: str) -> User:
    suffix = str(uuid.uuid4())[:8]
    user = User(
        id=str(uuid.uuid4()),
        org_id=org_id,
        email=f"tenant-test-{suffix}@example.com",
        username=f"tenant-test-{suffix}",
        hashed_password="not-used-in-test",
        role="admin",
        is_active=True,
    )
    async with SessionLocal() as session:
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _tenant_isolation_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_jobs_are_scoped_by_org(core_client):
    org_a = await _create_org()
    org_b = await _create_org()
    user_a = await _create_user(org_a.id)
    user_b = await _create_user(org_b.id)
    try:
        create_resp = await core_client.post(
            f"/api/orgs/{org_a.id}/alerts",
            headers={"Authorization": f"Bearer {make_jwt(user_a.id, 'admin', org_a.id)}"},
            json={
                "severity": "high",
                "category": "cpu",
                "title": "CPU threshold exceeded",
                "detail": "CPU at 92%, threshold 80%",
                "metric_value": 92.0,
                "threshold": 80.0,
            },
        )
        assert create_resp.status_code == 201, create_resp.text

        list_resp = await core_client.get(
            "/api/remediation/jobs",
            headers={"Authorization": f"Bearer {make_jwt(user_a.id, 'admin', org_a.id)}"},
        )
        assert list_resp.status_code == 200, list_resp.text
        jobs = list_resp.json()
        assert jobs, "Expected a remediation job for the org that created the alert"
        job_id = jobs[0]["id"]

        other_list_resp = await core_client.get(
            "/api/remediation/jobs",
            headers={"Authorization": f"Bearer {make_jwt(user_b.id, 'admin', org_b.id)}"},
        )
        assert other_list_resp.status_code == 200, other_list_resp.text
        assert other_list_resp.json() == []

        detail_resp = await core_client.get(
            f"/api/remediation/jobs/{job_id}",
            headers={"Authorization": f"Bearer {make_jwt(user_b.id, 'admin', org_b.id)}"},
        )
        assert detail_resp.status_code == 404, detail_resp.text
    finally:
        async with SessionLocal() as session:
            await session.delete(user_a)
            await session.delete(user_b)
            await session.execute(User.__table__.delete().where(User.org_id.in_([org_a.id, org_b.id])))
            await session.execute(Base.metadata.tables["remediation_jobs"].delete())
            await session.execute(Base.metadata.tables["alert_records"].delete())
            await session.delete(org_a)
            await session.delete(org_b)
            await session.commit()
