"""
logs_api.py — Log ingestion endpoints.

Routes:
  POST /agents/{agent_id}/logs    — ingest a batch of log lines from an agent
  GET  /agents/{agent_id}/logs    — retrieve recent log lines (debug/review)
  DELETE /agents/{agent_id}/logs  — purge all logs for an agent (admin)

Agents (desktop_agent or remote) POST structured log batches here.
Logs are stored in log_entries and used by log_collector.py during investigations.

Retention: enforced per-write via _prune_old_logs() — keeps last 500 lines per
agent and drops lines older than 7 days.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import asc, delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Agent, LogEntry, Organization, get_db

router = APIRouter(tags=["logs"])
_log = logging.getLogger(__name__)

_MAX_LINES_PER_AGENT = 500
_LOG_TTL_DAYS        = 7
_INGEST_BATCH_LIMIT  = 200   # max lines accepted per POST


# ── Auth helper ───────────────────────────────────────────────────────────────

async def _require_token(request: Request) -> dict[str, Any]:
    from jose import JWTError, jwt
    import os
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    try:
        return jwt.decode(
            auth[7:],
            os.getenv("JWT_SECRET_KEY", ""),
            algorithms=["HS256"],
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


# ── Retention helper ──────────────────────────────────────────────────────────

async def _prune_old_logs(db: AsyncSession, agent_id: str) -> None:
    """
    Keep only the most recent _MAX_LINES_PER_AGENT lines for this agent,
    and drop anything older than _LOG_TTL_DAYS.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=_LOG_TTL_DAYS)

    # Delete by TTL first (cheap)
    await db.execute(
        delete(LogEntry)
        .where(LogEntry.agent_id == agent_id)
        .where(LogEntry.collected_at < cutoff)
    )

    # Count remaining
    count_result = await db.execute(
        select(func.count()).where(LogEntry.agent_id == agent_id)
    )
    total = count_result.scalar() or 0

    if total > _MAX_LINES_PER_AGENT:
        # Find the (total - MAX) oldest IDs to delete
        excess = total - _MAX_LINES_PER_AGENT
        oldest_result = await db.execute(
            select(LogEntry.id)
            .where(LogEntry.agent_id == agent_id)
            .order_by(asc(LogEntry.collected_at))
            .limit(excess)
        )
        old_ids = [row[0] for row in oldest_result.fetchall()]
        if old_ids:
            await db.execute(
                delete(LogEntry).where(LogEntry.id.in_(old_ids))
            )


# ── POST /agents/{agent_id}/logs ──────────────────────────────────────────────

@router.post("/agents/{agent_id}/logs", status_code=201)
async def ingest_logs(
    agent_id: str,
    body: dict[str, Any],
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Ingest a batch of log lines from an agent.

    Body:
      alert_id  : str | null  — associate logs with a specific alert
      lines     : list[{
        source   : str              — syslog|journald|app|windows_event
        level    : str              — ERROR|WARN|INFO|DEBUG
        message  : str              — parsed log message
        raw_line : str | null       — original unparsed line
        log_ts   : ISO8601 | null   — original log timestamp
      }]
    """
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")
    if not org_id:
        raise HTTPException(status_code=403, detail="No org_id in token")

    # Verify agent belongs to org
    agent_result = await db.execute(
        select(Agent)
        .where(Agent.id == agent_id)
        .where(Agent.org_id == org_id)
    )
    if agent_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    lines = body.get("lines") or []
    if not lines:
        return {"ok": True, "stored": 0, "message": "no lines provided"}

    alert_id: str | None = body.get("alert_id")
    now = datetime.now(timezone.utc)
    stored = 0

    for item in lines[:_INGEST_BATCH_LIMIT]:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or item.get("raw_line") or "").strip()
        if not message:
            continue

        # Parse log_ts if provided
        log_ts: datetime | None = None
        ts_str = item.get("log_ts")
        if ts_str:
            try:
                log_ts = datetime.fromisoformat(str(ts_str))
                if log_ts.tzinfo is None:
                    log_ts = log_ts.replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        entry = LogEntry(
            id=str(uuid.uuid4()),
            org_id=org_id,
            agent_id=agent_id,
            alert_id=alert_id,
            source=str(item.get("source") or "app")[:100],
            level=str(item.get("level") or "INFO").upper()[:20],
            message=message[:4000],
            raw_line=str(item.get("raw_line") or "")[:4000] or None,
            collected_at=now,
            log_ts=log_ts,
        )
        db.add(entry)
        stored += 1

    await db.flush()
    await _prune_old_logs(db, agent_id)
    await db.commit()

    _log.info("[LOGS] Ingested %d lines for agent=%s alert=%s", stored, agent_id[:8], alert_id)
    return {"ok": True, "stored": stored, "agent_id": agent_id}


# ── GET /agents/{agent_id}/logs ───────────────────────────────────────────────

@router.get("/agents/{agent_id}/logs")
async def get_agent_logs(
    agent_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    level: str | None = Query(default=None, description="Filter: ERROR|WARN|INFO|DEBUG"),
    alert_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Retrieve recent log lines for an agent (for dashboard review)."""
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")
    if not org_id:
        raise HTTPException(status_code=403, detail="No org_id in token")

    q = (
        select(LogEntry)
        .where(LogEntry.agent_id == agent_id)
        .where(LogEntry.org_id  == org_id)
    )
    if level:
        q = q.where(LogEntry.level == level.upper())
    if alert_id:
        q = q.where(LogEntry.alert_id == alert_id)

    q = q.order_by(desc(LogEntry.collected_at)).limit(limit)
    result = await db.execute(q)
    rows = result.scalars().all()

    return {
        "ok":       True,
        "agent_id": agent_id,
        "count":    len(rows),
        "lines": [
            {
                "id":           e.id,
                "source":       e.source,
                "level":        e.level,
                "message":      e.message,
                "log_ts":       e.log_ts.isoformat() if e.log_ts else None,
                "collected_at": e.collected_at.isoformat() if e.collected_at else None,
                "alert_id":     e.alert_id,
            }
            for e in rows
        ],
    }


# ── DELETE /agents/{agent_id}/logs ────────────────────────────────────────────

@router.delete("/agents/{agent_id}/logs", status_code=200)
async def purge_agent_logs(
    agent_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Purge all stored logs for an agent. Admin-only."""
    payload = await _require_token(request)
    org_id: str = payload.get("org_id", "")
    role:   str = payload.get("role", "")
    if not org_id or role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Admin required")

    await db.execute(
        delete(LogEntry)
        .where(LogEntry.agent_id == agent_id)
        .where(LogEntry.org_id   == org_id)
    )
    await db.commit()
    _log.info("[LOGS] Purged all logs for agent=%s by=%s", agent_id[:8], payload.get("sub"))
    return {"ok": True, "agent_id": agent_id, "purged": True}
