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

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse, StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import (Agent, AlertRecord, MetricSnapshot,
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
    org_name:  str
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


class HeartbeatRequest(BaseModel):
    org_id: str
    metrics: MetricPayload


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


def _serialize_agent(agent: Agent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "org_id": agent.org_id,
        "label": agent.label,
        "status": agent.status,
        "is_active": agent.is_active,
        "last_seen": agent.last_seen.isoformat() if agent.last_seen else None,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "platform_info": agent.platform_info or {},
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


async def _stream_realtime_events(event_type: str, org_id: str, request: Request):
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
            if event.get("type") != event_type:
                continue
            yield f"event: {event_type}\ndata: {json.dumps(event['data'])}\n\n"
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
    {"category": "cpu",    "severity": "critical", "threshold": 85.0, "recover": 70.0, "field": "cpu",
     "title": "High CPU usage",    "detail": "CPU usage exceeded {value:.1f}% (threshold {threshold:.0f}%)"},
    {"category": "memory", "severity": "high",     "threshold": 90.0, "recover": 75.0, "field": "memory",
     "title": "High memory usage", "detail": "Memory usage exceeded {value:.1f}% (threshold {threshold:.0f}%)"},
]


async def _check_anomalies(db: AsyncSession, org_id: str, agent_id: str, cpu: float, memory: float) -> list[AlertRecord]:
    values = {"cpu": cpu, "memory": memory}
    created: list[AlertRecord] = []
    for rule in _ALERT_RULES:
        value = values.get(rule["field"], 0.0)

        if value >= rule["threshold"]:
            existing = await db.execute(
                select(AlertRecord).where(
                    AlertRecord.agent_id == agent_id,
                    AlertRecord.category == rule["category"],
                    AlertRecord.status == "open",
                )
            )
            if existing.scalar_one_or_none() is None:
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
                asyncio.create_task(_lc_analyze(alert, cpu, memory))

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
                logging.info("[auto-resolve] %s alert resolved for agent %s", rule["category"], agent_id)

    return created


_AI_SYSTEM_PROMPT = """You are an expert SRE analyzing a system alert.
Respond ONLY with a valid JSON object — no markdown, no prose.
Schema:
{
  "root_cause": "<concise technical root cause>",
  "confidence": <0.0-1.0>,
  "impact": "low|medium|high|critical",
  "summary": "<1-2 sentence human-readable summary>",
  "recommended_action": "<single best action to take>",
  "safe_to_auto_fix": <true|false>
}"""


async def _ai_analyze(alert: AlertRecord, cpu: float, memory: float) -> None:
    """Call NVIDIA NIM to analyze a new alert. Runs as a background task — never raises."""
    api_key = os.getenv("NVIDIA_API_KEY", "")
    exec_mode = _AGENT_EXEC_MODE.get(alert.agent_id, "dry_run")

    payload = {
        "alert_name": alert.category,
        "severity": alert.severity,
        "title": alert.title,
        "detail": alert.detail,
        "metrics": {"cpu": cpu, "memory": memory},
    }
    logging.info("[EXEC MODE] agent=%s mode=%s", alert.agent_id, exec_mode)

    if not api_key:
        logging.warning("[AI] NVIDIA_API_KEY not set — skipping LLM analysis")
        return

    try:
        nim_payload = {
            "model": os.getenv("LLM_MODEL", "meta/llama-3.3-70b-instruct"),
            "messages": [
                {"role": "system", "content": _AI_SYSTEM_PROMPT},
                {"role": "user", "content": f"Alert data:\n{json.dumps(payload, indent=2)}"},
            ],
            "temperature": 0.2,
            "max_tokens": 512,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=45) as client:
            r = await client.post(
                f"{os.getenv('NVIDIA_BASE_URL', 'https://integrate.api.nvidia.com/v1')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=nim_payload,
            )
            r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()
        start = raw.find("{"); end = raw.rfind("}") + 1
        plan = json.loads(raw[start:end]) if start != -1 else {}
        logging.info("[AI PLAN] %s", json.dumps(plan))

        action = plan.get("recommended_action", "")
        target = plan.get("target", alert.category)

        if exec_mode == "dry_run":
            disp_status = "dry_run"
            logging.info("[AI RESULT] DRY RUN — no action executed. Recommended: %s", action)
        elif exec_mode == "manual_approval":
            approval = {
                "id": str(uuid.uuid4()),
                "action": action,
                "target": target,
                "alert_category": alert.category,
                "created_at": _now().isoformat(),
            }
            _PENDING_APPROVALS.setdefault(alert.agent_id, []).append(approval)
            disp_status = "needs_approval"
            logging.info("[APPROVAL] Waiting for approval: %s → %s", action, target)
        elif exec_mode == "auto_safe":
            if action in _SAFE_ACTIONS:
                _PENDING_COMMANDS.setdefault(alert.agent_id, []).append({"action": action, "target": target})
                disp_status = "queued"
                logging.info("[EXECUTED] Auto-queued safe action: %s → %s", action, target)
            else:
                disp_status = "needs_review"
                logging.info("[BLOCKED] Unsafe action blocked in auto_safe mode: %s", action)
        else:
            disp_status = "dry_run"

        decision = {
            "timestamp": _now().isoformat(),
            "alert_category": alert.category,
            "severity": alert.severity,
            "root_cause": plan.get("root_cause", ""),
            "confidence": plan.get("confidence", 0.0),
            "impact": plan.get("impact", ""),
            "summary": plan.get("summary", ""),
            "recommended_action": action,
            "safe_to_auto_fix": plan.get("safe_to_auto_fix", False),
            "status": disp_status,
        }
        hist = _AI_HISTORY.setdefault(alert.agent_id, [])
        hist.insert(0, decision)
        if len(hist) > 10:
            hist.pop()

    except Exception as exc:
        logging.warning("[AI] Analysis failed for alert %s: %s", alert.category, exc)


async def _lc_analyze(alert: AlertRecord, cpu: float, memory: float) -> None:
    """LangChain agent analysis — background task, never raises."""
    from app.agents.langchain_agent import analyze_alert as _lc_agent

    exec_mode = _AGENT_EXEC_MODE.get(alert.agent_id, "dry_run")
    logging.info("[AGENT] Alert received: agent=%s mode=%s", alert.agent_id, exec_mode)

    alert_data = {
        "category": alert.category,
        "severity": alert.severity,
        "title": alert.title,
        "detail": alert.detail,
    }
    metrics = {"cpu": cpu, "memory": memory, "disk": 0.0}

    success_rate = _get_success_rate(alert.agent_id, "restart_service")
    decision = await _lc_agent(alert_data, metrics, success_rate)
    action  = decision["action"]
    target  = decision["target"]

    if exec_mode == "dry_run":
        disp_status = "dry_run"
        logging.info("[AGENT EXECUTION] mode=dry_run — no action. Recommended: %s → %s", action, target)
    elif exec_mode == "manual_approval":
        approval = {
            "id": str(uuid.uuid4()),
            "action": action,
            "target": target,
            "alert_category": alert.category,
            "created_at": _now().isoformat(),
        }
        _PENDING_APPROVALS.setdefault(alert.agent_id, []).append(approval)
        disp_status = "needs_approval"
        logging.info("[AGENT EXECUTION] mode=supervised — queued for approval: %s → %s", action, target)
    elif exec_mode == "auto_safe":
        if action in _SAFE_ACTIONS and decision["safe"]:
            _PENDING_COMMANDS.setdefault(alert.agent_id, []).append({"action": action, "target": target})
            disp_status = "queued"
            logging.info("[AGENT EXECUTION] mode=autonomous — auto-queued: %s → %s", action, target)
            asyncio.create_task(_schedule_feedback_check(alert.agent_id, action, target, cpu, memory))
        else:
            disp_status = "needs_review"
            logging.info("[AGENT EXECUTION] mode=autonomous — unsafe action blocked: %s", action)
    else:
        disp_status = "dry_run"

    record = {
        "timestamp": _now().isoformat(),
        "alert_category": alert.category,
        "severity": alert.severity,
        "root_cause": decision["reason"],
        "confidence": decision["confidence"],
        "impact": alert.severity,
        "summary": f"LangChain agent: {action}" + (f" → {target}" if target else ""),
        "recommended_action": action,
        "safe_to_auto_fix": decision["safe"],
        "status": disp_status,
    }
    hist = _AI_HISTORY.setdefault(alert.agent_id, [])
    hist.insert(0, record)
    if len(hist) > 10:
        hist.pop()


def _get_success_rate(agent_id: str, action: str) -> float | None:
    """Return historical success rate for (agent, action) or None if no history."""
    records = [r for r in _ACTION_FEEDBACK.get(agent_id, []) if r["action"] == action]
    if not records:
        return None
    return sum(1 for r in records if r["success"]) / len(records)


async def _schedule_feedback_check(
    agent_id: str, action: str, target: str, cpu_before: float, memory_before: float
) -> None:
    """Wait 30 s then measure whether the action actually improved metrics."""
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
            success = (cpu_after < cpu_before - 5) or (memory_after < memory_before - 5)
            feedback = {
                "timestamp":     _now().isoformat(),
                "action":        action,
                "target":        target,
                "cpu_before":    round(cpu_before,    1),
                "cpu_after":     round(cpu_after,     1),
                "memory_before": round(memory_before, 1),
                "memory_after":  round(memory_after,  1),
                "success":       success,
            }
            hist = _ACTION_FEEDBACK.setdefault(agent_id, [])
            hist.insert(0, feedback)
            if len(hist) > 20:
                hist.pop()
            logging.info(
                "[FEEDBACK] agent=%s action=%s success=%s cpu=%.1f→%.1f mem=%.1f→%.1f",
                agent_id, action, success,
                cpu_before, cpu_after, memory_before, memory_after,
            )
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
        org_name = body.org_name.strip()

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

    return router


# In-memory command queue: agent_id → [{"action": ..., "target": ...}, ...]
_PENDING_COMMANDS: dict[str, list[dict]] = {}

# In-memory AI decision history: agent_id → last 10 decisions
_AI_HISTORY: dict[str, list[dict]] = {}

# Per-agent execution mode: "dry_run" | "manual_approval" | "auto_safe"
_AGENT_EXEC_MODE: dict[str, str] = {}

# Pending approvals: agent_id → [{id, action, target, ai_decision, created_at}]
_PENDING_APPROVALS: dict[str, list[dict]] = {}

# Feedback loop: agent_id → last 20 action outcome records
_ACTION_FEEDBACK: dict[str, list[dict]] = {}

_SAFE_ACTIONS: frozenset[str] = frozenset({"restart_service", "notify_only"})


def build_metrics_router() -> APIRouter:
    router = APIRouter()

    @router.post("/ingest/heartbeat")
    async def ingest_heartbeat(
        body: HeartbeatRequest,
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
        )
        db.add(snapshot)
        await db.commit()
        await db.refresh(snapshot)
        await _check_anomalies(db, body.org_id, agent.id, body.metrics.cpu, body.metrics.memory)
        await db.commit()
        _get_realtime_hub(request).publish("metric_update", _serialize_metric(snapshot), body.org_id)
        return {"ok": True, "received_at": snapshot.timestamp.isoformat(), "snapshot": _serialize_metric(snapshot)}

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
        _PENDING_COMMANDS.setdefault(agent.id, []).append({"action": action, "target": target})
        logging.info("[CMD] Queued %s → %s for agent %s", action, target, agent.id)
        return {"ok": True, "agent_id": agent.id, "queued": {"action": action, "target": target}}

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
        return {"commands": commands}

    @router.post("/agent/approve")
    async def approve_action(body: dict[str, Any], request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        """Human approves a pending AI action — dispatches it to the agent's command queue."""
        await _require_access_token(request)
        agent_id = body.get("agent_id", "")
        approval_id = body.get("approval_id", "")
        pending = _PENDING_APPROVALS.get(agent_id, [])
        approval = next((a for a in pending if a["id"] == approval_id), None)
        if approval is None:
            raise HTTPException(status_code=404, detail="Approval not found")
        _PENDING_APPROVALS[agent_id] = [a for a in pending if a["id"] != approval_id]
        if approval["action"] not in {"restart_service", "run_script", "notify_only"}:
            raise HTTPException(status_code=400, detail="Action not in allowlist")
        _PENDING_COMMANDS.setdefault(agent_id, []).append({"action": approval["action"], "target": approval["target"]})
        logging.info("[APPROVAL] Approved and queued: %s → %s for agent %s", approval["action"], approval["target"], agent_id)
        return {"ok": True, "queued": approval}

    @router.patch("/api/orgs/{org_id}/agents/{agent_id}/execution-mode")
    async def set_execution_mode(org_id: str, agent_id: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Set per-agent execution mode: dry_run | manual_approval | auto_safe."""
        await _require_org_access(request, org_id)
        mode = body.get("mode", "dry_run")
        if mode not in ("dry_run", "manual_approval", "auto_safe"):
            raise HTTPException(status_code=400, detail="mode must be dry_run | manual_approval | auto_safe")
        _AGENT_EXEC_MODE[agent_id] = mode
        logging.info("[EXEC MODE] agent=%s → mode=%s", agent_id, mode)
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
        return {
            **_serialize_agent(agent),
            "metrics": _serialize_metric(latest) if latest else {},
            "info": (latest.extra or {}) if latest else {},
            "history": [
                {"timestamp": s.timestamp.isoformat(), "cpu": s.cpu, "memory": s.memory}
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
                action: round(_get_success_rate(agent_id, action) * 100)
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
        command = {
            "id": str(uuid.uuid4()),
            "agent_id": agent_id,
            "action": body.get("action"),
            "params": body.get("params", {}),
            "status": "queued",
        }
        pending = list(agent.pending_cmds or [])
        pending.append(command)
        agent.pending_cmds = pending
        await db.commit()
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
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        record = OnboardingToken(
            token=raw_token,
            org_id=org_id,
            created_by=user_id,
            label=request.headers.get("X-Agent-Label", "desktop-agent"),
            expires_at=expires_at,
        )
        db.add(record)
        await db.commit()
        return {"token": raw_token, "expires_in": 300, "org_id": org_id}

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













