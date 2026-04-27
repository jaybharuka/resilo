from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any

import psutil

BACKEND_URL = os.getenv("RESILO_BACKEND_URL", "http://host.docker.internal:8000").rstrip("/")
ORG_ID = os.getenv("RESILO_ORG_ID", "")
AGENT_KEY = os.getenv("RESILO_AGENT_KEY", "")
AGENT_LABEL = os.getenv("RESILO_AGENT_LABEL", f"docker-agent-{socket.gethostname()}")
INTERVAL = int(os.getenv("RESILO_AGENT_INTERVAL", "5"))
REGISTER_TOKEN = os.getenv("RESILO_REGISTER_TOKEN", "")


def _request(path: str, method: str = "GET", body: dict[str, Any] | None = None, token: str | None = None) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if AGENT_KEY:
        headers["X-Agent-Key"] = AGENT_KEY
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{BACKEND_URL}{path}", method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            payload = response.read().decode("utf-8")
            return response.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8")
        try:
            parsed = json.loads(payload) if payload else {}
        except json.JSONDecodeError:
            parsed = {"raw": payload}
        return exc.code, parsed


def _metrics() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    return {
        "cpu": round(psutil.cpu_percent(interval=0.5), 2),
        "memory": round(vm.percent, 2),
        "disk": round(disk.percent, 2),
        "network_in": int(net.bytes_recv),
        "network_out": int(net.bytes_sent),
        "processes": len(psutil.pids()),
        "uptime_secs": int(time.time() - psutil.boot_time()),
        "extra": {"agent_label": AGENT_LABEL, "hostname": socket.gethostname(), "error_rate": 0},
    }


def _discover_org() -> str:
    if ORG_ID:
        return ORG_ID
    if not REGISTER_TOKEN:
        return ""
    status, payload = _request("/api/orgs", token=REGISTER_TOKEN)
    if status == 200 and isinstance(payload, list) and payload:
        return payload[0].get("id", "")
    return ""


def _auto_register(org_id: str) -> None:
    global AGENT_KEY
    if AGENT_KEY or not REGISTER_TOKEN:
        return
    status, payload = _request(f"/api/orgs/{org_id}/agents", method="POST", body={"label": AGENT_LABEL}, token=REGISTER_TOKEN)
    if status in (200, 201):
        AGENT_KEY = payload.get("raw_key", "")


def main() -> None:
    org_id = _discover_org()
    if not org_id:
        raise SystemExit("RESILO_ORG_ID required unless RESILO_REGISTER_TOKEN can query orgs")
    _auto_register(org_id)
    if not AGENT_KEY:
        raise SystemExit("RESILO_AGENT_KEY required (or provide RESILO_REGISTER_TOKEN)")

    print(f"Docker agent started for org={org_id} backend={BACKEND_URL}")
    while True:
        status, payload = _request("/ingest/heartbeat", method="POST", body={"org_id": org_id, "metrics": _metrics()})
        if status != 200:
            print(f"Heartbeat failed ({status}): {payload}")
        time.sleep(max(2, INTERVAL))


if __name__ == "__main__":
    main()
