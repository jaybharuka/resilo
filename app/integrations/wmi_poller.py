"""
wmi_poller.py — Agentless Windows machine monitoring via WinRM/WMI
──────────────────────────────────────────────────────────────────
The server polls remote Windows machines over WinRM (HTTP port 5985) using
PowerShell+WMI queries. No software needs to be installed on the target machine
beyond enabling WinRM (one-time, 30-second setup by the end user).

User one-time setup (admin sends this command to the user):
    Enable-PSRemoting -Force -SkipNetworkProfileCheck

Requirements (auto-installed if missing):
    pywinrm

Protocol:
    WinRM HTTP  port 5985  (default, plaintext on LAN)
    WinRM HTTPS port 5986  (set port=5986 and use SSL certs for internet)
"""

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("wmi_poller")

# ── Auto-install pywinrm ───────────────────────────────────────────────────────
try:
    import winrm  # type: ignore
except ImportError:
    import subprocess, sys
    log.info("Installing pywinrm…")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pywinrm", "-q"])
    import winrm  # type: ignore

# ── Password encryption (Fernet keyed from JWT_SECRET_KEY) ───────────────────
def _fernet():
    from cryptography.fernet import Fernet
    import hashlib
    raw = os.environ.get("JWT_SECRET_KEY")
    if not raw:
        raise RuntimeError("JWT_SECRET_KEY is not set. Cannot initialize password encryption.")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    return Fernet(key)


def encrypt_password(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_password(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


# ── PowerShell metrics collector ──────────────────────────────────────────────
_PS_METRICS = r"""
try {
  $cpu = [math]::Round((Get-WmiObject Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average, 1)
  $os  = Get-WmiObject Win32_OperatingSystem
  $memTotal = $os.TotalVisibleMemorySize * 1024
  $memFree  = $os.FreePhysicalMemory * 1024
  $memPct   = [math]::Round((($memTotal - $memFree) / $memTotal) * 100, 1)
  $disk = Get-WmiObject Win32_LogicalDisk -Filter "DeviceID='C:'" -ErrorAction SilentlyContinue
  if ($disk -and $disk.Size -gt 0) {
    $diskPct = [math]::Round((($disk.Size - $disk.FreeSpace) / $disk.Size) * 100, 1)
  } else { $diskPct = 0.0 }
  $net = Get-WmiObject Win32_PerfRawData_Tcpip_NetworkInterface -ErrorAction SilentlyContinue | Select-Object -First 1
  $netIn  = if ($net) { [long]$net.BytesReceivedPerSec } else { 0 }
  $netOut = if ($net) { [long]$net.BytesSentPerSec } else { 0 }
  $procs  = (Get-Process -ErrorAction SilentlyContinue).Count
  $uptime = [math]::Round(((Get-Date) - $os.ConvertToDateTime($os.LastBootUpTime)).TotalSeconds)
  [PSCustomObject]@{
    ok=1; cpu=$cpu; memory=$memPct; memory_used=($memTotal-$memFree)
    memory_total=$memTotal; disk=$diskPct; network_in=$netIn; network_out=$netOut
    processes=$procs; uptime_secs=$uptime
  } | ConvertTo-Json -Compress
} catch { Write-Output "{`"ok`":0,`"error`":""$($_.Exception.Message)""}" }
""".strip()

_PS_INFO = r"""
try {
  $cs  = Get-WmiObject Win32_ComputerSystem
  $cpu = Get-WmiObject Win32_Processor | Select-Object -First 1
  [PSCustomObject]@{
    hostname=$env:COMPUTERNAME; os="Windows"
    platform=(Get-WmiObject Win32_OperatingSystem).Caption
    cpu_cores=[int]$cs.NumberOfLogicalProcessors
    cpu_model=$cpu.Name.Trim()
  } | ConvertTo-Json -Compress
} catch { Write-Output "{`"hostname`":""unknown"",`"os`":""Windows""}" }
""".strip()


# ── WMI Poller ────────────────────────────────────────────────────────────────

class WMIPoller:
    """
    Polls a registry of Windows machines via WinRM and stores results
    as MetricSnapshot rows using the provided async DB session factory.
    """

    def __init__(self):
        # target_id → {id, org_id, label, host, port, username, password(plain)}
        self._targets: dict = {}
        self._running = False

    # ── Target registry ───────────────────────────────────────────────────────

    def load_target(self, target_id: str, org_id: str, label: str,
                    host: str, username: str, password_plain: str,
                    agent_id: str, port: int = 5985):
        """Register a target for background polling."""
        self._targets[target_id] = {
            "id": target_id,
            "org_id": org_id,
            "agent_id": agent_id,
            "label": label,
            "host": host,
            "port": port,
            "username": username,
            "password": password_plain,
        }

    def unload_target(self, target_id: str):
        self._targets.pop(target_id, None)

    # ── Connection test (synchronous, called from thread pool) ────────────────

    def test_connection_sync(self, host: str, username: str,
                             password: str, port: int = 5985) -> tuple[bool, str]:
        """
        Try a trivial WinRM command. Returns (success, message).
        Called via asyncio.run_in_executor to avoid blocking the event loop.
        """
        try:
            session = winrm.Session(
                f"http://{host}:{port}/wsman",
                auth=(username, password),
                transport="ntlm",
                read_timeout_sec=15,
                operation_timeout_sec=12,
            )
            result = session.run_ps('Write-Output "aiops-ok"')
            if result.status_code == 0:
                out = result.std_out.decode(errors="replace").strip()
                if "aiops-ok" in out:
                    return True, "Connection successful"
            err = result.std_err.decode(errors="replace").strip()[:300]
            return False, err or f"Exit code {result.status_code}"
        except Exception as exc:
            return False, str(exc)[:300]

    def get_info_sync(self, host: str, username: str,
                      password: str, port: int = 5985) -> Optional[dict]:
        """Collect static machine info. Returns dict or None."""
        try:
            session = winrm.Session(
                f"http://{host}:{port}/wsman",
                auth=(username, password),
                transport="ntlm",
                read_timeout_sec=20,
                operation_timeout_sec=18,
            )
            result = session.run_ps(_PS_INFO)
            if result.status_code == 0:
                return json.loads(result.std_out.decode(errors="replace"))
        except Exception:
            pass
        return None

    # ── Poll one target (synchronous, runs in thread pool) ────────────────────

    def _poll_sync(self, target: dict) -> Optional[dict]:
        try:
            session = winrm.Session(
                f"http://{target['host']}:{target['port']}/wsman",
                auth=(target["username"], target["password"]),
                transport="ntlm",
                read_timeout_sec=20,
                operation_timeout_sec=18,
            )
            result = session.run_ps(_PS_METRICS)
            if result.status_code != 0:
                err = result.std_err.decode(errors="replace")[:200]
                log.warning("WMI poll failed for %s: %s", target["label"], err)
                return None
            data = json.loads(result.std_out.decode(errors="replace"))
            if not data.get("ok"):
                log.warning("WMI script error for %s: %s",
                            target["label"], data.get("error", "unknown"))
                return None
            return {
                "cpu":          float(data.get("cpu", 0)),
                "memory":       float(data.get("memory", 0)),
                "memory_used":  int(data.get("memory_used", 0)),
                "memory_total": int(data.get("memory_total", 0)),
                "disk":         float(data.get("disk", 0)),
                "network_in":   int(data.get("network_in", 0)),
                "network_out":  int(data.get("network_out", 0)),
                "processes":    int(data.get("processes", 0)),
                "uptime_secs":  int(data.get("uptime_secs", 0)),
            }
        except Exception as exc:
            log.error("WMI poll exception for %s: %s", target["label"], exc)
            return None

    # ── Background polling loop ───────────────────────────────────────────────

    async def run(self, session_factory, interval: int = 30):
        """
        Polls all registered targets every `interval` seconds.
        Stores results as MetricSnapshot rows and updates WMITarget status.
        `session_factory` is an async SQLAlchemy sessionmaker (SessionLocal).
        """
        self._running = True
        log.info("WMI poller started (interval=%ds)", interval)
        await asyncio.sleep(10)   # let DB settle on startup

        while self._running:
            loop = asyncio.get_event_loop()
            for target in list(self._targets.values()):
                asyncio.create_task(
                    self._poll_and_store(target, session_factory, loop)
                )
            await asyncio.sleep(interval)

    async def _poll_and_store(self, target: dict, session_factory, loop):
        """Poll one target and persist results — runs poll in thread pool."""
        from sqlalchemy import select
        from database import MetricSnapshot, Agent, WMITarget

        metrics = await loop.run_in_executor(None, self._poll_sync, target)
        now = datetime.now(timezone.utc)

        async with session_factory() as db:
            # Update WMITarget status
            wt_result = await db.execute(
                select(WMITarget).where(WMITarget.id == target["id"])
            )
            wt = wt_result.scalar_one_or_none()
            if wt:
                wt.last_polled = now
                wt.last_status = "ok" if metrics else "error"
                wt.last_error  = None if metrics else "Poll failed — see server logs"

            if metrics and target.get("agent_id"):
                # Keep agent status live
                ag_result = await db.execute(
                    select(Agent).where(Agent.id == target["agent_id"])
                )
                agent = ag_result.scalar_one_or_none()
                if agent:
                    agent.status    = "live"
                    agent.last_seen = now

                snap = MetricSnapshot(
                    org_id=target["org_id"],
                    agent_id=target["agent_id"],
                    timestamp=now,
                    cpu=metrics["cpu"],
                    memory=metrics["memory"],
                    disk=metrics["disk"],
                    network_in=metrics["network_in"],
                    network_out=metrics["network_out"],
                    processes=metrics["processes"],
                    uptime_secs=metrics["uptime_secs"],
                    extra={
                        "source": "wmi",
                        "host": target["host"],
                        "label": target["label"],
                        "memory_used": metrics["memory_used"],
                        "memory_total": metrics["memory_total"],
                    },
                )
                db.add(snap)

            await db.commit()

    def stop(self):
        self._running = False


# Shared singleton used by core_api.py
wmi_poller = WMIPoller()
