#!/usr/bin/env python3
"""
test_prometheus_bridge.py
Smoke-tests the three Prometheus bridge endpoints against a running core_api.

Usage:
    python scripts/test_prometheus_bridge.py [--base-url http://localhost:8000]
"""
from __future__ import annotations

import argparse
import json
import sys
import time

try:
    import requests
except ImportError:
    sys.exit("requests is required: pip install requests")

# ─── Config ───────────────────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://localhost:8000")
parser.add_argument("--token", default="",
                    help="PROMETHEUS_WEBHOOK_TOKEN (empty = dev/unauthenticated)")
parser.add_argument("--admin-password", default="",
                    help="Admin password to authenticate agent-list queries")
ARGS = parser.parse_args()

BASE = ARGS.base_url.rstrip("/")
HEADERS: dict[str, str] = {}
if ARGS.token:
    HEADERS["Authorization"] = f"Bearer {ARGS.token}"

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    mark = PASS if ok else FAIL
    print(f"  {mark}  {name}" + (f" — {detail}" if detail else ""))


# ── Optional admin auth (needed to query agent list) ─────────────────────────

_ACCESS_TOKEN: str = ""
_ORG_ID: str = ""


def _try_login() -> None:
    global _ACCESS_TOKEN, _ORG_ID
    import os, pathlib
    try:
        from dotenv import load_dotenv
        load_dotenv(pathlib.Path(__file__).parent.parent / ".env", override=False)
    except ImportError:
        pass
    password = ARGS.admin_password or os.getenv("ADMIN_DEFAULT_PASSWORD", "")
    if not password:
        return
    try:
        r = requests.post(
            f"{BASE}/auth/login",
            json={"email": "admin@company.local", "password": password},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            _ACCESS_TOKEN = data.get("access_token") or data.get("token", "")
        if not _ACCESS_TOKEN:
            return
        # Get default org id
        r2 = requests.get(
            f"{BASE}/api/orgs",
            headers={"Authorization": f"Bearer {_ACCESS_TOKEN}"},
            timeout=10,
        )
        if r2.status_code == 200:
            orgs = r2.json()
            # Prefer the 'default' org; fall back to first
            default = next((o for o in orgs if o.get("slug") == "default"), None)
            _ORG_ID = (default or orgs[0])["id"] if orgs else ""
    except Exception as e:
        print(f"  (auth skipped: {e})")


def get_agents() -> list[dict]:
    if not (_ACCESS_TOKEN and _ORG_ID):
        return []
    r = requests.get(
        f"{BASE}/api/orgs/{_ORG_ID}/agents",
        headers={"Authorization": f"Bearer {_ACCESS_TOKEN}"},
        timeout=10,
    )
    if r.status_code != 200:
        return []
    return r.json()


_try_login()

# ─── Test 1: Alertmanager webhook ─────────────────────────────────────────────

print("\n── Test 1: POST /ingest/prometheus/alertmanager ──")

ALERTMANAGER_PAYLOAD = {
    "receiver": "aiops-webhook",
    "status": "firing",
    "alerts": [
        {
            "status": "firing",
            "labels": {
                "alertname": "HighCPUUsage",
                "instance": "test-prom-01:9100",
                "job": "node",
                "severity": "critical",
            },
            "annotations": {
                "summary": "CPU usage above 90%",
                "description": "CPU usage on test-prom-01 is 91.3%",
            },
            "generatorURL": "http://prometheus:9090/graph",
        }
    ],
}

r1 = requests.post(
    f"{BASE}/ingest/prometheus/alertmanager",
    json=ALERTMANAGER_PAYLOAD,
    headers=HEADERS,
    timeout=15,
)
check("HTTP 200", r1.status_code == 200, f"got {r1.status_code}")
try:
    body1 = r1.json()
    check("ok=True", body1.get("ok") is True)
    check("agents_notified=1", body1.get("agents_notified") == 1,
          f"got {body1.get('agents_notified')}")
except Exception as e:
    check("response parseable", False, str(e))

# Give background tasks a moment
time.sleep(2)

# Verify agent was auto-provisioned
agents_after_1 = get_agents()
prom_agents = [a for a in agents_after_1 if "test-prom-01" in (a.get("label") or "")]
check("agent auto-provisioned", len(prom_agents) >= 1,
      f"found {len(prom_agents)} agent(s) labelled test-prom-01")

if prom_agents:
    ag1 = prom_agents[0]
    check("source=prometheus", ag1.get("source") == "prometheus",
          f"got {ag1.get('source')!r}")
    check("execution_mode=manual_approval",
          ag1.get("execution_mode") == "manual_approval",
          f"got {ag1.get('execution_mode')!r}")
    check("cpu snapshot stored", ag1.get("cpu") is not None,
          f"cpu={ag1.get('cpu')}")

# ─── Test 2: Prometheus text-format push ──────────────────────────────────────

print("\n── Test 2: POST /ingest/prometheus/metrics ──")

PROM_TEXT = """\
# HELP node_cpu_seconds_total CPU seconds total
# TYPE node_cpu_seconds_total counter
node_cpu_seconds_total{cpu="0",mode="idle"} 12345.6
node_cpu_seconds_total{cpu="0",mode="user"} 1234.5
node_cpu_seconds_total{cpu="0",mode="system"} 432.1
node_memory_MemAvailable_bytes 2147483648
node_memory_MemTotal_bytes 8589934592
node_filesystem_avail_bytes{mountpoint="/",fstype="ext4"} 10737418240
node_filesystem_size_bytes{mountpoint="/",fstype="ext4"} 107374182400
node_network_receive_bytes_total{device="eth0"} 9876543
node_network_transmit_bytes_total{device="eth0"} 3456789
"""

r2 = requests.post(
    f"{BASE}/ingest/prometheus/metrics?instance=test-prom-02",
    data=PROM_TEXT,
    headers={**HEADERS, "Content-Type": "text/plain"},
    timeout=15,
)
check("HTTP 200", r2.status_code == 200, f"got {r2.status_code}")
try:
    body2 = r2.json()
    check("ok=True", body2.get("ok") is True)
    check("agent_id returned", bool(body2.get("agent_id")))
    m = body2.get("metrics", {})
    # cpu ≈ 100 - (12345.6 / (12345.6+1234.5+432.1)) * 100 ≈ 11.8%
    cpu_ok = isinstance(m.get("cpu"), (int, float))
    check("cpu parsed", cpu_ok, f"cpu={m.get('cpu')}")
    # memory = 1 - (2GB / 8GB) = 75%
    mem_ok = isinstance(m.get("memory"), (int, float))
    check("memory parsed", mem_ok, f"memory={m.get('memory')}")
    # disk = 1 - (10GB / 100GB) = 90%
    disk_ok = isinstance(m.get("disk"), (int, float))
    check("disk parsed", disk_ok, f"disk={m.get('disk')}")
except Exception as e:
    check("response parseable", False, str(e))

time.sleep(2)

agents_after_2 = get_agents()
prom2 = [a for a in agents_after_2 if "test-prom-02" in (a.get("label") or "")]
check("agent auto-provisioned", len(prom2) >= 1,
      f"found {len(prom2)} agent(s) labelled test-prom-02")

# ─── Test 3: Grafana webhook ───────────────────────────────────────────────────

print("\n── Test 3: POST /ingest/grafana/alert ──")

GRAFANA_PAYLOAD = {
    "title": "High CPU Usage",
    "state": "alerting",
    "ruleName": "CPU > 90%",
    "message": "CPU usage is 91.3% on test-grafana-01",
    "tags": {
        "instance": "test-grafana-01",
        "severity": "critical",
    },
    "evalMatches": [
        {"metric": "cpu_usage", "value": 91.3, "tags": {"host": "test-grafana-01"}},
        {"metric": "memory_usage", "value": 72.1, "tags": {"host": "test-grafana-01"}},
    ],
}

r3 = requests.post(
    f"{BASE}/ingest/grafana/alert",
    json=GRAFANA_PAYLOAD,
    headers=HEADERS,
    timeout=15,
)
check("HTTP 200", r3.status_code == 200, f"got {r3.status_code}")
try:
    body3 = r3.json()
    check("ok=True", body3.get("ok") is True)
    check("instance echoed", "test-grafana-01" in str(body3.get("instance", "")),
          f"instance={body3.get('instance')!r}")
    check("agents_notified=1", body3.get("agents_notified") == 1)
except Exception as e:
    check("response parseable", False, str(e))

time.sleep(2)

agents_after_3 = get_agents()
graf = [a for a in agents_after_3 if "test-grafana-01" in (a.get("label") or "")]
check("agent auto-provisioned", len(graf) >= 1,
      f"found {len(graf)} agent(s) labelled test-grafana-01")

# ─── Test 4: Resolved / non-firing payloads are ignored ──────────────────────

print("\n── Test 4: Resolved payloads ignored ──")

RESOLVED_AM = {
    "receiver": "aiops-webhook",
    "status": "resolved",
    "alerts": [{"status": "resolved", "labels": {"instance": "test-prom-01:9100"}}],
}
r4a = requests.post(
    f"{BASE}/ingest/prometheus/alertmanager",
    json=RESOLVED_AM,
    headers=HEADERS,
    timeout=10,
)
check("alertmanager resolved → 200", r4a.status_code == 200)
check("agents_notified=0 for resolved",
      r4a.json().get("agents_notified") == 0,
      f"got {r4a.json().get('agents_notified')}")

RESOLVED_GRAFANA = {"state": "ok", "title": "CPU normal", "tags": {}}
r4b = requests.post(
    f"{BASE}/ingest/grafana/alert",
    json=RESOLVED_GRAFANA,
    headers=HEADERS,
    timeout=10,
)
check("grafana resolved → 200", r4b.status_code == 200)
check("agents_notified=0 for grafana ok",
      r4b.json().get("agents_notified") == 0)

# ─── Test 5: Empty Prometheus text body → 400 ─────────────────────────────────

print("\n── Test 5: Empty body → 400 ──")

r5 = requests.post(
    f"{BASE}/ingest/prometheus/metrics?instance=dummy",
    data="",
    headers={**HEADERS, "Content-Type": "text/plain"},
    timeout=10,
)
check("empty body → 400", r5.status_code == 400, f"got {r5.status_code}")

# ─── Summary ──────────────────────────────────────────────────────────────────

print()
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
bar = "█" * passed + "░" * (total - passed)
colour = "\033[92m" if passed == total else "\033[93m"
print(f"{colour}[{bar}] {passed}/{total} checks passed\033[0m")

if passed < total:
    print("\nFailed checks:")
    for name, ok, detail in results:
        if not ok:
            print(f"  ✗  {name}" + (f" — {detail}" if detail else ""))
    sys.exit(1)

print("\nAll checks passed.")
