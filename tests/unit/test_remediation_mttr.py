from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from helpers import make_jwt

from app.core.database import (AlertRecord, Base, Organization, RemediationJob,
                               SessionLocal, User, engine)


async def _create_org() -> Organization:
    suffix = str(uuid.uuid4())[:8]
    org = Organization(
        id=str(uuid.uuid4()),
        name=f"MTTR Test Org {suffix}",
        slug=f"mttr-test-{suffix}",
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
        email=f"mttr-test-{suffix}@example.com",
        username=f"mttr-test-{suffix}",
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
async def _mttr_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_mttr_uses_alert_detection_to_success_completion(core_client):
    org = await _create_org()
    user = await _create_user(org.id)
    alert_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    alert_time = now - timedelta(hours=3)
    success_time = alert_time + timedelta(minutes=90)

    try:
        async with SessionLocal() as session:
            session.add(
                AlertRecord(
                    id=alert_id,
                    org_id=org.id,
                    severity="high",
                    category="cpu",
                    title="CPU saturation",
                    detail="CPU exceeded threshold",
                    status="open",
                    created_at=alert_time,
                )
            )
            session.add(
                RemediationJob(
                    org_id=org.id,
                    alert_id=alert_id,
                    playbook_type="restart_service",
                    status="success",
                    attempts=1,
                    max_retries=3,
                    created_at=alert_time,
                    updated_at=success_time,
                )
            )
            await session.commit()

        token = make_jwt(user.id, "admin", org.id)
        resp = await core_client.get(
            "/api/remediation/mttr?days=14",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["incident_count"] >= 1
        assert data["mttr_avg_seconds"] == pytest.approx(5400.0, abs=1.0)
        assert any(item.get("incident_id") == alert_id for item in data.get("timeline", []))
        assert any(bucket.get("incidents", 0) >= 1 for bucket in data.get("trend", []))
    finally:
        async with SessionLocal() as session:
            await session.execute(RemediationJob.__table__.delete().where(RemediationJob.org_id == org.id))
            await session.execute(AlertRecord.__table__.delete().where(AlertRecord.org_id == org.id))
            await session.execute(User.__table__.delete().where(User.org_id == org.id))
            await session.delete(org)
            await session.commit()
