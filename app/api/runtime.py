from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import base64
import uuid
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import (
    Agent,
    AlertRecord,
    MetricSnapshot,
    Organization,
    User,
    UserSession,
    RemediationJob,
    get_db,
    SessionLocal,
)

from app.remediation.executor import execute_playbook

JWT_ALGORITHM = "HS256"
ACCESS_TTL_SECONDS = int(os.getenv("JWT_ACCESS_TTL", "86400"))
REFRESH_TTL_SECONDS = int(os.getenv("JWT_REFRESH_TTL", "2592000"))
STREAM_TTL_SECONDS = int(os.getenv("JWT_STREAM_TTL", "60"))
FAILED_ATTEMPT_LIMIT = 5
LOCKOUT_MINUTES = 15
PASSWORD_ITERATIONS = 260000
DEFAULT_ADMIN_EMAIL = "admin@company.local"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_ORG = "default"
SSE_HEARTBEAT_SECONDS = int(os.getenv("SSE_HEARTBEAT_SECONDS", "30"))
WS_QUEUE_MAX_SIZE = int(os.getenv("WS_QUEUE_MAX_SIZE", "100"))
MAX_CONNECTED_CLIENTS = int(os.getenv("MAX_CONNECTED_CLIENTS", "50"))

ALERT_TO_PLAYBOOK = {
    "cpu": "high_cpu",
    "cpu_spike": "high_cpu",
    "error_rate": "high_error_rate",
    "error_spike": "high_error_rate",
    "disk": "disk_full",
    "disk_usage": "disk_full",
}


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


async def _require_access_token(request: Request, *, allow_stream_token: bool = False) -> dict[str, Any]:
    header = request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        return await _require_valid_access_payload(header.removeprefix("Bearer ").strip())

    token = request.query_params.get("token")
    if allow_stream_token and token:
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
    if not token_org:
        raise HTTPException(status_code=403, detail="Organization scope required")
    if token_org != org_id:
        raise HTTPException(status_code=403, detail="Forbidden for this organization")
    return payload


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
        org_result = await db.execute(select(Organization).where(Organization.slug == DEFAULT_ADMIN_ORG))
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

    @router.post("/auth/login")
    async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        user = await _get_user_by_email(db, body.email)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        now = _now()
        locked_until = _as_utc(user.locked_until)
        if locked_until and locked_until > now:
            raise HTTPException(status_code=403, detail="Account is locked")

        if not _verify_password(body.password, user.hashed_password):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= FAILED_ATTEMPT_LIMIT:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_attempts = FAILED_ATTEMPT_LIMIT
                await db.commit()
                raise HTTPException(status_code=403, detail="Account is locked")
            await db.commit()
            raise HTTPException(status_code=401, detail="Invalid credentials")

        user.failed_attempts = 0
        user.locked_until = None
        user.last_login = now
        access_token = _create_access_token(user)
        refresh_token = _create_refresh_token(user)
        session = UserSession(
            user_id=user.id,
            refresh_token_hash=_hash_refresh_token(refresh_token),
            expires_at=now + timedelta(seconds=REFRESH_TTL_SECONDS),
            is_revoked=False,
        )
        db.add(session)
        await db.commit()
        return {
            "token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    @router.get("/auth/me")
    async def me(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        payload = await _require_access_token(request)
        user = await _get_user_by_id(db, payload["sub"])
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid token")
        return _serialize_user(user)

    @router.post("/auth/refresh")
    async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        payload = _decode_token(body.refresh_token, "refresh")
        session = await _get_session_by_refresh_token(db, body.refresh_token)
        expires_at = _as_utc(session.expires_at) if session is not None else None
        if session is None or session.is_revoked or (expires_at is not None and expires_at < _now()):
            raise HTTPException(status_code=401, detail="Refresh token is invalid")

        user = await _get_user_by_id(db, payload["sub"])
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Invalid token")

        session.is_revoked = True
        new_refresh = _create_refresh_token(user)
        new_session = UserSession(
            user_id=user.id,
            refresh_token_hash=_hash_refresh_token(new_refresh),
            expires_at=_now() + timedelta(seconds=REFRESH_TTL_SECONDS),
            is_revoked=False,
        )
        db.add(new_session)
        await db.commit()
        return {
            "token": _create_access_token(user),
            "refresh_token": new_refresh,
            "token_type": "bearer",
        }

    @router.post("/auth/logout")
    async def logout(body: LogoutRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        session = await _get_session_by_refresh_token(db, body.refresh_token)
        if session is not None:
            session.is_revoked = True
            await db.commit()
        return {"ok": True}

    @router.get("/auth/health")
    async def auth_health() -> dict[str, str]:
        return {"status": "ok", "service": "auth"}

    return router


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
        agent.status = "online"

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
        _get_realtime_hub(request).publish("metric_update", _serialize_metric(snapshot), body.org_id)
        return {"ok": True, "received_at": snapshot.timestamp.isoformat(), "snapshot": _serialize_metric(snapshot)}

    # Allowed bucket/window intervals to prevent caller-supplied unbounded SQL interval strings.
    _ALLOWED_BUCKETS = frozenset({"5 minutes", "15 minutes", "30 minutes", "1 hour", "6 hours", "12 hours", "1 day"})
    _ALLOWED_WINDOWS = frozenset({"1 hour", "6 hours", "12 hours", "24 hours", "3 days", "7 days", "30 days"})
    _METRICS_MAX_LIMIT = 500

    @router.get("/api/orgs/{org_id}/metrics/summary")
    async def metrics_summary(org_id: str, request: Request, bucket: str = "1 hour", window: str = "24 hours", limit: int = 100, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        await _require_org_access(request, org_id)
        if bucket not in _ALLOWED_BUCKETS:
            raise HTTPException(status_code=400, detail=f"Invalid bucket. Allowed: {sorted(_ALLOWED_BUCKETS)}")
        if window not in _ALLOWED_WINDOWS:
            raise HTTPException(status_code=400, detail=f"Invalid window. Allowed: {sorted(_ALLOWED_WINDOWS)}")
        effective_limit = max(1, min(limit, _METRICS_MAX_LIMIT))
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
            {"bucket": bucket, "window": window, "org_id": org_id, "limit": effective_limit},
        )
        return [dict(row) for row in result.mappings().all()]

    @router.get("/api/orgs/{org_id}/metrics")
    async def list_metrics(org_id: str, request: Request, limit: int = 100, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        await _require_org_access(request, org_id)
        effective_limit = max(1, min(limit, _METRICS_MAX_LIMIT))
        result = await db.execute(
            select(MetricSnapshot)
            .where(MetricSnapshot.org_id == org_id)
            .order_by(desc(MetricSnapshot.timestamp))
            .limit(effective_limit)
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

    @router.post("/api/orgs/{org_id}/alerts", status_code=status.HTTP_201_CREATED)
    async def create_alert(org_id: str, body: AlertCreateRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
        payload = await _require_org_access(request, org_id)
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

        playbook_type = ALERT_TO_PLAYBOOK.get((body.category or "").strip().lower())
        if playbook_type:
            context = {
                "org_id": org_id,
                "agent_id": body.agent_id,
                "severity": body.severity,
                "category": body.category,
                "title": body.title,
                "detail": body.detail,
                "metric_value": body.metric_value,
                "threshold": body.threshold,
                "status": body.status,
            }
            db.add(
                RemediationJob(
                    org_id=org_id,
                    alert_id=alert.id,
                    playbook_type=playbook_type,
                    status="pending",
                    payload=context,
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

    return router


def build_agents_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/orgs")
    async def list_orgs(request: Request, db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
        payload = await _require_access_token(request)
        token_org = payload.get("org_id")
        if token_org:
            result = await db.execute(
                select(Organization)
                .where(Organization.id == token_org)
                .order_by(Organization.name)
            )
        else:
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
        payload = await _require_access_token(request, allow_stream_token=True)
        org_id = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")
        return StreamingResponse(_stream_realtime_events("metric_update", org_id, request), media_type="text/event-stream")

    @router.get("/stream/alerts")
    async def alerts_stream(request: Request) -> StreamingResponse:
        payload = await _require_access_token(request, allow_stream_token=True)
        org_id = payload.get("org_id")
        if not org_id:
            raise HTTPException(status_code=403, detail="Organization scope required")
        return StreamingResponse(_stream_realtime_events("alert_update", org_id, request), media_type="text/event-stream")

    return router

