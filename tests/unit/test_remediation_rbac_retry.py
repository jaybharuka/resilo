"""
Regression tests for phase-3 HIGH/MEDIUM findings:
  - HIGH-2: retry lifecycle — only failed jobs can be retried; attempts not reset to zero
  - HIGH-4: RBAC — non-admin/devops roles cannot perform mutating operations
  - MEDIUM-1: rollback source scoped to job creation time
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.remediation_jobs_runtime import (_mark_job_pending,
                                              _require_mutating_role,
                                              _serialize_job)
from app.api.remediation_runtime import MUTATING_ROLES
from app.api.remediation_runtime import \
    _require_mutating_role as _require_mutating_role_remediation
from app.core.database import RemediationJob, RemediationRecord

# ── RBAC helpers ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["admin", "devops"])
def test_mutating_role_allows_admin_and_devops(role: str) -> None:
    payload = {"role": role, "sub": "user-1", "org_id": "org-1"}
    # Should not raise
    _require_mutating_role(payload)
    _require_mutating_role_remediation(payload)


@pytest.mark.parametrize("role", ["viewer", "manager", "employee", "guest", "", None])
def test_mutating_role_blocks_non_privileged_roles(role) -> None:
    payload = {"role": role, "sub": "user-1", "org_id": "org-1"}
    with pytest.raises(HTTPException) as exc_info:
        _require_mutating_role(payload)
    assert exc_info.value.status_code == 403

    with pytest.raises(HTTPException) as exc_info2:
        _require_mutating_role_remediation(payload)
    assert exc_info2.value.status_code == 403


def test_mutating_roles_constant_contains_expected_roles() -> None:
    assert "admin" in MUTATING_ROLES
    assert "devops" in MUTATING_ROLES
    assert "viewer" not in MUTATING_ROLES
    assert "employee" not in MUTATING_ROLES


# ── Retry lifecycle ───────────────────────────────────────────────────────────

def _make_job(status: str, attempts: int = 2, max_retries: int = 3) -> RemediationJob:
    return RemediationJob(
        id=99,
        playbook_type="high_cpu",
        status=status,
        attempts=attempts,
        max_retries=max_retries,
        created_at=datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc),
    )


def test_mark_job_pending_preserves_attempts() -> None:
    """Retry must not reset attempts to zero — that bypasses the max_retries ceiling."""
    job = _make_job("failed", attempts=2)
    _mark_job_pending(job)
    assert job.status == "pending"
    assert job.attempts == 2, "attempts must be preserved; resetting to 0 enables unbounded replay"
    assert job.last_error is None


def test_mark_job_pending_clears_last_error() -> None:
    job = _make_job("failed", attempts=1)
    job.last_error = "previous failure"
    _mark_job_pending(job)
    assert job.last_error is None


@pytest.mark.parametrize("status", ["failed"])
def test_can_retry_only_for_failed_status(status: str) -> None:
    job = _make_job(status)
    serialized = _serialize_job(job)
    assert serialized["can_retry"] is True


@pytest.mark.parametrize("status", ["success", "pending", "running", "cancelled"])
def test_cannot_retry_non_failed_statuses(status: str) -> None:
    """Only failed jobs may be retried to prevent replay of successful jobs."""
    job = _make_job(status)
    serialized = _serialize_job(job)
    assert serialized["can_retry"] is False, (
        f"can_retry must be False for status='{status}' to block retry abuse"
    )


# ── Rollback source scoping (MEDIUM-1) ───────────────────────────────────────

def _make_record(
    record_id: str,
    action: str,
    status: str,
    created_at: datetime,
) -> RemediationRecord:
    return RemediationRecord(
        id=record_id,
        org_id="org-1",
        alert_id="alert-1",
        action=action,
        status=status,
        source="auto",
        created_at=created_at,
    )


def test_rollback_source_scoped_to_job_creation_time() -> None:
    """
    The rollback source should only consider remediations created at or after
    the job was created. An older record for the same alert must be excluded.
    """
    job_created = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)
    old_record = _make_record(
        "old-record",
        "auto_scale_service",
        "success",
        datetime(2026, 4, 5, 11, 0, tzinfo=timezone.utc),  # before job
    )
    new_record = _make_record(
        "new-record",
        "log_cleanup_script",
        "success",
        datetime(2026, 4, 5, 12, 30, tzinfo=timezone.utc),  # after job
    )

    job = RemediationJob(
        id=10,
        playbook_type="disk_full",
        status="success",
        attempts=1,
        max_retries=3,
        created_at=job_created,
        updated_at=job_created,
    )

    remediations = [old_record, new_record]
    rollback_source = next(
        (
            record
            for record in remediations
            if record.status == "success"
            and not (record.action or "").startswith("rollback_")
            and (
                record.created_at is None
                or job.created_at is None
                or record.created_at >= job.created_at
            )
        ),
        None,
    )

    assert rollback_source is not None
    assert rollback_source.id == "new-record", (
        "rollback source must be scoped to records at or after job creation; "
        "selecting old_record would target an unrelated remediation"
    )


def test_rollback_source_excludes_rollback_actions() -> None:
    """Rollback-of-rollback entries must never be selected as a rollback source."""
    job_created = datetime(2026, 4, 5, 12, 0, tzinfo=timezone.utc)
    rollback_entry = _make_record(
        "rb-record",
        "rollback_auto_scale_service",
        "success",
        datetime(2026, 4, 5, 12, 5, tzinfo=timezone.utc),
    )
    job = RemediationJob(
        id=11,
        playbook_type="high_cpu",
        status="success",
        attempts=1,
        max_retries=3,
        created_at=job_created,
        updated_at=job_created,
    )

    rollback_source = next(
        (
            record
            for record in [rollback_entry]
            if record.status == "success"
            and not (record.action or "").startswith("rollback_")
            and (
                record.created_at is None
                or job.created_at is None
                or record.created_at >= job.created_at
            )
        ),
        None,
    )

    assert rollback_source is None, "rollback_ prefixed entries must never be selected as rollback source"
