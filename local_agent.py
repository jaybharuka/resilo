"""
local_agent.py — Tiny local metrics server for Resilo dashboard.

Run this once on the machine you want to monitor:
    pip install psutil
    python local_agent.py

It starts a lightweight HTTP server on http://localhost:9090.
The Resilo dashboard automatically detects it and reads real CPU, memory,
disk, and network metrics from your machine instead of browser estimates.

Press Ctrl+C to stop.
"""

import http.server
import json
import platform
import socket
import time

try:
    import psutil
except ImportError:
    raise SystemExit("psutil is required: pip install psutil")

PORT = 9090
ALLOWED_ORIGIN = "*"   # dashboard fetches from resilo-ai.web.app or localhost

# Snapshot taken once per interval to avoid blocking the HTTP thread
_last_snapshot: dict = {}
_last_ts: float = 0.0
INTERVAL = 5  # seconds between real collections


def _collect() -> dict:
    global _last_snapshot, _last_ts
    now = time.monotonic()
    if now - _last_ts < INTERVAL and _last_snapshot:
        return _last_snapshot

    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()

    # Aggregate disk usage across all partitions
    total_disk = used_disk = 0
    for part in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(part.mountpoint)
            total_disk += u.total
            used_disk  += u.used
        except PermissionError:
            pass
    disk_pct = round(used_disk / total_disk * 100, 1) if total_disk else 0

    net = psutil.net_io_counters()

    try:
        temps = psutil.sensors_temperatures() or {}
        flat  = [t.current for lst in temps.values() for t in lst]
        temp  = round(sum(flat) / len(flat), 1) if flat else None
    except Exception:
        temp = None

    try:
        load = psutil.getloadavg()[0]
    except AttributeError:
        load = None  # Windows doesn't have getloadavg

    boot       = psutil.boot_time()
    uptime_sec = int(time.time() - boot)

    _last_snapshot = {
        "cpu":              round(cpu, 1),
        "memory":           round(mem.percent, 1),
        "disk":             disk_pct,
        "network_in":       round(net.bytes_recv / (1024 * 1024), 2),   # MB
        "network_out":      round(net.bytes_sent / (1024 * 1024), 2),
        "temperature":      temp,
        "processes":        len(psutil.pids()),
        "uptime_secs":      uptime_sec,
        "cpu_cores":        psutil.cpu_count(logical=True),
        "device_memory_gb": round(mem.total / (1024 ** 3), 1),
        "platform":         platform.system() + " " + platform.release(),
        "hostname":         socket.gethostname(),
        "source":           "local-agent",
    }
    _last_ts = now
    return _last_snapshot


class MetricsHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path not in ("/metrics", "/metrics/"):
            self.send_response(404)
            self.end_headers()
            return
        try:
            data = json.dumps(_collect()).encode()
            self.send_response(200)
            self.send_header("Content-Type",   "application/json")
            self.send_header("Content-Length", str(len(data)))
            self._cors()
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(exc).encode())


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), MetricsHandler)
    print(f"Resilo local agent running on http://localhost:{PORT}/metrics")
    print("Open your Resilo dashboard — it will automatically detect this agent.")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
