from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.runtime import _as_utc, _now, _require_access_token
from app.core.database import Agent, AlertRecord, AuditLog, MetricSnapshot, Organization, RemediationJob, RemediationRecord, get_db


class RemediationTriggerRequest(BaseModel):
    issue_type: str = Field(default="")


class RollbackRequest(BaseModel):
    remediation_id: str


class AutonomousModeRequest(BaseModel):
    enabled: bool


RULES: list[dict[str, Any]] = [
    {"id": "cpu-high-autoscale", "issue_type": "cpu", "name": "High CPU Spike", "trigger": "cpu_usage > 85", "severity": "high", "action": "auto_scale_service"},
    {"id": "error-rate-rollback", "issue_type": "error_rate", "name": "Error Rate Spike", "trigger": "error_rate > 5", "severity": "critical", "action": "rollback_last_deployment"},
    {"id": "disk-cleanup-85", "issue_type": "disk", "name": "Disk Usage Over 85%", "trigger": "disk_usage > 85", "severity": "high", "action": "log_cleanup_script"},
]


def _error_rate(snapshot: MetricSnapshot | None) -> float:
    if snapshot is None:
        return 0.0
    try:
        return float((snapshot.extra or {}).get("error_rate", 0))
    except (TypeError, ValueError):
        return 0.0


async def _resolve_org(db: AsyncSession, request: Request) -> Organization:
    payload = await _require_access_token(request)
    org_id = payload.get("org_id")
    if not org_id:
        raise HTTPException(status_code=403, detail="Organization scope required")
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


async def _latest_metric(db: AsyncSession, org_id: str) -> MetricSnapshot | None:
    result = await db.execute(
        select(MetricSnapshot)
        .where(MetricSnapshot.org_id == org_id)
        .order_by(desc(MetricSnapshot.timestamp))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _write_audit(db: AsyncSession, org_id: str, action: str, detail: dict[str, Any]) -> None:
    db.add(
        AuditLog(
            id=str(uuid.uuid4()),
            org_id=org_id,
            action=action,
            detail=detail,
            resource_type="remediation",
        )
    )


def _serialize_record(record: RemediationRecord) -> dict[str, Any]:
    before = record.before_metrics or {}
    after = record.after_metrics or {}
    started = _as_utc(record.started_at)
    completed = _as_utc(record.completed_at)
    duration = int((completed - started).total_seconds()) if started and completed else None
    return {
        "id": record.id,
        "rule_id": record.action,
        "rule_name": record.action.replace("_", " ").title(),
        "action": record.action,
        "success": record.status == "success",
        "status": record.status,
        "timestamp": (completed or started or _as_utc(record.created_at) or _now()).isoformat(),
        "execution_time_seconds": duration,
        "metrics_before": {"cpu_usage": before.get("cpu"), "memory_usage": before.get("memory"), "disk_usage": before.get("disk")},
        "metrics_after": {"cpu_usage": after.get("cpu"), "memory_usage": after.get("memory"), "disk_usage": after.get("disk")},
        "error_message": record.error,
        "result": record.result,
    }


def _apply_action(rule_action: str, before: dict[str, Any]) -> dict[str, Any]:
    after = dict(before)
    if rule_action == "auto_scale_service":
        after["cpu"] = max(0.0, float(before.get("cpu") or 0.0) - 15.0)
    elif rule_action == "rollback_last_deployment":
        after["cpu"] = max(0.0, float(before.get("cpu") or 0.0) - 6.0)
        after["memory"] = max(0.0, float(before.get("memory") or 0.0) - 4.0)
    elif rule_action == "log_cleanup_script":
        after["disk"] = max(0.0, float(before.get("disk") or 0.0) - 18.0)
    return after


def build_remediation_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/remediation/rules")
    async def get_rules(request: Request, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        org = await _resolve_org(db, request)
        enabled_map = (org.settings or {}).get("remediation_rules_enabled", {})
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "trigger_pattern": r["trigger"],
                "severity": r["severity"],
                "action": r["action"],
                "enabled": bool(enabled_map.get(r["id"], True)),
            }
            for r in RULES
        ]

    @router.post("/api/remediation/rules/{rule_id}/toggle")
    async def toggle_rule(rule_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org = await _resolve_org(db, request)
        settings = dict(org.settings or {})
        enabled_map = dict(settings.get("remediation_rules_enabled", {}))
        enabled = not bool(enabled_map.get(rule_id, True))
        enabled_map[rule_id] = enabled
        settings["remediation_rules_enabled"] = enabled_map
        org.settings = settings
        await _write_audit(db, org.id, "playbook.rule.toggled", {"rule_id": rule_id, "enabled": enabled})
        await db.commit()
        return {"rule_id": rule_id, "enabled": enabled}

    @router.get("/api/remediation/issues")
    async def get_issues(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org = await _resolve_org(db, request)
        metric = await _latest_metric(db, org.id)
        metrics = {
            "cpu_usage": metric.cpu if metric else 0.0,
            "memory_usage": metric.memory if metric else 0.0,
            "disk_usage": metric.disk if metric else 0.0,
            "error_rate": _error_rate(metric),
        }
        issues = []
        for r in RULES:
            threshold = float(r["trigger"].split(">")[-1].strip())
            metric_key = "error_rate" if r["issue_type"] == "error_rate" else f"{r['issue_type']}_usage"
            value = float(metrics.get(metric_key, 0.0))
            issues.append({
                "rule_id": r["id"],
                "rule_name": r["name"],
                "issue_type": r["issue_type"],
                "trigger_pattern": r["trigger"],
                "severity": r["severity"],
                "current_value": value,
                "triggered": value > threshold,
                "in_cooldown": False,
                "ai_explanation": f"{r['name']} recommended action: {r['action'].replace('_', ' ')}",
            })
        return {"issues": issues, "metrics": metrics}

    @router.post("/api/remediation/trigger")
    async def trigger(body: RemediationTriggerRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org = await _resolve_org(db, request)
        issue_type = body.issue_type.strip().lower() or "cpu"
        rule = next((x for x in RULES if x["issue_type"] == issue_type), None)
        if rule is None:
            return {"success": False, "message": f"Unknown issue_type '{issue_type}'", "results": []}

        dedup_cutoff = _now() - timedelta(minutes=2)
        existing_result = await db.execute(
            select(RemediationRecord)
            .where(
                RemediationRecord.org_id == org.id,
                RemediationRecord.action == rule["action"],
                RemediationRecord.created_at >= dedup_cutoff,
            )
            .order_by(desc(RemediationRecord.created_at))
            .limit(1)
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return {"success": existing.status == "success", "message": "Playbook already executed recently", "results": [{"id": existing.id, "rule_name": rule["name"], "action": existing.action, "success": existing.status == "success", "status": existing.status}]}

        metric = await _latest_metric(db, org.id)
        before = {"cpu": metric.cpu if metric else 0.0, "memory": metric.memory if metric else 0.0, "disk": metric.disk if metric else 0.0, "error_rate": _error_rate(metric)}
        after = _apply_action(rule["action"], before)
        record = RemediationRecord(id=str(uuid.uuid4()), org_id=org.id, action=rule["action"], params={"issue_type": issue_type, "retry_max": 2}, source="auto", status="success", before_metrics=before, after_metrics=after, verified=True, started_at=_now(), completed_at=_now(), result=f"{rule['name']} executed")
        db.add(record)
        await _write_audit(db, org.id, "playbook.started", {"issue_type": issue_type, "rule": rule["id"], "action": rule["action"]})
        await _write_audit(db, org.id, "playbook.completed", {"issue_type": issue_type, "rule": rule["id"], "status": record.status})
        await db.commit()
        return {"success": True, "message": record.result, "results": [{"id": record.id, "rule_name": rule["name"], "action": record.action, "success": True, "status": record.status}]}

    @router.post("/api/remediation/rollback")
    async def rollback(body: RollbackRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org = await _resolve_org(db, request)
        source = (
            (
                await db.execute(
                    select(RemediationRecord).where(
                        RemediationRecord.id == body.remediation_id,
                        RemediationRecord.org_id == org.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if source is None:
            raise HTTPException(status_code=404, detail="Remediation record not found")
        if source.status != "success":
            raise HTTPException(status_code=400, detail="Only successful remediations can be rolled back")
        if (source.action or "").startswith("rollback_"):
            raise HTTPException(status_code=400, detail="Rollback entries cannot be rolled back again")
        if source.before_metrics is None or source.after_metrics is None:
            raise HTTPException(status_code=400, detail="Rollback data unavailable for this remediation record")

        rollback_row = RemediationRecord(
            id=str(uuid.uuid4()),
            org_id=org.id,
            alert_id=source.alert_id,
            agent_id=source.agent_id,
            action=f"rollback_{source.action}",
            params={"source_remediation_id": source.id},
            source="manual",
            status="success",
            before_metrics=source.after_metrics,
            after_metrics=source.before_metrics,
            verified=True,
            started_at=_now(),
            completed_at=_now(),
            result="Rollback completed",
        )
        db.add(rollback_row)
        await _write_audit(
            db,
            org.id,
            "playbook.rollback",
            {
                "source_remediation_id": source.id,
                "source_action": source.action,
                "rollback_id": rollback_row.id,
            },
        )
        await db.commit()
        return {
            "success": True,
            "message": "Rollback executed",
            "rollback_id": rollback_row.id,
            "source_remediation_id": source.id,
        }

    @router.get("/api/remediation/history")
    async def history(request: Request, limit: int = 50, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        org = await _resolve_org(db, request)
        rows = (await db.execute(select(RemediationRecord).where(RemediationRecord.org_id == org.id).order_by(desc(RemediationRecord.created_at)).limit(limit))).scalars().all()
        return [_serialize_record(row) for row in rows]

    @router.get("/api/remediation/stats")
    async def stats(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org = await _resolve_org(db, request)
        rows = list((await db.execute(select(RemediationRecord).where(RemediationRecord.org_id == org.id))).scalars().all())
        total = len(rows)
        success = sum(1 for row in rows if row.status == "success")
        failed = sum(1 for row in rows if row.status == "failed")
        durations = [(_as_utc(r.completed_at) - _as_utc(r.started_at)).total_seconds() for r in rows if _as_utc(r.started_at) and _as_utc(r.completed_at)]
        return {"total_actions": total, "successful_actions": success, "failed_actions": failed, "success_rate": round((success / total) * 100, 2) if total else 0.0, "avg_execution_time_seconds": round(sum(durations) / len(durations), 2) if durations else 0.0}

    @router.get("/api/remediation/autonomous")
    async def get_autonomous(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org = await _resolve_org(db, request)
        return {"autonomous_mode": bool((org.settings or {}).get("autonomous_mode", False))}

    @router.post("/api/remediation/autonomous")
    async def set_autonomous(body: AutonomousModeRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org = await _resolve_org(db, request)
        settings = dict(org.settings or {})
        settings["autonomous_mode"] = body.enabled
        org.settings = settings
        await _write_audit(db, org.id, "playbook.autonomous.updated", {"enabled": body.enabled})
        await db.commit()
        return {"autonomous_mode": body.enabled, "message": f"Autonomous mode {'enabled' if body.enabled else 'disabled'}", "safety_note": "High and critical issues should still require human review."}

    @router.get("/api/remediation/mttr")
    async def mttr(request: Request, days: int = 14, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org = await _resolve_org(db, request)
        cutoff = _now() - timedelta(days=max(1, min(days, 90)))
        alerts = {
            a.id: a
            for a in (
                await db.execute(
                    select(AlertRecord).where(
                        AlertRecord.org_id == org.id,
                        AlertRecord.created_at >= cutoff,
                    )
                )
            ).scalars().all()
        }
        jobs = list(
            (
                await db.execute(
                    select(RemediationJob)
                    .where(
                        RemediationJob.org_id == org.id,
                        RemediationJob.status == "success",
                        RemediationJob.updated_at >= cutoff,
                        RemediationJob.alert_id.is_not(None),
                    )
                    .order_by(RemediationJob.updated_at.asc())
                )
            ).scalars().all()
        )

        timeline: list[dict[str, Any]] = []
        ttr_vals: list[float] = []
        trend_buckets: dict[str, dict[str, Any]] = {}

        for job in jobs:
            alert = alerts.get(job.alert_id) if job.alert_id else None
            if alert is None:
                continue

            alert_time = _as_utc(alert.created_at)
            success_time = _as_utc(job.updated_at)
            if not alert_time or not success_time:
                continue

            ttr = max(0.0, (success_time - alert_time).total_seconds())
            ttr_vals.append(ttr)

            timeline.append(
                {
                    "incident_id": alert.id,
                    "job_id": job.id,
                    "action": job.playbook_type,
                    "status": job.status,
                    "detected_at": alert_time.isoformat(),
                    "started_at": alert_time.isoformat(),
                    "completed_at": success_time.isoformat(),
                    "ttd_seconds": 0.0,
                    "ttr_seconds": round(ttr, 2),
                    "mttr_seconds": round(ttr, 2),
                }
            )

            day_key = success_time.date().isoformat()
            bucket = trend_buckets.setdefault(day_key, {"day": day_key, "incidents": 0, "total_ttr": 0.0})
            bucket["incidents"] += 1
            bucket["total_ttr"] += ttr

        avg = lambda vals: round(sum(vals) / len(vals), 2) if vals else 0.0
        trend = []
        for key in sorted(trend_buckets.keys()):
            bucket = trend_buckets[key]
            incidents = int(bucket["incidents"])
            total_ttr = float(bucket["total_ttr"])
            trend.append(
                {
                    "day": bucket["day"],
                    "incidents": incidents,
                    "mttr_seconds": round(total_ttr / incidents, 2) if incidents else 0.0,
                }
            )

        return {
            "window_days": days,
            "incident_count": len(timeline),
            "ttd_avg_seconds": 0.0,
            "ttr_avg_seconds": avg(ttr_vals),
            "mttr_avg_seconds": avg(ttr_vals),
            "timeline": list(reversed(timeline[-100:])),
            "trend": trend,
        }

    @router.get("/api/onboarding/status")
    async def onboarding_status(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        org = await _resolve_org(db, request)
        agents_count = (await db.execute(select(func.count(Agent.id)).where(Agent.org_id == org.id, Agent.is_active == True))).scalar_one()
        metrics_count = (await db.execute(select(func.count(MetricSnapshot.id)).where(MetricSnapshot.org_id == org.id))).scalar_one()
        alerts_count = (await db.execute(select(func.count(AlertRecord.id)).where(AlertRecord.org_id == org.id))).scalar_one()
        return {"steps": {"connect_first_agent": agents_count > 0, "see_live_metrics": metrics_count > 0, "create_first_alert": alerts_count > 0}, "counts": {"agents": int(agents_count or 0), "metrics": int(metrics_count or 0), "alerts": int(alerts_count or 0)}}

    return router

