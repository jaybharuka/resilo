"""
investigations_api.py — REST endpoints for the investigation engine.

Routes:
  GET  /investigations                     — list recent investigations for the org
  GET  /investigations/{id}               — get single investigation with full detail
  GET  /incidents/{incident_id}/timeline  — structured timeline for an incident
  GET  /incidents/{incident_id}/similar   — similar historical incidents from memory
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.incident_memory import find_similar_incidents
from app.core.database import (
    Incident, IncidentMemory, Investigation, get_db,
)

router = APIRouter(tags=["investigations"])
_log = logging.getLogger(__name__)


# ── Auth helper (mirrors pattern in runtime.py / v1_api.py) ──────────────────

async def _require_token(request: Request) -> dict[str, Any]:
    """Extract and validate the JWT Bearer token from Authorization header."""
    from jose import JWTError, jwt as _jwt
    import os

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth[7:]
    secret = os.getenv("JWT_SECRET_KEY", "")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT_SECRET_KEY not configured")
    try:
        payload = _jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc


def _inv_to_dict(inv: Investigation) -> dict[str, Any]:
    return {
        "id":                 inv.id,
        "org_id":             inv.org_id,
        "agent_id":           inv.agent_id,
        "alert_id":           inv.alert_id,
        "incident_id":        inv.incident_id,
        "status":             inv.status,
        "stage":              inv.stage,
        "confidence":         inv.confidence,
        "recommended_action": inv.recommended_action,
        "action_routing":     inv.action_routing,
        "evidence":           inv.evidence,
        "similar_incidents":  inv.similar_incidents,
        "hypotheses":         inv.hypotheses,
        "root_cause":         inv.root_cause,
        "timeline":           inv.timeline,
        "created_at":         inv.created_at.isoformat() if inv.created_at else None,
        "completed_at":       inv.completed_at.isoformat() if inv.completed_at else None,
    }


# ── GET /investigations ───────────────────────────────────────────────────────

@router.get("/investigations")
async def list_investigations(
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, description="Filter: running|completed|failed"),
    agent_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """List recent investigations for the authenticated org."""
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")
    if not org_id:
        raise HTTPException(status_code=403, detail="No org_id in token")

    q = select(Investigation).where(Investigation.org_id == org_id)
    if status:
        q = q.where(Investigation.status == status)
    if agent_id:
        q = q.where(Investigation.agent_id == agent_id)
    q = q.order_by(desc(Investigation.created_at)).limit(limit)

    result = await db.execute(q)
    investigations = result.scalars().all()

    return {
        "ok":    True,
        "count": len(investigations),
        "items": [_inv_to_dict(inv) for inv in investigations],
    }


# ── GET /investigations/{id} ──────────────────────────────────────────────────

@router.get("/investigations/{investigation_id}")
async def get_investigation(
    investigation_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return a single investigation with all stage outputs."""
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")

    result = await db.execute(
        select(Investigation)
        .where(Investigation.id == investigation_id)
        .where(Investigation.org_id == org_id)
    )
    inv = result.scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    return {"ok": True, "investigation": _inv_to_dict(inv)}


# ── GET /incidents/{incident_id}/timeline ─────────────────────────────────────

@router.get("/incidents/{incident_id}/timeline")
async def get_incident_timeline(
    incident_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Return the structured AI investigation timeline for an incident.

    Merges the incident's own timeline with any linked investigation timelines
    for a complete end-to-end event log.
    """
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")

    # Fetch the parent incident
    inc_result = await db.execute(
        select(Incident)
        .where(Incident.id == incident_id)
        .where(Incident.org_id == org_id)
    )
    incident = inc_result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Fetch linked investigations
    inv_result = await db.execute(
        select(Investigation)
        .where(Investigation.incident_id == incident_id)
        .where(Investigation.org_id == org_id)
        .order_by(Investigation.created_at)
    )
    investigations = inv_result.scalars().all()

    # Merge and sort all timeline events by timestamp
    merged: list[dict] = []

    for entry in (incident.timeline or []):
        merged.append({
            "timestamp": entry.get("ts") or entry.get("timestamp", ""),
            "source":    "incident",
            "actor":     entry.get("actor", "system"),
            "event":     entry.get("note") or entry.get("event", ""),
            "data":      entry.get("data"),
        })

    for inv in investigations:
        for entry in (inv.timeline or []):
            merged.append({
                "timestamp":        entry.get("timestamp", ""),
                "source":           "investigation",
                "investigation_id": inv.id,
                "stage":            entry.get("stage", ""),
                "event":            entry.get("event", ""),
            })

    merged.sort(key=lambda e: e.get("timestamp", ""))

    return {
        "ok":             True,
        "incident_id":    incident_id,
        "incident_status": incident.status,
        "event_count":    len(merged),
        "timeline":       merged,
    }


# ── GET /incidents/{incident_id}/similar ──────────────────────────────────────

@router.get("/incidents/{incident_id}/similar")
async def get_similar_incidents(
    incident_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=5, ge=1, le=20),
) -> dict[str, Any]:
    """
    Find historically similar incidents from the knowledge base
    for a given incident.
    """
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")

    inc_result = await db.execute(
        select(Incident)
        .where(Incident.id == incident_id)
        .where(Incident.org_id == org_id)
    )
    incident = inc_result.scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    # Pull metrics from the linked investigation if available
    metrics: dict = {}
    inv_result = await db.execute(
        select(Investigation)
        .where(Investigation.incident_id == incident_id)
        .where(Investigation.org_id == org_id)
        .order_by(desc(Investigation.created_at))
        .limit(1)
    )
    inv = inv_result.scalar_one_or_none()
    if inv and inv.evidence:
        ev = inv.evidence
        metrics = {
            "cpu":    ev.get("cpu", 0),
            "memory": ev.get("memory", 0),
            "disk":   ev.get("disk", 0),
        }
        category = ev.get("incident_type", "cpu")
    else:
        category = "fleet"

    similar = await find_similar_incidents(
        db,
        org_id=org_id,
        category=category,
        severity=incident.severity,
        metrics=metrics,
        root_cause_hint=incident.description,
        limit=limit,
    )

    return {
        "ok":          True,
        "incident_id": incident_id,
        "count":       len(similar),
        "similar":     similar,
    }
