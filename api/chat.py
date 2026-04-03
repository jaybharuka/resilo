from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import psutil
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1")
legacy_router = APIRouter()


class ChatState:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._perf_history: list[dict[str, Any]] = []
        self._chat_hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _parse_rate_limit(rule: str) -> tuple[int, int]:
        # Supports "30 per minute" style config; defaults to 30 req / 60s.
        try:
            parts = rule.strip().lower().split()
            limit = int(parts[0])
            unit = parts[-1]
            if "hour" in unit:
                return limit, 3600
            if "second" in unit:
                return limit, 1
            return limit, 60
        except Exception:
            return 30, 60

    def allow_chat(self, client_id: str, rule: str) -> bool:
        limit, window = self._parse_rate_limit(rule)
        now = time.time()
        with self._lock:
            hits = [t for t in self._chat_hits.get(client_id, []) if now - t < window]
            if len(hits) >= limit:
                self._chat_hits[client_id] = hits
                return False
            hits.append(now)
            self._chat_hits[client_id] = hits
            return True

    def track_performance(self) -> None:
        snapshot = {
            "timestamp": datetime.now(timezone.utc).timestamp(),
            "cpu": psutil.cpu_percent(interval=0.0),
            "memory": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("/").percent if hasattr(psutil, "disk_usage") else 0,
        }
        with self._lock:
            self._perf_history.append(snapshot)
            if len(self._perf_history) > 2000:
                del self._perf_history[:-500]

    def make_job(self, name: str, result: dict[str, Any]) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        payload = {
            "id": job_id,
            "name": name,
            "status": "completed",
            "result": result,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            self._jobs[job_id] = payload
        return payload

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._jobs.get(job_id)

    def has_job(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._jobs

    def perf_tail(self, size: int) -> list[dict[str, Any]]:
        with self._lock:
            if not self._perf_history:
                return []
            return list(self._perf_history[-size:])


def _get_chat_state(request: Request) -> ChatState:
    state = getattr(request.app.state, "chat_state", None)
    if state is None:
        raise RuntimeError("chat_state was not initialized on app startup")
    return state


class ChatRequest(BaseModel):
    message: str


async def _chat_impl(message: str, state: ChatState) -> dict[str, Any]:
    if not message.strip():
        raise HTTPException(status_code=400, detail="Message is required")
    state.track_performance()
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    return {
        "response": (
            f"System snapshot: CPU {cpu:.1f}%, Memory {mem:.1f}%, Disk {disk:.1f}%. "
            "Legacy Flask chat endpoint migrated to FastAPI."
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _enforce_chat_guards(state: ChatState, request: Request, message: str) -> None:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        client_id = forwarded_for.split(",")[0].strip()
    else:
        client_id = request.client.host if request.client else "unknown"
    if not state.allow_chat(client_id, os.getenv("RATE_LIMIT_CHAT", "30 per minute")):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    max_len = int(os.getenv("CHAT_MAX_MESSAGE_LEN", "4000"))
    if len(message) > max_len:
        raise HTTPException(
            status_code=400,
            detail=f"Message exceeds maximum length of {max_len} characters",
        )


def _require_auth(request: Request) -> None:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT secret is not configured")
    token = auth.replace("Bearer ", "", 1).strip()
    try:
        jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/chat")
@legacy_router.post("/api/chat")
@legacy_router.post("/chat")
async def chat(body: ChatRequest, request: Request):
    state = _get_chat_state(request)
    _require_auth(request)
    _enforce_chat_guards(state, request, body.message)
    return await _chat_impl(body.message, state)


@router.post("/chat/stream")
@legacy_router.post("/chat/stream")
async def chat_stream(body: ChatRequest, request: Request):
    state = _get_chat_state(request)
    _require_auth(request)
    _enforce_chat_guards(state, request, body.message)
    payload = await _chat_impl(body.message, state)
    text = payload["response"]

    async def gen():
        for token in text.split(" "):
            yield f"data: {token}\\n\\n"
            await asyncio.sleep(0.01)
        yield "event: done\\n"
        yield "data: [DONE]\\n\\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@legacy_router.get("/api/system")
async def system_metrics(request: Request):
    _require_auth(request)
    return {
        "cpu": psutil.cpu_percent(interval=0.0),
        "memory": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage("/").percent,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


@legacy_router.get("/events/system")
async def system_events(request: Request):
    _require_auth(request)

    async def gen():
        while True:
            if await request.is_disconnected():
                break
            yield f"data: {json.dumps(await system_metrics(request))}\\n\\n"
            await asyncio.sleep(3)

    return StreamingResponse(gen(), media_type="text/event-stream")


@legacy_router.get("/api/insights")
async def insights(request: Request):
    _require_auth(request)
    return []


@legacy_router.post("/api/analyze")
async def analyze(_: dict[str, Any], request: Request):
    _require_auth(request)
    return {"status": "queued", "message": "Analyzer endpoint migrated to FastAPI"}


@legacy_router.api_route(
    "/auth/ping",
    methods=["GET", "POST", "OPTIONS"],
    operation_id="legacy_auth_ping",
)
async def auth_ping():
    return {"ok": True, "auth_system": True}


@legacy_router.post("/actions/process-monitor")
async def process_monitor(request: Request):
    _require_auth(request)
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
    state = _get_chat_state(request)
    return state.make_job(
        "process-monitor",
        {
            "total_processes": len(procs),
            "top_processes": procs[:10],
            "message": f"Snapshot of {len(procs)} processes captured",
        },
    )


@legacy_router.post("/actions/emergency-stop")
async def emergency_stop(_: dict[str, Any], request: Request):
    _require_auth(request)
    confirm = bool(_.get("confirm", False))
    if not confirm:
        raise HTTPException(status_code=400, detail="Confirmation required. Send {confirm: true}")
    own_pid = os.getpid()
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
        try:
            info = p.info
            if info.get("pid") != own_pid:
                procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
    if not procs:
        return {"message": "No candidate processes found"}
    top = procs[0]
    state = _get_chat_state(request)
    return state.make_job(
        "emergency-stop",
        {
            "targeted_pid": top.get("pid"),
            "targeted_name": top.get("name"),
            "cpu_percent": top.get("cpu_percent"),
            "message": (
                f"Identified top CPU process: {top.get('name')} (PID {top.get('pid')}) "
                "- kill not executed for safety"
            ),
            "note": "Automatic kill is disabled; use OS task manager to terminate if needed",
        },
    )


@legacy_router.post("/ai/diagnostics")
async def ai_diagnostics(request: Request):
    _require_auth(request)
    state = _get_chat_state(request)
    return state.make_job("ai-diagnostics", {"status": "healthy"})


@legacy_router.post("/ai/retrain")
async def ai_retrain(request: Request):
    _require_auth(request)
    state = _get_chat_state(request)
    return state.make_job("ai-retrain", {"status": "queued"})


@legacy_router.post("/ai/update-params")
async def ai_update_params(payload: dict[str, Any], request: Request):
    _require_auth(request)
    state = _get_chat_state(request)
    return state.make_job("ai-update-params", {"params_received": list(payload.keys())})


@legacy_router.post("/ai/export-insights")
async def ai_export(request: Request):
    _require_auth(request)
    state = _get_chat_state(request)
    return state.make_job("ai-export", {"exported_at": datetime.now(timezone.utc).isoformat()})


@legacy_router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    _require_auth(request)
    state = _get_chat_state(request)
    job = state.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@legacy_router.get("/jobs/{job_id}/logs")
async def get_job_logs(job_id: str, request: Request):
    _require_auth(request)
    state = _get_chat_state(request)
    if not state.has_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"logs": [f"[INFO] Job {job_id} completed"]}


@legacy_router.get("/jobs/{job_id}/download")
async def get_job_download(job_id: str, request: Request):
    _require_auth(request)
    state = _get_chat_state(request)
    job = state.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.get("result", {})


@legacy_router.post("/integrations/slack/test")
async def slack_test(_: dict[str, Any], request: Request):
    _require_auth(request)
    return {"ok": True, "message": "Slack test payload accepted"}


@legacy_router.post("/integrations/discord/test")
async def discord_test(_: dict[str, Any], request: Request):
    _require_auth(request)
    return {"ok": True, "message": "Discord test payload accepted"}


@legacy_router.get("/api/performance")
async def performance_data(request: Request):
    _require_auth(request)
    state = _get_chat_state(request)
    timeframe = request.query_params.get("timeframe", "1hour")
    try:
        max_points = int(request.query_params.get("max_points", "120"))
    except ValueError:
        raise HTTPException(status_code=400, detail="max_points must be an integer")
    max_points = max(1, min(max_points, 2000))

    window_map = {"1hour": 3600, "6hours": 21600, "24hours": 86400}
    cutoff = datetime.now(timezone.utc).timestamp() - window_map.get(timeframe, 3600)

    history = [p for p in state.perf_tail(2000) if p.get("timestamp", 0) >= cutoff]
    if not history:
        state.track_performance()
        history = [p for p in state.perf_tail(2000) if p.get("timestamp", 0) >= cutoff]

    if len(history) > max_points:
        step = len(history) / max_points
        history = [history[int(i * step)] for i in range(max_points)]

    return history
