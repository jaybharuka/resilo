from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.request
import uuid
from typing import Any

# Allow running as `python main.py` or packaged with PyInstaller
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import autostart
import collector
import config
import sender

# ── Token-based auto-registration ────────────────────────────────────────────
# Priority: env var > --token CLI arg > already-configured agent_key in config


def _register_via_token(backend_url: str, onboard_token: str, label: str) -> dict[str, Any]:
    """
    Exchange a one-time onboarding token for a persistent device_id + agent_key.
    Calls POST /agents/register on the Core API (no user auth required).
    """
    body = json.dumps({"token": onboard_token, "label": label}).encode()
    req = urllib.request.Request(
        f"{backend_url.rstrip('/')}/agents/register",
        method="POST",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        raise RuntimeError(f"Registration failed ({exc.code}): {raw}") from exc
    except Exception as exc:
        raise RuntimeError(f"Registration failed: {exc}") from exc


def main() -> None:
    cfg = config.load()

    # ── Step 1: resolve onboarding token (first-run only) ─────────────────────
    onboard_token = (
        os.getenv("RESILO_ONBOARD_TOKEN")
        or (sys.argv[1] if len(sys.argv) > 1 else "")
    )

    if onboard_token and not cfg.get("agent_key"):
        backend_url = os.getenv("RESILO_BACKEND_URL", cfg.get("backend_url", "http://localhost:8000"))
        label = os.getenv("RESILO_AGENT_LABEL") or f"desktop-{socket.gethostname()}"
        print(f"[info] Registering with backend {backend_url} …")
        try:
            result = _register_via_token(backend_url, onboard_token, label)
        except RuntimeError as exc:
            print(f"[error] {exc}")
            sys.exit(1)

        cfg["backend_url"] = backend_url
        cfg["org_id"]      = result["org_id"]
        cfg["agent_key"]   = result["agent_key"]
        cfg["device_id"]   = result["device_id"]
        cfg["label"]       = label
        cfg["consented"]   = True
        cfg["autostart"]   = os.getenv("RESILO_AUTOSTART", "0") == "1"
        config.save(cfg)
        print(f"[info] Registered — agent_id={result['agent_id']} device_id={cfg['device_id']}")

    # ── Step 2: ensure we have credentials ────────────────────────────────────
    if not cfg.get("agent_key"):
        print("[error] No agent_key. Set RESILO_ONBOARD_TOKEN=<token> and re-run.")
        sys.exit(1)

    if not cfg.get("device_id"):
        cfg["device_id"] = str(uuid.uuid4())
        config.save(cfg)

    # ── Step 3: optional auto-start ───────────────────────────────────────────
    if cfg.get("autostart"):
        try:
            autostart.register()
        except Exception as exc:
            print(f"[warn] Auto-start setup failed: {exc}")

    # ── Step 4: heartbeat loop ────────────────────────────────────────────────
    interval = max(2, int(cfg.get("interval", 5)))
    print(
        f"[info] Agent running — org={cfg['org_id']} "
        f"backend={cfg['backend_url']} interval={interval}s"
    )

    while True:
        try:
            metrics = collector.collect(cfg["device_id"], cfg["label"])
            ok = sender.send(cfg["backend_url"], cfg["org_id"], cfg["agent_key"], metrics)
            if ok:
                print(f"[heartbeat] cpu={metrics['cpu']}% mem={metrics['memory']}% disk={metrics['disk']}%")
            else:
                print("[warn] Heartbeat failed — data buffered for retry")
        except Exception as exc:
            print(f"[error] {exc}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
