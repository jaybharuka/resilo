from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault("BACKUP_DIR", "./backups")
os.environ.setdefault("DEPLOY_HOST", "http://localhost:8000")
os.environ.setdefault("ADMIN_DEFAULT_EMAIL", "admin@company.local")

import api.websocket as websocket_module
import app.api.runtime as runtime_module
from app.api.runtime import (RealtimeHub, build_stream_router,
                             get_realtime_hub_from_app)


class _DummySession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, user_id):
        return SimpleNamespace(is_active=True)


def _build_test_app(monkeypatch) -> FastAPI:
    app = FastAPI()
    app.state.realtime_hub = RealtimeHub()
    app.include_router(runtime_module.build_stream_router())
    app.include_router(websocket_module.router)

    async def _fake_require_access_token(request):
        return {"org_id": "org-1", "sub": "user-1", "role": "admin", "type": "access"}

    monkeypatch.setattr(runtime_module, "_require_access_token", _fake_require_access_token)
    monkeypatch.setattr(websocket_module.jwt, "decode", lambda *_args, **_kwargs: {"type": "access", "sub": "user-1", "org_id": "org-1"})
    monkeypatch.setattr(websocket_module, "SessionLocal", lambda: _DummySession())
    os.environ["JWT_SECRET_KEY"] = "test-secret"
    return app


class _FakeRequest:
    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected


def test_sse_metrics_stream_receives_published_event(monkeypatch):
    app = _build_test_app(monkeypatch)
    hub = get_realtime_hub_from_app(app)
    request = _FakeRequest(app)

    payload = {
        "id": "snapshot-1",
        "org_id": "org-1",
        "cpu": 41.0,
        "memory": 62.0,
        "disk": 38.0,
    }
    stream = runtime_module._stream_realtime_events("metric_update", "org-1", request)

    async def _read_chunk() -> str:
        async def _publish_later() -> None:
            await asyncio.sleep(0.05)
            hub.publish("metric_update", payload, "org-1")

        publisher = asyncio.create_task(_publish_later())
        chunk = await asyncio.wait_for(stream.__anext__(), timeout=1)
        await publisher
        return chunk

    chunk = asyncio.run(_read_chunk())
    request._disconnected = True
    asyncio.run(stream.aclose())

    assert chunk.startswith("event: metric_update")
    line = next(part for part in chunk.splitlines() if part.startswith("data: "))
    seen = json.loads(line[6:])
    assert seen["id"] == "snapshot-1"
    assert seen["org_id"] == "org-1"


def test_websocket_receives_published_metric_event(monkeypatch):
    app = _build_test_app(monkeypatch)
    hub = get_realtime_hub_from_app(app)

    payload = {
        "id": "metric-evt-1",
        "org_id": "org-1",
        "cpu": 33.0,
        "memory": 48.0,
        "disk": 22.0,
    }

    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/v1/ws",
            headers={"Authorization": "Bearer test"},
        ) as ws:
            hub.publish("metric_update", payload, "org-1")
            message = json.loads(ws.receive_text())

    assert message["type"] == "metric_update"
    assert message["data"]["id"] == "metric-evt-1"
    assert message["org_id"] == "org-1"


def test_realtime_hub_backpressure_drops_oldest_and_preserves_order():
    hub = RealtimeHub()
    queue = hub.subscribe("org-1")
    max_size = queue.maxsize

    total_events = max_size + 5
    for seq in range(total_events):
        hub.publish("metric_update", {"seq": seq}, "org-1")

    assert queue.qsize() == max_size

    received = [queue.get_nowait()["data"]["seq"] for _ in range(max_size)]
    expected = list(range(total_events - max_size, total_events))
    assert received == expected
