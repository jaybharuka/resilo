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

_prev_disk_io: dict[str, Any] = {"read_bytes": 0, "write_bytes": 0, "ts": 0.0}
_BUFFER_PATH = os.path.join(os.path.expanduser("~"), ".resilo_buffer.json")


def _disk_root() -> str:
    return "C:\\" if platform.system() == "Windows" else "/"


def _load_avg_full() -> tuple[float, float, float] | None:
    try:
        avg = psutil.getloadavg()
        return (round(avg[0], 2), round(avg[1], 2), round(avg[2], 2))
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


_PSEUDO_PROCESSES = {"system idle process", "idle", "system", "registry", "memory compression"}

def get_top_processes(n: int = 5) -> dict[str, list[dict]]:
    cpu_count = max(psutil.cpu_count(logical=True) or 1, 1)
    by_cpu: list[dict] = []
    by_mem: list[dict] = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = proc.info
            name = info["name"] or ""
            if name.lower() in _PSEUDO_PROCESSES:
                continue
            entry = {
                "pid": info["pid"],
                "name": name,
                "cpu_percent": round((info["cpu_percent"] or 0.0) / cpu_count, 1),
                "memory_percent": round(info["memory_percent"] or 0.0, 1),
            }
            by_cpu.append(entry)
            by_mem.append(entry)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    by_cpu.sort(key=lambda x: x["cpu_percent"], reverse=True)
    by_mem.sort(key=lambda x: x["memory_percent"], reverse=True)
    return {"by_cpu": by_cpu[:n], "by_mem": by_mem[:n]}


def _disk_io_delta() -> tuple[float, float]:
    global _prev_disk_io
    now = time.time()
    try:
        io = psutil.disk_io_counters()
        if io is None:
            return 0.0, 0.0
        dt = now - _prev_disk_io["ts"]
        if _prev_disk_io["ts"] == 0.0 or dt <= 0:
            _prev_disk_io = {"read_bytes": io.read_bytes, "write_bytes": io.write_bytes, "ts": now}
            return 0.0, 0.0
        dr = round((io.read_bytes  - _prev_disk_io["read_bytes"])  / dt / 1_048_576, 2)
        dw = round((io.write_bytes - _prev_disk_io["write_bytes"]) / dt / 1_048_576, 2)
        _prev_disk_io = {"read_bytes": io.read_bytes, "write_bytes": io.write_bytes, "ts": now}
        return max(0.0, dr), max(0.0, dw)
    except Exception:
        return 0.0, 0.0


def _net_conn_counts() -> dict[str, int]:
    counts = {"established": 0, "close_wait": 0, "time_wait": 0}
    try:
        for conn in psutil.net_connections():
            s = conn.status
            if s == "ESTABLISHED":
                counts["established"] += 1
            elif s == "CLOSE_WAIT":
                counts["close_wait"] += 1
            elif s == "TIME_WAIT":
                counts["time_wait"] += 1
    except (psutil.AccessDenied, Exception):
        pass
    return counts


def _disk_partitions_list() -> list[dict]:
    parts = []
    for p in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(p.mountpoint)
            parts.append({
                "device": p.device,
                "mountpoint": p.mountpoint,
                "total_gb": round(usage.total / 1_073_741_824, 2),
                "used_gb":  round(usage.used  / 1_073_741_824, 2),
                "percent":  round(usage.percent, 1),
            })
        except PermissionError:
            continue
    return parts


def collect(device_id: str, label: str) -> dict[str, Any]:
    vm   = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage(_disk_root())
    net  = psutil.net_io_counters()
    load = _load_avg_full()
    dr_mbps, dw_mbps = _disk_io_delta()
    net_counts = _net_conn_counts()
    battery    = psutil.sensors_battery()
    payload: dict[str, Any] = {
        "cpu":         round(psutil.cpu_percent(interval=0.5), 2),
        "memory":      round(vm.percent, 2),
        "disk":        round(disk.percent, 2),
        "network_in":  int(net.bytes_recv),
        "network_out": int(net.bytes_sent),
        "temperature": _temperature(),
        "load_avg":    f"{load[0]} {load[1]} {load[2]}" if load else None,
        "processes":   len(psutil.pids()),
        "uptime_secs": int(time.time() - psutil.boot_time()),
        "top_processes": get_top_processes(),
        "swap_percent":  round(swap.percent, 1),
        "swap_used_gb":  round(swap.used / 1_073_741_824, 2),
        "disk_read_mbps":  dr_mbps,
        "disk_write_mbps": dw_mbps,
        "net_established": net_counts["established"],
        "net_close_wait":  net_counts["close_wait"],
        "net_time_wait":   net_counts["time_wait"],
        "uptime_hours":    round((time.time() - psutil.boot_time()) / 3600, 1),
        "disk_partitions": _disk_partitions_list(),
    }
    if load:
        payload["load_avg_1m"]  = load[0]
        payload["load_avg_5m"]  = load[1]
        payload["load_avg_15m"] = load[2]
    if battery is not None:
        payload["battery_percent"] = round(battery.percent, 1)
        payload["battery_plugged"] = battery.power_plugged
    payload["extra"] = {
        "device_id":   device_id,
        "agent_label": label,
        "hostname":    socket.gethostname(),
        "platform":    platform.system(),
        "os_version":  platform.version(),
        "error_rate":  0,
    }
    return payload


# ── Sender ───────────────────────────────────────────────────────────────────
_BUFFER: deque[dict[str, Any]] = deque(maxlen=20)
_RETRY_DELAYS = (5, 10, 30, 60, 60)
_OFFLINE_MODE = False


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


def _save_buffer() -> None:
    try:
        with open(_BUFFER_PATH, "w") as f:
            json.dump(list(_BUFFER), f)
    except Exception:
        pass


def _load_buffer() -> None:
    try:
        with open(_BUFFER_PATH) as f:
            data = json.load(f)
        if isinstance(data, list):
            for item in data:
                _BUFFER.append(item)
        if _BUFFER:
            print(f"[offline] Loaded {len(_BUFFER)} buffered payload(s) from disk")
    except Exception:
        pass


def _flush_buffer(url: str, agent_key: str) -> None:
    flushed = 0
    while _BUFFER:
        status, _ = _post(url, _BUFFER[0], agent_key)
        if status == 200:
            _BUFFER.popleft()
            flushed += 1
        else:
            break
    if flushed:
        print(f"[reconnect] Flushed {flushed} buffered heartbeat(s) to backend")
    _save_buffer()


def send(backend_url: str, org_id: str, agent_key: str, metrics: dict[str, Any]) -> tuple[bool, float]:
    """Send heartbeat with backoff retry. Returns (success, poll_interval)."""
    global _OFFLINE_MODE
    url  = f"{backend_url.rstrip('/')}/ingest/heartbeat"
    body = {"org_id": org_id, "metrics": metrics}
    for i, delay in enumerate((*_RETRY_DELAYS, None)):
        status, resp = _post(url, body, agent_key)
        if status == 200:
            if _OFFLINE_MODE:
                print("[reconnect] Back online — flushing offline buffer …")
                _OFFLINE_MODE = False
                _flush_buffer(url, agent_key)
            return True, float(resp.get("poll_interval", 5))
        if delay is None:
            break
        if i == 0 and not _OFFLINE_MODE:
            print(f"[warn] Heartbeat failed (status={status}) — retrying with backoff …")
        time.sleep(delay)
    if not _OFFLINE_MODE:
        print("[offline] Entering offline mode — payloads buffered to disk")
        _OFFLINE_MODE = True
    _BUFFER.append(body)
    _save_buffer()
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

    _load_buffer()

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
