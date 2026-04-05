from __future__ import annotations

from datetime import datetime, timedelta
import uuid

import pytest

from app.core.database import AlertRecord, RemediationJob, SessionLocal
from helpers import make_jwt


@pytest.mark.asyncio
async def test_mttr_uses_alert_detection_to_success_completion(core_client, sample_org):
    now = datetime.utcnow()
    alert_time = now - timedelta(hours=3)
    success_time = alert_time + timedelta(minutes=90)
    alert_id = str(uuid.uuid4())

    try:
        async with SessionLocal() as session:
            session.add(
                AlertRecord(
                    id=alert_id,
                    org_id=sample_org.id,
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
                    org_id=sample_org.id,
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

        token = make_jwt(str(uuid.uuid4()), "admin", sample_org.id)
        resp = await core_client.get(
            "/api/remediation/mttr?days=14",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["incident_count"] >= 1
        assert data["mttr_avg_seconds"] >= 5400.0
        assert any(item.get("incident_id") == alert_id for item in data.get("timeline", []))
        assert any(bucket.get("incidents", 0) >= 1 for bucket in data.get("trend", []))
    finally:
        async with SessionLocal() as session:
            await session.execute(AlertRecord.__table__.delete().where(AlertRecord.org_id == sample_org.id))
            await session.execute(RemediationJob.__table__.delete().where(RemediationJob.org_id == sample_org.id))
            await session.commit()
