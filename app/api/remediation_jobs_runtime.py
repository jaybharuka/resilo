from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.runtime import _as_utc, _now, _require_valid_access_payload
from app.core.database import AlertRecord, AuditLog, Organization, RemediationJob, RemediationRecord, get_db


async def _resolve_jobs_org(db: AsyncSession, request: Request) -> Organization:
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    payload = await _require_valid_access_payload(header.removeprefix("Bearer ").strip())
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization scope required")

    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org

async def _resolve_job_context(
    db: AsyncSession,
    request: Request,
    job_id: int,
) -> tuple[Organization, RemediationJob, AlertRecord]:
    org = await _resolve_jobs_org(db, request)
    result = await db.execute(select(RemediationJob).where(RemediationJob.id == job_id, RemediationJob.org_id == org.id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Remediation job not found")

    alert: AlertRecord | None = None
    if job.alert_id is not None:
        alert_result = await db.execute(select(AlertRecord).where(AlertRecord.id == job.alert_id, AlertRecord.org_id == org.id))
        alert = alert_result.scalar_one_or_none()
        if alert is None:
            raise HTTPException(status_code=404, detail="Remediation job not found")

    return org, job, alert


def _serialize_job(job: RemediationJob, alert: AlertRecord | None = None) -> dict[str, Any]:
    created_at = _as_utc(job.created_at) or _now()
    updated_at = _as_utc(job.updated_at) or created_at
    return {
        "id": job.id,
        "alert_id": job.alert_id,
        "alert_title": alert.title if alert else None,
        "playbook_type": job.playbook_type,
        "status": job.status,
        "attempts": job.attempts,
        "max_retries": job.max_retries,
        "payload": job.payload or {},
        "last_error": job.last_error,
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
        "can_retry": job.status != "running",
        "can_cancel": job.status in {"pending", "failed"},
    }


def _serialize_job_log(
    *,
    timestamp,
    level: str,
    event: str,
    message: str,
    source: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": (_as_utc(timestamp) or _now()).isoformat(),
        "level": level,
        "event": event,
        "message": message,
        "source": source,
        "details": details or {},
    }


def _build_job_logs(
    job: RemediationJob,
    *,
    alert: AlertRecord | None = None,
    remediations: list[RemediationRecord] | None = None,
) -> list[dict[str, Any]]:
    logs: list[dict[str, Any]] = []
    created_at = _as_utc(job.created_at) or _now()
    updated_at = _as_utc(job.updated_at) or created_at

    logs.append(
        _serialize_job_log(
            timestamp=created_at,
            level="info",
            event="queued",
            message=f"Job queued for {job.playbook_type}",
            source="job",
            details={"status": job.status, "attempts": job.attempts, "alert_title": alert.title if alert else None},
        )
    )

    if job.attempts > 0:
        logs.append(
            _serialize_job_log(
                timestamp=updated_at,
                level="info",
                event="claimed",
                message=f"Job claimed by worker on attempt {job.attempts}",
                source="job",
                details={"attempts": job.attempts},
            )
        )

    if job.status == "running":
        logs.append(
            _serialize_job_log(
                timestamp=updated_at,
                level="info",
                event="running",
                message="Job is currently running",
                source="job",
            )
        )
    elif job.status == "success":
        logs.append(
            _serialize_job_log(
                timestamp=updated_at,
                level="info",
                event="completed",
                message="Job completed successfully",
                source="job",
            )
        )
    elif job.status == "failed":
        logs.append(
            _serialize_job_log(
                timestamp=updated_at,
                level="error",
                event="failed",
                message=job.last_error or "Job failed",
                source="job",
            )
        )
    elif job.status == "cancelled":
        logs.append(
            _serialize_job_log(
                timestamp=updated_at,
                level="warning",
                event="cancelled",
                message="Job was cancelled",
                source="job",
            )
        )

    if job.last_error:
        logs.append(
            _serialize_job_log(
                timestamp=updated_at,
                level="error",
                event="error",
                message=job.last_error,
                source="job",
            )
        )

    for record in remediations or []:
        started_at = _as_utc(record.started_at) or _as_utc(record.created_at) or _now()
        completed_at = _as_utc(record.completed_at) or started_at
        logs.append(
            _serialize_job_log(
                timestamp=started_at,
                level="info",
                event="remediation.started",
                message=f"Remediation record started: {record.action}",
                source="remediation_record",
                details={"status": record.status, "action": record.action},
            )
        )
        logs.append(
            _serialize_job_log(
                timestamp=completed_at,
                level="info" if record.status == "success" else "error",
                event=f"remediation.{record.status}",
                message=record.result or record.error or record.action.replace("_", " "),
                source="remediation_record",
                details={"status": record.status, "action": record.action},
            )
        )

    logs.sort(key=lambda entry: entry["timestamp"])
    return logs


def _mark_job_pending(job: RemediationJob) -> None:
    job.status = "pending"
    job.attempts = 0
    job.last_error = None
    job.updated_at = _now()


def _mark_job_cancelled(job: RemediationJob) -> None:
    job.status = "cancelled"
    job.updated_at = _now()


async def _write_job_audit(db: AsyncSession, org_id: str, action: str, job: RemediationJob) -> None:
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            org_id=org_id,
            action=action,
            resource_type="remediation_job",
            resource_id=str(job.id),
            detail={"job_id": job.id, "playbook_type": job.playbook_type, "status": job.status},
        )
    )


def build_remediation_jobs_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/remediation/jobs")
    async def get_jobs(request: Request, limit: int = 100, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        org = await _resolve_jobs_org(db, request)
        effective_limit = max(1, min(limit, 100))
        jobs_result = await db.execute(
            select(RemediationJob)
            .where(RemediationJob.org_id == org.id)
            .order_by(desc(RemediationJob.created_at))
            .limit(effective_limit)
        )
        jobs = list(jobs_result.scalars().all())
        alert_ids = [job.alert_id for job in jobs if job.alert_id]
        alert_map: dict[str, AlertRecord] = {}
        if alert_ids:
            alerts_result = await db.execute(
                select(AlertRecord).where(AlertRecord.org_id == org.id, AlertRecord.id.in_(alert_ids))
            )
            for alert in alerts_result.scalars().all():
                alert_map[alert.id] = alert

        items: list[dict[str, Any]] = []
        for job in jobs:
            items.append(_serialize_job(job, alert_map.get(job.alert_id)))
        return items

    @router.get("/api/remediation/jobs/{job_id}")
    async def get_job(job_id: int, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org, job, alert = await _resolve_job_context(db, request, job_id)
        remediations: list[RemediationRecord] = []
        if job.alert_id:
            remediation_result = await db.execute(
                select(RemediationRecord)
                .where(RemediationRecord.org_id == org.id, RemediationRecord.alert_id == job.alert_id)
                .order_by(desc(RemediationRecord.created_at))
                .limit(20)
            )
            remediations = list(remediation_result.scalars().all())

        await _write_job_audit(db, org.id, "remediation.job.viewed", job)
        await db.commit()
        return {
            "job": _serialize_job(job, alert),
            "logs": _build_job_logs(job, alert=alert, remediations=remediations),
        }

    @router.get("/api/remediation/jobs/{job_id}/logs")
    async def get_job_logs(job_id: int, request: Request, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        org, job, alert = await _resolve_job_context(db, request, job_id)
        remediations: list[RemediationRecord] = []
        if job.alert_id:
            remediation_result = await db.execute(
                select(RemediationRecord)
                .where(RemediationRecord.org_id == org.id, RemediationRecord.alert_id == job.alert_id)
                .order_by(desc(RemediationRecord.created_at))
                .limit(20)
            )
            remediations = list(remediation_result.scalars().all())
        return _build_job_logs(job, alert=alert, remediations=remediations)

    @router.post("/api/remediation/jobs/{job_id}/retry")
    async def retry_job(job_id: int, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org, job, alert = await _resolve_job_context(db, request, job_id)
        if job.status == "running":
            raise HTTPException(status_code=409, detail="Running jobs cannot be retried")
        _mark_job_pending(job)
        await _write_job_audit(db, org.id, "remediation.job.retry", job)
        await db.commit()
        return {"status": job.status, "job": _serialize_job(job, alert), "message": "Job re-queued"}

    @router.post("/api/remediation/jobs/{job_id}/cancel")
    async def cancel_job(job_id: int, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org, job, alert = await _resolve_job_context(db, request, job_id)
        if job.status not in {"pending", "failed"}:
            raise HTTPException(status_code=409, detail="Only pending or failed jobs can be cancelled")
        _mark_job_cancelled(job)
        await _write_job_audit(db, org.id, "remediation.job.cancel", job)
        await db.commit()
        return {"status": job.status, "job": _serialize_job(job, alert), "message": "Job cancelled"}

    return router



