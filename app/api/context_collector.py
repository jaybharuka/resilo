"""
context_collector.py — Dynamic, incident-type-aware evidence collection.

Dispatches to the right collector based on incident type:

  cpu     → process tree, service ownership, CPU scheduler pressure
  memory  → memory pressure breakdown, OOM history, swap state
  disk    → largest dirs, inode usage, IO wait, mount health
  network → open ports, connection states, recent DNS/TCP errors
  db      → connection count, active queries, pool saturation (Postgres)
  service → systemd/Windows service state, recent restarts

All collectors:
  - Run in parallel via asyncio.gather (no collector blocks another)
  - Timeout individually (default 10s)
  - Never raise — return empty dict on any failure
  - Return plain dicts ready for JSON serialisation

Entry point:
  collect_context(incident_type, agent_id, platform, extra_metrics) -> dict
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform as _platform
import re
import subprocess
from typing import Any

_log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 10.0   # seconds per collector


# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Run a subprocess, return stdout. Returns '' on any failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, errors="replace",
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _run_ps(script: str, timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Run a PowerShell one-liner, return stdout."""
    try:
        result = subprocess.run(
            ["powershell", "-NonInteractive", "-Command", script],
            capture_output=True, text=True,
            timeout=timeout, errors="replace",
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _parse_table(raw: str, sep: str = r"\s{2,}") -> list[dict[str, str]]:
    """Parse whitespace-separated multi-column CLI output into list of dicts."""
    lines = [l for l in raw.splitlines() if l.strip()]
    if len(lines) < 2:
        return []
    headers = re.split(sep, lines[0].strip())
    rows = []
    for line in lines[1:20]:
        parts = re.split(sep, line.strip(), maxsplit=len(headers) - 1)
        if parts:
            rows.append(dict(zip(headers, parts + [""] * len(headers))))
    return rows


_IS_WIN = _platform.system() == "Windows"


# ── CPU Collectors ────────────────────────────────────────────────────────────

async def _cpu_process_tree() -> dict[str, Any]:
    """Top 10 processes with PID, parent, CPU%, MEM%, command."""
    if _IS_WIN:
        raw = _run_ps(
            "Get-Process | Sort-Object CPU -Desc | Select-Object -First 10 "
            "Id,ProcessName,CPU,WorkingSet64,Handles | "
            "Format-Table -AutoSize | Out-String"
        )
        lines = [l for l in raw.splitlines() if l.strip() and not l.startswith("-")]
        return {"process_tree_raw": lines[:12]}
    else:
        raw = _run(["ps", "axo", "pid,ppid,pcpu,pmem,comm", "--sort=-pcpu"])
        rows = _parse_table(raw)[:10]
        return {"top_processes_tree": rows}


async def _cpu_scheduler_pressure() -> dict[str, Any]:
    """PSI (Pressure Stall Information) if available on Linux."""
    result: dict[str, Any] = {}
    if _IS_WIN:
        return result
    for resource in ("cpu", "memory", "io"):
        path = f"/proc/pressure/{resource}"
        if os.path.exists(path):
            try:
                with open(path) as f:
                    result[f"psi_{resource}"] = f.read().strip()
            except OSError:
                pass
    return result


async def _cpu_service_ownership(top_cpu_processes: list[dict]) -> dict[str, Any]:
    """
    For the top CPU-consuming process, attempt to identify owning systemd
    service (Linux) or Windows service (Windows).
    """
    if not top_cpu_processes:
        return {}
    top_name = top_cpu_processes[0].get("name", "")
    if not top_name:
        return {}

    if _IS_WIN:
        raw = _run_ps(
            f"Get-WmiObject Win32_Process | Where-Object {{$_.Name -like '*{top_name[:20]}*'}} | "
            "Select-Object ProcessId,Name,CommandLine | Format-List"
        )
        return {"service_owner_raw": raw[:500]}
    else:
        # systemd: find unit owning the main pid
        raw = _run(["pgrep", "-f", top_name[:30]])
        pid = raw.split()[0] if raw.split() else ""
        if pid:
            unit = _run(["systemctl", "status", pid, "--no-pager", "-l"])
            return {"service_unit": unit[:600]}
        return {}


# ── Memory Collectors ─────────────────────────────────────────────────────────

async def _memory_pressure_breakdown() -> dict[str, Any]:
    """Detailed memory breakdown: cached, buffers, available, anon, mapped."""
    if _IS_WIN:
        raw = _run_ps(
            "Get-WmiObject Win32_OperatingSystem | "
            "Select-Object TotalVisibleMemorySize,FreePhysicalMemory,TotalVirtualMemorySize,FreeVirtualMemory | "
            "Format-List"
        )
        return {"memory_detail_raw": raw[:500]}
    # Linux: parse /proc/meminfo
    result: dict[str, str] = {}
    keys = {"MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached",
            "AnonPages", "Mapped", "SwapTotal", "SwapFree", "CommitLimit", "Committed_AS"}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                if k.strip() in keys:
                    result[k.strip()] = v.strip()
    except OSError:
        pass
    return {"meminfo": result}


async def _oom_history() -> dict[str, Any]:
    """Recent OOM kills from kernel ring buffer or journald."""
    if _IS_WIN:
        return {}
    # Try journald first
    raw = _run(
        ["journalctl", "-k", "--no-pager", "-n", "50",
         "--grep", "Out of memory|oom_kill|Killed process"],
        timeout=8,
    )
    if raw:
        return {"oom_events": raw.splitlines()[:10]}
    # Fallback: dmesg
    raw = _run(["dmesg", "--level=err,crit", "--notime"])
    oom_lines = [l for l in raw.splitlines() if "oom" in l.lower() or "killed" in l.lower()]
    return {"oom_events": oom_lines[:10]}


async def _high_mem_processes() -> dict[str, Any]:
    """Top 10 processes by RSS."""
    if _IS_WIN:
        raw = _run_ps(
            "Get-Process | Sort-Object WorkingSet64 -Desc | "
            "Select-Object -First 10 Id,ProcessName,WorkingSet64 | "
            "Format-Table -AutoSize | Out-String"
        )
        return {"high_mem_processes_raw": raw.splitlines()[:12]}
    raw = _run(["ps", "axo", "pid,comm,rss,pmem", "--sort=-rss"])
    return {"high_mem_processes": _parse_table(raw)[:10]}


# ── Disk Collectors ───────────────────────────────────────────────────────────

async def _disk_largest_dirs() -> dict[str, Any]:
    """Top 10 largest directories under common paths."""
    if _IS_WIN:
        raw = _run_ps(
            "Get-ChildItem C:\\ -ErrorAction SilentlyContinue | "
            "Select-Object Name,@{N='SizeMB';E={(Get-ChildItem $_.FullName -Recurse -ErrorAction SilentlyContinue | "
            "Measure-Object -Property Length -Sum).Sum / 1MB}} | "
            "Sort-Object SizeMB -Desc | Select-Object -First 10 | Format-Table",
            timeout=15,
        )
        return {"largest_dirs_raw": raw.splitlines()[:12]}
    # Linux: du on common large paths
    raw = _run(["du", "-sh", "--max-depth=1", "/var", "/home", "/opt", "/tmp", "/usr"], timeout=8)
    return {"dir_sizes": raw.splitlines()[:15]}


async def _disk_inode_usage() -> dict[str, Any]:
    """Inode usage per filesystem (Linux only)."""
    if _IS_WIN:
        return {}
    raw = _run(["df", "-i"])
    return {"inode_usage": raw.splitlines()[:10]}


async def _disk_io_wait() -> dict[str, Any]:
    """IO wait %, read/write throughput from iostat or /proc/diskstats."""
    if _IS_WIN:
        raw = _run_ps(
            "Get-Counter '\\PhysicalDisk(_Total)\\% Disk Time' | "
            "Select-Object -ExpandProperty CounterSamples | "
            "Select-Object CookedValue | Format-List",
            timeout=8,
        )
        return {"disk_time_raw": raw[:300]}
    raw = _run(["iostat", "-x", "1", "1"], timeout=8)
    return {"iostat": raw.splitlines()[:20]}


# ── Network Collectors ────────────────────────────────────────────────────────

async def _net_open_ports() -> dict[str, Any]:
    """Listening ports with owning process."""
    if _IS_WIN:
        raw = _run_ps(
            "netstat -ano | Select-String LISTENING | "
            "Select-Object -First 20 | Out-String"
        )
        return {"listening_ports": raw.splitlines()[:22]}
    raw = _run(["ss", "-tlnp"])
    return {"listening_ports": raw.splitlines()[:20]}


async def _net_connection_summary() -> dict[str, Any]:
    """Count of connections by state."""
    if _IS_WIN:
        raw = _run_ps("netstat -an | Group-Object { $_.Split(' ')[5] } | "
                      "Select-Object Name,Count | Format-Table | Out-String")
        return {"conn_states_raw": raw[:400]}
    raw = _run(["ss", "-s"])
    return {"connection_summary": raw[:400]}


async def _net_dns_errors() -> dict[str, Any]:
    """Recent DNS/TCP errors from syslog/journald."""
    if _IS_WIN:
        return {}
    raw = _run(
        ["journalctl", "--no-pager", "-n", "30",
         "--grep", "NXDOMAIN|SERVFAIL|connection timed out|Connection refused"],
        timeout=8,
    )
    return {"dns_tcp_errors": raw.splitlines()[:10]}


# ── Database Collectors (Postgres-oriented) ───────────────────────────────────

async def _db_pg_connection_count() -> dict[str, Any]:
    """
    Query pg_stat_activity if psql is available.
    Uses PGHOST/PGPORT/PGUSER/PGDATABASE from env — same credentials the
    backend uses.
    """
    pg_env = {
        "PGHOST":     os.getenv("POSTGRES_HOST", "localhost"),
        "PGPORT":     os.getenv("POSTGRES_PORT", "5432"),
        "PGUSER":     os.getenv("POSTGRES_USER", "postgres"),
        "PGPASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "PGDATABASE": os.getenv("POSTGRES_DB", "postgres"),
    }
    try:
        result = subprocess.run(
            ["psql", "-c",
             "SELECT state, count(*) FROM pg_stat_activity GROUP BY state ORDER BY count DESC LIMIT 10;",
             "--no-psqlrc", "-t"],
            capture_output=True, text=True, timeout=8,
            env={**os.environ, **pg_env},
        )
        return {"pg_activity": result.stdout.strip().splitlines()[:12]}
    except Exception:
        return {}


async def _db_pg_long_queries() -> dict[str, Any]:
    """Queries running longer than 5 seconds."""
    pg_env = {
        "PGHOST":     os.getenv("POSTGRES_HOST", "localhost"),
        "PGPORT":     os.getenv("POSTGRES_PORT", "5432"),
        "PGUSER":     os.getenv("POSTGRES_USER", "postgres"),
        "PGPASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "PGDATABASE": os.getenv("POSTGRES_DB", "postgres"),
    }
    try:
        result = subprocess.run(
            ["psql", "-c",
             "SELECT pid, now() - pg_stat_activity.query_start AS duration, query "
             "FROM pg_stat_activity WHERE query != '<IDLE>' "
             "AND query NOT ILIKE '%pg_stat_activity%' "
             "AND (now() - pg_stat_activity.query_start) > interval '5 seconds' "
             "ORDER BY duration DESC LIMIT 5;",
             "--no-psqlrc", "-t"],
            capture_output=True, text=True, timeout=8,
            env={**os.environ, **pg_env},
        )
        return {"pg_long_queries": result.stdout.strip().splitlines()[:8]}
    except Exception:
        return {}


# ── Service Collectors ────────────────────────────────────────────────────────

async def _service_state_summary() -> dict[str, Any]:
    """
    List recently failed or restarted services.
    Linux: systemctl --failed
    Windows: services in Stopped state that should be running
    """
    if _IS_WIN:
        raw = _run_ps(
            "Get-Service | Where-Object {$_.Status -eq 'Stopped' -and $_.StartType -eq 'Automatic'} | "
            "Select-Object Name,DisplayName,Status | Format-Table | Out-String"
        )
        return {"stopped_auto_services": raw.splitlines()[:15]}
    raw = _run(["systemctl", "--failed", "--no-pager", "--no-legend"])
    return {"failed_units": raw.splitlines()[:15]}


async def _service_recent_restarts() -> dict[str, Any]:
    """Services that restarted in the last 30 minutes (Linux only)."""
    if _IS_WIN:
        return {}
    raw = _run(
        ["journalctl", "--no-pager", "-n", "100",
         "--grep", "Started|Stopped|Failed|restarting",
         "--since", "30 min ago"],
        timeout=8,
    )
    return {"recent_service_events": raw.splitlines()[:15]}


# ── Dispatcher ────────────────────────────────────────────────────────────────

async def _run_with_timeout(coro, name: str, timeout: float = _DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Run a collector coroutine with timeout. Returns {} on any failure."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout) or {}
    except asyncio.TimeoutError:
        _log.debug("[context_collector] %s timed out", name)
        return {}
    except Exception as exc:
        _log.debug("[context_collector] %s failed: %s", name, exc)
        return {}


async def collect_context(
    incident_type: str,
    top_cpu_processes: list[dict] | None = None,
    top_mem_processes: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Dispatch collectors by incident type.
    All collectors run in parallel; stragglers are abandoned at timeout.
    Returns a flat dict of all gathered evidence, ready for JSON storage.

    Args:
        incident_type: one of cpu|memory|disk|network|db|service
        top_cpu_processes: top CPU procs already collected by the metrics agent
        top_mem_processes: top mem procs already collected by the metrics agent
    """
    top_cpu = top_cpu_processes or []
    collectors: dict[str, Any] = {}

    itype = incident_type.lower()

    # CPU incident
    if itype == "cpu":
        collectors = {
            "process_tree":        _cpu_process_tree(),
            "scheduler_pressure":  _cpu_scheduler_pressure(),
            "service_ownership":   _cpu_service_ownership(top_cpu),
        }

    # Memory incident
    elif itype == "memory":
        collectors = {
            "memory_breakdown": _memory_pressure_breakdown(),
            "oom_history":      _oom_history(),
            "high_mem_procs":   _high_mem_processes(),
        }

    # Disk incident
    elif itype == "disk":
        collectors = {
            "largest_dirs": _disk_largest_dirs(),
            "inode_usage":  _disk_inode_usage(),
            "io_wait":      _disk_io_wait(),
        }

    # Network incident
    elif itype == "network":
        collectors = {
            "open_ports":         _net_open_ports(),
            "connection_summary": _net_connection_summary(),
            "dns_tcp_errors":     _net_dns_errors(),
        }

    # Database incident
    elif itype == "db":
        collectors = {
            "pg_connections": _db_pg_connection_count(),
            "pg_long_queries": _db_pg_long_queries(),
        }

    # Service incident (or catch-all)
    else:
        collectors = {
            "service_state":    _service_state_summary(),
            "recent_restarts":  _service_recent_restarts(),
        }

    if not collectors:
        return {}

    # Run all collectors in parallel
    keys   = list(collectors.keys())
    coros  = list(collectors.values())
    tasks  = [_run_with_timeout(c, k) for k, c in zip(keys, coros)]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    merged: dict[str, Any] = {}
    for key, res in zip(keys, results):
        if res:
            merged[key] = res

    return merged


def format_context_evidence(ctx: dict[str, Any]) -> str:
    """
    Format collected context evidence into a compact plain-text block
    suitable for LLM prompt injection.
    """
    if not ctx:
        return ""
    lines = ["DYNAMIC EVIDENCE:"]
    for section, data in ctx.items():
        lines.append(f"\n[{section.upper().replace('_', ' ')}]")
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, list):
                    lines.append(f"  {k}:")
                    for item in v[:8]:
                        lines.append(f"    {item}")
                else:
                    lines.append(f"  {k}: {str(v)[:200]}")
        elif isinstance(data, list):
            for item in data[:8]:
                lines.append(f"  {item}")
        else:
            lines.append(f"  {str(data)[:300]}")
    return "\n".join(lines)
