"""
core_api.py — AIOps Bot Unified Core API (FastAPI, port 8000)

Consolidates agent management, metrics, alerts, and remediation into one
multi-tenant FastAPI service. Replaces the scattered Flask endpoints over time.

Architecture:
    Nginx (443) → core_api (8000)
    Nginx (443) → auth_api (5001)
    Flask (5000) → legacy (deprecated, being migrated here)

Start:
    uvicorn core_api:app --host 0.0.0.0 --port 8000 --reload

Environment variables:
    DATABASE_URL        postgresql+asyncpg://aiops:aiops@localhost:5432/aiops
    JWT_SECRET_KEY      same secret as auth_api.py
    ANOMALY_AUTONOMOUS  "org"|"true"|"false"  (default: org)
    ANOMALY_POLL_INTERVAL  seconds (default: 30)
"""

import sys as _sys
import os

# Ensure all app sub-packages are importable regardless of working directory
_here = os.path.dirname(os.path.abspath(__file__))   # app/api
_app  = os.path.dirname(_here)                        # app/
_root = os.path.dirname(_app)                         # repo root
for _p in [_here, _app, _root,
           os.path.join(_app, 'core'),
           os.path.join(_app, 'auth'),
           os.path.join(_app, 'analytics'),
           os.path.join(_app, 'integrations')]:
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

import sys as _sys2
if _app not in _sys2.path:
    _sys2.path.insert(0, _app)
from secret_config import validate_secrets
validate_secrets("JWT_SECRET_KEY")

import asyncio
import hashlib
import logging
import secrets
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any

import bcrypt
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from pythonjsonlogger import jsonlogger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import select, func as sqlfunc, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    init_db, get_db, SessionLocal,
    Organization, User, Agent, MetricSnapshot,
    AlertRecord, RemediationRecord, AuditLog,
    NotificationChannel, AlertRule, NotificationLog, WMITarget, WmiInvite,
)
from rbac import (
    TokenPayload, get_token_payload, get_current_user,
    require_permission, require, get_agent_from_key, generate_agent_key,
)
from anomaly_engine import start_anomaly_engine, start_daily_summary_scheduler

# ── Structured JSON logging ───────────────────────────────────────────────────

_handler = logging.StreamHandler()
_handler.setFormatter(jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
))
logging.root.handlers = [_handler]
logging.root.setLevel(logging.INFO)
log = logging.getLogger("core_api")

# ── Rate limiter ──────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="AIOps Core API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
# Wildcard origins with allow_credentials=True is a critical misconfiguration —
# it allows any site on the internet to make authenticated requests on behalf
# of your logged-in users (session riding / credential theft).
# ALLOWED_ORIGINS must be a comma-separated list of your actual frontend URLs.
_CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:3001,http://localhost:3000,http://127.0.0.1:3001,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)


# ── Request logging middleware ────────────────────────────────────────────────

@app.middleware("http")
async def _log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    latency = round((time.perf_counter() - start) * 1000, 1)
    log.info(
        "HTTP %s %s",
        request.method,
        request.url.path,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": latency,
            "ip": request.client.host if request.client else "unknown",
        },
    )
    return response


# ── Startup / Shutdown ────────────────────────────────────────────────────────

@app.on_event("startup")
async def _startup():
    await init_db()
    await _seed_default_org()
    asyncio.create_task(start_anomaly_engine())
    asyncio.create_task(start_daily_summary_scheduler())
    asyncio.create_task(_local_metrics_loop())
    asyncio.create_task(_wmi_polling_loop())
    log.info("Core API started")


# ── Local machine metrics collector ──────────────────────────────────────────
# Registers this server as a built-in agent in the default org and stores
# live psutil metrics so all org members can see them without deploying an agent.

_LOCAL_AGENT_LABEL = "local-server"

# ── SSE config & fan-out ──────────────────────────────────────────────────────
# Each connected /stream/metrics client registers its own asyncio.Queue here.
# _local_metrics_loop puts snapshots into every queue so the SSE stream is
# driven by real data events rather than an independent sleep timer.
SSE_HEARTBEAT_SECONDS: int = int(os.getenv("SSE_HEARTBEAT_SECONDS", "30"))
_metrics_subscribers: set[asyncio.Queue] = set()

async def _get_or_create_local_agent(db: AsyncSession, org_id: str) -> Agent:
    """Return the built-in local-server agent for the given org, creating it if needed."""
    import socket
    from rbac import generate_agent_key
    result = await db.execute(
        select(Agent).where(Agent.org_id == org_id, Agent.label == _LOCAL_AGENT_LABEL)
    )
    agent = result.scalar_one_or_none()
    if agent:
        return agent
    raw_key, key_hash = generate_agent_key()
    agent = Agent(
        id=str(uuid.uuid4()),
        org_id=org_id,
        label=_LOCAL_AGENT_LABEL,
        key_hash=key_hash,
        status="live",
        pending_cmds=[],
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    log.info("Local-server agent registered (org=%s, agent=%s)", org_id, agent.id)
    return agent


async def _collect_local_metrics() -> dict:
    """Read live metrics from psutil (runs in thread-pool to avoid blocking)."""
    import asyncio, socket
    loop = asyncio.get_event_loop()

    def _read():
        import psutil, time
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk_parts = psutil.disk_partitions()
        total_disk = used_disk = 0
        for p in disk_parts:
            try:
                u = psutil.disk_usage(p.mountpoint)
                total_disk += u.total
                used_disk += u.used
            except Exception:
                pass
        disk_pct = round(used_disk / total_disk * 100, 1) if total_disk else 0
        net = psutil.net_io_counters()
        try:
            temps = psutil.sensors_temperatures() or {}
            flat = [t.current for lst in temps.values() for t in lst]
            temperature = round(sum(flat) / len(flat), 1) if flat else None
        except Exception:
            temperature = None
        try:
            load = psutil.getloadavg()
            load_avg = round(load[0], 2)
        except Exception:
            load_avg = None
        boot = psutil.boot_time()
        uptime_secs = int(time.time() - boot)
        return {
            "cpu": round(cpu, 1),
            "memory": round(mem.percent, 1),
            "memory_used": mem.used,
            "memory_total": mem.total,
            "disk": disk_pct,
            "network_in": round(net.bytes_recv / (1024 * 1024), 2),
            "network_out": round(net.bytes_sent / (1024 * 1024), 2),
            "temperature": temperature,
            "load_avg": load_avg,
            "processes": len(psutil.pids()),
            "uptime_secs": uptime_secs,
        }

    return await loop.run_in_executor(None, _read)


async def _local_metrics_loop():
    """Every 30 s: collect psutil metrics and store as MetricSnapshot for every org."""
    import socket
    hostname = socket.gethostname()
    interval = int(os.getenv("ANOMALY_POLL_INTERVAL", "30"))
    await asyncio.sleep(2)  # let the DB settle on first startup
    while True:
        try:
            metrics = await _collect_local_metrics()
            async with SessionLocal() as db:
                # Find all orgs
                orgs_result = await db.execute(select(Organization).where(Organization.is_active == True))
                orgs = orgs_result.scalars().all()
                for org in orgs:
                    agent = await _get_or_create_local_agent(db, org.id)
                    # network_in/out stored as bytes (BigInteger) — convert from MB float
                    net_in_mb  = metrics.get("network_in")  or 0.0
                    net_out_mb = metrics.get("network_out") or 0.0
                    load       = metrics.get("load_avg")
                    snap = MetricSnapshot(
                        org_id=org.id,
                        agent_id=agent.id,
                        timestamp=datetime.now(timezone.utc),
                        cpu=metrics["cpu"],
                        memory=metrics["memory"],
                        disk=metrics["disk"],
                        network_in=int(net_in_mb * 1024 * 1024),
                        network_out=int(net_out_mb * 1024 * 1024),
                        temperature=metrics.get("temperature"),
                        load_avg=str(load) if load is not None else None,
                        processes=metrics.get("processes"),
                        uptime_secs=metrics.get("uptime_secs"),
                        extra={"hostname": hostname, "source": "local"},
                    )
                    db.add(snap)
                    # Keep agent status live
                    agent.status = "live"
                    agent.last_seen = datetime.now(timezone.utc)
                await db.commit()

                # Fan-out fresh metrics to all connected SSE /stream/metrics clients.
                # Uses put_nowait so a slow consumer never blocks the collection loop.
                if _metrics_subscribers:
                    import json as _json
                    snap_payload = {
                        "org_id":      org.id,
                        "agent_id":    agent.id,
                        "timestamp":   datetime.now(timezone.utc).isoformat(),
                        "cpu":         metrics["cpu"],
                        "memory":      metrics["memory"],
                        "disk":        metrics["disk"],
                        "network_in":  metrics.get("network_in", 0),
                        "network_out": metrics.get("network_out", 0),
                        "temperature": metrics.get("temperature"),
                        "processes":   metrics.get("processes"),
                        "uptime_secs": metrics.get("uptime_secs"),
                    }
                    dead: set[asyncio.Queue] = set()
                    for _q in _metrics_subscribers:
                        try:
                            _q.put_nowait(snap_payload)
                        except asyncio.QueueFull:
                            dead.add(_q)   # evict unresponsive consumer
                    _metrics_subscribers.difference_update(dead)

        except Exception as exc:
            log.error("Local metrics collection failed: %s", exc)
        await asyncio.sleep(interval)


async def _seed_default_org():
    """Ensure a 'Default' org exists and all existing users are assigned to it."""
    async with SessionLocal() as db:
        # Check if any org exists
        result = await db.execute(select(sqlfunc.count()).select_from(Organization))
        if result.scalar() > 0:
            # Still migrate any users / invites that slipped through without org_id
            orgs_result = await db.execute(select(Organization).limit(1))
            first_org = orgs_result.scalar_one_or_none()
            if first_org:
                await db.execute(
                    __import__("sqlalchemy").text(
                        f"UPDATE users SET org_id = '{first_org.id}' WHERE org_id IS NULL"
                    )
                )
                await db.execute(
                    __import__("sqlalchemy").text(
                        f"UPDATE invite_tokens SET org_id = '{first_org.id}' WHERE org_id IS NULL"
                    )
                )
                await db.commit()
            return

        org = Organization(
            id=str(uuid.uuid4()),
            name="Default Organization",
            slug="default",
            plan="enterprise",
            settings={"autonomous_mode": False},
        )
        db.add(org)
        await db.flush()

        # Assign all existing users to this org (migration for users created before orgs)
        await db.execute(
            __import__("sqlalchemy").text(
                f"UPDATE users SET org_id = '{org.id}' WHERE org_id IS NULL"
            )
        )
        # Also set invite tokens org_id
        await db.execute(
            __import__("sqlalchemy").text(
                f"UPDATE invite_tokens SET org_id = '{org.id}' WHERE org_id IS NULL"
            )
        )
        await db.commit()
        log.info("Default organization seeded (id=%s)", org.id)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "core-api", "version": "1.0.0"}


@app.get("/api/dashboard-snapshot")
async def dashboard_snapshot(
    token: TokenPayload = Depends(require_permission("metrics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated system snapshot for the authenticated user's org.

    Priority:
      1. User's local psutil agent (browser-{user_id[:8]} with source=local-agent, fresh <60s)
      2. Server's psutil agent (local-server) — always running, real data
      3. Average across all agents (last resort)
    """
    org_id  = token.org_id
    user_id = token.sub

    # Resolve org_id from DB when JWT pre-dates org support
    if not org_id:
        u_res = await db.execute(select(User).where(User.id == user_id))
        u_obj = u_res.scalar_one_or_none()
        if u_obj:
            org_id = u_obj.org_id
    if not org_id:
        return {
            "cpu": 0, "memory": 0, "disk": 0, "network_in": 0, "network_out": 0,
            "status": "no_org", "temperature": None, "uptime_secs": None,
            "processes": None, "agents_count": 0, "open_alerts": 0,
            "last_updated": datetime.now(timezone.utc).isoformat(), "source": "core-api",
        }

    # Shared counts used in every response path
    agents_count = (await db.execute(
        select(sqlfunc.count()).select_from(Agent).where(Agent.org_id == org_id)
    )).scalar() or 0
    open_alerts = (await db.execute(
        select(sqlfunc.count()).select_from(AlertRecord).where(
            AlertRecord.org_id == org_id, AlertRecord.status == "open"
        )
    )).scalar() or 0

    now_utc = datetime.now(timezone.utc)

    def _age(snap):
        ts = snap.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (now_utc - ts).total_seconds()

    def _build(s, src=None):
        cpu, mem, disk = s.cpu or 0, s.memory or 0, s.disk or 0
        st = "healthy"
        if cpu > 90 or mem > 90 or disk > 90:
            st = "critical"
        elif cpu > 75 or mem > 80 or disk > 80:
            st = "warning"
        source = src or ((s.extra or {}).get("source", "server") if s.extra else "server")
        return {
            "cpu":          round(cpu, 1),
            "memory":       round(mem, 1),
            "disk":         round(disk, 1) if disk else None,
            "network_in":   round((s.network_in  or 0) / (1024 * 1024), 2),
            "network_out":  round((s.network_out or 0) / (1024 * 1024), 2),
            "status":       st,
            "temperature":  s.temperature,
            "uptime_secs":  s.uptime_secs,
            "processes":    s.processes,
            "agents_count": agents_count,
            "open_alerts":  open_alerts,
            "last_updated": s.timestamp.isoformat(),
            "source":       source,
        }

    async def _latest_snap(agent_id):
        r = await db.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.org_id == org_id, MetricSnapshot.agent_id == agent_id)
            .order_by(desc(MetricSnapshot.timestamp))
            .limit(1)
        )
        return r.scalar_one_or_none()

    # ── Priority 1: user's real local psutil agent (local_agent.py) ──────────
    browser_label = f"browser-{user_id[:8]}"
    ba_res = await db.execute(
        select(Agent).where(Agent.org_id == org_id, Agent.label == browser_label)
    )
    browser_agent = ba_res.scalar_one_or_none()
    browser_snap = None
    if browser_agent:
        browser_snap = await _latest_snap(browser_agent.id)
        if browser_snap and _age(browser_snap) < 60:
            source = (browser_snap.extra or {}).get("source", "browser") if browser_snap.extra else "browser"
            if source == "local-agent":
                # Full real psutil data from user's machine — use directly
                return _build(browser_snap)

    # ── Priority 2: server psutil (always running) ────────────────────────────
    sa_res = await db.execute(
        select(Agent).where(Agent.org_id == org_id, Agent.label == "local-server")
    )
    server_agent = sa_res.scalar_one_or_none()
    server_snap = None
    if server_agent:
        server_snap = await _latest_snap(server_agent.id)

    # ── Merge: server as baseline + override with any fresh browser values ────
    # Browser API gives partial data (cpu estimate, memory on Chrome).
    # Server gives full psutil. Combine: prefer non-zero browser values.
    if server_snap:
        base = server_snap
        if browser_snap and _age(browser_snap) < 60:
            cpu  = (browser_snap.cpu    or 0) if (browser_snap.cpu    and browser_snap.cpu    > 0) else (base.cpu    or 0)
            mem  = (browser_snap.memory or 0) if (browser_snap.memory and browser_snap.memory > 0) else (base.memory or 0)
            disk = base.disk
            net_in, net_out = base.network_in, base.network_out
            temp, uptime, procs = base.temperature, base.uptime_secs, base.processes
            ts  = browser_snap.timestamp
            src = (browser_snap.extra or {}).get("source", "browser") if browser_snap.extra else "browser"
        else:
            cpu, mem, disk = base.cpu or 0, base.memory or 0, base.disk or 0
            net_in, net_out = base.network_in, base.network_out
            temp, uptime, procs, ts, src = base.temperature, base.uptime_secs, base.processes, base.timestamp, "server"
        st = "healthy"
        if cpu > 90 or mem > 90 or (disk or 0) > 90:   st = "critical"
        elif cpu > 75 or mem > 80 or (disk or 0) > 80: st = "warning"
        return {
            "cpu":          round(cpu, 1),
            "memory":       round(mem, 1),
            "disk":         round(disk, 1) if disk else None,
            "network_in":   round((net_in  or 0) / (1024 * 1024), 2),
            "network_out":  round((net_out or 0) / (1024 * 1024), 2),
            "status":       st,
            "temperature":  temp,
            "uptime_secs":  uptime,
            "processes":    procs,
            "agents_count": agents_count,
            "open_alerts":  open_alerts,
            "last_updated": ts.isoformat() if ts else datetime.now(timezone.utc).isoformat(),
            "source":       src,
        }

    # ── Priority 3: average across all agents ────────────────────────────────
    sub = (
        select(MetricSnapshot.agent_id, sqlfunc.max(MetricSnapshot.timestamp).label("max_ts"))
        .where(MetricSnapshot.org_id == org_id)
        .group_by(MetricSnapshot.agent_id)
        .subquery()
    )
    snapshots = (await db.execute(
        select(MetricSnapshot).join(
            sub,
            (MetricSnapshot.agent_id == sub.c.agent_id)
            & (MetricSnapshot.timestamp == sub.c.max_ts),
        )
    )).scalars().all()

    if not snapshots:
        return {
            "cpu": 0, "memory": 0, "disk": 0,
            "network_in": 0, "network_out": 0,
            "status": "no_agents",
            "temperature": None, "uptime_secs": None, "processes": None,
            "agents_count": agents_count, "open_alerts": open_alerts,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "source": "core-api",
        }

    cpu_avg  = sum(s.cpu    or 0 for s in snapshots) / len(snapshots)
    mem_avg  = sum(s.memory or 0 for s in snapshots) / len(snapshots)
    disk_avg = sum(s.disk   or 0 for s in snapshots) / len(snapshots)
    net_in   = sum((s.network_in  or 0) / (1024 * 1024) for s in snapshots)
    net_out  = sum((s.network_out or 0) / (1024 * 1024) for s in snapshots)

    st = "healthy"
    if cpu_avg > 90 or mem_avg > 90 or disk_avg > 90:   st = "critical"
    elif cpu_avg > 75 or mem_avg > 80 or disk_avg > 80: st = "warning"

    latest = max(snapshots, key=lambda s: s.timestamp or datetime.min.replace(tzinfo=timezone.utc))
    return {
        "cpu":          round(cpu_avg, 1),
        "memory":       round(mem_avg, 1),
        "disk":         round(disk_avg, 1),
        "network_in":   round(net_in,  2),
        "network_out":  round(net_out, 2),
        "status":       st,
        "temperature":  latest.temperature,
        "uptime_secs":  latest.uptime_secs,
        "processes":    latest.processes,
        "agents_count": agents_count,
        "open_alerts":  open_alerts,
        "last_updated": latest.timestamp.isoformat() if latest.timestamp else datetime.now(timezone.utc).isoformat(),
        "source":       "core-api",
    }


@app.get("/api/whoami")
async def whoami(request: Request):
    """Debug: decode the Bearer token without enforcing permissions."""
    import base64 as _b64, json as _json
    from jose import jwt as _jwt, JWTError as _JWTError
    _secret = os.getenv("JWT_SECRET_KEY")
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return {"error": "no bearer token"}
    raw_tok = auth[7:]
    # Always decode without verification first to see claims
    try:
        parts = raw_tok.split(".")
        pad = parts[1] + "=" * (4 - len(parts[1]) % 4)
        raw_payload = _json.loads(_b64.urlsafe_b64decode(pad))
    except Exception as e:
        return {"error": f"base64 decode failed: {e}"}
    # Then verify signature
    try:
        _jwt.decode(raw_tok, _secret, algorithms=["HS256"])
        return {"decoded": raw_payload, "secret_ok": True}
    except _JWTError as e:
        return {"decoded": raw_payload, "secret_ok": False, "jwt_error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# ORGANIZATIONS
# ─────────────────────────────────────────────────────────────────────────────

class CreateOrgRequest(BaseModel):
    name: str
    slug: str
    plan: str = "free"


class OrgSettingsRequest(BaseModel):
    autonomous_mode: Optional[bool] = None


@app.get("/api/orgs")
@limiter.limit("60/minute")
async def list_orgs(
    request: Request,
    token: TokenPayload = Depends(require_permission("admin:orgs")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Organization).order_by(Organization.created_at))
    return [_org_out(o) for o in result.scalars().all()]


@app.post("/api/orgs", status_code=201)
@limiter.limit("10/minute")
async def create_org(
    request: Request,
    body: CreateOrgRequest,
    token: TokenPayload = Depends(require_permission("admin:orgs")),
    db: AsyncSession = Depends(get_db),
):
    dup = await db.execute(select(Organization).where(Organization.slug == body.slug))
    if dup.scalar_one_or_none():
        raise HTTPException(409, "Slug already in use")
    org = Organization(name=body.name, slug=body.slug, plan=body.plan)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return _org_out(org)


@app.get("/api/orgs/{org_id}")
async def get_org(
    org_id: str,
    token: TokenPayload = Depends(require("orgs:read")),
    db: AsyncSession = Depends(get_db),
):
    return _org_out(await _fetch_org(db, org_id))


@app.patch("/api/orgs/{org_id}/settings")
async def update_org_settings(
    org_id: str,
    body: OrgSettingsRequest,
    token: TokenPayload = Depends(require("admin:orgs")),
    db: AsyncSession = Depends(get_db),
):
    org = await _fetch_org(db, org_id)
    settings = dict(org.settings or {})
    if body.autonomous_mode is not None:
        settings["autonomous_mode"] = body.autonomous_mode
    org.settings = settings
    await db.commit()
    return _org_out(org)


def _org_out(org: Organization) -> dict:
    return {
        "id": org.id, "name": org.name, "slug": org.slug,
        "plan": org.plan, "is_active": org.is_active,
        "settings": org.settings or {},
        "created_at": org.created_at.isoformat() if org.created_at else None,
    }


async def _fetch_org(db: AsyncSession, org_id: str) -> Organization:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(404, "Organization not found")
    return org


# ─────────────────────────────────────────────────────────────────────────────
# AGENTS
# ─────────────────────────────────────────────────────────────────────────────

class CreateAgentRequest(BaseModel):
    label: str
    owner_user_id: Optional[str] = None  # user whose machine this agent monitors


class SendCommandRequest(BaseModel):
    action: str
    params: dict = {}


AGENT_ALLOWLIST = {
    "clear_cache", "disk_cleanup", "free_memory", "run_gc",
    "kill_process", "restart_service",
}


@app.get("/api/orgs/{org_id}/agents")
@limiter.limit("60/minute")
async def list_agents(
    request: Request,
    org_id: str,
    token: TokenPayload = Depends(require("agents:read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Agent)
        .where(Agent.org_id == org_id, Agent.is_active == True)
        .order_by(Agent.created_at.desc())
    )
    agents = result.scalars().all()

    # Fetch latest snapshot for every agent in one query (avoids N+1 calls)
    if agents:
        sub = (
            select(
                MetricSnapshot.agent_id,
                sqlfunc.max(MetricSnapshot.timestamp).label("max_ts"),
            )
            .where(MetricSnapshot.org_id == org_id)
            .group_by(MetricSnapshot.agent_id)
            .subquery()
        )
        snap_result = await db.execute(
            select(MetricSnapshot).join(
                sub,
                (MetricSnapshot.agent_id == sub.c.agent_id)
                & (MetricSnapshot.timestamp == sub.c.max_ts),
            )
        )
        snap_map = {s.agent_id: s for s in snap_result.scalars().all()}
    else:
        snap_map = {}

    out = []
    for a in agents:
        snap = snap_map.get(a.id)
        row = _agent_out(a)
        row["metrics"] = {
            "cpu":         snap.cpu         if snap else None,
            "memory":      snap.memory      if snap else None,
            "disk":        snap.disk        if snap else None,
            "network_in":  snap.network_in  if snap else None,
            "network_out": snap.network_out if snap else None,
            "processes":   snap.processes   if snap else None,
            "uptime_secs": snap.uptime_secs if snap else None,
            "timestamp":   snap.timestamp.isoformat() if snap and snap.timestamp else None,
        }
        out.append(row)
    return out


@app.post("/api/orgs/{org_id}/agents", status_code=201)
@limiter.limit("20/minute")
async def create_agent(
    request: Request,
    org_id: str,
    body: CreateAgentRequest,
    token: TokenPayload = Depends(require("agents:write")),
    db: AsyncSession = Depends(get_db),
):
    await _fetch_org(db, org_id)
    raw_key, key_hash = generate_agent_key()

    agent = Agent(
        org_id=org_id,
        label=body.label,
        key_hash=key_hash,
        created_by=token.sub,
        owner_user_id=body.owner_user_id,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    await _audit(db, org_id, token.sub, "agent.created", "agent", agent.id,
                 {"label": body.label})

    hostname = request.headers.get("host", "localhost:8000")
    install_cmd = (
        f"AIOPS_SERVER=http://{hostname} "
        f"AIOPS_KEY={raw_key} "
        f"AIOPS_ORG={org_id} "
        f"python app/integrations/remote_agent.py"
    )

    return {
        **_agent_out(agent),
        "api_key": raw_key,  # shown ONCE — not stored in plain text
        "install_cmd": install_cmd,
        "warning": "Save this API key now. It will not be shown again.",
    }


@app.get("/api/orgs/{org_id}/agents/{agent_id}")
async def get_agent(
    org_id: str,
    agent_id: str,
    token: TokenPayload = Depends(require("agents:read")),
    db: AsyncSession = Depends(get_db),
):
    agent = await _fetch_agent(db, org_id, agent_id)
    # Latest metrics
    snap_result = await db.execute(
        select(MetricSnapshot)
        .where(MetricSnapshot.agent_id == agent_id)
        .order_by(desc(MetricSnapshot.timestamp))
        .limit(1)
    )
    snap = snap_result.scalar_one_or_none()
    return {**_agent_out(agent), "latest_metrics": _snap_out(snap) if snap else None}


class PatchAgentRequest(BaseModel):
    owner_user_id: Optional[str] = None
    label: Optional[str] = None


@app.patch("/api/orgs/{org_id}/agents/{agent_id}")
async def patch_agent(
    org_id: str,
    agent_id: str,
    body: PatchAgentRequest,
    token: TokenPayload = Depends(require("agents:write")),
    db: AsyncSession = Depends(get_db),
):
    """Update mutable agent fields (label, owner_user_id)."""
    agent = await _fetch_agent(db, org_id, agent_id)
    if body.label is not None:
        agent.label = body.label
    if body.owner_user_id is not None:
        agent.owner_user_id = body.owner_user_id
    await db.commit()
    await db.refresh(agent)
    await _audit(db, org_id, token.sub, "agent.updated", "agent", agent_id,
                 {"owner_user_id": body.owner_user_id})
    return _agent_out(agent)


@app.delete("/api/orgs/{org_id}/agents/{agent_id}")
async def delete_agent(
    org_id: str,
    agent_id: str,
    token: TokenPayload = Depends(require("agents:delete")),
    db: AsyncSession = Depends(get_db),
):
    agent = await _fetch_agent(db, org_id, agent_id)
    agent.is_active = False
    await db.commit()
    await _audit(db, org_id, token.sub, "agent.deactivated", "agent", agent_id)
    return {"ok": True}


@app.post("/api/orgs/{org_id}/agents/{agent_id}/command")
@limiter.limit("30/minute")
async def send_command(
    request: Request,
    org_id: str,
    agent_id: str,
    body: SendCommandRequest,
    token: TokenPayload = Depends(require("remediation:execute")),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in AGENT_ALLOWLIST:
        raise HTTPException(400, f"Action not allowed. Allowed: {sorted(AGENT_ALLOWLIST)}")

    agent = await _fetch_agent(db, org_id, agent_id)
    cmd_id = str(uuid.uuid4())
    cmds = list(agent.pending_cmds or [])
    cmds.append({"cmd_id": cmd_id, "action": body.action, "params": body.params})
    agent.pending_cmds = cmds

    # Create pending remediation record
    record = RemediationRecord(
        id=cmd_id,
        org_id=org_id,
        agent_id=agent_id,
        action=body.action,
        params=body.params,
        source="manual",
        triggered_by=token.sub,
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()

    await _audit(db, org_id, token.sub, "remediation.queued", "remediation", cmd_id,
                 {"action": body.action, "agent": agent.label})
    return {"ok": True, "cmd_id": cmd_id}


@app.get("/api/orgs/{org_id}/agents/{agent_id}/commands")
async def get_agent_commands(
    org_id: str,
    agent_id: str,
    token: TokenPayload = Depends(require("agents:read")),
    db: AsyncSession = Depends(get_db),
):
    await _fetch_agent(db, org_id, agent_id)
    result = await db.execute(
        select(RemediationRecord)
        .where(RemediationRecord.agent_id == agent_id)
        .order_by(desc(RemediationRecord.created_at))
        .limit(50)
    )
    return [_remediation_out(r) for r in result.scalars().all()]


def _agent_out(a: Agent) -> dict:
    return {
        "id": a.id, "org_id": a.org_id, "label": a.label,
        "owner_user_id": a.owner_user_id,
        "status": a.status, "is_active": a.is_active,
        "platform_info": a.platform_info,
        "last_seen": a.last_seen.isoformat() if a.last_seen else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


async def _fetch_agent(db: AsyncSession, org_id: str, agent_id: str) -> Agent:
    result = await db.execute(
        select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id, Agent.is_active == True)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


# ─────────────────────────────────────────────────────────────────────────────
# INGEST — Agent heartbeat (X-Agent-Key auth, no JWT)
# ─────────────────────────────────────────────────────────────────────────────

class MetricsPayload(BaseModel):
    cpu: float
    memory: float
    disk: float
    network_in: int = 0
    network_out: int = 0
    temperature: Optional[float] = None
    load_avg: Optional[str] = None
    processes: Optional[int] = None
    uptime_secs: Optional[int] = None


class HeartbeatBody(BaseModel):
    org_id: str
    metrics: MetricsPayload
    info: Optional[dict] = None    # hostname, os, cpu_cores, python_version


class CommandResultBody(BaseModel):
    org_id: str
    cmd_id: str
    status: str   # success|failed|skipped
    result: Optional[str] = None
    error: Optional[str] = None


@app.post("/ingest/heartbeat")
@limiter.limit("30/minute")
async def agent_heartbeat(
    request: Request,
    body: HeartbeatBody,
    agent: Agent = Depends(get_agent_from_key),
    db: AsyncSession = Depends(get_db),
):
    # Enforce org isolation
    if agent.org_id != body.org_id:
        raise HTTPException(403, "Org ID mismatch")

    now = datetime.now(timezone.utc)

    # Persist metric snapshot
    snap = MetricSnapshot(
        id=str(uuid.uuid4()),
        org_id=agent.org_id,
        agent_id=agent.id,
        timestamp=now,
        cpu=body.metrics.cpu,
        memory=body.metrics.memory,
        disk=body.metrics.disk,
        network_in=body.metrics.network_in,
        network_out=body.metrics.network_out,
        temperature=body.metrics.temperature,
        load_avg=body.metrics.load_avg,
        processes=body.metrics.processes,
        uptime_secs=body.metrics.uptime_secs,
    )
    db.add(snap)

    # Update platform info if provided
    if body.info:
        agent.platform_info = body.info

    # Drain pending commands to deliver in response
    pending = list(agent.pending_cmds or [])
    agent.pending_cmds = []

    await db.commit()

    return {"agent_id": agent.id, "commands": pending, "received_at": now.isoformat()}


class BrowserMetricsPayload(BaseModel):
    cpu: Optional[float] = None
    memory: Optional[float] = None
    disk: Optional[float] = None
    network_in: Optional[float] = None
    network_out: Optional[float] = None
    temperature: Optional[float] = None
    processes: Optional[int] = None
    uptime_secs: Optional[int] = None
    cpu_cores: Optional[int] = None
    device_memory_gb: Optional[float] = None
    platform: Optional[str] = None
    source: Optional[str] = "browser"
    battery: Optional[dict] = None
    effective_type: Optional[str] = None


class BrowserMetricsBody(BaseModel):
    org_id: str
    metrics: BrowserMetricsPayload


@app.post("/api/ingest/browser-metrics")
@limiter.limit("30/minute")
async def browser_metrics(
    request: Request,
    body: BrowserMetricsBody,
    token: TokenPayload = Depends(require_permission("metrics:read")),
    db: AsyncSession = Depends(get_db),
):
    """
    Receive metrics pushed from the user's browser (or local psutil agent).
    Each authenticated user gets a dedicated 'browser-{user_id}' agent that
    represents their machine. Metrics are stored as normal MetricSnapshots so
    the dashboard can display them without any special-casing.
    """
    org_id = token.org_id or body.org_id
    user_id = token.sub

    # Ensure org isolation
    if token.role != "admin" and token.org_id and token.org_id != body.org_id:
        raise HTTPException(403, "Organization access denied")

    # Find or create a browser agent for this user
    browser_label = f"browser-{user_id[:8]}"
    result = await db.execute(
        select(Agent).where(Agent.org_id == org_id, Agent.label == browser_label)
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        from rbac import generate_agent_key
        _, key_hash = generate_agent_key()
        agent = Agent(
            id=str(uuid.uuid4()),
            org_id=org_id,
            label=browser_label,
            key_hash=key_hash,
            status="live",
            pending_cmds=[],
            platform_info={
                "type": "browser",
                "platform": body.metrics.platform,
                "cpu_cores": body.metrics.cpu_cores,
                "device_memory_gb": body.metrics.device_memory_gb,
                "source": body.metrics.source,
            },
        )
        db.add(agent)
        await db.flush()
        log.info("Browser agent created (org=%s, user=%s)", org_id[:8], user_id[:8])

    m = body.metrics

    now = datetime.now(timezone.utc)

    snap = MetricSnapshot(
        id=str(uuid.uuid4()),
        org_id=org_id,
        agent_id=agent.id,
        timestamp=now,
        cpu=m.cpu or 0.0,
        memory=m.memory or 0.0,
        disk=m.disk or 0.0,
        network_in=int((m.network_in or 0) * 1024),   # KB → bytes
        network_out=int((m.network_out or 0) * 1024),
        temperature=m.temperature,
        processes=m.processes,
        uptime_secs=m.uptime_secs,
        extra={
            "source": m.source,
            "platform": m.platform,
            "cpu_cores": m.cpu_cores,
            "device_memory_gb": m.device_memory_gb,
            "battery": m.battery,
            "effective_type": m.effective_type,
        },
    )
    db.add(snap)

    agent.status = "live"
    agent.last_seen = now

    await db.commit()
    return {"ok": True, "agent_id": agent.id, "source": m.source}


@app.post("/ingest/command-result")
async def command_result(
    body: CommandResultBody,
    agent: Agent = Depends(get_agent_from_key),
    db: AsyncSession = Depends(get_db),
):
    if agent.org_id != body.org_id:
        raise HTTPException(403, "Org ID mismatch")

    result = await db.execute(
        select(RemediationRecord).where(RemediationRecord.id == body.cmd_id)
    )
    record = result.scalar_one_or_none()
    if record:
        record.status       = body.status
        record.result       = body.result
        record.error        = body.error
        record.completed_at = datetime.now(timezone.utc)
        record.verified     = body.status == "success"
        await db.commit()

    await _audit(db, agent.org_id, agent_id=agent.id, action="remediation.completed",
                 resource_type="remediation", resource_id=body.cmd_id,
                 detail={"status": body.status})
    return {"ok": True}


# ── Legacy heartbeat compatibility (existing remote_agent.py uses token in body) ──

class LegacyHeartbeatBody(BaseModel):
    token: str
    info: Optional[dict] = None
    metrics: Optional[dict] = None


@app.post("/agents/heartbeat")
@limiter.limit("30/minute")
async def legacy_heartbeat(
    request: Request,
    body: LegacyHeartbeatBody,
    db: AsyncSession = Depends(get_db),
):
    """
    Backward-compatible endpoint for remote_agent.py instances using the old
    token-in-body protocol. Logs a deprecation warning.
    Clients should migrate to POST /ingest/heartbeat with X-Agent-Key header.
    """
    import hashlib as _hl
    log.warning("Legacy agent heartbeat — migrate to /ingest/heartbeat with X-Agent-Key")

    token_hash = _hl.sha256(body.token.encode()).hexdigest()
    result = await db.execute(
        select(Agent).where(Agent.key_hash == token_hash, Agent.is_active == True)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(401, "Invalid token")

    now = datetime.now(timezone.utc)
    agent.last_seen = now
    agent.status = "online"
    if body.info:
        agent.platform_info = body.info

    if body.metrics:
        m = body.metrics
        snap = MetricSnapshot(
            id=str(uuid.uuid4()),
            org_id=agent.org_id,
            agent_id=agent.id,
            timestamp=now,
            cpu=m.get("cpu", 0.0),
            memory=m.get("memory", 0.0),
            disk=m.get("disk", 0.0),
            network_in=int(m.get("network_in", 0)),
            network_out=int(m.get("network_out", 0)),
            temperature=m.get("temperature"),
            load_avg=str(m.get("load_avg", "")) or None,
            processes=m.get("processes"),
            uptime_secs=m.get("uptime_secs"),
        )
        db.add(snap)

    pending = list(agent.pending_cmds or [])
    agent.pending_cmds = []
    await db.commit()

    return {"ok": True, "agent_id": agent.id, "commands": pending}


# ─────────────────────────────────────────────────────────────────────────────
# STREAMING  (Server-Sent Events)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/stream/metrics", include_in_schema=True)
async def stream_metrics(request: Request):
    """
    SSE stream of metric snapshots.

    Emits a ``data: {…}`` event whenever _local_metrics_loop collects fresh
    data (every ANOMALY_POLL_INTERVAL seconds, default 30 s).  Sends a
    ``: heartbeat`` comment every SSE_HEARTBEAT_SECONDS to keep proxies alive.
    Cleans up its subscriber queue the moment the client disconnects.
    """
    import json as _json

    async def _generator():
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        _metrics_subscribers.add(q)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(
                        q.get(), timeout=float(SSE_HEARTBEAT_SECONDS)
                    )
                    yield f"data: {_json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # No new data within the heartbeat window — keep alive.
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass   # client gone — exit silently
        finally:
            _metrics_subscribers.discard(q)

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


@app.get("/stream/alerts", include_in_schema=True)
async def stream_alerts(request: Request):
    """
    SSE stream of alert records.

    Polls the DB every ANOMALY_POLL_INTERVAL seconds for alerts created after
    the stream opened, emitting each new record immediately.  Heartbeats fill
    any quiet window longer than SSE_HEARTBEAT_SECONDS.
    """
    import json as _json

    poll_secs: int = int(os.getenv("ANOMALY_POLL_INTERVAL", "30"))

    async def _generator():
        since = datetime.now(timezone.utc)
        loop = asyncio.get_event_loop()
        next_poll      = loop.time() + poll_secs
        next_heartbeat = loop.time() + SSE_HEARTBEAT_SECONDS

        try:
            while True:
                if await request.is_disconnected():
                    break

                now = loop.time()

                if now >= next_poll:
                    next_poll = now + poll_secs
                    try:
                        async with SessionLocal() as db:
                            result = await db.execute(
                                select(AlertRecord)
                                .where(AlertRecord.created_at > since)
                                .order_by(AlertRecord.created_at)
                                .limit(50)
                            )
                            new_alerts = list(result.scalars().all())
                        for alert in new_alerts:
                            yield f"data: {_json.dumps(_alert_out(alert))}\n\n"
                            since = alert.created_at
                            # Extend heartbeat deadline after emitting real data.
                            next_heartbeat = loop.time() + SSE_HEARTBEAT_SECONDS
                    except Exception as exc:
                        log.error("SSE alerts poll error: %s", exc)

                if now >= next_heartbeat:
                    yield ": heartbeat\n\n"
                    next_heartbeat = now + SSE_HEARTBEAT_SECONDS

                # Small tick so disconnect is detected within 2 s.
                await asyncio.sleep(2)

        except asyncio.CancelledError:
            pass   # client gone — exit silently

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/orgs/{org_id}/metrics")
@limiter.limit("120/minute")
async def list_metrics(
    request: Request,
    org_id: str,
    agent_id: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    limit: int = 200,
    token: TokenPayload = Depends(require("metrics:read")),
    db: AsyncSession = Depends(get_db),
):
    # Default to the last 24 h when no explicit window is given.
    # This prevents unbounded scans on the hypertable and keeps response times
    # predictable as data volume grows.
    _default_from = datetime.now(timezone.utc) - timedelta(hours=24)

    q = select(MetricSnapshot).where(MetricSnapshot.org_id == org_id)
    if agent_id:
        q = q.where(MetricSnapshot.agent_id == agent_id)
    q = q.where(
        MetricSnapshot.timestamp >= (
            datetime.fromisoformat(from_ts) if from_ts else _default_from
        )
    )
    if to_ts:
        q = q.where(MetricSnapshot.timestamp <= datetime.fromisoformat(to_ts))
    q = q.order_by(desc(MetricSnapshot.timestamp)).limit(min(limit, 1000))

    result = await db.execute(q)
    return [_snap_out(s) for s in result.scalars().all()]


@app.get("/api/orgs/{org_id}/metrics/latest")
async def latest_metrics(
    org_id: str,
    token: TokenPayload = Depends(require("metrics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Latest snapshot per agent for the org."""
    sub = (
        select(
            MetricSnapshot.agent_id,
            sqlfunc.max(MetricSnapshot.timestamp).label("max_ts"),
        )
        .where(MetricSnapshot.org_id == org_id)
        .group_by(MetricSnapshot.agent_id)
        .subquery()
    )
    result = await db.execute(
        select(MetricSnapshot).join(
            sub,
            (MetricSnapshot.agent_id == sub.c.agent_id)
            & (MetricSnapshot.timestamp == sub.c.max_ts),
        )
    )
    return [_snap_out(s) for s in result.scalars().all()]


@app.get("/api/orgs/{org_id}/metrics/aggregate")
@limiter.limit("60/minute")
async def aggregate_metrics(
    request: Request,
    org_id: str,
    agent_id: Optional[str] = None,
    bucket: str = "1 hour",
    hours: int = 24,
    token: TokenPayload = Depends(require("metrics:read")),
    db: AsyncSession = Depends(get_db),
):
    """
    TimescaleDB time_bucket() aggregation: returns avg CPU/memory/disk per
    time bucket over the requested window.  Falls back to a plain GROUP BY
    on non-TimescaleDB instances (slower but correct).
    """
    from sqlalchemy import text

    # Validate bucket string to prevent injection (only allow digits + known units)
    import re as _re
    if not _re.fullmatch(r"\d+\s*(second|minute|hour|day|week)s?", bucket.strip()):
        raise HTTPException(status_code=400, detail="Invalid bucket interval")

    from_ts = datetime.now(timezone.utc) - timedelta(hours=max(1, min(hours, 720)))
    agent_filter = "AND agent_id = :agent_id" if agent_id else ""

    try:
        # TimescaleDB path: time_bucket() collapses rows into fixed-size chunks
        sql = text(f"""
            SELECT
                time_bucket(:bucket, timestamp)       AS bucket,
                agent_id,
                avg(cpu)                              AS avg_cpu,
                avg(memory)                           AS avg_memory,
                avg(disk)                             AS avg_disk,
                avg(network_in)                       AS avg_net_in,
                avg(network_out)                      AS avg_net_out
            FROM metric_snapshots
            WHERE org_id    = :org_id
              AND timestamp >= :from_ts
              {agent_filter}
            GROUP BY bucket, agent_id
            ORDER BY bucket DESC, agent_id
        """)
        params: dict = {"bucket": bucket, "org_id": org_id, "from_ts": from_ts}
        if agent_id:
            params["agent_id"] = agent_id
        rows = (await db.execute(sql, params)).mappings().all()
    except Exception:
        # Plain-PostgreSQL fallback: date_trunc is not ideal for variable
        # bucket sizes but works correctly for hour/day granularity.
        unit = bucket.strip().rstrip("s")
        sql = text(f"""
            SELECT
                date_trunc(:unit, timestamp)          AS bucket,
                agent_id,
                avg(cpu)                              AS avg_cpu,
                avg(memory)                           AS avg_memory,
                avg(disk)                             AS avg_disk,
                avg(network_in)                       AS avg_net_in,
                avg(network_out)                      AS avg_net_out
            FROM metric_snapshots
            WHERE org_id    = :org_id
              AND timestamp >= :from_ts
              {agent_filter}
            GROUP BY bucket, agent_id
            ORDER BY bucket DESC, agent_id
        """)
        params = {"unit": unit, "org_id": org_id, "from_ts": from_ts}
        if agent_id:
            params["agent_id"] = agent_id
        rows = (await db.execute(sql, params)).mappings().all()

    return [
        {
            "bucket":     row["bucket"].isoformat() if row["bucket"] else None,
            "agent_id":   row["agent_id"],
            "avg_cpu":    round(row["avg_cpu"]    or 0, 2),
            "avg_memory": round(row["avg_memory"] or 0, 2),
            "avg_disk":   round(row["avg_disk"]   or 0, 2),
            "avg_net_in": round(row["avg_net_in"] or 0, 2),
            "avg_net_out":round(row["avg_net_out"]or 0, 2),
        }
        for row in rows
    ]


def _snap_out(s: MetricSnapshot) -> dict:
    return {
        "id": s.id, "org_id": s.org_id, "agent_id": s.agent_id,
        "timestamp": s.timestamp.isoformat() if s.timestamp else None,
        "cpu": s.cpu, "memory": s.memory, "disk": s.disk,
        "network_in": s.network_in, "network_out": s.network_out,
        "temperature": s.temperature, "load_avg": s.load_avg,
        "processes": s.processes, "uptime_secs": s.uptime_secs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ALERTS
# ─────────────────────────────────────────────────────────────────────────────

class UpdateAlertRequest(BaseModel):
    status: str   # acknowledged | resolved


class CreateAlertRequest(BaseModel):
    agent_id: Optional[str] = None
    severity: str
    category: str
    title: str
    detail: str
    metric_value: Optional[float] = None
    threshold: Optional[float] = None


@app.get("/api/orgs/{org_id}/alerts")
@limiter.limit("120/minute")
async def list_alerts(
    request: Request,
    org_id: str,
    alert_status: Optional[str] = None,
    severity: Optional[str] = None,
    agent_id: Optional[str] = None,
    limit: int = 50,
    token: TokenPayload = Depends(require("alerts:read")),
    db: AsyncSession = Depends(get_db),
):
    q = select(AlertRecord).where(AlertRecord.org_id == org_id)
    if alert_status:
        q = q.where(AlertRecord.status == alert_status)
    if severity:
        q = q.where(AlertRecord.severity == severity)
    if agent_id:
        q = q.where(AlertRecord.agent_id == agent_id)
    q = q.order_by(desc(AlertRecord.created_at)).limit(min(limit, 500))

    result = await db.execute(q)
    return [_alert_out(a) for a in result.scalars().all()]


@app.post("/api/orgs/{org_id}/alerts", status_code=201)
async def create_alert(
    org_id: str,
    body: CreateAlertRequest,
    token: TokenPayload = Depends(require("alerts:write")),
    db: AsyncSession = Depends(get_db),
):
    alert = AlertRecord(
        org_id=org_id,
        agent_id=body.agent_id,
        severity=body.severity,
        category=body.category,
        title=body.title,
        detail=body.detail,
        metric_value=body.metric_value,
        threshold=body.threshold,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    await _audit(db, org_id, token.sub, "alert.created.manual", "alert", alert.id)
    return _alert_out(alert)


@app.put("/api/orgs/{org_id}/alerts/{alert_id}")
async def update_alert(
    org_id: str,
    alert_id: str,
    body: UpdateAlertRequest,
    token: TokenPayload = Depends(require("alerts:write")),
    db: AsyncSession = Depends(get_db),
):
    if body.status not in ("acknowledged", "resolved"):
        raise HTTPException(400, "Status must be 'acknowledged' or 'resolved'")

    result = await db.execute(
        select(AlertRecord).where(AlertRecord.id == alert_id, AlertRecord.org_id == org_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404, "Alert not found")

    alert.status = body.status
    if body.status == "resolved":
        alert.resolved_at = datetime.now(timezone.utc)
    await db.commit()
    await _audit(db, org_id, token.sub, f"alert.{body.status}", "alert", alert_id)
    return _alert_out(alert)


def _alert_out(a: AlertRecord) -> dict:
    return {
        "id": a.id, "org_id": a.org_id, "agent_id": a.agent_id,
        "owner_user_id": a.owner_user_id,
        "severity": a.severity, "category": a.category,
        "title": a.title, "detail": a.detail,
        "metric_value": a.metric_value, "threshold": a.threshold,
        "status": a.status,
        "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# REMEDIATION
# ─────────────────────────────────────────────────────────────────────────────

class TriggerRemediationRequest(BaseModel):
    agent_id: str
    action: str
    params: dict = {}
    dry_run: bool = False


@app.get("/api/orgs/{org_id}/remediation")
@limiter.limit("60/minute")
async def list_remediations(
    request: Request,
    org_id: str,
    agent_id: Optional[str] = None,
    rem_status: Optional[str] = None,
    limit: int = 50,
    token: TokenPayload = Depends(require("remediation:read")),
    db: AsyncSession = Depends(get_db),
):
    q = select(RemediationRecord).where(RemediationRecord.org_id == org_id)
    if agent_id:
        q = q.where(RemediationRecord.agent_id == agent_id)
    if rem_status:
        q = q.where(RemediationRecord.status == rem_status)
    q = q.order_by(desc(RemediationRecord.created_at)).limit(min(limit, 500))

    result = await db.execute(q)
    return [_remediation_out(r) for r in result.scalars().all()]


@app.post("/api/orgs/{org_id}/remediation", status_code=201)
@limiter.limit("20/minute")
async def trigger_remediation(
    request: Request,
    org_id: str,
    body: TriggerRemediationRequest,
    token: TokenPayload = Depends(require("remediation:execute")),
    db: AsyncSession = Depends(get_db),
):
    if body.action not in AGENT_ALLOWLIST:
        raise HTTPException(400, f"Action not in allowlist: {sorted(AGENT_ALLOWLIST)}")

    agent = await _fetch_agent(db, org_id, body.agent_id)

    cmd_id = str(uuid.uuid4())
    record = RemediationRecord(
        id=cmd_id,
        org_id=org_id,
        agent_id=body.agent_id,
        action=body.action,
        params=body.params,
        source="manual",
        triggered_by=token.sub,
        status="pending",
        started_at=datetime.now(timezone.utc),
    )
    db.add(record)

    if not body.dry_run:
        cmds = list(agent.pending_cmds or [])
        cmds.append({"cmd_id": cmd_id, "action": body.action, "params": body.params})
        agent.pending_cmds = cmds
        record.status = "running"

    await db.commit()
    await _audit(db, org_id, token.sub, "remediation.triggered.manual", "remediation",
                 cmd_id, {"action": body.action, "dry_run": body.dry_run})
    return _remediation_out(record)


@app.get("/api/orgs/{org_id}/remediation/stats")
async def remediation_stats(
    org_id: str,
    token: TokenPayload = Depends(require("remediation:read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RemediationRecord).where(RemediationRecord.org_id == org_id)
    )
    records = result.scalars().all()
    total  = len(records)
    ok     = sum(1 for r in records if r.status == "success")
    failed = sum(1 for r in records if r.status == "failed")
    auto   = sum(1 for r in records if r.source == "auto")
    return {
        "total": total, "success": ok, "failed": failed,
        "auto": auto, "manual": total - auto,
        "success_rate": round(ok / total * 100, 1) if total else 0,
    }


@app.get("/api/orgs/{org_id}/remediation/{record_id}")
async def get_remediation(
    org_id: str,
    record_id: str,
    token: TokenPayload = Depends(require("remediation:read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RemediationRecord)
        .where(RemediationRecord.id == record_id, RemediationRecord.org_id == org_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "Remediation record not found")
    return _remediation_out(record)


def _remediation_out(r: RemediationRecord) -> dict:
    return {
        "id": r.id, "org_id": r.org_id,
        "alert_id": r.alert_id, "agent_id": r.agent_id,
        "action": r.action, "params": r.params or {},
        "source": r.source, "triggered_by": r.triggered_by,
        "status": r.status, "result": r.result, "error": r.error,
        "before_metrics": r.before_metrics, "after_metrics": r.after_metrics,
        "verified": r.verified,
        "started_at":   r.started_at.isoformat()   if r.started_at   else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "created_at":   r.created_at.isoformat()   if r.created_at   else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/orgs/{org_id}/audit")
@limiter.limit("30/minute")
async def list_audit(
    request: Request,
    org_id: str,
    limit: int = 100,
    token: TokenPayload = Depends(require("audit:read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.org_id == org_id)
        .order_by(desc(AuditLog.created_at))
        .limit(min(limit, 1000))
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id, "action": l.action, "user_id": l.user_id,
            "agent_id": l.agent_id, "resource_type": l.resource_type,
            "resource_id": l.resource_id, "detail": l.detail,
            "ip_address": l.ip_address,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Helper: write audit log
# ─────────────────────────────────────────────────────────────────────────────

async def _audit(
    db: AsyncSession,
    org_id: Optional[str],
    user_id: Optional[str] = None,
    action: str = "",
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    detail: Optional[dict] = None,
    agent_id: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    db.add(AuditLog(
        id=str(uuid.uuid4()),
        org_id=org_id,
        user_id=user_id,
        agent_id=agent_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
    ))


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION CHANNELS
# ─────────────────────────────────────────────────────────────────────────────

_VALID_CHANNEL_TYPES = {"email", "slack", "telegram"}
_VALID_SEVERITIES    = {"critical", "high", "medium", "low", "info"}


class CreateChannelRequest(BaseModel):
    channel_type: str                        # email | slack | telegram
    label:        Optional[str] = None
    config:       dict                       # channel-specific credentials
    enabled:      bool = True
    severities:   Optional[List[str]] = None  # None → all


class UpdateChannelRequest(BaseModel):
    label:      Optional[str]       = None
    config:     Optional[dict]      = None
    enabled:    Optional[bool]      = None
    severities: Optional[List[str]] = None


def _channel_out(ch: NotificationChannel) -> dict:
    cfg = dict(ch.config or {})
    # Mask secrets in responses
    if ch.channel_type == "email":
        cfg.pop("smtp_password", None)
    if ch.channel_type == "telegram":
        token = cfg.get("bot_token", "")
        if token:
            cfg["bot_token"] = token[:6] + "…" + token[-4:] if len(token) > 10 else "***"
    return {
        "id":           ch.id,
        "org_id":       ch.org_id,
        "user_id":      ch.user_id,
        "channel_type": ch.channel_type,
        "label":        ch.label,
        "config":       cfg,
        "enabled":      ch.enabled,
        "severities":   ch.severities,
        "created_at":   ch.created_at.isoformat() if ch.created_at else None,
        "updated_at":   ch.updated_at.isoformat() if ch.updated_at else None,
    }


@app.get("/api/orgs/{org_id}/notification-channels")
@limiter.limit("60/minute")
async def list_notification_channels(
    request: Request,
    org_id: str,
    token: TokenPayload = Depends(require("alerts:read")),
    db: AsyncSession = Depends(get_db),
):
    """List all notification channels for the org."""
    result = await db.execute(
        select(NotificationChannel)
        .where(NotificationChannel.org_id == org_id)
        .order_by(NotificationChannel.created_at)
    )
    return [_channel_out(ch) for ch in result.scalars().all()]


@app.post("/api/orgs/{org_id}/notification-channels", status_code=201)
@limiter.limit("30/minute")
async def create_notification_channel(
    request: Request,
    org_id: str,
    body: CreateChannelRequest,
    token: TokenPayload = Depends(require("alerts:write")),
    db: AsyncSession = Depends(get_db),
):
    if body.channel_type not in _VALID_CHANNEL_TYPES:
        raise HTTPException(400, f"channel_type must be one of: {sorted(_VALID_CHANNEL_TYPES)}")

    bad_sevs = [s for s in (body.severities or []) if s not in _VALID_SEVERITIES]
    if bad_sevs:
        raise HTTPException(400, f"Invalid severities: {bad_sevs}")

    ch = NotificationChannel(
        org_id=org_id,
        user_id=token.sub,
        channel_type=body.channel_type,
        label=body.label,
        config=body.config,
        enabled=body.enabled,
        severities=body.severities,
    )
    db.add(ch)
    await db.commit()
    await db.refresh(ch)
    await _audit(db, org_id, token.sub, "notification_channel.created",
                 "notification_channel", ch.id, {"type": body.channel_type})
    return _channel_out(ch)


@app.put("/api/orgs/{org_id}/notification-channels/{channel_id}")
async def update_notification_channel(
    org_id: str,
    channel_id: str,
    body: UpdateChannelRequest,
    token: TokenPayload = Depends(require("alerts:write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.id     == channel_id,
            NotificationChannel.org_id == org_id,
        )
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(404, "Channel not found")

    if body.label      is not None: ch.label      = body.label
    if body.config     is not None: ch.config     = body.config
    if body.enabled    is not None: ch.enabled    = body.enabled
    if body.severities is not None:
        bad = [s for s in body.severities if s not in _VALID_SEVERITIES]
        if bad:
            raise HTTPException(400, f"Invalid severities: {bad}")
        ch.severities = body.severities

    await db.commit()
    await db.refresh(ch)
    await _audit(db, org_id, token.sub, "notification_channel.updated",
                 "notification_channel", channel_id)
    return _channel_out(ch)


@app.delete("/api/orgs/{org_id}/notification-channels/{channel_id}", status_code=204)
async def delete_notification_channel(
    org_id: str,
    channel_id: str,
    token: TokenPayload = Depends(require("alerts:write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.id     == channel_id,
            NotificationChannel.org_id == org_id,
        )
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(404, "Channel not found")
    await db.delete(ch)
    await db.commit()
    await _audit(db, org_id, token.sub, "notification_channel.deleted",
                 "notification_channel", channel_id)


@app.post("/api/orgs/{org_id}/notification-channels/{channel_id}/test")
@limiter.limit("10/minute")
async def test_notification_channel(
    request: Request,
    org_id: str,
    channel_id: str,
    token: TokenPayload = Depends(require("alerts:write")),
    db: AsyncSession = Depends(get_db),
):
    """Send a test message to verify a channel is reachable."""
    from notification_service import send_test_notification

    result = await db.execute(
        select(NotificationChannel).where(
            NotificationChannel.id     == channel_id,
            NotificationChannel.org_id == org_id,
        )
    )
    ch = result.scalar_one_or_none()
    if not ch:
        raise HTTPException(404, "Channel not found")

    outcome = await send_test_notification(ch)
    return outcome


# ─────────────────────────────────────────────────────────────────────────────
# ALERT RULES
# ─────────────────────────────────────────────────────────────────────────────

_VALID_METRICS = {"cpu", "memory", "disk"}


class CreateAlertRuleRequest(BaseModel):
    name:             str
    metric:           str            # cpu | memory | disk
    threshold:        float
    severity:         str            # critical | high | medium | low | info
    agent_id:         Optional[str] = None   # None = all agents
    cooldown_minutes: int            = 15
    enabled:          bool           = True
    notify_channels:  Optional[List[str]] = None


class UpdateAlertRuleRequest(BaseModel):
    name:             Optional[str]       = None
    metric:           Optional[str]       = None
    threshold:        Optional[float]     = None
    severity:         Optional[str]       = None
    agent_id:         Optional[str]       = None
    cooldown_minutes: Optional[int]       = None
    enabled:          Optional[bool]      = None
    notify_channels:  Optional[List[str]] = None


def _rule_out(r: AlertRule) -> dict:
    return {
        "id":               r.id,
        "org_id":           r.org_id,
        "agent_id":         r.agent_id,
        "name":             r.name,
        "metric":           r.metric,
        "threshold":        r.threshold,
        "severity":         r.severity,
        "cooldown_minutes": r.cooldown_minutes,
        "enabled":          r.enabled,
        "notify_channels":  r.notify_channels,
        "created_by":       r.created_by,
        "created_at":       r.created_at.isoformat() if r.created_at else None,
        "updated_at":       r.updated_at.isoformat() if r.updated_at else None,
    }


@app.get("/api/orgs/{org_id}/alert-rules")
@limiter.limit("60/minute")
async def list_alert_rules(
    request: Request,
    org_id: str,
    token: TokenPayload = Depends(require("alerts:read")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AlertRule)
        .where(AlertRule.org_id == org_id)
        .order_by(AlertRule.created_at)
    )
    return [_rule_out(r) for r in result.scalars().all()]


@app.post("/api/orgs/{org_id}/alert-rules", status_code=201)
@limiter.limit("30/minute")
async def create_alert_rule(
    request: Request,
    org_id: str,
    body: CreateAlertRuleRequest,
    token: TokenPayload = Depends(require("alerts:write")),
    db: AsyncSession = Depends(get_db),
):
    if body.metric not in _VALID_METRICS:
        raise HTTPException(400, f"metric must be one of: {sorted(_VALID_METRICS)}")
    if body.severity not in _VALID_SEVERITIES:
        raise HTTPException(400, f"severity must be one of: {sorted(_VALID_SEVERITIES)}")
    if not (0 < body.threshold <= 100):
        raise HTTPException(400, "threshold must be between 0 and 100")

    rule = AlertRule(
        org_id=org_id,
        agent_id=body.agent_id,
        name=body.name,
        metric=body.metric,
        threshold=body.threshold,
        severity=body.severity,
        cooldown_minutes=body.cooldown_minutes,
        enabled=body.enabled,
        notify_channels=body.notify_channels,
        created_by=token.sub,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    await _audit(db, org_id, token.sub, "alert_rule.created", "alert_rule", rule.id,
                 {"metric": body.metric, "threshold": body.threshold})
    return _rule_out(rule)


@app.put("/api/orgs/{org_id}/alert-rules/{rule_id}")
async def update_alert_rule(
    org_id: str,
    rule_id: str,
    body: UpdateAlertRuleRequest,
    token: TokenPayload = Depends(require("alerts:write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AlertRule).where(
            AlertRule.id     == rule_id,
            AlertRule.org_id == org_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Alert rule not found")

    if body.metric is not None:
        if body.metric not in _VALID_METRICS:
            raise HTTPException(400, f"metric must be one of: {sorted(_VALID_METRICS)}")
        rule.metric = body.metric
    if body.severity is not None:
        if body.severity not in _VALID_SEVERITIES:
            raise HTTPException(400, f"severity must be one of: {sorted(_VALID_SEVERITIES)}")
        rule.severity = body.severity
    if body.threshold is not None:
        if not (0 < body.threshold <= 100):
            raise HTTPException(400, "threshold must be between 0 and 100")
        rule.threshold = body.threshold
    if body.name             is not None: rule.name             = body.name
    if body.agent_id         is not None: rule.agent_id         = body.agent_id
    if body.cooldown_minutes is not None: rule.cooldown_minutes = body.cooldown_minutes
    if body.enabled          is not None: rule.enabled          = body.enabled
    if body.notify_channels  is not None: rule.notify_channels  = body.notify_channels

    await db.commit()
    await db.refresh(rule)
    await _audit(db, org_id, token.sub, "alert_rule.updated", "alert_rule", rule_id)
    return _rule_out(rule)


@app.delete("/api/orgs/{org_id}/alert-rules/{rule_id}", status_code=204)
async def delete_alert_rule(
    org_id: str,
    rule_id: str,
    token: TokenPayload = Depends(require("alerts:write")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AlertRule).where(
            AlertRule.id     == rule_id,
            AlertRule.org_id == org_id,
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Alert rule not found")
    await db.delete(rule)
    await db.commit()
    await _audit(db, org_id, token.sub, "alert_rule.deleted", "alert_rule", rule_id)


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION LOGS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/orgs/{org_id}/notification-logs")
@limiter.limit("60/minute")
async def list_notification_logs(
    request: Request,
    org_id: str,
    channel_type:      Optional[str] = None,
    notification_type: Optional[str] = None,
    status:            Optional[str] = None,
    limit: int = 100,
    token: TokenPayload = Depends(require("alerts:read")),
    db: AsyncSession = Depends(get_db),
):
    """Paginated notification history for the org."""
    q = select(NotificationLog).where(NotificationLog.org_id == org_id)
    if channel_type:
        q = q.where(NotificationLog.channel_type == channel_type)
    if notification_type:
        q = q.where(NotificationLog.notification_type == notification_type)
    if status:
        q = q.where(NotificationLog.status == status)
    q = q.order_by(desc(NotificationLog.sent_at)).limit(min(limit, 500))

    result = await db.execute(q)
    return [
        {
            "id":                nl.id,
            "org_id":            nl.org_id,
            "alert_id":          nl.alert_id,
            "channel_id":        nl.channel_id,
            "channel_type":      nl.channel_type,
            "notification_type": nl.notification_type,
            "recipient":         nl.recipient,
            "subject":           nl.subject,
            "status":            nl.status,
            "error":             nl.error,
            "sent_at":           nl.sent_at.isoformat() if nl.sent_at else None,
        }
        for nl in result.scalars().all()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# DAILY SUMMARY (manual trigger — for testing / on-demand)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/orgs/{org_id}/daily-summary/send")
@limiter.limit("5/minute")
async def trigger_daily_summary(
    request: Request,
    org_id: str,
    token: TokenPayload = Depends(require("alerts:write")),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger an on-demand daily summary for the org."""
    from notification_service import dispatch_daily_summary

    await _fetch_org(db, org_id)
    asyncio.create_task(_send_summary_bg(org_id))
    return {"ok": True, "message": "Daily summary dispatch queued"}


async def _send_summary_bg(org_id: str) -> None:
    from notification_service import dispatch_daily_summary
    try:
        async with SessionLocal() as db:
            await dispatch_daily_summary(db, org_id)
        log.info("On-demand daily summary dispatched: org=%s", org_id[:8])
    except Exception as exc:
        log.error("On-demand daily summary failed: org=%s: %s", org_id[:8], exc)


# ─────────────────────────────────────────────────────────────────────────────
# WMI AGENTLESS POLLING  (server-side, zero client touch)
# ─────────────────────────────────────────────────────────────────────────────

async def _wmi_polling_loop():
    """Load all active WMI targets from DB on startup, then start the poller."""
    from wmi_poller import wmi_poller, decrypt_password
    interval = int(os.getenv("WMI_POLL_INTERVAL", "10"))
    await asyncio.sleep(8)   # let DB settle

    async with SessionLocal() as db:
        result = await db.execute(
            select(WMITarget).where(WMITarget.is_active == True)
        )
        targets = result.scalars().all()
        for t in targets:
            try:
                wmi_poller.load_target(
                    target_id=t.id, org_id=t.org_id, label=t.label,
                    host=t.host, username=t.username,
                    password_plain=decrypt_password(t.enc_password),
                    agent_id=t.agent_id, port=t.port,
                )
            except Exception as exc:
                log.warning("Could not load WMI target %s: %s", t.label, exc)

    log.info("WMI poller loaded %d target(s)", len(targets))
    await wmi_poller.run(SessionLocal, interval=interval)


def _wmi_target_out(t: WMITarget) -> dict:
    return {
        "id":          t.id,
        "org_id":      t.org_id,
        "agent_id":    t.agent_id,
        "label":       t.label,
        "host":        t.host,
        "port":        t.port,
        "username":    t.username,
        "is_active":   t.is_active,
        "last_polled": t.last_polled.isoformat() if t.last_polled else None,
        "last_status": t.last_status,
        "last_error":  t.last_error,
        "created_at":  t.created_at.isoformat(),
    }


class CreateWMITargetRequest(BaseModel):
    label: str
    host: str
    port: int = 5985
    username: str
    password: str


@app.get("/api/orgs/{org_id}/wmi-targets")
@limiter.limit("60/minute")
async def list_wmi_targets(
    request: Request,
    org_id: str,
    token: TokenPayload = Depends(require("agents:read")),
    db: AsyncSession = Depends(get_db),
):
    """List all WMI polling targets for this org, with latest metrics embedded."""
    await _fetch_org(db, org_id)
    result = await db.execute(
        select(WMITarget)
        .where(WMITarget.org_id == org_id)
        .order_by(WMITarget.created_at)
    )
    targets = result.scalars().all()

    # Fetch latest MetricSnapshot for each target's agent_id in one query
    agent_ids = [t.agent_id for t in targets if t.agent_id]
    metrics_map: dict = {}
    if agent_ids:
        from sqlalchemy import func as _func
        sub = (
            select(
                MetricSnapshot.agent_id,
                _func.max(MetricSnapshot.timestamp).label("max_ts"),
            )
            .where(MetricSnapshot.agent_id.in_(agent_ids))
            .group_by(MetricSnapshot.agent_id)
            .subquery()
        )
        latest_rows = await db.execute(
            select(MetricSnapshot).join(
                sub,
                (MetricSnapshot.agent_id == sub.c.agent_id) &
                (MetricSnapshot.timestamp == sub.c.max_ts),
            )
        )
        for snap in latest_rows.scalars().all():
            metrics_map[snap.agent_id] = {
                "cpu":         snap.cpu,
                "memory":      snap.memory,
                "disk":        snap.disk,
                "network_in":  snap.network_in,
                "network_out": snap.network_out,
                "processes":   snap.processes,
                "uptime_secs": snap.uptime_secs,
                "timestamp":   snap.timestamp.isoformat() if snap.timestamp else None,
            }

    out = []
    for t in targets:
        row = _wmi_target_out(t)
        row["metrics"] = metrics_map.get(t.agent_id) if t.agent_id else None
        out.append(row)
    return out


@app.post("/api/orgs/{org_id}/wmi-targets", status_code=201)
@limiter.limit("20/minute")
async def create_wmi_target(
    request: Request,
    org_id: str,
    body: CreateWMITargetRequest,
    token: TokenPayload = Depends(require("agents:write")),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a Windows machine for agentless WMI polling.
    The server will poll the machine every WMI_POLL_INTERVAL seconds (default 30s).

    One-time setup on the target machine (admin sends to user):
        Enable-PSRemoting -Force -SkipNetworkProfileCheck
    """
    from wmi_poller import wmi_poller, encrypt_password, decrypt_password

    await _fetch_org(db, org_id)

    # Create a synthetic Agent record so metrics flow through the existing pipeline
    _, key_hash = generate_agent_key()
    agent = Agent(
        org_id=org_id,
        label=body.label,
        key_hash=key_hash,
        created_by=token.sub,
        status="pending",
        platform_info={"source": "wmi", "host": body.host, "os": "Windows"},
        pending_cmds=[],
    )
    db.add(agent)
    await db.flush()   # get agent.id

    target = WMITarget(
        org_id=org_id,
        agent_id=agent.id,
        label=body.label,
        host=body.host,
        port=body.port,
        username=body.username,
        enc_password=encrypt_password(body.password),
        created_by=token.sub,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)

    # Register with live poller
    wmi_poller.load_target(
        target_id=target.id, org_id=org_id, label=body.label,
        host=body.host, username=body.username,
        password_plain=body.password,
        agent_id=agent.id, port=body.port,
    )

    await _audit(db, org_id, token.sub, "wmi_target.created", "wmi_target", target.id,
                 {"label": body.label, "host": body.host})

    return {
        **_wmi_target_out(target),
        "setup_guide": (
            "Run this ONE-TIME command on the target Windows machine:\n\n"
            "    Enable-PSRemoting -Force -SkipNetworkProfileCheck\n\n"
            "Then use the 'Test Connection' button to verify."
        ),
    }


@app.post("/api/orgs/{org_id}/wmi-targets/{target_id}/test")
@limiter.limit("10/minute")
async def test_wmi_target(
    request: Request,
    org_id: str,
    target_id: str,
    token: TokenPayload = Depends(require("agents:write")),
    db: AsyncSession = Depends(get_db),
):
    """Test WinRM connectivity to the target machine."""
    from wmi_poller import wmi_poller, decrypt_password

    await _fetch_org(db, org_id)
    result = await db.execute(
        select(WMITarget).where(WMITarget.id == target_id, WMITarget.org_id == org_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "WMI target not found")

    password = decrypt_password(target.enc_password)
    loop = asyncio.get_event_loop()
    ok, message = await loop.run_in_executor(
        None,
        wmi_poller.test_connection_sync,
        target.host, target.username, password, target.port,
    )

    target.last_polled = datetime.now(timezone.utc)
    target.last_status = "ok" if ok else "error"
    target.last_error  = None if ok else message
    await db.commit()

    return {"success": ok, "message": message, "host": target.host}


_WMI_REMEDIATION_PS: dict = {
    "clear_cache": (
        "Clear-DnsClientCache -ErrorAction SilentlyContinue; "
        "Remove-Item -Path \"$env:TEMP\\*\" -Recurse -Force -ErrorAction SilentlyContinue; "
        "Write-Output 'cache_cleared'"
    ),
    "disk_cleanup": (
        "Remove-Item -Path \"$env:TEMP\\*\" -Recurse -Force -ErrorAction SilentlyContinue; "
        "Remove-Item -Path \"C:\\Windows\\Temp\\*\" -Recurse -Force -ErrorAction SilentlyContinue; "
        "Write-Output 'disk_cleaned'"
    ),
    "free_memory": (
        "[System.GC]::Collect(); [System.GC]::WaitForPendingFinalizers(); "
        "[System.GC]::Collect(); Write-Output 'memory_freed'"
    ),
    "run_gc": (
        "[System.GC]::Collect(); [System.GC]::WaitForPendingFinalizers(); "
        "Write-Output 'gc_complete'"
    ),
    "restart_service": (
        "param([string]$Name='Spooler'); "
        "Restart-Service -Name $Name -Force -ErrorAction SilentlyContinue; "
        "Write-Output \"restarted_$Name\""
    ),
    "kill_process": (
        "param([string]$Name=''); if($Name){ "
        "Stop-Process -Name $Name -Force -ErrorAction SilentlyContinue; "
        "Write-Output \"killed_$Name\" } else { Write-Output 'no_name' }"
    ),
}


class WmiRemediateRequest(BaseModel):
    action: str
    params: dict = {}


@app.post("/api/orgs/{org_id}/wmi-targets/{target_id}/remediate")
@limiter.limit("10/minute")
async def wmi_remediate(
    request: Request,
    org_id: str,
    target_id: str,
    body: WmiRemediateRequest,
    token: TokenPayload = Depends(require("remediation:execute")),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a remediation action on a WMI target machine directly via WinRM.
    Unlike agent-based remediation (which uses pending_cmds + heartbeat),
    this runs the PowerShell command synchronously over WinRM.
    """
    from wmi_poller import wmi_poller, decrypt_password

    if body.action not in AGENT_ALLOWLIST:
        raise HTTPException(400, f"Action not allowed: {sorted(AGENT_ALLOWLIST)}")
    if body.action not in _WMI_REMEDIATION_PS:
        raise HTTPException(400, f"No WMI PS mapping for action: {body.action}")

    await _fetch_org(db, org_id)
    result = await db.execute(
        select(WMITarget).where(WMITarget.id == target_id, WMITarget.org_id == org_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "WMI target not found")

    password = decrypt_password(target.enc_password)
    ps_cmd = _WMI_REMEDIATION_PS[body.action]

    # Inject params (e.g. service name, process name)
    if body.params.get("service_name"):
        ps_cmd = f"$Name='{body.params['service_name']}'; " + ps_cmd
    elif body.params.get("process_name"):
        ps_cmd = f"$Name='{body.params['process_name']}'; " + ps_cmd

    loop = asyncio.get_event_loop()
    ok, output = await loop.run_in_executor(
        None,
        wmi_poller.execute_command_sync,
        target.host, target.username, password, target.port, ps_cmd,
    )

    cmd_id = str(uuid.uuid4())
    record = RemediationRecord(
        id=cmd_id,
        org_id=org_id,
        agent_id=target.agent_id,
        action=body.action,
        params=body.params,
        source="manual",
        triggered_by=token.sub,
        status="success" if ok else "failed",
        result=output,
        error=None if ok else output,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        verified=ok,
    )
    db.add(record)
    await db.commit()

    await _audit(db, org_id, token.sub, "wmi_remediation.executed", "remediation", cmd_id,
                 {"action": body.action, "target": target.host, "ok": ok})
    return {"ok": ok, "cmd_id": cmd_id, "output": output, "action": body.action}


@app.delete("/api/orgs/{org_id}/wmi-targets/{target_id}", status_code=204)
async def delete_wmi_target(
    org_id: str,
    target_id: str,
    token: TokenPayload = Depends(require("agents:write")),
    db: AsyncSession = Depends(get_db),
):
    """Remove a WMI target and stop polling it."""
    from wmi_poller import wmi_poller

    await _fetch_org(db, org_id)
    result = await db.execute(
        select(WMITarget).where(WMITarget.id == target_id, WMITarget.org_id == org_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(404, "WMI target not found")

    wmi_poller.unload_target(target_id)
    await db.delete(target)
    await db.commit()
    await _audit(db, org_id, token.sub, "wmi_target.deleted", "wmi_target", target_id, {})


# ─────────────────────────────────────────────────────────────────────────────
# WMI BOOTSTRAP INVITE  (zero-input onboarding)
# ─────────────────────────────────────────────────────────────────────────────

class CreateWmiInviteRequest(BaseModel):
    pass  # no body needed; org + auth from path/token


@app.post("/api/orgs/{org_id}/wmi-invite", status_code=201)
@limiter.limit("10/minute")
async def create_wmi_invite(
    request: Request,
    org_id: str,
    token: TokenPayload = Depends(require("agents:write")),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a one-time bootstrap invite token.
    Returns a PowerShell one-liner the admin pastes or sends to the end user.
    The user runs it as Administrator; the machine self-registers automatically.
    Token expires in 30 minutes and is single-use.
    """
    await _fetch_org(db, org_id)

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)

    # Validate that token.sub references a real PostgreSQL user; fall back to None
    # when auth comes from the legacy Flask/SQLite auth system (different ID space).
    pg_user = await db.get(User, token.sub)
    creator_id = token.sub if pg_user else None

    invite = WmiInvite(
        org_id=org_id,
        token_hash=token_hash,
        created_by=creator_id,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    api_url = os.getenv("CORE_API_URL", "http://localhost:8000")
    connect_command = f"irm {api_url}/connect.ps1?token={raw_token} | iex"

    return {
        "invite_id": invite.id,
        "expires_at": expires_at.isoformat(),
        "connect_command": connect_command,
    }


class WmiRegisterRequest(BaseModel):
    token: str
    hostname: str
    ip: Optional[str] = None
    os: str
    arch: Optional[str] = None
    username: str
    password: str   # plaintext — caller must use HTTPS/internal network
    port: int = 5985


@app.post("/api/wmi-register")
@limiter.limit("30/minute")
async def wmi_register(
    request: Request,
    body: WmiRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint: Windows machine self-registers using a bootstrap token.
    No auth header — the token IS the credential (hashed, single-use, expiring).
    Creates a WMI target + synthetic agent and starts polling immediately.
    """
    from wmi_poller import wmi_poller, encrypt_password

    token_hash = hashlib.sha256(body.token.encode()).hexdigest()

    result = await db.execute(
        select(WmiInvite).where(
            WmiInvite.token_hash == token_hash,
            WmiInvite.used == False,
            WmiInvite.expires_at > datetime.now(timezone.utc),
        )
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(400, "Invalid or expired invite token")

    host = body.ip or body.hostname
    label = f"{body.hostname}"
    os_tag = body.os or "Windows"

    # Create synthetic Agent record (metrics flow through existing pipeline)
    _, key_hash = generate_agent_key()
    agent = Agent(
        org_id=invite.org_id,
        label=label,
        key_hash=key_hash,
        status="pending",
        platform_info={
            "source": "wmi",
            "host": host,
            "os": os_tag,
            "arch": body.arch or "",
            "hostname": body.hostname,
        },
        pending_cmds=[],
    )
    db.add(agent)
    await db.flush()

    target = WMITarget(
        org_id=invite.org_id,
        agent_id=agent.id,
        label=label,
        host=host,
        port=body.port,
        username=body.username,
        enc_password=encrypt_password(body.password),
        created_by=invite.created_by,
    )
    db.add(target)
    await db.flush()

    # Consume invite
    invite.used = True
    invite.used_at = datetime.now(timezone.utc)
    invite.registered_agent_id = agent.id
    invite.machine_label = label

    await db.commit()

    # Register with live poller so monitoring starts immediately
    try:
        wmi_poller.load_target(
            target_id=target.id, org_id=invite.org_id, label=label,
            host=host, username=body.username,
            password_plain=body.password,
            agent_id=agent.id, port=body.port,
        )
    except Exception as exc:
        log.warning("Could not hot-load WMI target after bootstrap: %s", exc)

    await _audit(db, invite.org_id, invite.created_by or "bootstrap",
                 "wmi_target.bootstrap_registered", "wmi_target", target.id,
                 {"label": label, "host": host, "invite_id": invite.id})

    return {"success": True, "agent_id": agent.id, "label": label}


@app.get("/api/orgs/{org_id}/wmi-invite/{invite_id}/status")
@limiter.limit("120/minute")
async def get_wmi_invite_status(
    request: Request,
    org_id: str,
    invite_id: str,
    token: TokenPayload = Depends(require("agents:read")),
    db: AsyncSession = Depends(get_db),
):
    """Poll for invite completion. Frontend calls this every 3s after generating the invite."""
    await _fetch_org(db, org_id)
    result = await db.execute(
        select(WmiInvite).where(WmiInvite.id == invite_id, WmiInvite.org_id == org_id)
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(404, "Invite not found")

    expired = invite.expires_at < datetime.now(timezone.utc)

    return {
        "invite_id": invite.id,
        "used": invite.used,
        "expired": expired and not invite.used,
        "machine_label": invite.machine_label,
        "registered_agent_id": invite.registered_agent_id,
        "expires_at": invite.expires_at.isoformat(),
    }


# ── User-facing setup guide (no auth — safe to share) ─────────────────────────

@app.get("/connect.ps1", response_class=None)
async def serve_connect_ps1(
    token: str,
    request: Request,
    _auth: TokenPayload = Depends(require("agents:write")),
):
    """
    PowerShell bootstrap script served to Windows machines via:
        irm http://<server>:8000/connect.ps1?token=<TOKEN> | iex

    The script:
      1. Enables WinRM (one-time, requires Admin)
      2. Creates a local 'aiops-monitor' account with a random password
      3. Collects hostname / IP / OS info
      4. POSTs to /api/wmi-register to self-register
    """
    from fastapi.responses import PlainTextResponse
    api_base = os.getenv("CORE_API_URL",
        f"http://{request.headers.get('host', 'localhost:8000')}")
    ps = r"""
$ErrorActionPreference = 'Stop'
$token   = '__TOKEN__'
$apiBase = '__API_BASE__'

Write-Host '[AIOps] Starting machine registration...' -ForegroundColor Cyan

# 1 - Enable WinRM
try {
    Enable-PSRemoting -Force -SkipNetworkProfileCheck | Out-Null
    Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $true -ErrorAction SilentlyContinue
    Set-Item WSMan:\localhost\Service\Auth\Basic -Value $true -ErrorAction SilentlyContinue
    Write-Host '[AIOps] WinRM enabled.' -ForegroundColor Green
} catch {
    Write-Host "[AIOps] WinRM warning: $($_.Exception.Message)" -ForegroundColor Yellow
}

# 2 - Create / update local monitoring account
$monUser = 'aiops-monitor'
$chars   = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#'
$monPass = -join ((1..20) | ForEach-Object { $chars[(Get-Random -Max $chars.Length)] })
try {
    $existing = Get-LocalUser -Name $monUser -ErrorAction SilentlyContinue
    if (-not $existing) {
        $secPass = ConvertTo-SecureString $monPass -AsPlainText -Force
        New-LocalUser -Name $monUser -Password $secPass -PasswordNeverExpires `
            -UserMayNotChangePassword -Description 'AIOps monitoring account' | Out-Null
        Add-LocalGroupMember -Group 'Administrators' -Member $monUser -ErrorAction SilentlyContinue
        Write-Host '[AIOps] Monitoring account created.' -ForegroundColor Green
    } else {
        $secPass = ConvertTo-SecureString $monPass -AsPlainText -Force
        Set-LocalUser -Name $monUser -Password $secPass
        Write-Host '[AIOps] Monitoring account password refreshed.' -ForegroundColor Green
    }
} catch {
    Write-Host "[AIOps] Account setup warning: $($_.Exception.Message)" -ForegroundColor Yellow
    $monUser = $env:USERNAME
    $monPass = ''
}

# 3 - Gather machine info
$hostname = $env:COMPUTERNAME
try {
    $route = Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1
    $ip = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $route.InterfaceIndex -ErrorAction Stop).IPAddress
} catch { $ip = '127.0.0.1' }
$osCaption = (Get-WmiObject Win32_OperatingSystem).Caption
$arch      = $env:PROCESSOR_ARCHITECTURE

# 4 - Register with AIOps
$body = @{
    token    = $token
    hostname = $hostname
    ip       = $ip
    os       = $osCaption
    arch     = $arch
    username = $monUser
    password = $monPass
    port     = 5985
} | ConvertTo-Json -Compress

try {
    $resp = Invoke-RestMethod -Uri "$apiBase/api/wmi-register" -Method POST `
        -Body $body -ContentType 'application/json'
    Write-Host "[AIOps] SUCCESS: Machine '$($resp.label)' registered!" -ForegroundColor Green
    Write-Host "[AIOps] Agent ID : $($resp.agent_id)" -ForegroundColor Cyan
    Write-Host '[AIOps] Metrics will appear in the dashboard within 30 seconds.' -ForegroundColor Cyan
} catch {
    Write-Host "[AIOps] Registration FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
"""
    ps = ps.replace("__TOKEN__", token).replace("__API_BASE__", api_base)
    return PlainTextResponse(ps.strip(), media_type="text/plain")


@app.get("/api/wmi/setup-guide")
async def wmi_setup_guide(
    _auth: TokenPayload = Depends(require("agents:read")),
):
    """
    Returns the PowerShell command the end-user needs to run ONCE on their
    Windows machine to allow WinRM polling from the AIOps server.
    Admins can copy and send this to users via email/Slack/Teams.
    """
    return {
        "title": "Enable Remote Monitoring (One-Time Setup)",
        "steps": [
            {
                "step": 1,
                "description": "Open PowerShell as Administrator on your Windows machine",
            },
            {
                "step": 2,
                "description": "Run the following command:",
                "command": "Enable-PSRemoting -Force -SkipNetworkProfileCheck",
            },
            {
                "step": 3,
                "description": "That's it! Your machine is now ready to be monitored.",
            },
        ],
        "note": (
            "This enables Windows Remote Management (WinRM) on port 5985. "
            "Your IT admin will need your machine's IP address or hostname. "
            "No software is installed — this is a built-in Windows feature."
        ),
    }
