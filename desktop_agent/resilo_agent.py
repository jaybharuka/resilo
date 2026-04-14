"""
Resilo Agent — single-file edition.
Install: pip install psutil
Run:     RESILO_ONBOARD_TOKEN=<token> RESILO_BACKEND_URL=https://... python resilo_agent.py
Persist: python resilo_agent.py --install      # install as startup service
Remove:  python resilo_agent.py --uninstall    # remove startup service
"""
from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from typing import Any

# ── Collector ────────────────────────────────────────────────────────────────
try:
    import psutil
except ImportError:
    print("[error] psutil not installed. Run: pip install psutil")
    sys.exit(1)


def _disk_root() -> str:
    return "C:\\" if platform.system() == "Windows" else "/"


def _load_avg() -> str | None:
    try:
        avg = psutil.getloadavg()
        return f"{avg[0]:.2f} {avg[1]:.2f} {avg[2]:.2f}"
    except AttributeError:
        return None


def _temperature() -> float | None:
    try:
        temps = psutil.sensors_temperatures()
        if not temps:
            return None
        for key in ("coretemp", "cpu_thermal", "k10temp", "acpitz"):
            if key in temps and temps[key]:
                return round(temps[key][0].current, 1)
        first_key = next(iter(temps))
        if temps[first_key]:
            return round(temps[first_key][0].current, 1)
    except (AttributeError, NotImplementedError):
        pass
    return None


def collect(device_id: str, label: str) -> dict[str, Any]:
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(_disk_root())
    net = psutil.net_io_counters()
    return {
        "cpu": round(psutil.cpu_percent(interval=0.5), 2),
        "memory": round(vm.percent, 2),
        "disk": round(disk.percent, 2),
        "network_in": int(net.bytes_recv),
        "network_out": int(net.bytes_sent),
        "temperature": _temperature(),
        "load_avg": _load_avg(),
        "processes": len(psutil.pids()),
        "uptime_secs": int(time.time() - psutil.boot_time()),
        "extra": {
            "device_id": device_id,
            "agent_label": label,
            "hostname": socket.gethostname(),
            "platform": platform.system(),
            "os_version": platform.version(),
            "error_rate": 0,
        },
    }


# ── Sender ───────────────────────────────────────────────────────────────────
_BUFFER: deque[dict[str, Any]] = deque(maxlen=50)
_RETRY_DELAYS = (2, 4, 8)


def _post(url: str, body: dict[str, Any], agent_key: str) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, method="POST", data=data,
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


def send(backend_url: str, org_id: str, agent_key: str, metrics: dict[str, Any]) -> tuple[bool, float]:
    """Send heartbeat. Returns (success, poll_interval)."""
    url = f"{backend_url.rstrip('/')}/ingest/heartbeat"
    body = {"org_id": org_id, "metrics": metrics}
    while _BUFFER:
        buffered = _BUFFER[0]
        for delay in _RETRY_DELAYS:
            status, _ = _post(url, buffered, agent_key)
            if status == 200:
                _BUFFER.popleft()
                break
            time.sleep(delay)
        else:
            break
    for delay in (*_RETRY_DELAYS, None):
        status, resp = _post(url, body, agent_key)
        if status == 200:
            return True, float(resp.get("poll_interval", 5))
        if delay is None:
            break
        time.sleep(delay)
    _BUFFER.append(body)
    return False, 5.0


def _poll_commands(backend_url: str, agent_key: str) -> list[dict[str, Any]]:
    """Fetch and clear pending commands from backend. Returns list of commands."""
    url = f"{backend_url.rstrip('/')}/agent/command?token={agent_key}"
    req = urllib.request.Request(url, method="GET",
                                  headers={"X-Agent-Key": agent_key})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("commands", [])
    except Exception:
        return []


def _execute_command(cmd: dict[str, Any]) -> None:
    """Execute a command received from backend."""
    action = cmd.get("action", "")
    target = cmd.get("target", "")
    print(f"[cmd] Executing: {action} → {target}")
    if action == "restart_service" and target:
        import subprocess
        try:
            subprocess.run(["systemctl", "restart", target], timeout=15, check=False)
        except Exception as exc:
            print(f"[cmd] restart_service failed: {exc}")
    elif action == "free_memory":
        try:
            import subprocess
            subprocess.run(["sync"], timeout=5, check=False)
        except Exception:
            pass
    elif action in ("scale_memory", "disk_cleanup", "notify_only", "noop"):
        print(f"[cmd] {action} acknowledged — no direct execution")
    else:
        print(f"[cmd] Unknown action '{action}' — ignored")


# ── Config ───────────────────────────────────────────────────────────────────
_CFG_PATH = os.path.join(os.path.expanduser("~"), ".resilo_agent.json")


def _load_cfg() -> dict[str, Any]:
    try:
        with open(_CFG_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cfg(cfg: dict[str, Any]) -> None:
    with open(_CFG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Registration ─────────────────────────────────────────────────────────────
def _register(backend_url: str, onboard_token: str, label: str) -> dict[str, Any]:
    body = json.dumps({"token": onboard_token, "label": label}).encode()
    req = urllib.request.Request(
        f"{backend_url.rstrip('/')}/agents/register",
        method="POST", data=body,
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


# ── Service persistence ───────────────────────────────────────────────────────
_TASK_NAME = "ResilioAgent"

def _install_service() -> None:
    """Register the agent to run on startup, surviving shell close."""
    script = os.path.abspath(__file__)
    system = platform.system()

    if system == "Windows":
        # Find pythonw.exe (runs without a console window)
        pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable  # fallback
        cmd = (
            f'schtasks /create /tn "{_TASK_NAME}" '
            f'/tr "\\"{pythonw}\\" \\"{script}\\"" '
            f'/sc onlogon /ru "{os.environ.get("USERNAME", "%USERNAME%")}" '
            f'/rl highest /f'
        )
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"[install] Registered Windows scheduled task '{_TASK_NAME}'")
            print(f"[install] Agent will start automatically on next login.")
            print(f"[install] To start now: schtasks /run /tn {_TASK_NAME}")
        else:
            print(f"[error] schtasks failed: {result.stderr.strip()}")
            sys.exit(1)

    elif system in ("Linux", "Darwin"):
        service_name = "resilo-agent"
        python_exe   = sys.executable
        unit = f"""[Unit]
Description=Resilo Agent — system metrics push agent
After=network.target

[Service]
Type=simple
ExecStart={python_exe} {script}
Restart=always
RestartSec=10
Environment=RESILO_BACKEND_URL={os.environ.get('RESILO_BACKEND_URL', 'https://resilo.onrender.com')}

[Install]
WantedBy=default.target
"""
        # Try user-level systemd first (no sudo needed)
        unit_dir = os.path.expanduser("~/.config/systemd/user")
        unit_path = os.path.join(unit_dir, f"{service_name}.service")
        os.makedirs(unit_dir, exist_ok=True)
        with open(unit_path, "w") as f:
            f.write(unit)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(["systemctl", "--user", "enable", "--now", service_name], check=False)
        subprocess.run(["loginctl", "enable-linger", os.environ.get("USER", "")], check=False)
        print(f"[install] systemd user service enabled: {service_name}")
        print(f"[install] Agent runs on boot — survives terminal close.")
        print(f"[install] Status: systemctl --user status {service_name}")
    else:
        print(f"[error] Unsupported platform: {system}")
        sys.exit(1)


def _uninstall_service() -> None:
    """Remove the startup service registration."""
    system = platform.system()
    if system == "Windows":
        result = subprocess.run(
            f'schtasks /delete /tn "{_TASK_NAME}" /f',
            shell=True, capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"[uninstall] Removed Windows scheduled task '{_TASK_NAME}'")
        else:
            print(f"[warn] Could not remove task: {result.stderr.strip()}")
    elif system in ("Linux", "Darwin"):
        service_name = "resilo-agent"
        subprocess.run(["systemctl", "--user", "disable", "--now", service_name], check=False)
        unit_path = os.path.expanduser(f"~/.config/systemd/user/{service_name}.service")
        if os.path.exists(unit_path):
            os.remove(unit_path)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        print(f"[uninstall] Removed systemd service '{service_name}'")
    else:
        print(f"[error] Unsupported platform: {system}")


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    args = sys.argv[1:]
    if "--install" in args:
        _install_service()
        return
    if "--uninstall" in args:
        _uninstall_service()
        return

    cfg = _load_cfg()

    onboard_token = os.getenv("RESILO_ONBOARD_TOKEN") or (args[0] if args and not args[0].startswith("--") else "")
    backend_url   = os.getenv("RESILO_BACKEND_URL") or cfg.get("backend_url", "https://resilo.onrender.com")

    if onboard_token and not cfg.get("agent_key"):
        label = os.getenv("RESILO_AGENT_LABEL") or f"desktop-{socket.gethostname()}"
        print(f"[info] Registering with {backend_url} …")
        try:
            result = _register(backend_url, onboard_token, label)
        except RuntimeError as exc:
            print(f"[error] {exc}")
            sys.exit(1)
        cfg.update({
            "backend_url": backend_url,
            "org_id":      result["org_id"],
            "agent_key":   result["agent_key"],
            "device_id":   result["device_id"],
            "label":       label,
        })
        _save_cfg(cfg)
        print(f"[info] Registered — agent_id={result['agent_id']}")

    if not cfg.get("agent_key"):
        print("[error] No agent_key. Set RESILO_ONBOARD_TOKEN=<token> and re-run.")
        sys.exit(1)

    if not cfg.get("device_id"):
        cfg["device_id"] = str(uuid.uuid4())
        _save_cfg(cfg)

    interval = 5.0
    print(f"[info] Agent running — backend={cfg['backend_url']} interval={interval}s")

    while True:
        try:
            metrics = collect(cfg["device_id"], cfg.get("label", "agent"))
            ok, srv_interval = send(cfg["backend_url"], cfg["org_id"], cfg["agent_key"], metrics)
            if ok:
                print(f"[heartbeat] cpu={metrics['cpu']}% mem={metrics['memory']}% disk={metrics['disk']}%")
                if srv_interval != interval:
                    print(f"[poll] interval={srv_interval}s")
                interval = srv_interval
            else:
                print("[warn] Heartbeat failed — buffered for retry")

            commands = _poll_commands(cfg["backend_url"], cfg["agent_key"])
            if commands:
                for cmd in commands:
                    _execute_command(cmd)
                print(f"[poll] {len(commands)} command(s) executed — re-polling immediately")
                time.sleep(0.5)
                continue
        except Exception as exc:
            print(f"[error] {exc}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
