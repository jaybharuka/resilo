"""Quick smoke test for the cross-server correlation engine."""
from __future__ import annotations
import os, pathlib, time, sys
import requests

BASE = "http://localhost:8000"

try:
    from dotenv import load_dotenv
    load_dotenv(pathlib.Path(__file__).parent.parent / ".env", override=False)
except ImportError:
    pass

pw = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
if not pw:
    sys.exit("Set ADMIN_DEFAULT_PASSWORD in .env")

tok = requests.post(
    f"{BASE}/auth/login",
    json={"email": "admin@company.local", "password": pw},
    timeout=5,
).json().get("token", "")

hdr = {"Authorization": f"Bearer {tok}"}

# Resolve any pre-existing active incident so the test is clean
pre = requests.get(f"{BASE}/api/v1/incidents/active", headers=hdr, timeout=5)
if pre.status_code == 200:
    old_id = pre.json()["id"]
    requests.post(f"{BASE}/api/v1/incidents/{old_id}/resolve", headers=hdr, timeout=5)
    print(f"[setup] Resolved pre-existing incident {old_id}")

# Send spiking alertmanager payload for 3 distinct nodes
def spike(instance: str) -> dict:
    return {
        "alerts": [{
            "status": "firing",
            "labels": {"alertname": "HighCPUUsage", "instance": instance, "severity": "warning"},
            "annotations": {"description": f"CPU usage on {instance} is 92.0%% CPU usage above 90%%"},
        }]
    }

nodes = ["corr-node-01", "corr-node-02", "corr-node-03"]
for node in nodes:
    r = requests.post(f"{BASE}/ingest/prometheus/alertmanager", json=spike(node), timeout=5)
    print(f"  push {node}: HTTP {r.status_code}")

print("Waiting 3s for DB writes...")
time.sleep(3)

# Verify SEV-2 incident was auto-created
inc = requests.get(f"{BASE}/api/v1/incidents/active", headers=hdr, timeout=5)
if inc.status_code != 200:
    print(f"FAIL  no active incident (HTTP {inc.status_code})")
    sys.exit(1)

d = inc.json()
print()
print(f"PASS  incident created  id={d['id']}")
print(f"      severity={d['severity']}  service={d['service']}")
print(f"      description: {d['description']}")
print(f"      timeline ({len(d.get('timeline', []))} entries):")
for e in d.get("timeline", []):
    actor = e.get("actor", "?")
    note  = e.get("note", "")[:120]
    print(f"        [{actor}] {note}")

assert d["severity"] == "SEV2", f"Expected SEV2, got {d['severity']}"
assert d["status"] == "active"
assert "Fleet-Wide" in d["service"]
print()
print("All correlation checks passed.")
