from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections import deque
from typing import Any

_BUFFER: deque[dict[str, Any]] = deque(maxlen=50)
_RETRY_DELAYS = (2, 4, 8)


def _post(url: str, body: dict[str, Any], agent_key: str) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/json", "X-Agent-Key": agent_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = resp.read().decode()
            return resp.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed
    except Exception as exc:
        return 0, {"error": str(exc)}


def send(backend_url: str, org_id: str, agent_key: str, metrics: dict[str, Any]) -> bool:
    url = f"{backend_url.rstrip('/')}/ingest/heartbeat"
    body = {"org_id": org_id, "metrics": metrics}

    # Flush offline buffer first (best-effort)
    while _BUFFER:
        buffered = _BUFFER[0]
        for delay in _RETRY_DELAYS:
            status, _ = _post(url, buffered, agent_key)
            if status == 200:
                _BUFFER.popleft()
                break
            time.sleep(delay)
        else:
            break  # Still failing — stop trying the buffer

    # Send current payload with retries
    for delay in (*_RETRY_DELAYS, None):
        status, _ = _post(url, body, agent_key)
        if status == 200:
            return True
        if delay is None:
            break
        time.sleep(delay)

    _BUFFER.append(body)
    return False
