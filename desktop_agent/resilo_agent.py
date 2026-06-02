"""
Resilo Agent — single-file edition.
Install: pip install psutil
Run:     RESILO_ONBOARD_TOKEN=<token> RESILO_BACKEND_URL=https://... python resilo_agent.py
Persist: python resilo_agent.py --install      # install as startup service
Remove:  python resilo_agent.py --uninstall    # remove startup service
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import os
import platform
import re
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


def _collect_open_ports() -> list[str]:
    """Return a list of listening ports (e.g. ['0.0.0.0:5432', ':::80'])."""
    try:
        conns = psutil.net_connections(kind="inet")
        ports = []
        for c in conns:
            if c.status == "LISTEN" and c.laddr:
                ports.append(f"{c.laddr.ip}:{c.laddr.port}")
        return sorted(set(ports))[:30]
    except Exception:
        return []


def _collect_failed_services() -> list[str]:
    """
    Return names of services in a bad state.
    Linux: systemctl --failed
    Windows: auto-start services that are stopped
    """
    try:
        if platform.system() == "Windows":
            result = subprocess.run(
                ["powershell", "-NonInteractive", "-Command",
                 "Get-Service | Where-Object {$_.Status -eq 'Stopped' -and "
                 "$_.StartType -eq 'Automatic'} | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, timeout=8,
            )
            return [l.strip() for l in result.stdout.splitlines() if l.strip()][:10]
        else:
            result = subprocess.run(
                ["systemctl", "--failed", "--no-pager", "--no-legend",
                 "--output=json"],
                capture_output=True, text=True, timeout=8,
            )
            if result.stdout.strip():
                try:
                    units = json.loads(result.stdout)
                    return [u.get("unit", "") for u in units if u.get("unit")][:10]
                except Exception:
                    pass
            # fallback: parse plain text
            lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
            return lines[:10]
    except Exception:
        return []


def _collect_disk_inodes() -> list[dict[str, Any]]:
    """Per-partition inode usage (Linux/macOS only)."""
    if platform.system() == "Windows":
        return []
    try:
        result = subprocess.run(
            ["df", "-i", "--output=source,ipcent,itotal,iused,iavail"],
            capture_output=True, text=True, timeout=5,
        )
        rows = []
        for line in result.stdout.splitlines()[1:6]:
            parts = line.split()
            if len(parts) >= 5:
                rows.append({
                    "device":       parts[0],
                    "inode_pct":    parts[1],
                    "inode_total":  parts[2],
                    "inode_used":   parts[3],
                    "inode_avail":  parts[4],
                })
        return rows
    except Exception:
        return []


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

    # \u2500\u2500 Phase 4: lightweight dynamic evidence shipped with every heartbeat \u2500\u2500\u2500\u2500\u2500\u2500\u2500
    payload["open_ports"]     = _collect_open_ports()
    payload["failed_services"] = _collect_failed_services()
    payload["disk_inodes"]    = _collect_disk_inodes()

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


def send(backend_url: str, org_id: str, agent_key: str, metrics: dict[str, Any]) -> tuple[bool, float, list]:
    """Send heartbeat with backoff retry. Returns (success, poll_interval, commands)."""
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
            return True, float(resp.get("poll_interval", 5)), resp.get("commands", [])
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
    return False, 5.0, []


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
    """Execute a command received from backend using sandboxed executor."""
    from executor import execute_command
    
    action = cmd.get("action", "")
    target = cmd.get("target", "")
    timeout = cmd.get("timeout", 30)
    dry_run = cmd.get("dry_run", False)
    
    print(f"[cmd] Executing: {action} → {target} (timeout={timeout}s, dry_run={dry_run})")
    
    result = execute_command(action, target, timeout, dry_run)
    
    if result.get("success"):
        print(f"[cmd] ✓ {action} completed in {result.get('duration_seconds', 0):.2f}s")
        if result.get("stdout"):
            print(f"[cmd] stdout: {result['stdout']}")
    else:
        print(f"[cmd] ✗ {action} failed (exit_code={result.get('exit_code')})")
        if result.get("stderr"):
            print(f"[cmd] stderr: {result['stderr']}")


# ── Log Shipper ──────────────────────────────────────────────────────────────

# Patterns that always pass the local filter regardless of level
_LOG_KEEP_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in [
        r"out.of.memory|oom.killer|killed.process",
        r"connection.(?:refused|reset|timeout|pool|exhaust)",
        r"too.many.(?:open.files|connections|clients)",
        r"disk.(?:full|quota)|no.space.left",
        r"segfault|segmentation.fault",
        r"exception|traceback|panic",
        r"timeout.*\d+\s*(?:ms|s)",
        r"circuit.breaker|retry.*\d+.of",
        r"health.check.fail",
        r"swap.(?:full|exhausted)",
    ]
]

# Levels that pass by default (case-insensitive)
_KEEP_LEVELS = {"error", "err", "warn", "warning", "critical", "crit", "fatal", "alert", "emerg"}

# Max messages to track for deduplication per ship cycle
_DEDUP_WINDOW = 500
# Max batch size per POST
_LOG_BATCH_SIZE = 200
# Ship interval seconds
_LOG_SHIP_INTERVAL = 30


class _DedupTracker:
    """Count-based deduplication within a sliding window."""
    def __init__(self, maxsize: int = _DEDUP_WINDOW) -> None:
        self._counts: dict[str, int] = {}
        self._maxsize = maxsize

    def _key(self, message: str) -> str:
        # Normalise numbers so "error 123" == "error 456"
        normalised = re.sub(r"\d+", "#", message.lower())[:120]
        return hashlib.md5(normalised.encode(), usedforsecurity=False).hexdigest()[:16]

    def seen(self, message: str) -> int:
        """Record message; return total count (1 = first occurrence)."""
        k = self._key(message)
        self._counts[k] = self._counts.get(k, 0) + 1
        if len(self._counts) > self._maxsize:
            # Evict oldest half
            keys = list(self._counts)[:self._maxsize // 2]
            for old in keys:
                del self._counts[old]
        return self._counts[k]

    def reset(self) -> None:
        self._counts.clear()


def _should_keep(level: str, message: str) -> bool:
    """True if this log line should be shipped."""
    if level.lower() in _KEEP_LEVELS:
        return True
    return any(p.search(message) for p in _LOG_KEEP_PATTERNS)


def _normalise_line(raw: str, source: str) -> dict[str, Any] | None:
    """
    Parse a raw log line into {level, source, message, raw_line, log_ts}.
    Returns None if the line should be dropped.
    """
    raw = raw.strip()
    if not raw or len(raw) < 4:
        return None

    level = "INFO"
    message = raw
    log_ts: str | None = None

    # Syslog / journald pattern: "Jan  2 15:04:05 host service[pid]: message"
    m = re.match(
        r'^(?P<ts>\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+\S+\s+\S+:\s+(?P<msg>.+)$',
        raw
    )
    if m:
        message = m.group("msg")
        log_ts = m.group("ts")

    # ISO timestamp prefix: "2024-01-02T15:04:05 LEVEL message"
    m2 = re.match(
        r'^(?P<ts>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*)\s+'
        r'(?P<lvl>ERROR|WARN(?:ING)?|INFO|DEBUG|CRITICAL|FATAL)\s+(?P<msg>.+)$',
        raw, re.IGNORECASE
    )
    if m2:
        log_ts  = m2.group("ts")
        level   = m2.group("lvl").upper()
        message = m2.group("msg")

    # Bare level prefix: "ERROR: message" or "[ERROR] message"
    m3 = re.match(
        r'^\[?(?P<lvl>ERROR|WARN(?:ING)?|INFO|DEBUG|CRITICAL|FATAL)\]?[:\s]+(?P<msg>.+)$',
        raw, re.IGNORECASE
    )
    if m3:
        level   = m3.group("lvl").upper()
        message = m3.group("msg")

    # Truncate giant lines
    message = message[:1000]

    if not _should_keep(level, message):
        return None

    return {
        "level":    level,
        "source":   source,
        "message":  message,
        "raw_line": raw[:500],
        "log_ts":   log_ts,
    }


# ── Platform-specific collectors ──────────────────────────────────────────────

def _collect_journald(lines: int = 300) -> list[dict[str, Any]]:
    """Read recent journald entries (Linux only)."""
    try:
        result = subprocess.run(
            ["journalctl", "-n", str(lines), "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, timeout=10
        )
        collected = []
        for raw in result.stdout.splitlines():
            entry = _normalise_line(raw, "journald")
            if entry:
                collected.append(entry)
        return collected
    except Exception:
        return []


def _collect_syslog(lines: int = 200) -> list[dict[str, Any]]:
    """Read tail of /var/log/syslog or /var/log/messages (Linux/macOS)."""
    for path in ("/var/log/syslog", "/var/log/messages", "/var/log/system.log"):
        if os.path.exists(path):
            try:
                result = subprocess.run(
                    ["tail", "-n", str(lines), path],
                    capture_output=True, text=True, timeout=10
                )
                collected = []
                for raw in result.stdout.splitlines():
                    entry = _normalise_line(raw, "syslog")
                    if entry:
                        collected.append(entry)
                return collected
            except Exception:
                return []
    return []


def _collect_windows_eventlog(max_events: int = 200) -> list[dict[str, Any]]:
    """
    Read Windows Application + System event logs using PowerShell.
    Only fetches Warning/Error/Critical events — avoids Information flood.
    """
    ps_script = (
        "$logs = @('Application','System'); "
        "$events = @(); "
        "foreach ($log in $logs) { "
        "  try { $events += Get-EventLog -LogName $log -EntryType Error,Warning "
        f"    -Newest {max_events // 2} -ErrorAction SilentlyContinue "
        "  } catch {} "
        "}; "
        "$events | Select-Object -First {max_events} TimeGenerated,EntryType,Source,Message | "
        "ConvertTo-Json -Depth 2 -Compress"
    ).replace("{max_events}", str(max_events))
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-Command", ps_script],
            capture_output=True, text=True, timeout=20
        )
        data = json.loads(result.stdout) if result.stdout.strip() else []
        if isinstance(data, dict):   # single event returned as object not array
            data = [data]
        collected = []
        for ev in data:
            if not isinstance(ev, dict):
                continue
            level_raw = str(ev.get("EntryType", "INFO")).lower()
            level = "ERROR" if "error" in level_raw else "WARN" if "warn" in level_raw else "INFO"
            msg   = str(ev.get("Message") or "").replace("\r\n", " ").replace("\n", " ").strip()[:500]
            ts    = str(ev.get("TimeGenerated") or "")
            if not msg:
                continue
            entry = _normalise_line(f"{level}: {msg}", f"windows/{ev.get('Source','system')}")
            if entry:
                entry["log_ts"] = ts or None
                collected.append(entry)
        return collected
    except Exception:
        return []


def _collect_agent_log() -> list[dict[str, Any]]:
    """Tail the agent's own log file if it exists."""
    log_path = os.path.join(os.path.expanduser("~"), ".resilo_agent.log")
    if not os.path.exists(log_path):
        return []
    try:
        result = subprocess.run(
            ["tail", "-n", "50", log_path] if platform.system() != "Windows"
            else ["powershell", "-Command", f"Get-Content '{log_path}' -Tail 50"],
            capture_output=True, text=True, timeout=5
        )
        collected = []
        for raw in result.stdout.splitlines():
            entry = _normalise_line(raw, "resilo-agent")
            if entry:
                collected.append(entry)
        return collected
    except Exception:
        return []


class LogShipper:
    """
    Collects, filters, deduplicates, and ships log lines to the backend.

    Call tick() from the main loop — it ships every _LOG_SHIP_INTERVAL seconds.
    Designed to never raise: all errors are printed and swallowed.
    """

    def __init__(
        self,
        backend_url: str,
        agent_id: str,
        agent_key: str,
        org_id: str,
    ) -> None:
        self._url       = f"{backend_url.rstrip('/')}/agents/{agent_id}/logs"
        self._agent_key = agent_key
        self._org_id    = org_id
        self._dedup     = _DedupTracker()
        self._last_ship = 0.0
        self._pending:  list[dict[str, Any]] = []
        self._is_win    = platform.system() == "Windows"
        self._is_linux  = platform.system() == "Linux"

    def _collect(self) -> list[dict[str, Any]]:
        """Collect logs from all available sources."""
        lines: list[dict[str, Any]] = []
        try:
            if self._is_win:
                lines += _collect_windows_eventlog(200)
            else:
                lines += _collect_journald(300)
                lines += _collect_syslog(200)
            lines += _collect_agent_log()
        except Exception as exc:
            print(f"[logs] Collection error: {exc}")
        return lines

    def _dedup_filter(self, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Deduplicate: keep first occurrence per cycle.
        Annotate repeated lines with count in message.
        """
        result = []
        for entry in lines:
            count = self._dedup.seen(entry["message"])
            if count == 1:
                result.append(entry)
            elif count == 5 or count == 20 or count == 50:
                # Surface periodic reminders for high-frequency errors
                entry = dict(entry)
                entry["message"] = f"[x{count}] {entry['message']}"
                result.append(entry)
        return result

    def _ship(self, lines: list[dict[str, Any]], alert_id: str | None = None) -> None:
        """POST a batch of log lines. Silently drops on failure — metric send is primary."""
        if not lines:
            return
        body = json.dumps({"lines": lines[:_LOG_BATCH_SIZE], "alert_id": alert_id}).encode()
        req = urllib.request.Request(
            self._url, method="POST", data=body,
            headers={
                "Content-Type":  "application/json",
                "X-Agent-Key":   self._agent_key,
                "Authorization": f"Bearer {self._agent_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                stored = json.loads(resp.read().decode()).get("stored", 0)
                print(f"[logs] Shipped {stored} line(s)")
        except Exception as exc:
            print(f"[logs] Ship failed (non-fatal): {exc}")

    def tick(self, alert_id: str | None = None) -> None:
        """Call from main loop. Ships once per _LOG_SHIP_INTERVAL seconds."""
        now = time.time()
        if now - self._last_ship < _LOG_SHIP_INTERVAL:
            return
        self._last_ship = now
        self._dedup.reset()    # fresh dedup window each cycle

        raw = self._collect()
        filtered = self._dedup_filter(raw)

        if not filtered:
            return

        # Ship in batches
        for i in range(0, len(filtered), _LOG_BATCH_SIZE):
            self._ship(filtered[i:i + _LOG_BATCH_SIZE], alert_id)


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
            "agent_id":    result.get("agent_id", result.get("device_id", "")),
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

    # ── Log shipper — instantiated once, ticks every 30s independently ────────
    log_shipper = LogShipper(
        backend_url=cfg["backend_url"],
        agent_id=cfg.get("agent_id", cfg.get("device_id", "")),
        agent_key=cfg["agent_key"],
        org_id=cfg["org_id"],
    )

    interval = 5.0
    print(f"[info] Agent running — backend={cfg['backend_url']} interval={interval}s")
    print(f"[info] Log shipping enabled — every {_LOG_SHIP_INTERVAL}s")

    while True:
        try:
            metrics = collect(cfg["device_id"], cfg.get("label", "agent"))
            ok, srv_interval, commands = send(cfg["backend_url"], cfg["org_id"], cfg["agent_key"], metrics)
            if ok:
                print(f"[heartbeat] cpu={metrics['cpu']}% mem={metrics['memory']}% disk={metrics['disk']}%")
                if srv_interval != interval:
                    print(f"[poll] interval={srv_interval}s")
                interval = srv_interval
            else:
                print("[warn] Heartbeat failed — buffered for retry")

            # Ship logs every _LOG_SHIP_INTERVAL seconds (non-blocking, never raises)
            log_shipper.tick()

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
