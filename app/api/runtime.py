from __future__ import annotations

import asyncio
import base64
import collections
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import (Agent, AgentActionLog, AlertRecord, AlertRule, Incident,
                               IncidentMemory, Investigation,
                               MetricSnapshot, NotificationChannel, NotificationLog,
                               OnboardingToken, Organization, RemediationJob,
                               SessionLocal, User, UserSession, get_db)
from app.core.pricing import PricingService

JWT_ALGORITHM = "HS256"
ACCESS_TTL_SECONDS = int(os.getenv("JWT_ACCESS_TTL", "86400"))
REFRESH_TTL_SECONDS = int(os.getenv("JWT_REFRESH_TTL", "2592000"))
STREAM_TTL_SECONDS = int(os.getenv("JWT_STREAM_TTL", "60"))
FAILED_ATTEMPT_LIMIT = 5
LOCKOUT_MINUTES = 15
_IS_PROD       = os.getenv("ENV", "dev").lower() == "production"
_FRONTEND_URL  = os.getenv("FRONTEND_URL", "http://localhost:3000")
_REFRESH_COOKIE = "rt"  # short name to reduce header size
_LOGIN_RATE_WINDOW = int(os.getenv("LOGIN_RATE_WINDOW", "60"))   # seconds
_LOGIN_RATE_LIMIT  = int(os.getenv("LOGIN_RATE_LIMIT",  "10"))   # max attempts per window per IP
_ALLOWED_ORIGINS   = {o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",") if o.strip()}

# IP-based sliding-window counter — Redis when available, in-memory fallback
_ip_attempts: dict[str, collections.deque] = {}
_ip_lock = threading.Lock()

# Optional Redis client — initialised once at import time if REDIS_URL is set
_redis: Any = None
try:
    _redis_url = os.getenv("REDIS_URL", "")
    if _redis_url:
        import redis as _redis_lib  # type: ignore
        _redis = _redis_lib.Redis.from_url(_redis_url, decode_responses=True, socket_connect_timeout=2)
        _redis.ping()  # fail fast if unreachable
        logging.getLogger(__name__).info("Redis rate limiter active: %s", _redis_url)
except Exception as _e:
    _redis = None
    logging.getLogger(__name__).warning("Redis unavailable (%s) — falling back to in-memory rate limiter", _e)

_auth_logger = logging.getLogger("auth.events")


def _check_ip_rate(ip: str) -> None:
    """Raise 429 if this IP has exceeded the login rate limit.
    Uses Redis sliding-window (ZADD/ZREMRANGEBYSCORE) when REDIS_URL is configured;
    falls back to an in-process deque when Redis is unavailable.
    """
    if not ip:
        return
    if _redis is not None:
        try:
            key  = f"rl:login:{ip}"
            now  = time.time()
            pipe = _redis.pipeline()
            pipe.zremrangebyscore(key, 0, now - _LOGIN_RATE_WINDOW)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, _LOGIN_RATE_WINDOW)
            results = pipe.execute()
            count = results[2]
            if count > _LOGIN_RATE_LIMIT:
                raise HTTPException(
                    status_code=429,
                    detail="Too many login attempts. Please wait before trying again.",
                    headers={"Retry-After": str(_LOGIN_RATE_WINDOW)},
                )
            return
        except HTTPException:
            raise
        except Exception:
            pass  # Redis error → fall through to in-memory
    # In-memory fallback
    now = time.monotonic()
    with _ip_lock:
        q = _ip_attempts.setdefault(ip, collections.deque())
        cutoff = now - _LOGIN_RATE_WINDOW
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= _LOGIN_RATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts. Please wait before trying again.",
                headers={"Retry-After": str(_LOGIN_RATE_WINDOW)},
            )
        q.append(now)


def _check_csrf(request: Request) -> None:
    """Reject requests from unexpected origins (protects cookie endpoints from CSRF).
    Only enforced in production; in dev, all localhost origins are allowed.
    """
    if not _IS_PROD:
        return
    origin = request.headers.get("origin") or request.headers.get("referer", "")
    if not any(origin.startswith(allowed) for allowed in _ALLOWED_ORIGINS):
        raise HTTPException(status_code=403, detail="CSRF check failed")


def _log_auth_event(event: str, *, email: str = "", user_id: str = "", ip: str = "", detail: str = "") -> None:
    _auth_logger.info(json.dumps({
        "event": event, "email": email, "user_id": user_id,
        "ip": ip, "detail": detail, "ts": _now().isoformat(),
    }))


def require_role(*roles: str):
    """FastAPI dependency that enforces role from the access token.

    Usage:  @router.post("/admin/thing", dependencies=[require_role("admin")])
    Or as a param:  payload = Depends(require_role("admin", "devops"))
    """
    async def _check(request: Request) -> dict[str, Any]:
        payload = await _require_access_token(request)
        if payload.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {', '.join(roles)}",
            )
        return payload
    return Depends(_check)


PASSWORD_ITERATIONS = 260000
DEFAULT_ADMIN_EMAIL = "admin@company.local"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_ORG = "default"
SSE_HEARTBEAT_SECONDS = int(os.getenv("SSE_HEARTBEAT_SECONDS", "30"))

# ── Cross-server correlation constants ────────────────────────────────────────
_CORR_CPU_THRESH   = float(os.getenv("CORR_CPU_THRESH",   "85"))
_CORR_MEM_THRESH   = float(os.getenv("CORR_MEM_THRESH",   "85"))
_CORR_DISK_THRESH  = float(os.getenv("CORR_DISK_THRESH",  "90"))
_CORR_MIN_AGENTS   = int(os.getenv("CORR_MIN_AGENTS",      "3"))
_CORR_WINDOW_SECS  = int(os.getenv("CORR_WINDOW_SECS",  "120"))  # 2-minute look-back
WS_QUEUE_MAX_SIZE = int(os.getenv("WS_QUEUE_MAX_SIZE", "100"))
MAX_CONNECTED_CLIENTS = int(os.getenv("MAX_CONNECTED_CLIENTS", "50"))


class RealtimeHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._clients = 0

    def subscribe(self, org_id: str) -> asyncio.Queue[dict[str, Any]]:
        with self._lock:
            if self._clients >= MAX_CONNECTED_CLIENTS:
                raise HTTPException(status_code=503, detail="Too many realtime clients connected")
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=WS_QUEUE_MAX_SIZE)
            self._subscribers.setdefault(org_id, set()).add(queue)
            self._clients += 1
            return queue

    def unsubscribe(self, org_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            subscribers = self._subscribers.get(org_id)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(org_id, None)
            if self._clients > 0:
                self._clients -= 1

    def publish(self, event_type: str, payload: dict[str, Any], org_id: str) -> None:
        event = {"type": event_type, "data": payload, "org_id": org_id}
        with self._lock:
            subscribers = list(self._subscribers.get(org_id, set()))
        for queue in subscribers:
            try:
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(event)
            except Exception:
                continue


class RegisterRequest(BaseModel):
    full_name: str
    email:     str
    username:  str
    password:  str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class MetricPayload(BaseModel):
    cpu: float
    memory: float
    disk: float
    network_in: int = 0
    network_out: int = 0
    temperature: float | None = None
    load_avg: str | None = None
    processes: int | None = None
    uptime_secs: int | None = None
    extra: dict[str, Any] | None = None
    # Extended metrics (Section 5A) — all Optional so old agents still work
    top_processes:   dict[str, Any] | None = None
    swap_percent:    float | None = None
    swap_used_gb:    float | None = None
    disk_read_mbps:  float | None = None
    disk_write_mbps: float | None = None
    net_established: int | None = None
    net_close_wait:  int | None = None
    net_time_wait:   int | None = None
    load_avg_1m:     float | None = None
    load_avg_5m:     float | None = None
    load_avg_15m:    float | None = None
    uptime_hours:    float | None = None
    battery_percent: float | None = None
    battery_plugged: bool | None = None
    disk_partitions: list | None = None


class HeartbeatRequest(BaseModel):
    org_id: str
    metrics: MetricPayload
    info: dict[str, Any] | None = None


class AlertCreateRequest(BaseModel):
    severity: str = Field(default="high")
    category: str = Field(default="cpu")
    title: str
    detail: str
    metric_value: float | None = None
    threshold: float | None = None
    status: str = Field(default="open")
    agent_id: str | None = None


class AgentCreateRequest(BaseModel):
    label: str
    key: str | None = None


class AgentUpdateRequest(BaseModel):
    label: str | None = None
    status: str | None = None
    is_active: bool | None = None


class AgentRegisterRequest(BaseModel):
    token: str
    label: str | None = None


class GoMetricPayload(BaseModel):
    token: str
    cpu: float
    memory: float
    disk: float = 0.0
    net_sent: int = 0
    net_recv: int = 0
    uptime: int = 0
    processes: int | None = None
    timestamp: datetime | None = None


class OrgSettingsUpdate(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


class ClerkSyncRequest(BaseModel):
    clerk_token: str
    email: str
    full_name: str = ""
    username: str = ""


_CLERK_JWKS_URL = os.getenv(
    "CLERK_JWKS_URL",
    "https://genuine-python-45.clerk.accounts.dev/.well-known/jwks.json",
)
_clerk_jwks_cache: dict = {}
_clerk_jwks_ts: float = 0.0
_clerk_jwks_ttl: float = 3600.0


async def _get_clerk_jwks() -> dict:
    global _clerk_jwks_cache, _clerk_jwks_ts
    if _clerk_jwks_cache and (time.time() - _clerk_jwks_ts < _clerk_jwks_ttl):
        return _clerk_jwks_cache
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(_CLERK_JWKS_URL)
        res.raise_for_status()
        _clerk_jwks_cache = res.json()
        _clerk_jwks_ts = time.time()
    return _clerk_jwks_cache


async def _verify_clerk_token(token: str) -> str | None:
    """Verify a Clerk-issued JWT via JWKS. Returns the Clerk user_id (sub) or None."""
    try:
        jwks = await _get_clerk_jwks()
        payload = jwt.decode(token, jwks, algorithms=["RS256"], options={"verify_aud": False})
        return payload.get("sub")
    except Exception as exc:
        logging.getLogger(__name__).warning("Clerk token verification failed: %s", exc)
        return None


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT secret is not configured")
    return secret


def _hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def _verify_password(password: str, hashed_password: str) -> bool:
    if hashed_password.startswith("$2"):
        try:
            import bcrypt

            return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
        except Exception:
            return False

    if not hashed_password.startswith("pbkdf2_sha256$"):
        return False
    try:
        _, iterations_text, salt_text, digest_text = hashed_password.split("$", 3)
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text.encode("ascii"))
        expected = base64.b64decode(digest_text.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _encode_token(payload: dict[str, Any]) -> str:
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def _build_token_payload(user: User, token_type: str, ttl_seconds: int, *, session_id: str | None = None) -> dict[str, Any]:
    if not user.org_id:
        raise HTTPException(status_code=403, detail="User is missing org_id")

    now = _now()
    payload = {
        "sub": user.id,
        "email": user.email,
        "username": user.username,
        "role": user.role,
        "org_id": user.org_id,
        "type": token_type,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "jti": session_id or str(uuid.uuid4()),
    }
    return payload


def _create_access_token(user: User) -> str:
    return _encode_token(_build_token_payload(user, "access", ACCESS_TTL_SECONDS))


def _create_refresh_token(user: User, session_id: str | None = None) -> str:
    return _encode_token(_build_token_payload(user, "refresh", REFRESH_TTL_SECONDS, session_id=session_id))


def _create_stream_token(user: User) -> str:
    return _encode_token(_build_token_payload(user, "stream", STREAM_TTL_SECONDS))


def _decode_token(token: str, token_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    if payload.get("type") != token_type:
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def _get_session_by_refresh_token(db: AsyncSession, refresh_token: str) -> UserSession | None:
    token_hash = _hash_refresh_token(refresh_token)
    result = await db.execute(select(UserSession).where(UserSession.refresh_token_hash == token_hash))
    return result.scalar_one_or_none()


def _serialize_org(org: Organization) -> dict[str, Any]:
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "plan": org.plan,
        "is_active": org.is_active,
        "settings": org.settings or {},
        "created_at": org.created_at.isoformat() if org.created_at else None,
    }


def _serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "org_id": user.org_id,
        "email": user.email,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "full_name": user.full_name,
        "two_factor_enabled": user.two_factor_enabled,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


def _serialize_metric(snapshot: MetricSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "org_id": snapshot.org_id,
        "agent_id": snapshot.agent_id,
        "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
        "cpu": snapshot.cpu,
        "memory": snapshot.memory,
        "disk": snapshot.disk,
        "network_in": snapshot.network_in,
        "network_out": snapshot.network_out,
        "temperature": snapshot.temperature,
        "load_avg": snapshot.load_avg,
        "processes": snapshot.processes,
        "uptime_secs": snapshot.uptime_secs,
        "extra": snapshot.extra or {},
        # Extended metrics
        "top_processes":   snapshot.top_processes,
        "swap_percent":    snapshot.swap_percent,
        "swap_used_gb":    snapshot.swap_used_gb,
        "disk_read_mbps":  snapshot.disk_read_mbps,
        "disk_write_mbps": snapshot.disk_write_mbps,
        "net_established": snapshot.net_established,
        "net_close_wait":  snapshot.net_close_wait,
        "net_time_wait":   snapshot.net_time_wait,
        "load_avg_1m":     snapshot.load_avg_1m,
        "load_avg_5m":     snapshot.load_avg_5m,
        "load_avg_15m":    snapshot.load_avg_15m,
        "uptime_hours":    snapshot.uptime_hours,
        "battery_percent": snapshot.battery_percent,
        "battery_plugged": snapshot.battery_plugged,
        "disk_partitions": snapshot.disk_partitions,
    }


def _serialize_alert(alert: AlertRecord) -> dict[str, Any]:
    return {
        "id": alert.id,
        "org_id": alert.org_id,
        "agent_id": alert.agent_id,
        "severity": alert.severity,
        "category": alert.category,
        "title": alert.title,
        "detail": alert.detail,
        "metric_value": alert.metric_value,
        "threshold": alert.threshold,
        "status": alert.status,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


_AGENT_LIVE_SECS = 45  # agent is "live" if heartbeat arrived within this window


def _compute_agent_status(agent: "Agent") -> str:
    """Compute real-time status from last_seen — never reads stale DB field."""
    if not agent.last_seen:
        return "pending"
    last = agent.last_seen if agent.last_seen.tzinfo else agent.last_seen.replace(tzinfo=timezone.utc)
    delta = (_now() - last).total_seconds()
    return "live" if delta < _AGENT_LIVE_SECS else "offline"


def _serialize_agent(agent: Agent) -> dict[str, Any]:
    pinfo = agent.platform_info or {}
    return {
        "id": agent.id,
        "org_id": agent.org_id,
        "label": agent.label,
        "status": _compute_agent_status(agent),
        "is_active": agent.is_active,
        "last_seen": agent.last_seen.isoformat() if agent.last_seen else None,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "platform_info": pinfo,
        "cpu": pinfo.get("last_cpu"),
        "memory": pinfo.get("last_memory"),
        "disk": pinfo.get("last_disk"),
        "hostname": pinfo.get("hostname"),
        "ai_history": _AI_HISTORY.get(agent.id, []),
        "execution_mode": _AGENT_EXEC_MODE.get(agent.id, "dry_run"),
        "source": agent.source or pinfo.get("source", "agent"),
    }


def _serialize_agent_action_log(entry: AgentActionLog) -> dict[str, Any]:
    return {
        "id": entry.id,
        "org_id": entry.org_id,
        "agent_id": entry.agent_id,
        "remediation_job_id": entry.remediation_job_id,
        "action": entry.action,
        "target": entry.target,
        "initiated_by": entry.initiated_by,
        "execution_mode": entry.execution_mode,
        "decision_source": entry.decision_source,
        "llm_raw_response": entry.llm_raw_response,
        "policy_evaluation": entry.policy_evaluation,
        "status": entry.status,
        "success": entry.success,
        "exit_code": entry.exit_code,
        "stdout": entry.stdout,
        "stderr": entry.stderr,
        "correlation_id": entry.correlation_id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "completed_at": entry.completed_at.isoformat() if entry.completed_at else None,
    }


async def _require_valid_access_payload(token: str) -> dict[str, Any]:
    payload = _decode_token(token, "access")
    async with SessionLocal() as db:
        user = await _get_user_by_id(db, payload["sub"])
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid token")
    return payload


async def _require_access_token(request: Request) -> dict[str, Any]:
    header = request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        return await _require_valid_access_payload(header.removeprefix("Bearer ").strip())

    token = request.query_params.get("token")
    if token:
        payload = _decode_token(token, "stream")
        async with SessionLocal() as db:
            user = await _get_user_by_id(db, payload["sub"])
            if user is None or not user.is_active:
                raise HTTPException(status_code=401, detail="Invalid token")
        return payload

    raise HTTPException(status_code=401, detail="Missing bearer token")


def get_realtime_hub_from_app(app: Any) -> RealtimeHub:
    hub = getattr(app.state, "realtime_hub", None)
    if hub is None:
        hub = RealtimeHub()
        app.state.realtime_hub = hub
    return hub


def _get_realtime_hub(request: Request) -> RealtimeHub:
    return get_realtime_hub_from_app(request.app)


async def _stream_realtime_events(
    event_types: str | set[str], org_id: str, request: Request
):
    """SSE generator. event_types can be a single string or a set for multi-type streams."""
    allowed: set[str] = {event_types} if isinstance(event_types, str) else set(event_types)
    hub = _get_realtime_hub(request)
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
            etype = event.get("type")
            if etype not in allowed:
                continue
            yield f"event: {etype}\ndata: {json.dumps(event['data'])}\n\n"
    finally:
        hub.unsubscribe(org_id, queue)


async def _require_org_access(request: Request, org_id: str) -> dict[str, Any]:
    payload = await _require_access_token(request)
    token_org = payload.get("org_id")
    role = payload.get("role")
    if not token_org:
        raise HTTPException(status_code=403, detail="Organization scope required")
    if token_org != org_id and role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden for this organization")
    return payload


_ALERT_RULES = [
    {"category": "cpu",    "severity": "critical", "threshold": 85.0, "recover": 80.0, "field": "cpu",
     "title": "High CPU usage",    "detail": "CPU usage exceeded {value:.1f}% (threshold {threshold:.0f}%)"},
    {"category": "memory", "severity": "high",     "threshold": 90.0, "recover": 85.0, "field": "memory",
     "title": "High memory usage", "detail": "Memory usage exceeded {value:.1f}% (threshold {threshold:.0f}%)"},
]


async def _send_alert_rule_to_channel(
    org_id: str,
    alert_id: str,
    channel: NotificationChannel,
    alert_data: dict,
) -> None:
    """Dispatch one notification for a fired AlertRule. Always writes a notification_logs row."""
    cfg = channel.config or {}
    status: str = "sent"
    error_msg: str | None = None

    try:
        if channel.channel_type == "slack":
            severity = alert_data.get("severity", "high")
            color = "danger" if severity in ("critical", "high") else "warning"
            payload = {
                "text": f":rotating_light: *{severity.upper()}* — {alert_data.get('title', 'Alert')}",
                "attachments": [{
                    "color": color,
                    "fields": [
                        {"title": "Category",     "value": alert_data.get("category", "—"),         "short": True},
                        {"title": "Metric Value", "value": f"{alert_data.get('metric_value', 0):.1f}%", "short": True},
                        {"title": "Detail",       "value": alert_data.get("detail", "—"),            "short": False},
                    ],
                }],
            }
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(cfg["webhook_url"], json=payload)
                r.raise_for_status()

        elif channel.channel_type == "email":
            # Delegate to existing notification_service which has full SMTP support
            try:
                from app.integrations.notification_service import dispatch_alert_notification
                async with SessionLocal() as _db:
                    await dispatch_alert_notification(_db, org_id, None, agent_label="")
            except Exception as _e:
                status = "pending"
                error_msg = f"Email deferred (service error): {_e}"

        else:
            status = "unsupported"
            error_msg = f"Channel type '{channel.channel_type}' not supported for alert rules"

    except Exception as exc:
        status = "failed"
        error_msg = str(exc)
        logging.warning("[NOTIFY] Channel %s (%s) failed: %s",
                        channel.id[:8], channel.channel_type, exc)

    # Always write a notification_logs audit row
    try:
        async with SessionLocal() as _log_db:
            _log_db.add(NotificationLog(
                id=str(uuid.uuid4()),
                org_id=org_id,
                alert_id=alert_id,
                channel_id=channel.id,
                channel_type=channel.channel_type,
                notification_type="alert",
                status=status,
                error=error_msg,
            ))
            await _log_db.commit()
    except Exception as _log_exc:
        logging.warning("[NOTIFY] Could not write notification_log: %s", _log_exc)


async def _notify_alert_rule(
    alert_id: str,
    org_id: str,
    channel_ids: list[str],
    alert_data: dict,
) -> None:
    """Background task: send notifications for a fired DB alert rule to its configured channels."""
    if not channel_ids:
        return
    async with SessionLocal() as db:
        for channel_id in channel_ids:
            result = await db.execute(
                select(NotificationChannel)
                .where(NotificationChannel.id == channel_id)
                .where(NotificationChannel.org_id == org_id)
                .where(NotificationChannel.enabled.is_(True))
            )
            channel = result.scalar_one_or_none()
            if not channel:
                continue
            await _send_alert_rule_to_channel(org_id, alert_id, channel, alert_data)


async def _alert_already_open(db: AsyncSession, agent_id: str, category: str) -> bool:
    """True if an open or acknowledged alert of this category already exists for this agent."""
    result = await db.execute(
        select(AlertRecord)
        .where(AlertRecord.agent_id == agent_id)
        .where(AlertRecord.category == category)
        .where(AlertRecord.status.in_(["open", "acknowledged"]))
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _check_anomalies(
    db: AsyncSession, org_id: str, agent_id: str, cpu: float, memory: float, disk: float = 0.0,
) -> tuple[list[AlertRecord], list[str], list[tuple[str, list[str], dict]]]:
    """Return (newly_created, resolved_ids, notify_pairs).
    notify_pairs = [(alert_id, channel_ids, alert_data)] for DB-rule alerts needing notifications."""
    values = {"cpu": cpu, "memory": memory, "disk": disk}
    created: list[AlertRecord] = []
    resolved_ids: list[str] = []
    notify_pairs: list[tuple[str, list[str], dict]] = []

    # ── Hardcoded rules ───────────────────────────────────────────────────────
    for rule in _ALERT_RULES:
        value = values.get(rule["field"], 0.0)

        if value >= rule["threshold"]:
            if await _alert_already_open(db, agent_id, rule["category"]):
                continue
            alert = AlertRecord(
                org_id=org_id,
                agent_id=agent_id,
                severity=rule["severity"],
                category=rule["category"],
                title=rule["title"],
                detail=rule["detail"].format(value=value, threshold=rule["threshold"]),
                metric_value=value,
                threshold=rule["threshold"],
                status="open",
            )
            db.add(alert)
            created.append(alert)

            existing_job = await db.execute(
                select(RemediationJob).where(
                    RemediationJob.org_id == org_id,
                    RemediationJob.alert_id == alert.id,
                    RemediationJob.status == "pending",
                )
            )
            if existing_job.scalar_one_or_none() is None:
                db.add(
                    RemediationJob(
                        org_id=org_id,
                        alert_id=alert.id,
                        playbook_type="restart_service",
                        status="pending",
                        attempts=0,
                        max_retries=1,
                        payload={"action": "restart_service", "target": agent_id, "agent_id": agent_id},
                        execution_mode="manual_approval",
                        decision_source="rule_fallback",
                        llm_raw_response=json.dumps({
                            "root_cause": f"{rule['category']} threshold exceeded",
                            "confidence": 0.91,
                            "impact": "high" if rule["severity"] == "high" else "critical",
                            "summary": f"Queued restart_service after {rule['category']} alert",
                            "recommended_action": "restart_service",
                            "safe_to_auto_fix": False,
                        }),
                        policy_evaluation={
                            "risk_level": "high",
                            "allowed": True,
                            "reason": "auto-queued from alert threshold",
                        },
                    )
                )

        elif value <= rule["recover"]:
            open_alerts = await db.execute(
                select(AlertRecord).where(
                    AlertRecord.agent_id == agent_id,
                    AlertRecord.category == rule["category"],
                    AlertRecord.status == "open",
                )
            )
            for alert in open_alerts.scalars().all():
                alert.status = "resolved"
                alert.resolved_at = _now()
                alert.resolution_reason = "Metric returned to normal"
                resolved_ids.append(alert.id)
                logging.info("[auto-resolve] %s alert resolved for agent %s", rule["category"], agent_id)

    # ── User-defined AlertRules from DB ───────────────────────────────────────
    try:
        db_rules_result = await db.execute(
            select(AlertRule).where(
                AlertRule.org_id == org_id,
                AlertRule.enabled.is_(True),
            ).where(
                (AlertRule.agent_id == agent_id) | (AlertRule.agent_id.is_(None))
            )
        )
        db_rules = db_rules_result.scalars().all()
        for db_rule in db_rules:
            value = values.get(db_rule.metric, 0.0)
            if value < db_rule.threshold:
                continue
            # Dedup: skip if an open/acknowledged alert of this category already exists
            if await _alert_already_open(db, agent_id, db_rule.metric):
                continue
            # Cooldown: skip if an alert (even resolved) was created within cooldown_minutes
            cooldown_cutoff = _now() - timedelta(minutes=db_rule.cooldown_minutes)
            existing = await db.execute(
                select(AlertRecord).where(
                    AlertRecord.agent_id == agent_id,
                    AlertRecord.category == db_rule.metric,
                    AlertRecord.status == "open",
                    AlertRecord.created_at >= cooldown_cutoff,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            alert = AlertRecord(
                org_id=org_id,
                agent_id=agent_id,
                severity=db_rule.severity,
                category=db_rule.metric,
                title=db_rule.name,
                detail=f"{db_rule.metric} at {value:.1f}% exceeded user-defined threshold {db_rule.threshold:.0f}%",
                metric_value=value,
                threshold=db_rule.threshold,
                status="open",
            )
            db.add(alert)
            created.append(alert)
            # Collect notify pair: alert_id is not yet assigned (pre-flush), stored by object ref
            if db_rule.notify_channels:
                notify_pairs.append((alert, list(db_rule.notify_channels), {
                    "severity":     db_rule.severity,
                    "title":        db_rule.name,
                    "category":     db_rule.metric,
                    "metric_value": value,
                    "detail":       f"{db_rule.metric} at {value:.1f}% exceeded threshold {db_rule.threshold:.0f}%",
                }))
            logging.info("[alert-rule] DB rule '%s' fired for agent %s (%s=%.1f%%)",
                         db_rule.name, agent_id, db_rule.metric, value)
    except Exception as _exc:
        logging.warning("[alert-rule] Failed to evaluate DB alert rules: %s", _exc)

    return created, resolved_ids, notify_pairs


# ── Cross-server correlation ──────────────────────────────────────────────────

async def _detect_correlated_spike(
    db: AsyncSession,
    org_id: str,
    trigger_agent_id: str,
    cpu: float,
    memory: float,
    disk: float,
    background_tasks: BackgroundTasks,
    hub: Any = None,
) -> "Incident | None":
    """Auto-create a SEV-2 incident when 3+ agents in the same org spike simultaneously.

    Returns the Incident if one was created or updated, else None.
    Never raises — all errors are logged and swallowed.
    """
    try:
        # 1. Is the current reading actually spiking?
        if cpu < _CORR_CPU_THRESH and memory < _CORR_MEM_THRESH and disk < _CORR_DISK_THRESH:
            return None

        # 2. Count agents with recent spikes (2-min window)
        cutoff = _now() - timedelta(seconds=_CORR_WINDOW_SECS)
        spike_result = await db.execute(
            select(MetricSnapshot.agent_id)
            .distinct()
            .where(
                MetricSnapshot.org_id == org_id,
                MetricSnapshot.timestamp >= cutoff,
            )
            .where(
                (MetricSnapshot.cpu >= _CORR_CPU_THRESH) |
                (MetricSnapshot.memory >= _CORR_MEM_THRESH) |
                (MetricSnapshot.disk >= _CORR_DISK_THRESH)
            )
        )
        spiking_ids: set[str] = {row[0] for row in spike_result.all()}
        # Always include the trigger agent (its snapshot may just have been written)
        spiking_ids.add(trigger_agent_id)

        if len(spiking_ids) < _CORR_MIN_AGENTS:
            return None

        # 3. Resolve agent labels for the description
        labels_result = await db.execute(
            select(Agent.id, Agent.label).where(Agent.id.in_(list(spiking_ids)))
        )
        agent_labels: dict[str, str] = {row[0]: row[1] for row in labels_result.all()}

        n = len(spiking_ids)
        label_list = ", ".join(agent_labels.get(aid, aid[:8]) for aid in list(spiking_ids)[:5])
        if n > 5:
            label_list += f" (+{n - 5} more)"

        # Determine dominant spike category
        if cpu >= _CORR_CPU_THRESH:
            spike_type = "CPU"
        elif memory >= _CORR_MEM_THRESH:
            spike_type = "Memory"
        else:
            spike_type = "Disk"

        now = _now()
        ts_str = now.isoformat()

        # 4. Check for an already-active incident — update timeline instead of creating duplicate
        existing_result = await db.execute(
            select(Incident)
            .where(Incident.org_id == org_id, Incident.status == "active")
            .order_by(Incident.declared_at.desc())
            .limit(1)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            timeline = list(existing.timeline or [])
            note = (f"Correlation update: {n} agents now spiking "
                    f"({spike_type}) — {label_list}.")
            timeline.append({"ts": ts_str, "actor": "system", "note": note})
            existing.timeline = timeline
            await db.commit()
            logging.info("[CORRELATION] Updated timeline of existing incident %s (%d agents)", existing.id, n)
            return existing

        # 5. Create new SEV-2 incident
        inc_id = f"INC-{now.strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
        description = (
            f"Auto-detected: {n} agents reporting high {spike_type} simultaneously. "
            f"Affected: {label_list}. Possible fleet-wide event."
        )
        timeline_entry = {
            "ts": ts_str,
            "actor": "system",
            "note": f"Auto-created by correlation engine ({n} agents spiking {spike_type}).",
        }

        incident = Incident(
            id=inc_id,
            org_id=org_id,
            severity="SEV2",
            service="Fleet-Wide",
            description=description,
            status="active",
            timeline=[timeline_entry],
        )
        db.add(incident)
        await db.flush()

        # Build per-agent context for the LLM call
        affected: list[dict] = []
        for aid in spiking_ids:
            affected.append({
                "agent_id": aid,
                "label": agent_labels.get(aid, aid),
                "cpu": cpu if aid == trigger_agent_id else 0.0,
                "memory": memory if aid == trigger_agent_id else 0.0,
                "disk": disk if aid == trigger_agent_id else 0.0,
            })

        background_tasks.add_task(_lc_analyze_incident, inc_id, org_id, affected)
        await db.commit()

        if hub is not None:
            try:
                hub.publish("incident_update", {
                    "id": inc_id, "severity": "SEV2", "status": "active",
                    "service": "Fleet-Wide", "description": description,
                    "agent_count": n,
                }, org_id)
            except Exception:
                pass

        logging.warning("[CORRELATION] SEV-2 incident %s auto-created: %d agents spiking %s",
                        inc_id, n, spike_type)
        return incident

    except Exception as _exc:
        logging.error("[CORRELATION] _detect_correlated_spike failed: %s", _exc)
        return None


async def _lc_analyze_incident(incident_id: str, org_id: str, affected: list[dict]) -> None:
    """Single LLM call with all affected machines as context; appends result to incident timeline."""
    agent_lines = "\n".join(
        f"  - {a['label']}: cpu={a['cpu']:.1f}%  mem={a['memory']:.1f}%  disk={a['disk']:.1f}%"
        for a in affected
    )
    n = len(affected)
    system_prompt = (
        "You are a senior SRE analyzing a cross-server incident. "
        "Respond with valid JSON only — no markdown fences, no prose outside the object."
    )
    user_msg = (
        f"{n} servers in the same organisation are spiking simultaneously:\n"
        f"{agent_lines}\n\n"
        "Respond with this exact JSON schema:\n"
        '{"likely_cause":"<1-2 sentence root-cause hypothesis>","confidence":<0.0-1.0>,'
        '"recommended_action":"<single most impactful remediation step>",'
        '"is_fleet_wide":<true|false>}'
    )

    data: dict = {}
    try:
        raw = await asyncio.wait_for(_call_llm(system_prompt, user_msg), timeout=30.0)
        # Strip optional fences
        j_start = raw.find("{")
        j_end   = raw.rfind("}") + 1
        data = json.loads(raw[j_start:j_end]) if j_start != -1 else {}
    except Exception as _exc:
        logging.warning("[CORRELATION] LLM incident analysis failed: %s", _exc)
        data = {
            "likely_cause": (
                "Multiple servers spiking concurrently — possible shared dependency, "
                "bad deployment, or upstream infrastructure event."
            ),
            "confidence": 0.4,
            "recommended_action": "Check recent deployments and shared infrastructure (DB, cache, LB).",
            "is_fleet_wide": True,
        }

    note = (
        f"AI analysis (confidence={data.get('confidence', 0):.0%}): "
        f"{data.get('likely_cause', '?')} — "
        f"Recommended: {data.get('recommended_action', '?')}"
    )

    try:
        async with SessionLocal() as db:
            result = await db.execute(select(Incident).where(Incident.id == incident_id))
            incident = result.scalar_one_or_none()
            if incident is None:
                return
            timeline = list(incident.timeline or [])
            timeline.append({
                "ts": _now().isoformat(), "actor": "ai",
                "note": note, "data": data,
            })
            incident.timeline = timeline
            await db.commit()
        logging.info("[CORRELATION] AI analysis appended to incident %s", incident_id)
    except Exception as _exc:
        logging.error("[CORRELATION] Failed to save incident AI note: %s", _exc)


# ---------------------------------------------------------------------------
# Backend action handlers — called directly by the server (not the agent)
# ---------------------------------------------------------------------------

async def _restart_service(target: str, params: dict) -> dict:
    """kubectl rollout restart deployment/<target>."""
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    if dry_run:
        logging.info("[DRY_RUN] would restart deployment/%s", target)
        return {"action": "restart_service", "target": target, "status": "dry_run"}
    ns = params.get("namespace", os.getenv("KUBE_NAMESPACE", "default"))
    proc = await asyncio.create_subprocess_shell(
        f"kubectl rollout restart deployment/{target} -n {ns}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    ok = proc.returncode == 0
    logging.info("[ACTION] restart_service %s ns=%s ok=%s", target, ns, ok)
    return {"action": "restart_service", "target": target, "status": "ok" if ok else "error",
            "stderr": stderr.decode(errors="replace")}


async def _scale_deployment(target: str, params: dict) -> dict:
    """kubectl scale deployment/<target> --replicas=N."""
    dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
    replicas = int(params.get("replicas", 2))
    ns = params.get("namespace", os.getenv("KUBE_NAMESPACE", "default"))
    if dry_run:
        logging.info("[DRY_RUN] would scale deployment/%s to %d replicas", target, replicas)
        return {"action": "scale_deployment", "target": target, "replicas": replicas, "status": "dry_run"}
    proc = await asyncio.create_subprocess_shell(
        f"kubectl scale deployment/{target} --replicas={replicas} -n {ns}",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
    ok = proc.returncode == 0
    logging.info("[ACTION] scale_deployment %s replicas=%d ok=%s", target, replicas, ok)
    return {"action": "scale_deployment", "target": target, "replicas": replicas,
            "status": "ok" if ok else "error", "stderr": stderr.decode(errors="replace")}


async def _notify_only(target: str, params: dict) -> dict:
    """Post alert notification to Slack webhook."""
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        logging.warning("[ACTION] SLACK_WEBHOOK_URL not set — notification skipped for %s", target)
        return {"action": "notify_only", "target": target, "status": "skipped"}
    msg = params.get("message", f"AIOps alert on {target}")
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(webhook, json={"text": f":warning: *AIOps Agent* — {msg}"})
        r.raise_for_status()
    logging.info("[ACTION] notify_only sent to Slack for %s", target)
    return {"action": "notify_only", "target": target, "status": "ok"}


async def _create_incident(target: str, params: dict) -> dict:
    """Trigger PagerDuty incident via Events API v2."""
    key = os.getenv("PAGERDUTY_ROUTING_KEY")
    if not key:
        logging.warning("[ACTION] PAGERDUTY_ROUTING_KEY not set — incident skipped for %s", target)
        return {"action": "create_incident", "target": target, "status": "skipped"}
    body = {
        "routing_key": key,
        "event_action": "trigger",
        "payload": {
            "summary": params.get("summary", f"AIOps: incident on {target}"),
            "severity": params.get("severity", "warning"),
            "source": target,
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post("https://events.pagerduty.com/v2/enqueue", json=body)
        r.raise_for_status()
    logging.info("[ACTION] create_incident triggered for %s dedup=%s", target, r.json().get("dedup_key"))
    return {"action": "create_incident", "target": target,
            "dedup_key": r.json().get("dedup_key"), "status": "ok"}


async def _dispatch_action(action: str, target: str, params: dict | None = None) -> dict:
    """Dispatch a resolved AI action to the appropriate backend handler."""
    p = params or {}
    try:
        if action == "restart_service":
            return await _restart_service(target, p)
        if action == "scale_deployment":
            return await _scale_deployment(target, p)
        if action == "notify_only":
            return await _notify_only(target, p)
        if action == "create_incident":
            return await _create_incident(target, p)
        logging.info("[DISPATCH] No backend handler for action=%s target=%s — agent will handle", action, target)
        return {"action": action, "target": target, "status": "agent_queued"}
    except Exception as exc:
        logging.error("[DISPATCH] action=%s target=%s failed: %s", action, target, exc)
        return {"action": action, "target": target, "status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------


async def _call_llm(system_prompt: str, user_message: str) -> str:
    """Gemini via direct REST API (httpx) — avoids google-generativeai SDK version conflicts."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY (or GOOGLE_API_KEY) not set")

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}"
        f":generateContent?key={api_key}"
    )
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _lc_analyze_cooldown_ok(agent_id: str) -> bool:
    """Return True if enough time has elapsed since the last LLM call for this agent."""
    return (time.time() - _LC_ANALYZE_LAST_RUN.get(agent_id, 0.0)) >= LC_ANALYZE_COOLDOWN_SECS


def _lc_analyze_mark_ran(agent_id: str) -> None:
    _LC_ANALYZE_LAST_RUN[agent_id] = time.time()


async def _get_confidence_threshold(org_id: str) -> float:
    """Return per-org AI confidence threshold, falling back to the global default."""
    try:
        async with SessionLocal() as _db:
            result = await _db.execute(
                select(Organization.ai_confidence_threshold).where(Organization.id == org_id)
            )
            val = result.scalar_one_or_none()
            return float(val) if val is not None else AUTO_EXEC_CONFIDENCE_THRESHOLD
    except Exception:
        return AUTO_EXEC_CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# THE single AI analysis path. All new AI logic goes here.
# _ai_analyze (NVIDIA NIM direct path) was removed — it was never called.
# ---------------------------------------------------------------------------

AUTO_EXEC_CONFIDENCE_THRESHOLD: float = 0.72

_LC_ALLOWED_ACTIONS: frozenset[str] = frozenset({
    "free_memory", "disk_cleanup", "clear_cache", "run_gc",
    "kill_process", "restart_service", "notify_only",
})

_LC_SYSTEM_PROMPT = """\
You are an AIOps remediation agent. You monitor remote machines and decide
what action to take when an anomaly is detected.

You will be given:
- Current system metrics
- Recent alert history for this machine
- Past actions taken and whether they succeeded
- Action success rates from historical data

Your job is to reason step by step and return a single JSON object.

Rules:
- Only recommend actions from the allowed action list
- Never recommend an action that failed twice in a row on this machine
- If success rate for an action is below 30%, prefer an alternative
- If you are not confident (< 0.6), recommend notify_only
- Always explain your reasoning before the JSON

Allowed actions: free_memory, disk_cleanup, clear_cache, run_gc,
kill_process, restart_service, notify_only

Respond with your reasoning first, then end with exactly this JSON block:
```json
{
  "action": "<action_name>",
  "confidence": <0.0-1.0>,
  "root_cause": "<one sentence>",
  "summary": "<two sentences max>",
  "safe_to_auto_fix": <true|false>,
  "reasoning_steps": ["step1", "step2", "step3"]
}
```\
"""


def _top_process(metrics: dict) -> str:
    """Return the top CPU process label from top_processes, or 'unknown'."""
    tp = metrics.get("top_processes") or {}
    by_cpu = tp.get("by_cpu") or []
    if by_cpu:
        p = by_cpu[0]
        return f"{p.get('name', '?')} ({p.get('cpu_percent', 0):.1f}% cpu)"
    return "unknown"


def _fmt_history(history: list) -> str:
    """Format last 5 AI decisions for the prompt context block."""
    if not history:
        return "  (none)"
    lines = []
    for h in history[:5]:
        ts = (h.get("timestamp") or "")[:19]
        lines.append(
            f"  [{ts}] {h.get('alert_category','?')} → "
            f"{h.get('recommended_action','?')} "
            f"(conf={h.get('confidence',0):.2f}, status={h.get('status','?')})"
        )
    return "\n".join(lines)


def _fmt_feedback(feedback: list) -> str:
    """Format last 10 action outcomes for the prompt context block."""
    if not feedback:
        return "  (none)"
    lines = []
    for f in feedback[:10]:
        ok = "✓" if f.get("success") else "✗"
        lines.append(
            f"  {ok} {f.get('action','?')} → "
            f"cpu {f.get('cpu_before','?')}%→{f.get('cpu_after','?')}%  "
            f"mem {f.get('memory_before','?')}%→{f.get('memory_after','?')}%"
        )
    return "\n".join(lines)


def _fmt_success_rates(rates: dict) -> str:
    """Format per-action success rates for the prompt context block."""
    lines = [
        f"  {act}: {round(rate * 100)}%" if rate is not None else f"  {act}: no data"
        for act, rate in rates.items()
    ]
    return "\n".join(lines) if lines else "  (no history)"


def _build_context(
    agent_id: str,
    metrics: dict,
    alert: dict,
    ai_history: list,
    feedback: list,
    success_rates: dict,
) -> str:
    """Build the per-call user message injected into the LLM prompt."""
    return (
        f"MACHINE STATE:\n"
        f"  CPU:    {metrics.get('cpu', 0):.1f}%\n"
        f"  Memory: {metrics.get('memory', 0):.1f}%\n"
        f"  Disk:   {metrics.get('disk', 0):.1f}%\n"
        f"  Top process: {_top_process(metrics)}\n\n"
        f"ALERT:\n"
        f"  Category: {alert.get('category')}\n"
        f"  Severity: {alert.get('severity')}\n"
        f"  Detail:   {alert.get('detail', '')}\n\n"
        f"RECENT AI DECISIONS (last 5):\n"
        f"{_fmt_history(ai_history)}\n\n"
        f"PAST ACTION OUTCOMES (last 10):\n"
        f"{_fmt_feedback(feedback)}\n\n"
        f"ACTION SUCCESS RATES:\n"
        f"{_fmt_success_rates(success_rates)}"
    )


def _rule_fallback(metrics: dict, alert: dict) -> dict:
    """Deterministic fallback used when LLM times out or parse fails."""
    cpu  = float(metrics.get("cpu",    0) or 0)
    mem  = float(metrics.get("memory", 0) or 0)
    disk = float(metrics.get("disk",   0) or 0)
    if mem >= 85:
        return {"action": "free_memory", "confidence": 0.75,
                "root_cause": "Memory above critical threshold",
                "summary": "Rule-based: memory critical, freeing caches.",
                "safe_to_auto_fix": True,
                "reasoning_steps": ["Memory >= 85%", "Rule: free_memory"],
                "decision_source": "rule_fallback"}
    if cpu >= 90:
        return {"action": "free_memory", "confidence": 0.65,
                "root_cause": "CPU above critical threshold",
                "summary": "Rule-based: CPU critical, attempting cache clear.",
                "safe_to_auto_fix": True,
                "reasoning_steps": ["CPU >= 90%", "Rule: free_memory"],
                "decision_source": "rule_fallback"}
    if disk >= 90:
        return {"action": "disk_cleanup", "confidence": 0.80,
                "root_cause": "Disk above critical threshold",
                "summary": "Rule-based: disk critical, running cleanup.",
                "safe_to_auto_fix": True,
                "reasoning_steps": ["Disk >= 90%", "Rule: disk_cleanup"],
                "decision_source": "rule_fallback"}
    return {"action": "notify_only", "confidence": 0.5,
            "root_cause": "Anomaly detected, cause unclear",
            "summary": "Rule-based: no clear action, notifying only.",
            "safe_to_auto_fix": False,
            "reasoning_steps": ["No threshold matched", "Rule: notify_only"],
            "decision_source": "rule_fallback"}


async def _lc_analyze(
    alert: AlertRecord,
    cpu: float,
    memory: float,
    org_id: str = "",
    top_processes: dict | None = None,
    load_avg_1m: float | None = None,
    load_avg_5m: float | None = None,
    load_avg_15m: float | None = None,
) -> None:
    """Context-rich agentic reasoning loop. Background task — never raises."""
    from app.agents.langchain_agent import can_auto_execute

    exec_mode = _AGENT_EXEC_MODE.get(alert.agent_id, "dry_run")
    logging.info("[AGENT] Alert received: agent=%s mode=%s category=%s",
                 alert.agent_id, exec_mode, alert.category)

    # ── Fix 1: Rate limit — skip LLM if this agent was analyzed recently ──────
    if not _lc_analyze_cooldown_ok(alert.agent_id):
        logging.info("[AGENT] Rate limited agent=%s (cooldown=%ds) — rule fallback",
                     alert.agent_id, LC_ANALYZE_COOLDOWN_SECS)
        _rl_decision = _rule_fallback(
            {"cpu": cpu, "memory": memory, "disk": 0.0},
            {"category": alert.category, "severity": alert.severity},
        )
        _rl_record = {
            "timestamp":          _now().isoformat(),
            "alert_category":     alert.category,
            "severity":           alert.severity,
            "root_cause":         _rl_decision.get("root_cause", ""),
            "confidence":         _rl_decision["confidence"],
            "impact":             alert.severity,
            "summary":            f"[Rate limited] {_rl_decision.get('summary', '')}",
            "recommended_action": _rl_decision["action"],
            "reasoning_steps":    _rl_decision.get("reasoning_steps", []),
            "safe_to_auto_fix":   _rl_decision.get("safe_to_auto_fix", False),
            "status":             "rate_limited",
            "decision_source":    "rate_limited",
            "block_reason":       f"LLM cooldown active ({LC_ANALYZE_COOLDOWN_SECS}s between calls)",
        }
        hist = _AI_HISTORY.setdefault(alert.agent_id, [])
        hist.insert(0, _rl_record)
        if len(hist) > 10:
            hist.pop()
        return

    _lc_analyze_mark_ran(alert.agent_id)

    # ── 1-4. MULTI-STAGE INVESTIGATION PIPELINE ───────────────────────────────
    from app.api.investigation_engine import run_investigation, ActionRouting as _ActionRouting

    extra_metrics = {
        "top_processes": top_processes,
        "load_avg_1m":   load_avg_1m,
        "load_avg_5m":   load_avg_5m,
        "load_avg_15m":  load_avg_15m,
    }
    raw = ""
    inv_result = None
    try:
        async with SessionLocal() as _inv_db:
            inv_result = await run_investigation(
                db=_inv_db,
                alert=alert,
                org_id=org_id or alert.org_id,
                agent_id=alert.agent_id,
                cpu=cpu,
                memory=memory,
                disk=0.0,
                extra_metrics=extra_metrics,
                call_llm_fn=_call_llm,
            )
            await _inv_db.commit()
    except Exception as _inv_exc:
        logging.warning("[AGENT] Investigation pipeline failed: %s", _inv_exc)

    metrics = {
        "cpu": cpu, "memory": memory, "disk": 0.0, "top_processes": top_processes,
        "load_avg_1m": load_avg_1m, "load_avg_5m": load_avg_5m, "load_avg_15m": load_avg_15m,
    }
    alert_dict = {"category": alert.category, "severity": alert.severity, "detail": alert.detail}
    alert_context = f"{alert.category}:{alert.severity}"

    if inv_result is not None:
        action = inv_result.recommended_action
        if action not in _LC_ALLOWED_ACTIONS:
            action = "notify_only"
        decision: dict = {
            "action":           action,
            "confidence":       inv_result.confidence,
            "root_cause":       inv_result.root_cause.root_cause,
            "summary":          (inv_result.root_cause.reasoning_steps or [""])[-1],
            "safe_to_auto_fix": inv_result.action_routing == _ActionRouting.AUTO_EXECUTE,
            "reasoning_steps":  inv_result.root_cause.reasoning_steps,
            "decision_source":  "llm",
            "investigation_id": inv_result.investigation_id,
            "action_routing":   inv_result.action_routing.value,
        }
        logging.info("[AGENT] Investigation complete: action=%s conf=%.2f routing=%s",
                     action, inv_result.confidence, inv_result.action_routing.value)
    else:
        decision = _rule_fallback(metrics, alert_dict)
        action   = decision["action"]
        decision["investigation_id"] = None
        decision["action_routing"]   = "investigation_only"

    # Derive target from action type
    target = (
        "system" if action in ("free_memory", "disk_cleanup", "clear_cache", "run_gc")
        else alert.category
    )

    # ── Confidence calibration: blend with historical success rate ─────────────
    success_rate = _get_success_rate(alert.agent_id, action, alert_context)
    if success_rate is not None:
        blended = round(decision["confidence"] * 0.6 + success_rate * 0.4, 2)
        logging.info("[AGENT] Calibrated confidence %.2f → %.2f (success_rate=%.0f%%)",
                     decision["confidence"], blended, success_rate * 100)
        decision["confidence"] = blended

    # ── 5. GATE ON EXECUTION MODE ─────────────────────────────────────────────
    block_reason: str | None = None

    # notify_only is never dispatched as a command — log to audit_logs and skip queueing
    if action == "notify_only":
        disp_status = "notify_only"
        try:
            async with SessionLocal() as _db:
                await _db.execute(text(
                    "INSERT INTO audit_logs (id, org_id, agent_id, action, detail) "
                    "VALUES (:id, :org_id, :agent_id, 'ai_notify_only', :detail)"
                ), {
                    "id":        str(uuid.uuid4()),
                    "org_id":    alert.org_id,
                    "agent_id":  alert.agent_id,
                    "detail":    json.dumps({
                        "root_cause": decision.get("root_cause"),
                        "summary":    decision.get("summary"),
                        "confidence": decision["confidence"],
                    }),
                })
                await _db.commit()
        except Exception as _al_exc:
            logging.warning("[AGENT] Could not write audit log for notify_only: %s", _al_exc)
        logging.info("[AGENT] notify_only — decision logged, no command queued (agent=%s)", alert.agent_id)

    elif exec_mode == "dry_run":
        disp_status = "dry_run"
        logging.info("[AGENT] dry_run — recommended: %s → %s", action, target)

    elif exec_mode == "manual_approval":
        _PENDING_APPROVALS.setdefault(alert.agent_id, []).append({
            "id":             str(uuid.uuid4()),
            "action":         action,
            "target":         target,
            "alert_category": alert.category,
            "created_at":     _now().isoformat(),
        })
        disp_status = "needs_approval"
        logging.info("[AGENT] manual_approval — queued: %s → %s", action, target)

    elif exec_mode == "auto_safe":
        # Investigation-only routing: AI confidence < 70% — record but do not execute
        if decision.get("action_routing") == "investigation_only":
            disp_status = "investigation_only"
            block_reason = (f"AI confidence {decision['confidence']:.0%} below 70% threshold "
                            f"— investigation recorded, no action taken")
            logging.info("[AGENT] investigation_only routing — no command queued (agent=%s conf=%.2f)",
                         alert.agent_id, decision["confidence"])

        else:
            restart_count = 0
            try:
                async with SessionLocal() as _db:
                    from sqlalchemy import func as _sqlfunc
                    one_hour_ago = _now() - timedelta(hours=1)
                    row = await _db.execute(
                        select(_sqlfunc.count()).where(
                            AgentActionLog.agent_id == alert.agent_id,
                            AgentActionLog.action == "restart_service",
                            AgentActionLog.created_at >= one_hour_ago,
                        )
                    )
                    restart_count = row.scalar() or 0
            except Exception as _rc_exc:
                logging.warning("[AGENT] Could not query restart count: %s", _rc_exc)

            allowed, block_reason = can_auto_execute(action, target, alert.agent_id, restart_count)
            org_threshold = await _get_confidence_threshold(org_id or alert.org_id)
            min_conf = max(org_threshold, _CONFIDENCE_THRESHOLDS.get(action, org_threshold))
            low_conf = decision["confidence"] < min_conf

            if allowed and decision["safe_to_auto_fix"] and not low_conf:
                try:
                    from app.core.remediation_dispatch import safe_enqueue_command
                    dispatch_result = await safe_enqueue_command(
                        db=None,
                        org_id=alert.org_id,
                        agent_id=alert.agent_id,
                        command=action,
                        target=target,
                        args=None,
                        role="system",
                        initiated_by=None,
                        llm_raw_response=raw or json.dumps(decision),
                        correlation_id=None,
                    )
                    disp_status = "queued" if dispatch_result.get("dispatched") else "needs_approval"
                    logging.info("[AGENT] auto_safe dispatched: %s → %s (risk=%s)",
                                 action, target, dispatch_result.get("risk_level"))
                    asyncio.create_task(_schedule_feedback_check(
                        alert.agent_id, action, target,
                        cpu, memory, metrics.get("disk", 0.0),
                        alert_context, exec_mode,
                        org_id=alert.org_id,
                    ))
                except HTTPException as _he:
                    disp_status = "blocked"
                    block_reason = _he.detail
                    logging.warning("[AGENT] auto_safe blocked by policy: %s", block_reason)
                except Exception as _disp_exc:
                    disp_status = "error"
                    block_reason = str(_disp_exc)
                    logging.error("[AGENT] auto_safe dispatch failed: %s", _disp_exc)
            else:
                if low_conf:
                    block_reason = (f"confidence {decision['confidence']:.2f} < "
                                    f"{min_conf:.2f} for {action} (org threshold: {org_threshold:.2f})")
                disp_status = "needs_review"
                logging.info("[AGENT] auto_safe blocked: %s", block_reason or "unsafe action")

    else:
        disp_status = "dry_run"

    # ── 6. STORE DECISION ─────────────────────────────────────────────────────
    record = {
        "timestamp":          _now().isoformat(),
        "alert_category":     alert.category,
        "severity":           alert.severity,
        "root_cause":         decision.get("root_cause", ""),
        "confidence":         decision["confidence"],
        "impact":             alert.severity,
        "summary":            decision.get("summary", ""),
        "recommended_action": action,
        "reasoning_steps":    decision.get("reasoning_steps", []),
        "safe_to_auto_fix":   decision.get("safe_to_auto_fix", False),
        "status":             disp_status,
        "decision_source":    decision.get("decision_source", "llm"),
        "block_reason":       block_reason if disp_status in ("needs_review", "blocked", "investigation_only") else None,
        "investigation_id":   decision.get("investigation_id"),
        "action_routing":     decision.get("action_routing"),
    }

    hist = _AI_HISTORY.setdefault(alert.agent_id, [])
    hist.insert(0, record)
    if len(hist) > 10:
        hist.pop()

    try:
        async with SessionLocal() as _db:
            await _db.execute(text(
                "INSERT INTO agent_action_log "
                "(agent_id, action, target, success, decision_source, llm_raw_response, metadata_json) "
                "VALUES (:agent_id, :action, :target, :success, :source, :llm, :meta)"
            ), {
                "agent_id": alert.agent_id,
                "action":   action,
                "target":   target or "",
                "success":  disp_status == "queued",
                "source":   decision.get("decision_source", "llm"),
                "llm":      raw or None,
                "meta":     json.dumps(record),
            })
            await _db.commit()
    except Exception as _db_exc:
        logging.warning("[AGENT] Could not persist AI decision: %s", _db_exc)


def _get_success_rate(agent_id: str, action: str, context: str | None = None) -> float | None:
    """Return historical success rate for (agent, action[, context]) or None if no history."""
    all_records = [r for r in _ACTION_FEEDBACK.get(agent_id, []) if r["action"] == action]
    records = [r for r in all_records if r.get("context") == context] if context else all_records
    if not records:
        return None
    return sum(1 for r in records if r["success"]) / len(records)


def _get_failure_streak(agent_id: str, action: str, context: str = "") -> int:
    """Count consecutive failures for (action, context) — newest first."""
    records = [r for r in _ACTION_FEEDBACK.get(agent_id, [])
               if r["action"] == action and r.get("context", "") == context]
    streak = 0
    for r in records:
        if not r["success"]:
            streak += 1
        else:
            break
    return streak


def _get_action_rankings(agent_id: str, context: str = "") -> list[dict]:
    """Return all actions ranked by context-aware success rate (highest first)."""
    ranked = []
    for act in _ALL_ACTIONS:
        rate = _get_success_rate(agent_id, act, context)
        if rate is None:
            rate = _get_success_rate(agent_id, act)  # fallback to global
        ranked.append({"action": act, "rate": rate})
    ranked.sort(key=lambda x: (x["rate"] is None, -(x["rate"] or 0)))
    return ranked


def _compute_success_rates(agent_id: str) -> dict[str, float | None]:
    """
    Canonical success-rate computation for an agent across all actions.
    Returns {action: rate} where rate is None when fewer than 3 attempts exist.
    Only the last 20 attempts per action are considered.
    """
    feedback = _ACTION_FEEDBACK.get(agent_id, [])
    counts: dict[str, list[bool]] = {}
    for f in feedback:
        act = f.get("action")
        if act:
            counts.setdefault(act, []).append(bool(f.get("success")))
    result: dict[str, float | None] = {}
    for act, outcomes in counts.items():
        last20 = outcomes[-20:]
        result[act] = round(sum(last20) / len(last20), 2) if len(last20) >= 3 else None
    return result


def _action_succeeded(action: str, before: dict, after: dict) -> bool:
    """Determine if an action actually worked based on what it targets."""
    delta_cpu = before.get("cpu",    0.0) - after.get("cpu",    0.0)
    delta_mem = before.get("memory", 0.0) - after.get("memory", 0.0)
    delta_dsk = before.get("disk",   0.0) - after.get("disk",   0.0)

    if action in ("free_memory", "run_gc"):
        return delta_mem >= 3.0
    if action in ("clear_cache",):
        return delta_mem >= 2.0 or delta_cpu >= 3.0
    if action in ("disk_cleanup",):
        return delta_dsk >= 0.5
    if action in ("kill_process",):
        return delta_cpu >= 5.0 or delta_mem >= 3.0
    if action in ("restart_service",):
        return delta_cpu >= 2.0
    return (delta_cpu + delta_mem) >= 3.0


async def _schedule_feedback_check(
    agent_id: str, action: str, target: str,
    cpu_before: float, memory_before: float, disk_before: float = 0.0,
    context: str = "", exec_mode: str = "dry_run",
    retry_count: int = 0, retry_of: str = "",
    org_id: str = "",
) -> None:
    """Wait 30 s then measure whether the action improved metrics. Retries on failure (max 2)."""
    _MAX_RETRIES = 2
    await asyncio.sleep(30)
    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(MetricSnapshot)
                .where(MetricSnapshot.agent_id == agent_id)
                .order_by(desc(MetricSnapshot.timestamp))
                .limit(1)
            )
            snap = result.scalar_one_or_none()
            if snap is None:
                return
            cpu_after    = snap.cpu    or 0.0
            memory_after = snap.memory or 0.0
            disk_after   = snap.disk   or 0.0

            before = {"cpu": cpu_before, "memory": memory_before, "disk": disk_before}
            after  = {"cpu": cpu_after,  "memory": memory_after,  "disk": disk_after}
            success = _action_succeeded(action, before, after)

            feedback = {
                "timestamp":     _now().isoformat(),
                "action":        action,
                "target":        target,
                "context":       context,
                "retry_count":   retry_count,
                "retry_of":      retry_of,
                "cpu_before":    round(cpu_before,    1),
                "cpu_after":     round(cpu_after,     1),
                "memory_before": round(memory_before, 1),
                "memory_after":  round(memory_after,  1),
                "disk_before":   round(disk_before,   1),
                "disk_after":    round(disk_after,    1),
                "success":       success,
            }
            hist = _ACTION_FEEDBACK.setdefault(agent_id, [])
            hist.insert(0, feedback)
            if len(hist) > 20:
                hist.pop()
            logging.info(
                "[FEEDBACK] agent=%s action=%s success=%s retry=%d "
                "cpu=%.1f→%.1f mem=%.1f→%.1f disk=%.1f→%.1f",
                agent_id, action, success, retry_count,
                cpu_before, cpu_after, memory_before, memory_after, disk_before, disk_after,
            )

            # Persist feedback so it survives server restarts
            try:
                await db.execute(text(
                    "INSERT INTO agent_action_log "
                    "(agent_id, action, target, success, decision_source, metadata_json) "
                    "VALUES (:agent_id, :action, :target, :success, 'feedback', :meta)"
                ), {
                    "agent_id": agent_id,
                    "action":   action,
                    "target":   target or "",
                    "success":  success,
                    "meta":     json.dumps(feedback),
                })
                await db.commit()
            except Exception as _fb_exc:
                logging.warning("[FEEDBACK] Could not persist feedback to DB: %s", _fb_exc)

            # ── Retry logic ────────────────────────────────────────────────────
            if not success and exec_mode == "auto_safe" and retry_count < _MAX_RETRIES:
                # Exclude: failed action, noop, and any action with < 30% success rate
                rates = _compute_success_rates(agent_id)
                rankings = _get_action_rankings(agent_id, context)
                next_action = next(
                    (r["action"] for r in rankings
                     if r["action"] not in (action, "noop")
                     and r["action"] in _SAFE_ACTIONS
                     and (rates.get(r["action"]) is None or rates.get(r["action"], 1.0) >= 0.30)),
                    None,
                )
                if next_action:
                    logging.info(
                        "[RETRY] agent=%s attempt=%d/%d: %s failed → trying %s",
                        agent_id, retry_count + 1, _MAX_RETRIES, action, next_action,
                    )
                    try:
                        from app.core.remediation_dispatch import safe_enqueue_command
                        await safe_enqueue_command(
                            db=None,
                            org_id=org_id,
                            agent_id=agent_id,
                            command=next_action,
                            target=target,
                            args={"retry": True},
                            role="system",
                            initiated_by=None,
                            llm_raw_response=None,
                            correlation_id=None,
                        )
                    except Exception as _retry_exc:
                        logging.warning("[RETRY] Failed to queue %s: %s", next_action, _retry_exc)
                        _PENDING_COMMANDS.setdefault(agent_id, []).append(
                            {"action": next_action, "target": target, "retry": True}
                        )
                    retry_conf = round((_get_success_rate(agent_id, next_action, context) or 0.5), 2)
                    _AI_HISTORY.setdefault(agent_id, []).insert(0, {
                        "timestamp":          _now().isoformat(),
                        "alert_category":     context.split(":")[0] if ":" in context else context,
                        "severity":           context.split(":")[1] if ":" in context else "",
                        "root_cause":         f"Auto-retry after {action} failed — switching to {next_action}",
                        "confidence":         retry_conf,
                        "impact":             "auto-retry",
                        "summary":            (f"Auto-retry {retry_count + 1}/{_MAX_RETRIES}: "
                                               f"{action} failed → trying {next_action}"),
                        "recommended_action": next_action,
                        "reasoning_steps":    [f"{action} did not improve metrics",
                                               f"Next best action by success rate: {next_action}",
                                               f"Historical rate: {retry_conf:.0%}"],
                        "safe_to_auto_fix":   True,
                        "status":             "queued",
                        "decision_source":    "auto_retry",
                    })
                    asyncio.create_task(_schedule_feedback_check(
                        agent_id, next_action, target,
                        cpu_after, memory_after, disk_after,
                        context, exec_mode,
                        retry_count + 1, action,
                        org_id=org_id,
                    ))
                else:
                    logging.warning("[RETRY] agent=%s no eligible action after %s failed",
                                    agent_id, action)
    except Exception as exc:
        logging.warning("[FEEDBACK] check failed for agent %s: %s", agent_id, exc)


async def _require_agent(request: Request, raw_key: str, db: AsyncSession, org_id: str) -> Agent:
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    result = await db.execute(select(Agent).where(Agent.key_hash == key_hash))
    agent = result.scalar_one_or_none()
    if agent is None or not agent.is_active:
        raise HTTPException(status_code=401, detail="Invalid agent key")
    if agent.org_id != org_id:
        raise HTTPException(status_code=403, detail="Agent does not belong to this organization")
    return agent


async def seed_admin_user() -> None:
    from app.core.database import SessionLocal as _session_factory

    async with _session_factory() as db:
        org_result = await db.execute(select(Organization).where((Organization.slug == DEFAULT_ADMIN_ORG) | (Organization.name == "Default Organization")))
        org = org_result.scalar_one_or_none()
        if org is None:
            org = Organization(
                name="Default Organization",
                slug=DEFAULT_ADMIN_ORG,
                plan="enterprise",
                is_active=True,
                settings={},
            )
            db.add(org)
            await db.flush()

        email = os.getenv("ADMIN_DEFAULT_EMAIL", DEFAULT_ADMIN_EMAIL)
        password = os.getenv("ADMIN_DEFAULT_PASSWORD")
        if not password:
            raise RuntimeError(
                "ADMIN_DEFAULT_PASSWORD is not set. Add it to your .env file "
                "before starting the auth service."
            )
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                org_id=org.id,
                email=email,
                username=DEFAULT_ADMIN_USERNAME,
                hashed_password=_hash_password(password),
                role="admin",
                is_active=True,
                must_change_password=False,
                full_name="Administrator",
            )
            db.add(user)
        await db.commit()


def build_auth_router() -> APIRouter:
    router = APIRouter()

    @router.post("/auth/register", status_code=201)
    async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        email    = body.email.strip().lower()
        username = body.username.strip().lower()
        org_name = email.split("@")[0].capitalize()

        dup_email = await db.execute(select(User).where(User.email == email))
        if dup_email.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="An account with this email already exists.")

        # Build a unique slug from org name
        base_slug = re.sub(r"[^a-z0-9]+", "-", org_name.lower()).strip("-") or "org"
        slug = f"{base_slug}-{str(uuid.uuid4())[:6]}"

        org = Organization(name=org_name, slug=slug, plan="free", is_active=True, settings={})
        db.add(org)
        await db.flush()   # get org.id before user insert

        user = User(
            org_id=org.id,
            email=email,
            username=username,
            hashed_password=_hash_password(body.password),
            role="admin",
            is_active=True,
            must_change_password=False,
            full_name=body.full_name.strip() or None,
        )
        db.add(user)
        await db.commit()
        _log_auth_event("register", email=email, user_id=user.id, detail=f"org={org.id}")
        return {"ok": True, "message": "Account created. You can now sign in."}

    @router.post("/auth/login")
    async def login(request: Request, response: Response, body: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        ip = (request.client.host if request.client else "") or ""
        ua = request.headers.get("user-agent", "")[:512]
        _check_ip_rate(ip)
        user = await _get_user_by_email(db, body.email)
        if user is None:
            _log_auth_event("login_failed", email=body.email, ip=ip, detail="user_not_found")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        now = _now()
        locked_until = _as_utc(user.locked_until)
        if locked_until and locked_until > now:
            _log_auth_event("login_failed", email=body.email, ip=ip, detail="account_locked")
            raise HTTPException(status_code=403, detail="Account is locked")

        if not _verify_password(body.password, user.hashed_password):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= FAILED_ATTEMPT_LIMIT:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_attempts = FAILED_ATTEMPT_LIMIT
                await db.commit()
                _log_auth_event("account_locked", email=body.email, ip=ip, detail="too_many_failures")
                raise HTTPException(status_code=403, detail="Account is locked")
            await db.commit()
            _log_auth_event("login_failed", email=body.email, ip=ip, detail=f"bad_password attempt={user.failed_attempts}")
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user.failed_attempts = 0
        user.locked_until = None
        user.last_login = now
        access_token = _create_access_token(user)
        refresh_token = _create_refresh_token(user)
        family_id = str(uuid.uuid4())
        session = UserSession(
            user_id=user.id,
            refresh_token_hash=_hash_refresh_token(refresh_token),
            family_id=family_id,
            expires_at=now + timedelta(seconds=REFRESH_TTL_SECONDS),
            is_revoked=False,
            ip_address=ip,
            user_agent=ua,
        )
        db.add(session)
        await db.commit()
        await db.refresh(user)
        _log_auth_event("login_success", email=user.email, user_id=user.id, ip=ip)
        response.set_cookie(
            _REFRESH_COOKIE, refresh_token,
            httponly=True, samesite="lax",
            max_age=REFRESH_TTL_SECONDS,
            secure=_IS_PROD,
            path="/auth",
        )
        return {
            "token": access_token,
            "token_type": "bearer",
            "user": _serialize_user(user),
        }

    @router.get("/auth/me")
    async def me(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        payload = await _require_access_token(request)
        user = await _get_user_by_id(db, payload["sub"])
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid token")
        return _serialize_user(user)

    @router.post("/auth/refresh")
    async def refresh(request: Request, response: Response, body: RefreshRequest | None = None, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        _check_csrf(request)
        raw_token = request.cookies.get(_REFRESH_COOKIE) or (body.refresh_token if body else None)
        if not raw_token:
            raise HTTPException(status_code=401, detail="Refresh token missing")
        ip = (request.client.host if request.client else "") or ""
        payload = _decode_token(raw_token, "refresh")
        session = await _get_session_by_refresh_token(db, raw_token)
        expires_at = _as_utc(session.expires_at) if session is not None else None
        if session is not None and session.is_revoked:
            # Token reuse detected — invalidate the entire token family
            await db.execute(
                update(UserSession)
                .where(UserSession.family_id == session.family_id)
                .values(is_revoked=True)
            )
            await db.commit()
            _log_auth_event("token_theft_detected", user_id=payload.get("sub", ""), ip=ip,
                            detail=f"family={session.family_id}")
            raise HTTPException(status_code=401, detail="Session invalidated due to token reuse")
        if session is None or (expires_at is not None and expires_at < _now()):
            _log_auth_event("refresh_rejected", user_id=payload.get("sub", ""), ip=ip, detail="revoked_or_expired")
            raise HTTPException(status_code=401, detail="Refresh token is invalid")

        user = await _get_user_by_id(db, payload["sub"])
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid token")

        session.is_revoked = True
        new_refresh = _create_refresh_token(user)
        new_session = UserSession(
            user_id=user.id,
            refresh_token_hash=_hash_refresh_token(new_refresh),
            family_id=session.family_id,  # inherit family — chain stays trackable
            expires_at=_now() + timedelta(seconds=REFRESH_TTL_SECONDS),
            is_revoked=False,
            ip_address=ip,
            user_agent=request.headers.get("user-agent", "")[:512],
        )
        db.add(new_session)
        await db.commit()
        _log_auth_event("token_refreshed", user_id=user.id, ip=ip)
        response.set_cookie(
            _REFRESH_COOKIE, new_refresh,
            httponly=True, samesite="lax",
            max_age=REFRESH_TTL_SECONDS,
            secure=_IS_PROD,
            path="/auth",
        )
        return {
            "token": _create_access_token(user),
            "token_type": "bearer",
        }

    @router.post("/auth/logout")
    async def logout(request: Request, response: Response, body: LogoutRequest | None = None, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        _check_csrf(request)
        ip = (request.client.host if request.client else "") or ""
        raw_token = request.cookies.get(_REFRESH_COOKIE) or (body.refresh_token if body else None)
        user_id = ""
        if raw_token:
            try:
                p = _decode_token(raw_token, "refresh")
                user_id = p.get("sub", "")
            except HTTPException:
                pass
            session = await _get_session_by_refresh_token(db, raw_token)
            if session is not None:
                session.is_revoked = True
                await db.commit()
        response.delete_cookie(_REFRESH_COOKIE, path="/auth")
        _log_auth_event("logout", user_id=user_id, ip=ip)
        return {"ok": True}

    @router.post("/auth/logout-all")
    async def logout_all(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        _check_csrf(request)
        payload = await _require_access_token(request)
        ip = (request.client.host if request.client else "") or ""
        result = await db.execute(
            update(UserSession)
            .where(UserSession.user_id == payload["sub"], UserSession.is_revoked.is_(False))
            .values(is_revoked=True)
        )
        await db.commit()
        response.delete_cookie(_REFRESH_COOKIE, path="/auth")
        _log_auth_event("logout_all", user_id=payload["sub"], ip=ip, detail=f"sessions={result.rowcount}")
        return {"ok": True, "sessions_revoked": result.rowcount}

    @router.get("/auth/health")
    async def auth_health() -> dict[str, str]:
        return {"status": "ok", "service": "auth"}

    @router.post("/auth/clerk-sync")
    async def clerk_sync(body: ClerkSyncRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        clerk_user_id = await _verify_clerk_token(body.clerk_token)
        if not clerk_user_id:
            raise HTTPException(status_code=401, detail="Invalid Clerk token")

        email = body.email.strip().lower()
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            org_name = email.split("@")[0].capitalize()
            base_slug = re.sub(r"[^a-z0-9]+", "-", org_name.lower()).strip("-") or "org"
            slug = f"{base_slug}-{str(uuid.uuid4())[:6]}"
            org = Organization(name=org_name, slug=slug, plan="free", is_active=True, settings={})
            db.add(org)
            await db.flush()
            username = body.username.strip().lower() or email.split("@")[0]
            user = User(
                org_id=org.id,
                email=email,
                username=username,
                hashed_password=_hash_password(secrets.token_urlsafe(32)),
                role="admin",
                is_active=True,
                must_change_password=False,
                full_name=body.full_name.strip() or None,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            _log_auth_event("clerk_register", email=email, user_id=user.id, detail=f"clerk_id={clerk_user_id}")
        else:
            _log_auth_event("clerk_login", email=email, user_id=user.id)

        return {"token": _create_access_token(user), "user": _serialize_user(user)}

    return router


# In-memory command queue: agent_id → [{"action": ..., "target": ...}, ...]
_PENDING_COMMANDS: dict[str, list[dict]] = {}

# In-memory AI decision history: agent_id → last 10 decisions
_AI_HISTORY: dict[str, list[dict]] = {}

# Action-aware confidence thresholds for auto_safe execution
_CONFIDENCE_THRESHOLDS: dict[str, float] = {
    "notify_only":     0.0,   # notifying is always safe regardless of confidence
    "noop":            0.0,
    "disk_cleanup":    0.6,
    "scale_memory":    0.7,
    "restart_service": 0.85,  # highest bar — service restarts are disruptive
}

# Per-agent execution mode: "dry_run" | "manual_approval" | "auto_safe"
_AGENT_EXEC_MODE: dict[str, str] = {}

# LLM call rate limiter — one timestamp per agent (unix epoch)
_LC_ANALYZE_LAST_RUN: dict[str, float] = {}
LC_ANALYZE_COOLDOWN_SECS: int = 20


async def restore_ai_history_from_db() -> None:
    """Repopulate _AI_HISTORY from DB on startup so decisions survive server restarts."""
    try:
        async with SessionLocal() as db:
            rows = await db.execute(text(
                "SELECT agent_id, metadata_json FROM agent_action_log "
                "WHERE metadata_json IS NOT NULL "
                "AND (decision_source IS NULL OR decision_source != 'feedback') "
                "ORDER BY created_at DESC "
                "LIMIT 500"
            ))
            for agent_id, meta in rows:
                bucket = _AI_HISTORY.setdefault(agent_id, [])
                if len(bucket) >= 10:
                    continue
                try:
                    bucket.append(json.loads(meta))
                except Exception:
                    pass
        logging.info("[AGENT] Restored AI history for %d agents from DB", len(_AI_HISTORY))
    except Exception as exc:
        logging.warning("[AGENT] Could not restore AI history: %s", exc)


async def restore_exec_modes_from_db() -> None:
    """Reload per-agent execution_mode from agents table into _AGENT_EXEC_MODE on startup."""
    try:
        async with SessionLocal() as db:
            rows = await db.execute(text(
                "SELECT id, execution_mode FROM agents WHERE is_active = TRUE"
            ))
            count = 0
            for agent_id, mode in rows:
                if mode and mode in ("dry_run", "manual_approval", "auto_safe"):
                    _AGENT_EXEC_MODE[agent_id] = mode
                    count += 1
        logging.info("[AGENT] Restored execution_mode for %d agents from DB", count)
    except Exception as exc:
        logging.warning("[AGENT] Could not restore execution_mode: %s", exc)


async def restore_feedback_from_db() -> None:
    """Rebuild _ACTION_FEEDBACK from persisted feedback rows in agent_action_log on startup."""
    try:
        async with SessionLocal() as db:
            rows = await db.execute(text(
                "SELECT agent_id, metadata_json FROM agent_action_log "
                "WHERE decision_source = 'feedback' AND metadata_json IS NOT NULL "
                "ORDER BY created_at DESC "
                "LIMIT 1000"
            ))
            count = 0
            for agent_id, meta in rows:
                bucket = _ACTION_FEEDBACK.setdefault(agent_id, [])
                if len(bucket) >= 20:
                    continue
                try:
                    entry = json.loads(meta)
                    # Ensure required feedback keys are present
                    if "action" in entry and "success" in entry:
                        bucket.append(entry)
                        count += 1
                except Exception:
                    pass
        logging.info("[AGENT] Restored feedback for %d agents (%d records) from DB",
                     len(_ACTION_FEEDBACK), count)
    except Exception as exc:
        logging.warning("[AGENT] Could not restore feedback: %s", exc)


# Last AI error message + 60-second NIM health cache (5C)
_LAST_AI_ERROR: str | None = None
_NIM_HEALTH_CACHE: dict = {"status": None, "ts": 0.0}
_NIM_HEALTH_TTL = 60.0

# Pending approvals: agent_id → [{id, action, target, ai_decision, created_at}]
_PENDING_APPROVALS: dict[str, list[dict]] = {}

# On-demand remediation run history: agent_id → last 20 records
_REMEDIATION_HISTORY: dict[str, list[dict]] = {}

# Feedback loop: agent_id → last 20 action outcome records
_ACTION_FEEDBACK: dict[str, list[dict]] = {}

_SAFE_ACTIONS: frozenset[str] = frozenset({"restart_service", "scale_memory", "disk_cleanup", "notify_only"})
_ALL_ACTIONS: list[str] = ["restart_service", "scale_memory", "disk_cleanup", "notify_only", "noop"]


def _get_agent_poll_interval(agent_id: str) -> float:
    """Return the recommended poll interval (seconds) based on current agent state."""
    _MIN, _MAX = 0.5, 10.0
    # Retry loop active in last 3 feedback records
    recent = _ACTION_FEEDBACK.get(agent_id, [])[:3]
    if any(f.get("retry_count", 0) > 0 for f in recent):
        interval, state = 1.0, "retry"
    # Pending commands waiting to be picked up
    elif _PENDING_COMMANDS.get(agent_id):
        interval, state = 0.5, "commands_pending"
    # Active AI decision in progress (queued/needs_review)
    elif any(h.get("status") in ("queued", "needs_review")
             for h in _AI_HISTORY.get(agent_id, [])[:3]):
        interval, state = 2.0, "active_alert"
    else:
        interval, state = 5.0, "idle"
    logging.debug("[POLL] agent=%s interval=%.1fs (%s)", agent_id, interval, state)
    return max(_MIN, min(_MAX, interval))


def build_metrics_router() -> APIRouter:
    router = APIRouter()

    @router.post("/ingest/heartbeat")
    async def ingest_heartbeat(
        body: HeartbeatRequest,
        background_tasks: BackgroundTasks,
        request: Request,
        x_agent_key: str | None = Header(default=None, alias="X-Agent-Key"),
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        agent_key = request.headers.get("X-Agent-Key") or x_agent_key
        if not agent_key:
            raise HTTPException(status_code=401, detail="Missing agent key")
        agent = await _require_agent(request, agent_key, db, body.org_id)
        agent.last_seen = _now()
        agent.status = "live"
        _pinfo = agent.platform_info or {}
        if body.info:
            _pinfo.update(body.info)
        _pinfo.update({"last_cpu": body.metrics.cpu, "last_memory": body.metrics.memory, "last_disk": body.metrics.disk})
        agent.platform_info = _pinfo

        snapshot = MetricSnapshot(
            org_id=body.org_id,
            agent_id=agent.id,
            timestamp=_now(),
            cpu=body.metrics.cpu,
            memory=body.metrics.memory,
            disk=body.metrics.disk,
            network_in=body.metrics.network_in,
            network_out=body.metrics.network_out,
            temperature=body.metrics.temperature,
            load_avg=body.metrics.load_avg,
            processes=body.metrics.processes,
            uptime_secs=body.metrics.uptime_secs,
            extra=body.metrics.extra,
            top_processes=body.metrics.top_processes,
            swap_percent=body.metrics.swap_percent,
            swap_used_gb=body.metrics.swap_used_gb,
            disk_read_mbps=body.metrics.disk_read_mbps,
            disk_write_mbps=body.metrics.disk_write_mbps,
            net_established=body.metrics.net_established,
            net_close_wait=body.metrics.net_close_wait,
            net_time_wait=body.metrics.net_time_wait,
            load_avg_1m=body.metrics.load_avg_1m,
            load_avg_5m=body.metrics.load_avg_5m,
            load_avg_15m=body.metrics.load_avg_15m,
            uptime_hours=body.metrics.uptime_hours,
            battery_percent=body.metrics.battery_percent,
            battery_plugged=body.metrics.battery_plugged,
            disk_partitions=body.metrics.disk_partitions,
        )
        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)
        created_alerts, resolved_ids, notify_pairs = await _check_anomalies(
            db, body.org_id, agent.id, body.metrics.cpu, body.metrics.memory, body.metrics.disk
        )
        if created_alerts:
            await db.flush()
            for _a in created_alerts:
                db.expunge(_a)
        await db.commit()

        _hub = _get_realtime_hub(request)

        # Cross-server correlation — auto-create SEV-2 when 3+ agents spike together
        await _detect_correlated_spike(
            db, body.org_id, agent.id,
            body.metrics.cpu, body.metrics.memory, body.metrics.disk,
            background_tasks, _hub,
        )

        # SSE: alert_resolved events
        for rid in resolved_ids:
            _hub.publish("alert_resolved", {"alert_id": rid, "agent_id": agent.id}, body.org_id)

        # SSE: alert_created events
        for _a in created_alerts:
            _hub.publish("alert_created", {
                "alert_id": _a.id,
                "agent_id": agent.id,
                "severity": _a.severity,
                "category": _a.category,
            }, body.org_id)

        # Background: AI analysis for each new alert
        for _a in created_alerts:
            background_tasks.add_task(
                _lc_analyze, _a, body.metrics.cpu, body.metrics.memory,
                body.org_id,
                body.metrics.top_processes,
                body.metrics.load_avg_1m, body.metrics.load_avg_5m, body.metrics.load_avg_15m,
            )

        # Background: alert-rule notifications (only DB-rule alerts with notify_channels)
        for _a, _channel_ids, _alert_data in notify_pairs:
            if _a.id:  # id assigned after flush
                background_tasks.add_task(
                    _notify_alert_rule, _a.id, body.org_id, _channel_ids, _alert_data
                )

        # SSE: enriched metric_update
        _hub.publish("metric_update", {
            **_serialize_metric(snapshot),
            "agent_id": agent.id,
            "status":   "live",
            "alerts":   [_a.id for _a in created_alerts],
        }, body.org_id)
        poll_interval = _get_agent_poll_interval(agent.id)
        pending_cmds = _PENDING_COMMANDS.pop(agent.id, [])
        return {"ok": True, "received_at": snapshot.timestamp.isoformat(),
                "snapshot": _serialize_metric(snapshot), "poll_interval": poll_interval,
                "commands": pending_cmds}

    @router.post("/agent/metrics")
    async def go_agent_metrics(body: GoMetricPayload, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        key_hash = hashlib.sha256(body.token.encode("utf-8")).hexdigest()
        result = await db.execute(select(Agent).where(Agent.key_hash == key_hash, Agent.is_active.is_(True)))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=401, detail="Invalid agent token")
        agent.last_seen = _now()
        agent.status = "live"
        ts = body.timestamp or _now()
        snapshot = MetricSnapshot(
            org_id=agent.org_id,
            agent_id=agent.id,
            timestamp=ts,
            cpu=body.cpu,
            memory=body.memory,
            disk=body.disk,
            network_in=body.net_recv,
            network_out=body.net_sent,
            uptime_secs=body.uptime or None,
            processes=body.processes,
        )
        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)
        await _check_anomalies(db, agent.org_id, agent.id, body.cpu, body.memory)
        await db.commit()
        _get_realtime_hub(request).publish("metric_update", _serialize_metric(snapshot), agent.org_id)
        return {"ok": True, "agent_id": agent.id, "received_at": snapshot.timestamp.isoformat()}

    @router.get("/api/orgs/{org_id}/metrics/summary")
    async def metrics_summary(org_id: str, request: Request, bucket: str = "1 hour", window: str = "24 hours", limit: int = 100, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        await _require_org_access(request, org_id)
        result = await db.execute(
            text(
                """
                SELECT
                    time_bucket(:bucket::interval, timestamp) AS bucket_start,
                    avg(cpu) AS cpu_avg,
                    avg(memory) AS memory_avg,
                    avg(disk) AS disk_avg,
                    max(cpu) AS cpu_max,
                    max(memory) AS memory_max,
                    count(*) AS samples
                FROM metric_snapshots
                WHERE org_id = :org_id
                  AND timestamp >= now() - :window::interval
                GROUP BY bucket_start
                ORDER BY bucket_start DESC
                LIMIT :limit
                """
            ),
            {"bucket": bucket, "window": window, "org_id": org_id, "limit": limit},
        )
        return [dict(row) for row in result.mappings().all()]

    @router.get("/api/orgs/{org_id}/metrics")
    async def list_metrics(org_id: str, request: Request, limit: int = 100, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        await _require_org_access(request, org_id)
        result = await db.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.org_id == org_id)
            .order_by(desc(MetricSnapshot.timestamp))
            .limit(limit)
        )
        return [_serialize_metric(row) for row in result.scalars().all()]

    @router.get("/api/orgs/{org_id}/metrics/latest")
    async def latest_metric(org_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any] | None:
        await _require_org_access(request, org_id)
        result = await db.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.org_id == org_id)
            .order_by(desc(MetricSnapshot.timestamp))
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()
        return _serialize_metric(snapshot) if snapshot is not None else None

    return router


def build_alerts_router() -> APIRouter:
    router = APIRouter()

    playbook_by_category = {
        "cpu": "restart_service",
        "memory": "restart_service",
        "disk": "log_cleanup_script",
        "error_rate": "rollback_last_deployment",
    }

    @router.post("/api/orgs/{org_id}/alerts", status_code=status.HTTP_201_CREATED)
    async def create_alert(org_id: str, body: AlertCreateRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        alert = AlertRecord(
            org_id=org_id,
            agent_id=body.agent_id,
            severity=body.severity,
            category=body.category,
            title=body.title,
            detail=body.detail,
            metric_value=body.metric_value,
            threshold=body.threshold,
            status=body.status,
        )
        db.add(alert)
        await db.flush()

        db.add(
            RemediationJob(
                org_id=org_id,
                alert_id=alert.id,
                playbook_type=playbook_by_category.get(body.category, "restart_service"),
                status="pending",
                attempts=0,
                max_retries=3,
                payload={
                    "severity": body.severity,
                    "category": body.category,
                    "metric_value": body.metric_value,
                    "threshold": body.threshold,
                },
            )
        )

        await db.commit()
        await db.refresh(alert)
        _get_realtime_hub(request).publish("alert_update", _serialize_alert(alert), org_id)
        return _serialize_alert(alert)
    @router.get("/api/orgs/{org_id}/alerts")
    async def list_alerts(org_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        await _require_org_access(request, org_id)
        result = await db.execute(
            select(AlertRecord)
            .where(AlertRecord.org_id == org_id)
            .order_by(desc(AlertRecord.created_at))
        )
        return [_serialize_alert(row) for row in result.scalars().all()]

    @router.get("/api/alerts")
    async def list_alerts_for_token(request: Request, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        payload = await _require_access_token(request)
        org_id = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        result = await db.execute(
            select(AlertRecord)
            .where(AlertRecord.org_id == org_id)
            .order_by(desc(AlertRecord.created_at))
        )
        return [_serialize_alert(row) for row in result.scalars().all()]

    @router.get("/api/alerts/{alert_id}")
    async def get_alert(alert_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        payload = await _require_access_token(request)
        org_id = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        result = await db.execute(
            select(AlertRecord).where(AlertRecord.id == alert_id, AlertRecord.org_id == org_id)
        )
        alert = result.scalar_one_or_none()
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        return _serialize_alert(alert)

    @router.get("/api/agent-action-logs")
    async def list_agent_action_logs(request: Request, limit: int = 100, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        effective_limit = max(1, min(limit, 200))
        result = await db.execute(
            select(AgentActionLog)
            .order_by(desc(AgentActionLog.created_at))
            .limit(effective_limit)
        )
        items = [_serialize_agent_action_log(row) for row in result.scalars().all()]
        return {"items": items, "count": len(items), "limit": effective_limit}

    @router.get("/api/remediation/jobs")
    async def list_remediation_jobs(request: Request, limit: int = 100, offset: int = 0, status: str = "queued", db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        payload = await _require_access_token(request)
        org_id = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")

        effective_limit = max(1, min(limit, 100))
        effective_offset = max(0, offset)
        normalized_status = (status or "queued").strip().lower()
        query = select(RemediationJob).where(RemediationJob.org_id == org_id)
        if normalized_status != "all":
            query = query.where(RemediationJob.status == ("pending" if normalized_status == "queued" else normalized_status))

        result = await db.execute(
            query.order_by(desc(RemediationJob.created_at)).offset(effective_offset).limit(effective_limit)
        )
        jobs = result.scalars().all()
        items: list[dict[str, Any]] = []
        for job in jobs:
            proposed_command = (job.payload or {}).get("action") or job.playbook_type
            risk_level = None
            try:
                risk_level = (job.policy_evaluation or {}).get("risk_level")
            except Exception:
                risk_level = None
            items.append({
                "id": job.id,
                "machine_name": (job.payload or {}).get("target") or (job.payload or {}).get("agent_id"),
                "proposed_command": proposed_command,
                "risk_level": risk_level,
                "llm_raw_response": job.llm_raw_response,
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            })
        return {"items": items, "limit": effective_limit, "offset": effective_offset, "count": len(items)}

    @router.post("/api/remediation/jobs/{job_id}/approve")
    async def approve_remediation_job(job_id: int, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        payload = await _require_access_token(request)
        if payload.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Requires role: admin")

        result = await db.execute(select(RemediationJob).where(RemediationJob.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status != "pending":
            raise HTTPException(status_code=409, detail="Only pending jobs can be approved")

        alert = None
        if job.alert_id:
            alert_result = await db.execute(select(AlertRecord).where(AlertRecord.id == job.alert_id, AlertRecord.org_id == job.org_id))
            alert = alert_result.scalar_one_or_none()

        command = (job.payload or {}).get("action") or job.playbook_type
        target = (job.payload or {}).get("target") or (alert.agent_id if alert else None)
        agent_id = (job.payload or {}).get("agent_id") or (alert.agent_id if alert else None)
        if not agent_id:
            raise HTTPException(status_code=409, detail="No target agent available to run this job")

        _PENDING_COMMANDS.setdefault(agent_id, []).append({"action": command, "target": target, "params": (job.payload or {}).get("args")})
        job.status = "running"
        job.dispatched_at = _now()
        await db.commit()
        return {"status": job.status, "job": {"id": job.id, "status": job.status, "alert_id": job.alert_id, "payload": job.payload}, "message": "Job approved and dispatched"}

    @router.put("/api/orgs/{org_id}/alerts/{alert_id}")
    async def update_alert(org_id: str, alert_id: str, body: dict[str, Any], request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        result = await db.execute(select(AlertRecord).where(AlertRecord.id == alert_id, AlertRecord.org_id == org_id))
        alert = result.scalar_one_or_none()
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        for field in ("status", "severity", "category", "title", "detail", "metric_value", "threshold"):
            if field in body:
                setattr(alert, field, body[field])
        if alert.status == "resolved" and alert.resolved_at is None:
            alert.resolved_at = _now()
        await db.commit()
        await db.refresh(alert)
        _get_realtime_hub(request).publish("alert_update", _serialize_alert(alert), org_id)
        return _serialize_alert(alert)

    @router.post("/agent/command")
    async def queue_agent_command(body: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        """Backend or AI queues a command for a specific agent (identified by token)."""
        from app.core.remediation_dispatch import safe_enqueue_command
        
        token = body.get("token", "")
        action = body.get("action", "")
        target = body.get("target", "")
        _ALLOWED_ACTIONS = {"restart_service", "run_script", "notify_only"}
        if not token:
            raise HTTPException(status_code=400, detail="token required")
        if action not in _ALLOWED_ACTIONS:
            raise HTTPException(status_code=400, detail=f"action '{action}' not in allowlist")
        key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        result = await db.execute(select(Agent).where(Agent.key_hash == key_hash, Agent.is_active.is_(True)))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=401, detail="Invalid agent token")
        
        # Use centralized policy-aware enqueue
        try:
            response = await safe_enqueue_command(
                db=db,
                org_id=agent.org_id,
                agent_id=agent.id,
                command=action,
                target=target,
                role="system",
                initiated_by=None,
                correlation_id=None,
            )
            logging.info("[CMD] Queued %s → %s for agent %s (policy: %s)", action, target, agent.id, response.get("risk_level"))
            return {"ok": True, "agent_id": agent.id, "queued": {"action": action, "target": target}, "response": response}
        except HTTPException:
            raise
        except Exception as e:
            logging.error("[CMD] Failed to queue command: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/agent/command")
    async def poll_agent_commands(token: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        """Agent polls for pending commands. Commands are cleared after this call."""
        if not token:
            raise HTTPException(status_code=400, detail="token required")
        key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        result = await db.execute(select(Agent).where(Agent.key_hash == key_hash, Agent.is_active.is_(True)))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=401, detail="Invalid agent token")
        commands = _PENDING_COMMANDS.pop(agent.id, [])
        poll_interval = _get_agent_poll_interval(agent.id)
        return {"commands": commands, "poll_interval": poll_interval}

    @router.post("/agent/command/result")
    async def agent_command_result(request: Request, body: dict[str, Any], db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        """Agent posts command execution results. Auth by X-Agent-Key header or token param."""
        # Authenticate agent via header or token
        token = request.headers.get("X-Agent-Key") or body.get("token") or request.query_params.get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Missing agent token")
        key_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        result = await db.execute(select(Agent).where(Agent.key_hash == key_hash, Agent.is_active.is_(True)))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=401, detail="Invalid agent token")

        cmd_id = body.get("command_id") or body.get("id") or None
        correlation_id = body.get("correlation_id") or cmd_id
        status = body.get("status") or ("completed" if body.get("success") else "failed")
        success = body.get("success")
        exit_code = body.get("exit_code")
        stdout = body.get("stdout")
        stderr = body.get("stderr")
        remediation_job_id = body.get("remediation_job_id")

        # Try to find existing AgentActionLog by correlation_id or most recent queued entry
        from app.core.database import AgentActionLog

        audit_row = None
        if correlation_id:
            q = select(AgentActionLog).where(AgentActionLog.correlation_id == correlation_id, AgentActionLog.agent_id == agent.id).order_by(AgentActionLog.created_at.desc()).limit(1)
            res = await db.execute(q)
            audit_row = res.scalar_one_or_none()

        if audit_row is None:
            q = select(AgentActionLog).where(AgentActionLog.agent_id == agent.id, AgentActionLog.status.in_(("queued", "started"))).order_by(AgentActionLog.created_at.desc()).limit(1)
            res = await db.execute(q)
            audit_row = res.scalar_one_or_none()

        now_ts = _now()
        if audit_row is None:
            # create a new audit row if none found
            audit_row = AgentActionLog(
                org_id=agent.org_id,
                agent_id=agent.id,
                remediation_job_id=remediation_job_id,
                action=body.get("action") or "unknown",
                target=body.get("target") or None,
                initiated_by=None,
                execution_mode=None,
                decision_source=body.get("decision_source"),
                llm_raw_response=body.get("llm_raw_response"),
                policy_evaluation=body.get("policy_evaluation"),
                status=status or "completed",
                success=bool(success) if success is not None else None,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                correlation_id=correlation_id,
                created_at=now_ts,
                completed_at=now_ts,
            )
            db.add(audit_row)
        else:
            # update existing
            audit_row.status = status or audit_row.status
            if success is not None:
                audit_row.success = bool(success)
            if exit_code is not None:
                audit_row.exit_code = int(exit_code)
            if stdout is not None:
                audit_row.stdout = str(stdout)
            if stderr is not None:
                audit_row.stderr = str(stderr)
            if correlation_id and not audit_row.correlation_id:
                audit_row.correlation_id = correlation_id
            if remediation_job_id is not None:
                audit_row.remediation_job_id = remediation_job_id
            audit_row.completed_at = now_ts

        job_id_to_finalize = remediation_job_id or getattr(audit_row, "remediation_job_id", None)
        if success is True and job_id_to_finalize is not None:
            job_result = await db.execute(
                select(RemediationJob).where(
                    RemediationJob.id == job_id_to_finalize,
                    RemediationJob.org_id == agent.org_id,
                )
            )
            job = job_result.scalar_one_or_none()
            if job is not None:
                job.status = "success"
                job.completed_at = now_ts
                if job.alert_id:
                    alert_result = await db.execute(
                        select(AlertRecord).where(
                            AlertRecord.id == job.alert_id,
                            AlertRecord.org_id == agent.org_id,
                        )
                    )
                    alert = alert_result.scalar_one_or_none()
                    if alert is not None:
                        alert.status = "resolved"
                        alert.resolved_at = now_ts
                        alert.resolution_reason = alert.resolution_reason or "Resolved after successful command execution"

        await db.commit()
        return {"ok": True, "agent_id": agent.id, "audit_id": getattr(audit_row, "id", None)}

    @router.post("/agent/approve")
    async def approve_action(body: dict[str, Any], request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        """Human approves a pending AI action — dispatches it to the agent's command queue."""
        from app.core.remediation_dispatch import safe_enqueue_command
        
        payload = await _require_access_token(request)
        agent_id = body.get("agent_id", "")
        approval_id = body.get("approval_id", "")
        pending = _PENDING_APPROVALS.get(agent_id, [])
        approval = next((a for a in pending if a["id"] == approval_id), None)
        if approval is None:
            raise HTTPException(status_code=404, detail="Approval not found")
        _PENDING_APPROVALS[agent_id] = [a for a in pending if a["id"] != approval_id]
        if approval["action"] not in {"restart_service", "run_script", "notify_only"}:
            raise HTTPException(status_code=400, detail="Action not in allowlist")
        
        # Use centralized policy-aware enqueue
        try:
            response = await safe_enqueue_command(
                db=db,
                org_id=payload.get("org_id", ""),
                agent_id=agent_id,
                command=approval["action"],
                target=approval["target"],
                args=approval.get("params"),
                role=payload.get("role", "admin"),
                initiated_by=payload.get("sub"),
                correlation_id=approval_id,
            )
            logging.info("[APPROVAL] Approved and dispatched: %s → %s for agent %s (policy: %s)", 
                        approval["action"], approval["target"], agent_id, response.get("risk_level"))
            return {"ok": True, "queued": approval, "response": response}
        except HTTPException:
            raise
        except Exception as e:
            logging.error("[APPROVAL] Failed to dispatch: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.patch("/api/orgs/{org_id}/agents/{agent_id}/execution-mode")
    async def set_execution_mode(org_id: str, agent_id: str, body: dict[str, Any], request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        """Set per-agent execution mode: dry_run | manual_approval | auto_safe. Persisted to DB."""
        await _require_org_access(request, org_id)
        mode = body.get("mode", "dry_run")
        if mode not in ("dry_run", "manual_approval", "auto_safe"):
            raise HTTPException(status_code=400, detail="mode must be dry_run | manual_approval | auto_safe")
        # Persist to in-memory dict immediately
        _AGENT_EXEC_MODE[agent_id] = mode
        # Persist to DB so mode survives server restarts
        await db.execute(
            update(Agent).where(Agent.id == agent_id, Agent.org_id == org_id).values(execution_mode=mode)
        )
        await db.commit()
        logging.info("[EXEC MODE] agent=%s → mode=%s (persisted)", agent_id, mode)
        return {"ok": True, "agent_id": agent_id, "mode": mode}

    return router


def build_agents_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/orgs")
    async def list_orgs(request: Request, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        await _require_access_token(request)
        result = await db.execute(select(Organization).order_by(Organization.name))
        return [_serialize_org(org) for org in result.scalars().all()]

    @router.get("/api/orgs/{org_id}")
    async def get_org(org_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        result = await db.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        return _serialize_org(org)

    @router.patch("/api/orgs/{org_id}/settings")
    async def update_org_settings(org_id: str, body: OrgSettingsUpdate, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        result = await db.execute(select(Organization).where(Organization.id == org_id))
        org = result.scalar_one_or_none()
        if org is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        org.settings = body.settings
        await db.commit()
        await db.refresh(org)
        return _serialize_org(org)

    @router.get("/api/orgs/{org_id}/agents")
    async def list_agents(org_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        await _require_org_access(request, org_id)
        result = await db.execute(select(Agent).where(Agent.org_id == org_id).order_by(Agent.label))
        return [_serialize_agent(agent) for agent in result.scalars().all()]

    @router.post("/api/orgs/{org_id}/agents")
    async def create_agent(org_id: str, body: AgentCreateRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        pricing_service = PricingService()
        await pricing_service.ensure_service_limit(db, org_id)

        raw_key = body.key or secrets.token_urlsafe(32)
        agent = Agent(
            org_id=org_id,
            label=body.label,
            key_hash=hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
            status="pending",
            is_active=True,
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        return {**_serialize_agent(agent), "raw_key": raw_key}

    @router.get("/api/orgs/{org_id}/agents/{agent_id}")
    async def get_agent(org_id: str, agent_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        history_result = await db.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.agent_id == agent_id)
            .order_by(desc(MetricSnapshot.timestamp))
            .limit(30)
        )
        snapshots = list(reversed(history_result.scalars().all()))
        latest = snapshots[-1] if snapshots else None
        alerts_result = await db.execute(
            select(AlertRecord)
            .where(AlertRecord.agent_id == agent_id, AlertRecord.status == "open")
            .order_by(desc(AlertRecord.created_at))
            .limit(20)
        )
        alerts = alerts_result.scalars().all()
        last_cmd_result = await db.execute(
            select(AgentActionLog.created_at)
            .where(AgentActionLog.agent_id == agent_id)
            .order_by(desc(AgentActionLog.created_at))
            .limit(1)
        )
        last_cmd_row = last_cmd_result.scalar_one_or_none()
        last_command_at = last_cmd_row.isoformat() if last_cmd_row else None
        return {
            **_serialize_agent(agent),
            "last_command_at": last_command_at,
            "metrics": _serialize_metric(latest) if latest else {},
            "info": {
                **{k: v for k, v in (agent.platform_info or {}).items()
                   if k not in ("last_cpu", "last_memory", "last_disk")},
                **((latest.extra or {}) if latest else {}),
                # Normalize alternate key names from Go/desktop agents so the UI
                # always gets the canonical names it expects.
                "cpu_model": (agent.platform_info or {}).get("cpu_model")
                             or (agent.platform_info or {}).get("arch"),
                "python":    (agent.platform_info or {}).get("python")
                             or (agent.platform_info or {}).get("python_version"),
                "platform":  (agent.platform_info or {}).get("platform")
                             or (agent.platform_info or {}).get("os"),
            },
            "history": [
                {"timestamp": s.timestamp.isoformat(), "cpu": s.cpu, "memory": s.memory, "disk": s.disk}
                for s in snapshots
            ],
            "alerts": [
                {
                    "id": a.id, "severity": a.severity, "category": a.category,
                    "title": a.title, "detail": a.detail,
                    "metric_value": a.metric_value, "threshold": a.threshold,
                    "status": a.status, "created_at": a.created_at.isoformat(),
                }
                for a in alerts
            ],
            "ai_history": _AI_HISTORY.get(agent_id, []),
            "execution_mode": _AGENT_EXEC_MODE.get(agent_id, "dry_run"),
            "pending_approvals": _PENDING_APPROVALS.get(agent_id, []),
            "feedback": _ACTION_FEEDBACK.get(agent_id, [])[:10],
            "success_rates": {
                f"{r['action']}|{r['context']}": round((_get_success_rate(agent_id, r["action"], r["context"]) or 0) * 100)
                for r in _ACTION_FEEDBACK.get(agent_id, [])
            },
            "success_rates_global": {
                action: round((_get_success_rate(agent_id, action) or 0) * 100)
                for action in {r["action"] for r in _ACTION_FEEDBACK.get(agent_id, [])}
            },
        }

    @router.patch("/api/orgs/{org_id}/agents/{agent_id}/alerts/{alert_id}/resolve")
    async def resolve_agent_alert(org_id: str, agent_id: str, alert_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        result = await db.execute(select(AlertRecord).where(AlertRecord.id == alert_id, AlertRecord.agent_id == agent_id))
        alert = result.scalar_one_or_none()
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert.status = "resolved"
        alert.resolved_at = _now()
        await db.commit()
        return {"ok": True}

    @router.patch("/api/orgs/{org_id}/agents/{agent_id}")
    async def update_agent(org_id: str, agent_id: str, body: AgentUpdateRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        if body.label is not None:
            agent.label = body.label
        if body.status is not None:
            agent.status = body.status
        if body.is_active is not None:
            agent.is_active = body.is_active
        await db.commit()
        await db.refresh(agent)
        return _serialize_agent(agent)

    @router.delete("/api/orgs/{org_id}/agents/{agent_id}")
    async def delete_agent(org_id: str, agent_id: str, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        await db.delete(agent)
        await db.commit()
        return {"ok": True}

    @router.post("/api/orgs/{org_id}/agents/{agent_id}/command")
    async def issue_agent_command(org_id: str, agent_id: str, body: dict[str, Any], request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        action = body.get("action")
        command = {
            "id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "action": action,
            "params": body.get("params", {}),
            "source": "manual",
            "status": "queued",
        }
        _PENDING_COMMANDS.setdefault(agent_id, []).append(command)
        return command


    @router.post("/agents/onboard")
    async def create_onboard_token(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        """Generate a short-lived one-time onboarding token for a desktop agent."""
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token")
        payload = _decode_token(header.removeprefix("Bearer ").strip(), "access")
        org_id = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="No org in token")

        # Auto-provision org + user on first request to a fresh DB (e.g. Render)
        org = await db.get(Organization, org_id)
        if org is None:
            _slug = re.sub(r"[^a-z0-9]+", "-", payload.get("username", "default").lower())[:50] or "default"
            org = Organization(id=org_id, name=_slug, slug=_slug)
            db.add(org)
            await db.flush()

        user_id = payload.get("sub", str(uuid.uuid4()))
        user = await db.get(User, user_id)
        if user is None:
            user = User(
                id=user_id,
                org_id=org_id,
                email=payload.get("email", f"{user_id}@resilo.local"),
                username=payload.get("username", user_id[:16]),
                hashed_password="!",
                role=payload.get("role", "admin"),
                is_active=True,
            )
            db.add(user)
            await db.flush()

        raw_token = f"resilo_{secrets.token_urlsafe(32)}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
        record = OnboardingToken(
            token=raw_token,
            org_id=org_id,
            created_by=user_id,
            label=request.headers.get("X-Agent-Label", "desktop-agent"),
            expires_at=expires_at,
        )
        db.add(record)
        await db.commit()
        return {"token": raw_token, "expires_in": 1800, "org_id": org_id}

    @router.post("/agents/register")
    async def register_via_onboard_token(body: AgentRegisterRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        """Exchange a one-time onboarding token for a persistent agent_key. No auth required."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(OnboardingToken).where(
                OnboardingToken.token == body.token,
                OnboardingToken.used.is_(False),
                OnboardingToken.expires_at > now,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            raise HTTPException(status_code=401, detail="Invalid or expired onboarding token")

        record.used = True
        device_id = str(uuid.uuid4())
        label = (body.label or record.label or f"desktop-{device_id[:8]}")
        raw_key = secrets.token_urlsafe(32)
        agent = Agent(
            org_id=record.org_id,
            label=label,
            key_hash=hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
            status="pending",
            is_active=True,
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        return {
            "device_id": device_id,
            "org_id": record.org_id,
            "agent_id": agent.id,
            "agent_key": raw_key,
        }

    @router.get("/api/health/system")
    async def system_health_summary(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        """Dashboard health card: AI service (60s cached NIM ping), DB, agent counts, open alerts."""
        try:
            header = request.headers.get("authorization", "")
            if header.startswith("Bearer "):
                _decode_token(header.removeprefix("Bearer ").strip(), "access")
            else:
                raise HTTPException(status_code=401, detail="Unauthorized")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Unauthorized")

        api_key = os.getenv("NVIDIA_API_KEY", "")

        # 60-second cached NIM health check
        now_ts = time.time()
        if not api_key:
            ai_service = "offline"
        elif now_ts - _NIM_HEALTH_CACHE["ts"] > _NIM_HEALTH_TTL:
            try:
                async with httpx.AsyncClient(timeout=5) as _hc:
                    _r = await _hc.post(
                        f"{os.getenv('NVIDIA_BASE_URL', 'https://integrate.api.nvidia.com/v1')}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={"model": os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct"),
                              "messages": [{"role": "user", "content": "ping"}],
                              "max_tokens": 1},
                    )
                _NIM_HEALTH_CACHE["status"] = "online" if _r.status_code < 400 else "degraded"
            except Exception:
                _NIM_HEALTH_CACHE["status"] = "offline"
            _NIM_HEALTH_CACHE["ts"] = now_ts
            ai_service = _NIM_HEALTH_CACHE["status"]
        else:
            ai_service = _NIM_HEALTH_CACHE["status"] or "online"

        # Degrade if most recent decision was a rule_fallback
        all_decisions: list[dict] = []
        for decisions in _AI_HISTORY.values():
            all_decisions.extend(decisions)
        all_decisions.sort(key=lambda d: d.get("timestamp", ""), reverse=True)
        last_ai_call_at = all_decisions[0].get("timestamp") if all_decisions else None
        if ai_service == "online" and all_decisions and all_decisions[0].get("decision_source") == "rule_fallback":
            ai_service = "degraded"

        try:
            await db.execute(text("SELECT 1"))
            database = "online"
        except Exception:
            database = "offline"

        try:
            _cutoff = _now() - timedelta(seconds=_AGENT_LIVE_SECS)
            agent_rows = await db.execute(select(Agent).where(Agent.is_active.is_(True)))
            all_ag = agent_rows.scalars().all()
            agents_live    = sum(1 for a in all_ag if a.last_seen and (
                a.last_seen if a.last_seen.tzinfo else a.last_seen.replace(tzinfo=timezone.utc)
            ) > _cutoff)
            agents_offline = len(all_ag) - agents_live
        except Exception:
            agents_live = agents_offline = 0

        try:
            alert_rows = await db.execute(select(AlertRecord).where(AlertRecord.status == "open"))
            open_count = len(alert_rows.scalars().all())
        except Exception:
            open_count = 0

        return {
            "ai_service":      ai_service,
            "database":        database,
            "last_ai_call_at": last_ai_call_at,
            "last_ai_error":   _LAST_AI_ERROR,
            "agents_live":     agents_live,
            "agents_offline":  agents_offline,
            "open_alerts":     open_count,
        }

    # ── Remediation Agent endpoints ───────────────────────────────────────────

    @router.post("/api/orgs/{org_id}/agents/{agent_id}/remediation/analyze")
    async def remediation_analyze(
        org_id: str, agent_id: str, request: Request, db: AsyncSession = Depends(get_db)
    ) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        snap_result = await db.execute(
            select(MetricSnapshot).where(MetricSnapshot.agent_id == agent_id)
            .order_by(desc(MetricSnapshot.timestamp)).limit(1)
        )
        latest = snap_result.scalar_one_or_none()
        metrics   = _serialize_metric(latest) if latest else {}
        top_procs = (latest.top_processes or {}) if latest else {}
        exec_mode = _AGENT_EXEC_MODE.get(agent_id, "dry_run")
        from app.agents.remediation_agent import analyze_agent
        plan = await analyze_agent(agent.label, metrics, top_procs, exec_mode)

        # Auto-execute low-risk actions when mode is auto_safe
        _AUTO_SAFE_CMDS = {"free_memory", "disk_cleanup", "restart_service"}
        if exec_mode == "auto_safe":
            for action in plan.get("actions", []):
                if action.get("command") in _AUTO_SAFE_CMDS and action.get("risk") == "low":
                    _PENDING_COMMANDS.setdefault(agent_id, []).append({
                        "id": str(uuid.uuid4()),
                        "agent_id": agent_id,
                        "action": action["command"],
                        "params": {"target": action.get("target") or ""},
                        "source": "auto_safe",
                        "status": "queued",
                    })
                    action["auto_queued"] = True

        run_id = str(uuid.uuid4())
        record = {"id": run_id, "agent_id": agent_id,
                  "created_at": _now().isoformat(), "exec_mode": exec_mode, **plan}
        bucket = _REMEDIATION_HISTORY.setdefault(agent_id, [])
        bucket.insert(0, record)
        if len(bucket) > 20:
            bucket.pop()
        db.add(RemediationJob(org_id=org_id, playbook_type="on_demand",
                              status="complete", payload=record))
        await db.commit()
        return record

    @router.post("/api/orgs/{org_id}/agents/{agent_id}/remediation/execute")
    async def remediation_execute(
        org_id: str, agent_id: str, body: dict[str, Any], request: Request, db: AsyncSession = Depends(get_db)
    ) -> dict[str, Any]:
        await _require_org_access(request, org_id)
        result = await db.execute(select(Agent).where(Agent.id == agent_id, Agent.org_id == org_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        action = body.get("action", "noop")
        target = body.get("target") or ""
        cmd_id = str(uuid.uuid4())
        command = {"id": cmd_id, "agent_id": agent_id, "action": action,
                   "params": {"target": target}, "status": "queued"}
        pending = list(agent.pending_cmds or [])
        pending.append(command)
        agent.pending_cmds = pending
        await db.commit()
        return {"ok": True, "command_id": cmd_id, "action": action, "target": target}

    @router.get("/api/orgs/{org_id}/agents/{agent_id}/remediation/history")
    async def remediation_history_endpoint(
        org_id: str, agent_id: str, request: Request, db: AsyncSession = Depends(get_db)
    ) -> list[dict[str, Any]]:
        await _require_org_access(request, org_id)
        return _REMEDIATION_HISTORY.get(agent_id, [])

    return router


def build_health_router() -> APIRouter:
    router = APIRouter()

    async def _health_db(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            await db.execute(text("SELECT 1"))
            return {
                "status": "ok",
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "degraded",
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "error": str(exc),
                },
            ) from exc

    async def _health(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            await db.execute(text("SELECT 1"))
            database_status = "connected"
            status_text = "healthy"
            http_status = 200
        except Exception:
            database_status = "unreachable"
            status_text = "degraded"
            http_status = 503

        payload = {
            "status": status_text,
            "database": database_status,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "timestamp": _now().isoformat(),
        }
        if http_status != 200:
            raise HTTPException(status_code=http_status, detail=payload)
        return payload

    router.add_api_route("/health", _health, methods=["GET"])
    router.add_api_route("/api/health", _health, methods=["GET"])
    router.add_api_route("/health/db", _health_db, methods=["GET"])
    return router


def build_stream_router() -> APIRouter:
    import psutil

    router = APIRouter()

    @router.post("/stream/token")
    async def create_stream_token(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        payload = await _require_access_token(request)
        user = await _get_user_by_id(db, payload["sub"])
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"token": _create_stream_token(user), "token_type": "stream"}

    @router.get("/events/system")
    async def system_events() -> StreamingResponse:
        async def gen():
            while True:
                snapshot = {
                    "cpu": psutil.cpu_percent(interval=0.0),
                    "memory": psutil.virtual_memory().percent,
                    "disk": psutil.disk_usage("/").percent,
                    "timestamp": _now().isoformat(),
                }
                yield f"data: {json.dumps(snapshot)}\n\n"
                await asyncio.sleep(3)

        return StreamingResponse(gen(), media_type="text/event-stream")

    @router.get("/stream/metrics")
    async def metrics_stream(request: Request) -> StreamingResponse:
        payload = await _require_access_token(request)
        org_id = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")
        return StreamingResponse(_stream_realtime_events("metric_update", org_id, request), media_type="text/event-stream")

    @router.get("/stream/alerts")
    async def alerts_stream(request: Request) -> StreamingResponse:
        payload = await _require_access_token(request)
        org_id = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")
        return StreamingResponse(_stream_realtime_events("alert_update", org_id, request), media_type="text/event-stream")

    @router.get("/stream/agent-updates")
    async def agent_updates_stream(request: Request) -> StreamingResponse:
        """Combined SSE stream: metric_update + alert_created + alert_resolved events.
        Replaces the need for the frontend to poll GET /agents/{id} every 5s."""
        payload = await _require_access_token(request)
        org_id = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")
        return StreamingResponse(
            _stream_realtime_events(
                {"metric_update", "alert_created", "alert_resolved"}, org_id, request
            ),
            media_type="text/event-stream",
        )

    return router


# ── Google OAuth ──────────────────────────────────────────────────────────────

def _oauth_state() -> str:
    ts  = str(int(time.time()))
    sig = hmac.new(_jwt_secret().encode(), ts.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{ts}.{sig}"


def _verify_oauth_state(state: str) -> bool:
    try:
        ts, sig = state.split(".", 1)
        expected = hmac.new(_jwt_secret().encode(), ts.encode(), hashlib.sha256).hexdigest()[:16]
        return hmac.compare_digest(sig, expected) and abs(time.time() - int(ts)) < 600
    except Exception:
        return False


def build_oauth_router() -> APIRouter:
    router = APIRouter()

    @router.get("/auth/google")
    async def google_start() -> RedirectResponse:
        client_id    = os.getenv("GOOGLE_CLIENT_ID", "")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5001/auth/google/callback")
        if not client_id:
            return RedirectResponse(url=f"{_FRONTEND_URL}/login?error=oauth_not_configured")
        params = {
            "client_id":     client_id,
            "redirect_uri":  redirect_uri,
            "response_type": "code",
            "scope":         "openid email profile",
            "state":         _oauth_state(),
            "access_type":   "offline",
            "prompt":        "select_account",
        }
        return RedirectResponse(url="https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))

    @router.get("/auth/google/callback")
    async def google_callback(
        code:  str | None = None,
        state: str | None = None,
        error: str | None = None,
        db:    AsyncSession = Depends(get_db),
    ) -> RedirectResponse:
        fail = RedirectResponse(url=f"{_FRONTEND_URL}/login?error=oauth_failed")

        if error or not code or not state or not _verify_oauth_state(state):
            return fail

        client_id     = os.getenv("GOOGLE_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        redirect_uri  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5001/auth/google/callback")

        if not client_id or not client_secret:
            return fail

        try:
            async with httpx.AsyncClient(timeout=10) as hc:
                tok = await hc.post("https://oauth2.googleapis.com/token", data={
                    "code":          code,
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "redirect_uri":  redirect_uri,
                    "grant_type":    "authorization_code",
                })
                if tok.status_code != 200:
                    return fail
                access = tok.json().get("access_token", "")
                if not access:
                    return fail

                info_r = await hc.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {access}"},
                )
                if info_r.status_code != 200:
                    return fail
                ginfo = info_r.json()
        except Exception:
            return fail

        email = (ginfo.get("email") or "").strip().lower()
        if not email:
            return fail

        result = await db.execute(select(User).where(User.email == email))
        user   = result.scalar_one_or_none()

        if user is None:
            name      = ginfo.get("name") or email.split("@")[0]
            org_name  = f"{name}'s Workspace"
            base_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "org"
            slug      = f"{base_slug}-{str(uuid.uuid4())[:6]}"
            org = Organization(name=org_name, slug=slug, plan="free", is_active=True, settings={})
            db.add(org)
            await db.flush()
            username = re.sub(r"[^a-z0-9_]", "_", email.split("@")[0].lower())
            user = User(
                org_id=org.id, email=email, username=username,
                hashed_password="__oauth__",
                role="admin", is_active=True, must_change_password=False,
                full_name=name,
            )
            db.add(user)
            await db.flush()

        now           = _now()
        user.last_login = now
        access_token  = _create_access_token(user)
        refresh_token = _create_refresh_token(user)
        session = UserSession(
            user_id=user.id,
            refresh_token_hash=_hash_refresh_token(refresh_token),
            family_id=str(uuid.uuid4()),
            expires_at=now + timedelta(seconds=REFRESH_TTL_SECONDS),
            is_revoked=False,
        )
        db.add(session)
        await db.commit()
        _log_auth_event("oauth_login_google", email=email, user_id=user.id)

        resp = RedirectResponse(url=f"{_FRONTEND_URL}/auth/callback?token={access_token}", status_code=302)
        resp.set_cookie(
            _REFRESH_COOKIE, refresh_token,
            httponly=True, samesite="lax",
            max_age=REFRESH_TTL_SECONDS,
            secure=_IS_PROD, path="/auth",
        )
        return resp

    return router













