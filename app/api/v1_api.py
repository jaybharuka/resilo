"""
v1_api.py — /api/v1/* endpoints for the Resilo AIOps dashboard.

Implements:
  - GET  /api/v1/remediation/actions            (live feed + SSE stream)
  - GET  /api/v1/remediation/actions/stream     (SSE)
  - GET  /api/v1/tenants/health-summary
  - GET  /api/v1/predictions/upcoming
  - GET  /api/v1/remediation/circuit-breaker/status
  - POST /api/v1/remediation/circuit-breaker/{component}/reset
  - GET  /api/v1/api-keys/usage-heatmap
  - POST /api/v1/incidents
  - GET  /api/v1/incidents/active
  - POST /api/v1/incidents/{incident_id}/resolve
"""
from __future__ import annotations

import asyncio
import json
import math
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.runtime import (
    SSE_HEARTBEAT_SECONDS,
    _get_realtime_hub,
    _require_access_token,
    _now,
    require_role,
)
from app.core.database import (
    Agent, AlertRecord, Incident, MetricSnapshot, Organization,
    RemediationJob, RemediationRecord, get_db,
)

# ── In-memory stores ────────────────────────────────────────────────────────
# Incidents are DB-backed (see Incident model). Only CB reset timestamps
# stay in-memory since they are transient operational hints.
_circuit_breaker_resets: dict[str, datetime] = {}  # "{org_id}:{component}" → reset time

CB_FAILURE_THRESHOLD = int(5)   # failures in window → OPEN
CB_WINDOW_MINUTES    = int(10)  # look-back window for failure counting
CB_TIMEOUT_MINUTES   = int(5)   # after this long in OPEN, move to HALF_OPEN


# ── Pydantic models ──────────────────────────────────────────────────────────

class IncidentCreate(BaseModel):
    severity:    str         = Field(..., pattern=r"^SEV[1-4]$")
    service:     str         = Field(..., min_length=1, max_length=100)
    description: str         = Field(..., min_length=1, max_length=2000)
    commander:   Optional[str] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _utc_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


async def _require_token(request: Request) -> dict[str, Any]:
    return await _require_access_token(request)


def _serialize_action(rec: RemediationRecord) -> dict[str, Any]:
    outcome_map = {
        "success": "success", "failed": "failed",
        "running": "running", "pending": "pending", "skipped": "dry_run",
    }
    return {
        "id":            rec.id,
        "executed_at":   _utc_iso(rec.completed_at or rec.started_at or rec.created_at),
        "component":     rec.agent_id or "system",
        "action":        rec.action,
        "trigger_metric": (rec.params or {}).get("trigger_metric", ""),
        "trigger_value":  (rec.params or {}).get("trigger_value"),
        "outcome":        outcome_map.get(rec.status, rec.status),
        "source":         rec.source,
        "before_metrics": rec.before_metrics,
        "after_metrics":  rec.after_metrics,
        "result":         rec.result,
        "error":          rec.error,
        "created_at":     _utc_iso(rec.created_at),
    }


def _validate_list(data: Any, field: str = "items") -> list:
    """Raise 502 if backend returned something unexpected."""
    if data is None:
        raise HTTPException(status_code=502, detail=f"Backend returned null for {field}")
    if not isinstance(data, list):
        raise HTTPException(status_code=502, detail=f"Expected list for {field}, got {type(data).__name__}")
    return data


# ── Router ───────────────────────────────────────────────────────────────────

def build_v1_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    # ── 1. Remediation actions feed ─────────────────────────────────────────

    @router.get("/remediation/actions")
    async def remediation_actions(
        request: Request,
        limit: int = 20,
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        payload = await _require_token(request)
        org_id  = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        result = await db.execute(
            select(RemediationRecord)
            .where(RemediationRecord.org_id == org_id)
            .order_by(desc(RemediationRecord.created_at))
            .limit(limit)
        )
        records = result.scalars().all()
        items = [_serialize_action(r) for r in records]

        # Data integrity check
        _validate_list(items, "remediation actions")

        return {"items": items, "total": len(items)}

    # ── 1b. SSE stream for live remediation events ──────────────────────────

    @router.get("/remediation/actions/stream")
    async def remediation_actions_stream(request: Request, token: Optional[str] = None) -> StreamingResponse:
        # Accept a short-lived stream token (60s TTL) via query param.
        # The client obtains it by POSTing to /stream/token with their access token.
        # This avoids leaking the long-lived access token in logs/history.
        if token:
            from app.api.runtime import _decode_token
            try:
                payload = _decode_token(token, "stream")
            except Exception:
                raise HTTPException(status_code=401, detail="Invalid or expired stream token")
        else:
            payload = await _require_token(request)
        org_id  = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        async def _gen():
            hub   = _get_realtime_hub(request)
            queue = hub.subscribe(org_id)
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_SECONDS)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                        continue
                    if event.get("type") in ("remediation_action", "remediation_update"):
                        yield f"event: remediation_action\ndata: {json.dumps(event['data'])}\n\n"
            finally:
                hub.unsubscribe(org_id, queue)

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── 2. Tenant health heatmap ─────────────────────────────────────────────

    @router.get("/tenants/health-summary")
    async def tenant_health_summary(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        payload = await _require_token(request)
        role    = payload.get("role", "employee")

        # Admins see all orgs; others see only their own
        if role == "admin":
            orgs_result = await db.execute(select(Organization).where(Organization.is_active == True))
            orgs = list(orgs_result.scalars().all())
        else:
            org_id = payload.get("org_id")
            if not org_id:
                raise HTTPException(status_code=403, detail="Organization scope required")
            orgs_result = await db.execute(select(Organization).where(Organization.id == org_id))
            orgs = list(orgs_result.scalars().all())

        tenants = []
        for org in orgs:
            # Latest metric snapshot for this org
            snap_result = await db.execute(
                select(MetricSnapshot)
                .where(MetricSnapshot.org_id == org.id)
                .order_by(desc(MetricSnapshot.timestamp))
                .limit(1)
            )
            snap: Optional[MetricSnapshot] = snap_result.scalar_one_or_none()

            # Open alert count
            alerts_result = await db.execute(
                select(func.count(AlertRecord.id))
                .where(AlertRecord.org_id == org.id, AlertRecord.status == "open")
            )
            open_alerts = alerts_result.scalar_one() or 0

            # Critical alerts in last hour
            one_hour_ago = _now() - timedelta(hours=1)
            crit_result = await db.execute(
                select(func.count(AlertRecord.id))
                .where(
                    AlertRecord.org_id == org.id,
                    AlertRecord.severity == "critical",
                    AlertRecord.created_at >= one_hour_ago,
                )
            )
            crit_count = crit_result.scalar_one() or 0

            # Health score: start at 100, deduct for alerts and metric pressure
            score = 100
            if snap:
                if snap.cpu > 90:    score -= 25
                elif snap.cpu > 75:  score -= 10
                if snap.memory > 90: score -= 20
                elif snap.memory > 80: score -= 8
                if snap.disk > 90:   score -= 15
                elif snap.disk > 80: score -= 5
            score -= min(open_alerts * 5, 25)
            score -= min(crit_count * 15, 30)
            score = max(0, score)

            # Top issue
            top_issue = None
            if snap:
                if snap.cpu > 90:    top_issue = f"CPU at {snap.cpu:.0f}%"
                elif snap.memory > 85: top_issue = f"Memory at {snap.memory:.0f}%"
                elif snap.disk > 85:   top_issue = f"Disk at {snap.disk:.0f}%"
            if not top_issue and open_alerts > 0:
                top_issue = f"{open_alerts} open alert{'s' if open_alerts > 1 else ''}"

            # Last incident (latest critical alert)
            last_crit_result = await db.execute(
                select(AlertRecord.created_at)
                .where(AlertRecord.org_id == org.id, AlertRecord.severity == "critical")
                .order_by(desc(AlertRecord.created_at))
                .limit(1)
            )
            last_incident_at = last_crit_result.scalar_one_or_none()

            tenants.append({
                "org_id":           org.id,
                "org_name":         org.name,
                "health_score":     score,
                "top_issue":        top_issue,
                "last_incident_at": _utc_iso(last_incident_at),
                "error_rate":       None,   # would need request logs
                "p95_latency_ms":   None,   # would need tracing
                "active_sessions":  None,
                "failed_auth_1h":   None,
                "open_alerts":      open_alerts,
                "cpu":              snap.cpu    if snap else None,
                "memory":           snap.memory if snap else None,
                "disk":             snap.disk   if snap else None,
            })

        _validate_list(tenants, "tenants")
        return {"tenants": tenants}

    # ── 3. Predictive alert timeline ─────────────────────────────────────────

    @router.get("/predictions/upcoming")
    async def predictions_upcoming(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        payload = await _require_token(request)
        org_id  = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        # Fetch last 20 snapshots for trend analysis
        result = await db.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.org_id == org_id)
            .order_by(desc(MetricSnapshot.timestamp))
            .limit(20)
        )
        snaps = list(reversed(result.scalars().all()))  # oldest first

        _validate_list(snaps, "metric snapshots")
        predictions = []

        if len(snaps) >= 3:
            n = len(snaps)
            xs = list(range(n))

            def _mean(v: list[float]) -> float:
                return sum(v) / len(v) if v else 0.0

            def _variance(v: list[float]) -> float:
                if len(v) < 2:
                    return 0.0
                m = _mean(v)
                return sum((x - m) ** 2 for x in v) / (len(v) - 1)

            def _stddev(v: list[float]) -> float:
                return math.sqrt(_variance(v))

            def _moving_average(v: list[float], window: int = 5) -> list[float]:
                result = []
                for i in range(len(v)):
                    start = max(0, i - window + 1)
                    result.append(_mean(v[start : i + 1]))
                return result

            def _linear_trend(values: list[float]) -> tuple[float, float]:
                """OLS slope and last smoothed value using moving average."""
                smoothed = _moving_average(values)
                x_mean = _mean(xs)
                y_mean = _mean(smoothed)
                num = sum((xs[i] - x_mean) * (smoothed[i] - y_mean) for i in range(n))
                den = sum((x - x_mean) ** 2 for x in xs)
                slope = num / den if den else 0.0
                return slope, smoothed[-1]

            def _spike_detected(values: list[float]) -> bool:
                """True if the most recent value is > mean + 2σ of the series."""
                if len(values) < 3:
                    return False
                m = _mean(values[:-1])
                sd = _stddev(values[:-1])
                return sd > 0 and values[-1] > m + 2 * sd

            def _confidence(slope: float, variance: float, seconds_to_hit: float) -> float:
                """
                High confidence when:
                - slope is strong (fast approaching threshold)
                - variance is low (steady trend, not noise)
                - threshold is close (< 30 min away)
                """
                time_factor  = max(0.0, 1.0 - seconds_to_hit / 7200)      # 1.0 at 0min, 0.0 at 120min
                noise_factor = 1.0 / (1.0 + math.sqrt(variance) / 10.0)   # lower noise → higher confidence
                slope_factor = min(1.0, abs(slope) * 20)                   # stronger slope → more confident
                raw = (time_factor * 0.5 + noise_factor * 0.3 + slope_factor * 0.2)
                return round(min(0.97, max(0.35, raw)), 2)

            interval_secs = 30.0
            if len(snaps) >= 2 and snaps[-1].timestamp and snaps[0].timestamp:
                total = (snaps[-1].timestamp - snaps[0].timestamp).total_seconds()
                interval_secs = max(1.0, total / max(n - 1, 1))

            for metric, threshold, name in [
                ("cpu",    90, "CPU saturation"),
                ("memory", 85, "Memory pressure"),
                ("disk",   90, "Disk full"),
            ]:
                values = [getattr(s, metric, 0) or 0.0 for s in snaps]
                slope, last_smooth = _linear_trend(values)
                variance = _variance(values)
                spike = _spike_detected(values)
                last_raw = values[-1]

                # Already breached
                if last_raw >= threshold:
                    severity = "critical"
                    conf = 0.97
                    predictions.append({
                        "name":          name,
                        "metric":        metric,
                        "severity":      severity,
                        "predicted_at":  _utc_iso(_now()),
                        "confidence":    conf,
                        "current_value": round(last_raw, 1),
                        "threshold":     threshold,
                        "slope_per_sample": round(slope, 3),
                        "reason":        f"{name} ALREADY BREACHED at {last_raw:.1f}% (threshold {threshold}%).",
                        "contributing_signals": [
                            f"{metric} is {last_raw:.1f}% — above threshold of {threshold}%",
                            "Immediate action required",
                        ],
                        "spike_detected": spike,
                        "variance":       round(variance, 2),
                    })
                    continue

                if slope <= 0 and not spike:
                    continue  # stable or declining

                # Spike: predict breach within 3 × interval even if slope is low
                if spike and slope <= 0:
                    seconds_to_hit = interval_secs * 3
                else:
                    steps_to_threshold = (threshold - last_smooth) / slope if slope > 0 else 9999
                    seconds_to_hit = steps_to_threshold * interval_secs

                if seconds_to_hit > 7200:
                    continue  # beyond 2-hour horizon

                predicted_at = _now() + timedelta(seconds=seconds_to_hit)
                conf = _confidence(slope, variance, seconds_to_hit)
                severity = "critical" if seconds_to_hit < 900 else "warning"

                signals = [
                    f"{metric} at {last_raw:.1f}% (smoothed {last_smooth:.1f}%, threshold {threshold}%)",
                    f"Trend slope: {slope:+.3f}%/sample over {n} samples",
                    f"Sample interval: ~{int(interval_secs)}s",
                    f"Variance: {variance:.1f} ({'noisy' if variance > 25 else 'stable'} signal)",
                ]
                if spike:
                    signals.insert(0, f"SPIKE DETECTED: {last_raw:.1f}% > mean+2σ")

                predictions.append({
                    "name":          name,
                    "metric":        metric,
                    "severity":      severity,
                    "predicted_at":  _utc_iso(predicted_at),
                    "confidence":    conf,
                    "current_value": round(last_raw, 1),
                    "threshold":     threshold,
                    "slope_per_sample": round(slope, 3),
                    "reason":        (
                        f"{name}: smoothed value {last_smooth:.1f}% rising at "
                        f"{slope:+.2f}%/sample. Projected to breach {threshold}% in "
                        f"~{int(seconds_to_hit // 60)}m {int(seconds_to_hit % 60)}s. "
                        f"Confidence {int(conf * 100)}% (variance {variance:.1f})."
                    ),
                    "contributing_signals": signals,
                    "spike_detected": spike,
                    "variance":       round(variance, 2),
                })

        _validate_list(predictions, "predictions")
        return {"predictions": predictions}

    # ── 4. Circuit breaker status ─────────────────────────────────────────────

    @router.get("/remediation/circuit-breaker/status")
    async def circuit_breaker_status(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        payload = await _require_token(request)
        org_id  = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        window_start = _now() - timedelta(minutes=CB_WINDOW_MINUTES)

        result = await db.execute(
            select(RemediationRecord)
            .where(
                RemediationRecord.org_id == org_id,
                RemediationRecord.created_at >= window_start,
            )
            .order_by(desc(RemediationRecord.created_at))
        )
        recent = result.scalars().all()

        # Group by action (proxy for component)
        by_action: dict[str, list[RemediationRecord]] = defaultdict(list)
        for r in recent:
            by_action[r.action].append(r)

        breakers = []
        for action, records in by_action.items():
            failures = [r for r in records if r.status == "failed"]
            successes = [r for r in records if r.status == "success"]
            failure_count = len(failures)
            last_failure = failures[0].created_at if failures else None
            last_success = successes[0].created_at if successes else None

            # Determine state
            manual_reset = _circuit_breaker_resets.get(f"{org_id}:{action}")
            if manual_reset and last_failure and manual_reset > last_failure:
                state = "CLOSED"
            elif failure_count >= CB_FAILURE_THRESHOLD:
                if last_failure:
                    mins_since_trip = (_now() - last_failure).total_seconds() / 60
                    state = "HALF_OPEN" if mins_since_trip >= CB_TIMEOUT_MINUTES else "OPEN"
                else:
                    state = "OPEN"
            else:
                state = "CLOSED"

            if state != "CLOSED" or failure_count > 0:
                breakers.append({
                    "component":      action,
                    "service":        (records[0].params or {}).get("service", "remediation-engine"),
                    "state":          state,
                    "failure_count":  failure_count,
                    "threshold":      CB_FAILURE_THRESHOLD,
                    "opened_at":      _utc_iso(last_failure),
                    "last_success_at": _utc_iso(last_success),
                    "timeout_ms":     CB_TIMEOUT_MINUTES * 60 * 1000,
                })

        _validate_list(breakers, "circuit breakers")
        return {"breakers": breakers}

    @router.post("/remediation/circuit-breaker/{component}/reset")
    async def circuit_breaker_reset(
        component: str,
        request: Request,
    ) -> dict[str, Any]:
        payload = await _require_token(request)
        role    = payload.get("role", "employee")
        org_id  = payload.get("org_id")
        if role not in ("admin", "devops"):
            raise HTTPException(status_code=403, detail="Admin or DevOps role required")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        key = f"{org_id}:{component}"
        _circuit_breaker_resets[key] = _now()
        return {
            "component": component,
            "state":     "CLOSED",
            "reset_at":  _utc_iso(_now()),
        }

    # ── 5. API key usage heatmap ──────────────────────────────────────────────

    @router.get("/api-keys/usage-heatmap")
    async def api_key_heatmap(
        request: Request,
        hours: int = 24,
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        payload = await _require_token(request)
        org_id  = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        since = _now() - timedelta(hours=hours)

        # Use agents as proxy for API keys (each agent has a unique key_hash)
        agents_result = await db.execute(
            select(Agent).where(Agent.org_id == org_id, Agent.is_active == True)
        )
        agents = agents_result.scalars().all()

        keys_data = []
        for agent in agents:
            # Get metric snapshots bucketed by hour
            snaps_result = await db.execute(
                select(MetricSnapshot)
                .where(
                    MetricSnapshot.org_id == org_id,
                    MetricSnapshot.agent_id == agent.id,
                    MetricSnapshot.timestamp >= since,
                )
                .order_by(MetricSnapshot.timestamp)
            )
            snaps = snaps_result.scalars().all()

            # Bucket by hour-of-day
            hourly: dict[int, dict[str, Any]] = {}
            for snap in snaps:
                h = snap.timestamp.hour if snap.timestamp else 0
                bucket = hourly.setdefault(h, {"requests": 0, "errors": 0, "p95_ms": None})
                bucket["requests"] += 1
                # Use high CPU as a proxy for error conditions (heuristic)
                if snap.cpu > 90:
                    bucket["errors"] += 1

            # Compute error_rate for each bucket
            data: dict[str, Any] = {}
            for h, bucket in hourly.items():
                req = bucket["requests"]
                err = bucket["errors"]
                data[str(h)] = {
                    "requests":   req,
                    "errors":     err,
                    "error_rate": round((err / req) * 100, 2) if req else 0,
                    "p95_ms":     None,
                }

            if data:
                keys_data.append({
                    "key_id":    agent.id,
                    "key_label": agent.label or f"agent-{agent.id[:8]}",
                    "data":      data,
                })

        _validate_list(keys_data, "api-key heatmap")
        return {"keys": keys_data}

    # ── 6. Incidents (DB-backed, full audit trail) ───────────────────────────

    def _serialize_incident(inc: Incident) -> dict[str, Any]:
        return {
            "id":          inc.id,
            "severity":    inc.severity,
            "service":     inc.service,
            "description": inc.description,
            "commander":   inc.commander,
            "declared_by": inc.declared_by,
            "declared_at": _utc_iso(inc.declared_at),
            "resolved_at": _utc_iso(inc.resolved_at),
            "resolved_by": inc.resolved_by,
            "status":      inc.status,
            "timeline":    inc.timeline or [],
        }

    @router.post("/incidents", status_code=status.HTTP_201_CREATED)
    async def create_incident(
        body: IncidentCreate,
        request: Request,
        db: AsyncSession = Depends(get_db),
        _rbac: dict = require_role("admin", "devops"),
    ) -> dict[str, Any]:
        payload = await _require_token(request)
        org_id  = payload.get("org_id")
        user_id = payload.get("sub")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        # Reject if active incident already exists for this org
        existing = await db.execute(
            select(Incident)
            .where(Incident.org_id == org_id, Incident.status == "active")
            .limit(1)
        )
        active = existing.scalar_one_or_none()
        if active:
            raise HTTPException(
                status_code=409,
                detail=f"Active incident {active.id} already exists. Resolve it first.",
            )

        now = _now()
        incident_id = f"INC-{now.strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
        timeline_entry = {"ts": _utc_iso(now), "actor": user_id, "note": "Incident declared"}

        incident = Incident(
            id=incident_id,
            org_id=org_id,
            severity=body.severity,
            service=body.service,
            description=body.description,
            commander=body.commander,
            declared_by=user_id,
            status="active",
            timeline=[timeline_entry],
        )
        db.add(incident)
        await db.commit()
        await db.refresh(incident)

        serialized = _serialize_incident(incident)
        try:
            _get_realtime_hub(request).publish("incident_update", serialized, org_id)
        except Exception:
            pass

        return serialized

    @router.get("/incidents/active")
    async def get_active_incident(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        payload = await _require_token(request)
        org_id  = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        result = await db.execute(
            select(Incident)
            .where(Incident.org_id == org_id, Incident.status == "active")
            .order_by(desc(Incident.declared_at))
            .limit(1)
        )
        incident = result.scalar_one_or_none()
        if incident is None:
            raise HTTPException(status_code=404, detail="No active incident")
        return _serialize_incident(incident)

    @router.post("/incidents/{incident_id}/resolve")
    async def resolve_incident(
        incident_id: str,
        request: Request,
        db: AsyncSession = Depends(get_db),
        _rbac: dict = require_role("admin", "devops"),
    ) -> dict[str, Any]:
        payload = await _require_token(request)
        org_id  = payload.get("org_id")
        user_id = payload.get("sub")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        result = await db.execute(
            select(Incident).where(Incident.id == incident_id, Incident.org_id == org_id)
        )
        incident = result.scalar_one_or_none()
        if incident is None:
            raise HTTPException(status_code=404, detail="Incident not found")
        if incident.status != "active":
            raise HTTPException(status_code=409, detail="Incident is already resolved")

        now = _now()
        timeline = list(incident.timeline or [])
        timeline.append({"ts": _utc_iso(now), "actor": user_id, "note": "Incident resolved"})

        incident.status      = "resolved"
        incident.resolved_at = now
        incident.resolved_by = user_id
        incident.timeline    = timeline
        await db.commit()
        await db.refresh(incident)

        serialized = _serialize_incident(incident)
        try:
            _get_realtime_hub(request).publish("incident_update", serialized, org_id)
        except Exception:
            pass

        return serialized

    return router
