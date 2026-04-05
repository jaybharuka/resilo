from datetime import datetime, timezone

import pytest

from app.api.remediation_jobs_runtime import _build_job_logs, _mark_job_cancelled, _mark_job_pending, _serialize_job
from app.core.database import AlertRecord, AuditLog, RemediationJob, RemediationRecord


@pytest.mark.asyncio
async def test_playbook_execution():
    from app.remediation.executor import execute_playbook

    result = await execute_playbook("high_cpu", {"cpu": 95})

    assert result["status"] == "success"


def test_serialize_job_includes_expected_fields():
    created_at = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)
    updated_at = datetime(2026, 4, 5, 12, 10, tzinfo=timezone.utc)
    job = RemediationJob(
        id=7,
        alert_id="alert-1",
        playbook_type="cpu_high",
        status="failed",
        attempts=2,
        max_retries=3,
        payload={"source": "api"},
        last_error="boom",
        created_at=created_at,
        updated_at=updated_at,
    )
    alert = AlertRecord(
        id="alert-1",
        org_id="org-1",
        severity="high",
        category="cpu",
        title="CPU spike",
        detail="CPU crossed threshold",
        status="open",
        created_at=created_at,
    )

    result = _serialize_job(job, alert)

    assert result["id"] == 7
    assert result["alert_title"] == "CPU spike"
    assert result["playbook_type"] == "cpu_high"
    assert result["status"] == "failed"
    assert result["attempts"] == 2
    assert result["can_retry"] is True
    assert result["can_cancel"] is True
    assert result["last_error"] == "boom"


def test_build_job_logs_combines_job_and_record_history():
    created_at = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)
    updated_at = datetime(2026, 4, 5, 12, 10, tzinfo=timezone.utc)
    job = RemediationJob(
        id=9,
        alert_id="alert-9",
        playbook_type="disk_cleanup",
        status="failed",
        attempts=1,
        max_retries=3,
        last_error="disk cleanup failed",
        created_at=created_at,
        updated_at=updated_at,
    )
    alert = AlertRecord(
        id="alert-9",
        org_id="org-1",
        severity="high",
        category="disk",
        title="Disk pressure",
        detail="Disk usage is high",
        status="open",
        created_at=created_at,
    )
    audit = AuditLog(
        id="audit-1",
        org_id="org-1",
        action="remediation.job.retry",
        resource_type="remediation_job",
        resource_id="9",
        detail={"job_id": 9},
        created_at=updated_at,
    )
    record = RemediationRecord(
        id="record-1",
        org_id="org-1",
        alert_id="alert-9",
        action="log_cleanup_script",
        source="auto",
        status="success",
        started_at=created_at,
        completed_at=updated_at,
        result="Completed",
        created_at=created_at,
    )

    logs = _build_job_logs(job, alert=alert, remediations=[record])

    assert logs[0]["event"] == "queued"
    assert any(entry["event"] == "claimed" for entry in logs)
    assert any(entry["event"] == "failed" for entry in logs)
    assert any(entry["source"] == "remediation_record" for entry in logs)


def test_job_state_helpers_reset_and_cancel():
    job = RemediationJob(
        id=11,
        playbook_type="high_cpu",
        status="failed",
        attempts=3,
        max_retries=3,
        created_at=datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 5, 12, 10, tzinfo=timezone.utc),
    )

    _mark_job_pending(job)
    assert job.status == "pending"
    assert job.attempts == 3  # attempts are preserved — not reset — to enforce max_retries ceiling
    assert job.last_error is None

    _mark_job_cancelled(job)
    assert job.status == "cancelled"
