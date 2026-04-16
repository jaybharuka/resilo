"""
Resilo AI Pipeline Demo
Runs the full loop: normal → critical → AI fires → command queued → shown.

Usage:
  python demo_ai_pipeline.py                          # auto-creates agent via admin login
  python demo_ai_pipeline.py --token resilo_xxxx...   # use YOUR token from dashboard New Agent
"""
import json, sys, time, urllib.request, urllib.error

BACKEND = "http://localhost:8000"
AUTH    = "http://localhost:5001"

# ── HTTP helpers ──────────────────────────────────────────────────────────────
def _req(method, base, path, body=None, headers=None):
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(f"{base}{path}", method=method, data=data, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {method} {path}: {e.read().decode()[:200]}") from e

def login():
    r = _req("POST", AUTH, "/auth/login",
             {"email": "admin@company.local", "password": "Admin@1234"})
    t = r.get("token")
    org_id = r.get("user", {}).get("org_id") or r.get("org_id")
    if not t:
        raise RuntimeError(f"Login failed: {r}")
    return t, org_id

def create_onboard_token(jwt, org_id):
    r = _req("POST", BACKEND, "/agents/onboard",
             {}, {"Authorization": f"Bearer {jwt}"})
    return r.get("token") or r.get("onboard_token") or r.get("value") or list(r.values())[0]

def register_agent(onboard_token):
    r = _req("POST", BACKEND, "/agents/register",
             {"token": onboard_token, "label": "ai-demo-agent"})
    return r  # {org_id, agent_key, agent_id, ...}

def set_exec_mode(jwt, org_id, agent_id, mode):
    return _req("PATCH", BACKEND,
                f"/api/orgs/{org_id}/agents/{agent_id}/execution-mode",
                {"mode": mode}, {"Authorization": f"Bearer {jwt}"})

def heartbeat(org_id, agent_key, cpu, memory, disk=50.0):
    return _req("POST", BACKEND, "/ingest/heartbeat",
                {"org_id": org_id, "metrics": {
                    "cpu": cpu, "memory": memory, "disk": disk,
                    "network_in": 1024, "network_out": 512,
                    "temperature": None, "processes": 200, "uptime_secs": 3600,
                    "extra": {"device_id": "demo-device", "agent_label": "ai-demo-agent",
                              "hostname": "demo-host", "platform": "Windows", "error_rate": 0},
                }},
                {"X-Agent-Key": agent_key})

def poll_commands(agent_key):
    r = _req("GET", BACKEND, f"/agent/command?token={agent_key}",
             headers={"X-Agent-Key": agent_key})
    return r.get("commands", [])


# ── Accept --token from CLI (dashboard New Agent) ────────────────
EXTERNAL_TOKEN = None
if "--token" in sys.argv:
    idx = sys.argv.index("--token")
    if idx + 1 < len(sys.argv):
        EXTERNAL_TOKEN = sys.argv[idx + 1]

print("=" * 60)
print("  RESILO AI PIPELINE DEMO")
print("=" * 60)

# ── STEP 1: Create agent ─────────────────────────────────────────
if EXTERNAL_TOKEN:
    print("\n[1/5] Using token from dashboard…")
    agent_info = register_agent(EXTERNAL_TOKEN)
    agent_key  = agent_info.get("agent_key") or agent_info.get("key")
    agent_id   = agent_info.get("agent_id") or agent_info.get("id")
    org_id     = agent_info.get("org_id")
    print(f"      ✓ Agent registered  id={agent_id}  org={org_id}")
    jwt, _     = login()  # still need jwt to set exec mode
else:
    print("\n[1/5] Logging in and creating a demo agent…")
    jwt, org_id = login()
    print(f"      ✓ Logged in  org_id={org_id}")
    onboard_token = create_onboard_token(jwt, org_id)
    print(f"      ✓ Onboard token created")
    agent_info = register_agent(onboard_token)
    agent_key  = agent_info.get("agent_key") or agent_info.get("key")
    agent_id   = agent_info.get("agent_id") or agent_info.get("id")
    print(f"      ✓ Agent registered  id={agent_id}")

# ── STEP 2: Set execution mode → AUTO SAFE ───────────────────────
print("\n[2/5] Setting execution mode → AUTO SAFE…")
set_exec_mode(jwt, org_id, agent_id, "auto_safe")
print("      ✓ Execution mode = auto_safe")
time.sleep(1)

# ── STEP 3: Normal heartbeat (baseline + resolve any open alerts) ─
print("\n[3/5] Sending NORMAL metrics (cpu=12%, mem=40%)…")
r = heartbeat(org_id, agent_key, cpu=12.0, memory=40.0)
print(f"      ✓ Baseline recorded")
time.sleep(2)

# ── STEP 4: CRITICAL heartbeat → triggers AI ─────────────────────
print("\n[4/5] Sending CRITICAL metrics (cpu=96%, mem=94%)…")
print("      → Alert created → AI analysis triggered → command queued")
r = heartbeat(org_id, agent_key, cpu=96.0, memory=94.2)
print(f"      ✓ Snapshot id={r.get('snapshot', {}).get('id', '?')}")

# ── STEP 5: Poll for command ──────────────────────────────────────
print("\n[5/5] Waiting for AI to queue a command (up to 45s)…")
cmd_found = None
for i in range(15):
    time.sleep(3)
    cmds = poll_commands(agent_key)
    status = f"{'✓' if cmds else '…'} [{i+1}/15] commands={len(cmds)}"
    print(f"      {status}")
    if cmds:
        cmd_found = cmds[0]
        break

print("\n" + "=" * 60)
if cmd_found:
    print("  ✅  AI PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  ISSUE    : CPU 96% + Memory 94% — CRITICAL thresholds breached")
    print(f"  AI ACTION: {cmd_found.get('action')}")
    print(f"  TARGET   : {cmd_found.get('target') or '—'}")
    print(f"\n  What happens next:")
    print(f"  → Agent polls, receives this command, executes it")
    print(f"  → Metrics normalise → alert auto-resolves")
    print(f"  → Feedback loop records success/failure")
else:
    print("  ℹ️  AI analysed but action was DRY_RUN (no command queued)")
    print("=" * 60)
    print("  The AI DECISIONS panel in the dashboard shows the reasoning.")
    print("  If execution mode set correctly, action may be 'notify_only'")
    print("  (AI chose notification over execution — that is valid behaviour)")

print(f"\n  See full story in dashboard:")
print(f"  http://localhost:3000/remote-agents → click 'ai-demo-agent'")
print(f"  → AI DECISIONS  → ACTIVITY TIMELINE  → LEARNING FEEDBACK")
print("=" * 60)
