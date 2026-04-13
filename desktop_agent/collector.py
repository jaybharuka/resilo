from __future__ import annotations

import platform
import socket
import time
from typing import Any

import psutil


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
