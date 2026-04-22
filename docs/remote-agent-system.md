# Remote Agent System — Technical Reference

## 1. What It Is

The Remote Agent system allows any machine (Windows, Linux, Mac) to be monitored by the Resilo dashboard in real time. The agent is a single Python script (`resilo_agent.py`) that runs on the target machine, collects system metrics every 5 seconds, and pushes them to the production backend over HTTPS. No inbound ports or VPN required — the agent is entirely push-based.

---

## 2. System Architecture

```
[Target Machine]
   resilo_agent.py
        │  collect() every 5s
        │  POST /ingest/heartbeat  (X-Agent-Key header)
        ▼
[Production Backend — https://resilo.onrender.com]
   FastAPI → ingest_heartbeat()
        │  saves MetricSnapshot to PostgreSQL
        │  evaluates thresholds → creates AlertRecord
        │  if alert: calls analyze_alert() → LLM (NVIDIA NIM)
        ▼
[Dashboard — localhost:3000 or Netlify]
   RemoteAgents.js polls GET /api/orgs/{org_id}/agents every 5s
   AgentDetail.js polls GET /api/orgs/{org_id}/agents/{id} every 5s
   Dashboard.js reads ai_history from the agent list
```

---

## 3. Onboarding Flow (How an Agent Gets Connected)

1. Logged-in user opens `/remote-agents` → clicks **+ NEW AGENT**
2. Enters a label → clicks **Generate Token**
   - Frontend calls `POST https://resilo.onrender.com/agents/onboard` with the user's JWT
   - Backend auto-creates the user's org in production DB if it doesn't exist
   - Returns a one-time token (expires in 30 minutes)
3. User copies the displayed command and runs it on the target machine:
   ```powershell
   pip install psutil -q
   Invoke-WebRequest -Uri https://resilo.onrender.com/resilo_agent.py -OutFile resilo_agent.py
   $env:RESILO_ONBOARD_TOKEN="resilo_xxxx"
   $env:RESILO_BACKEND_URL="https://resilo.onrender.com"
   python resilo_agent.py
   ```
4. Agent runs `POST /agents/register` → exchanges token for a permanent `agent_key`
5. Agent saves `agent_key` + `org_id` to `~/.resilo_agent.json`
6. Agent begins heartbeat loop — appears as **LIVE** in the dashboard within 5 seconds

**Critical rule:** The token must be generated from the dashboard UI (not via a script) so it uses the logged-in user's JWT and registers the agent under their org. Tokens generated via a different user's credentials create the agent under the wrong org.

---

## 4. What the Agent Collects (every heartbeat)

| Field | Source |
|---|---|
| `cpu` | `psutil.cpu_percent(interval=0.5)` |
| `memory` | `psutil.virtual_memory().percent` |
| `disk` | `psutil.disk_usage("/").percent` |
| `network_in/out` | `psutil.net_io_counters()` bytes cumulative |
| `temperature` | `psutil.sensors_temperatures()` (None on Windows) |
| `load_avg_1m/5m/15m` | `psutil.getloadavg()` (None on Windows) |
| `processes` | `len(psutil.pids())` |
| `uptime_secs/hours` | `time.time() - psutil.boot_time()` |
| `swap_percent/used_gb` | `psutil.swap_memory()` |
| `disk_read_mbps/write_mbps` | Delta of `psutil.disk_io_counters()` per interval |
| `net_established/close_wait/time_wait` | `psutil.net_connections()` count by state |
| `top_processes` | Top 5 by CPU and top 5 by memory (filtered, normalized) |
| `battery_percent/plugged` | `psutil.sensors_battery()` |
| `disk_partitions` | All mounted partitions with size/used/percent |

### Top Processes — Important Details
- **Filtered:** `System Idle Process`, `Idle`, `System`, `Registry`, `Memory Compression` are excluded (Windows pseudo-processes that show inflated CPU numbers)
- **Normalized:** `cpu_percent` is divided by `cpu_count` (logical cores) so values stay in 0–100% range regardless of core count

---

## 5. Offline Buffering

When the backend is unreachable:
- Metrics are stored in `~/.resilo_buffer.json` (up to 20 payloads)
- Retry delays: 5s → 10s → 30s → 60s → 60s (capped)
- On reconnect, all buffered payloads are flushed in order before resuming normal heartbeat

---

## 6. Backend Heartbeat Processing (`/ingest/heartbeat`)

```
POST /ingest/heartbeat
Headers: X-Agent-Key: <raw_key>
Body: { org_id, metrics: { cpu, memory, disk, ... } }
```

Steps on the backend:
1. Hash the `X-Agent-Key` (SHA-256) and look up the `Agent` record
2. Validate `agent.org_id == body.org_id`
3. Update `agent.last_seen` and `agent.status = "live"`
4. Write a `MetricSnapshot` row to PostgreSQL
5. Evaluate thresholds → create `AlertRecord` if CPU > 85%, memory > 90%, disk > 95%
6. Auto-resolve alerts when values recover (CPU < 80%, memory < 85%)
7. If a new alert fires → call `_lc_analyze()` → LLM analysis → store in `_AI_HISTORY`

---

## 7. AI Analysis Pipeline

### Trigger
An alert fires during heartbeat processing. `_lc_analyze(alert, metrics, agent, db)` is called.

### LLM Call (`langchain_agent.analyze_alert`)
- Model: `meta/llama-3.3-70b-instruct` via NVIDIA NIM (OpenAI-compatible API)
- Endpoint: `https://integrate.api.nvidia.com/v1`
- Key: `NVIDIA_API_KEY` (must be set in Render environment)

### Input to LLM
```
Alert: cpu at 91.2% — Severity: critical
Agent mode: dry_run
Metrics: CPU=91.2%  Memory=52.3%  Disk=76.5%
Load average: 1.2 / 0.9 / 0.8
Top CPU processes: chrome.exe(18.5% cpu, 3.1% mem), python3.12.exe(12.0% cpu, 0.3% mem)
Top Memory processes: chrome.exe(3.1% cpu, 8.2% mem), ...
Historical action success rates: {"disk_cleanup": "3/4 (75%)"}
```

### LLM Output (JSON)
```json
{
  "action": "notify_only",
  "target": null,
  "reasoning": "Chrome is consuming 18.5% CPU. No immediate auto-action safe.",
  "confidence": 0.82,
  "contributing_process": "chrome.exe"
}
```

### Fallback
If `NVIDIA_API_KEY` is not set or the LLM call fails:
- `rule_based_fallback()` is used
- CPU alert → `notify_only` + reasoning `"CPU pressure detected — notifying operator (LLM unavailable)"`
- Memory alert → `scale_memory`
- Disk alert → `disk_cleanup`
- Confidence is hardcoded to `0.4`, `decision_source = "rule_fallback"`

### Execution Modes
| Mode | Behavior |
|---|---|
| `dry_run` | Decision recorded, nothing executed |
| `manual_approval` | Decision queued as `needs_review`, operator approves |
| `auto_safe` | Auto-executes if `confidence >= 0.75` and action is in safe list |

### Protected Services (never auto-restarted)
`sshd`, `postgresql`, `nginx`, `docker`, `systemd`, `etcd`, `kubelet`, `kube-apiserver`

### Safety Guard (auto_safe mode)
- If `confidence < 0.75` → status becomes `needs_review` (not executed)
- Max 3 auto-restarts per hour per agent
- `restart_service` blocked if target is in protected set

---

## 8. Dashboard UI — Remote Agents Page

### Agent List View
- **Status pills:** ALL / LIVE / OFFLINE / PENDING with counts
- **Sort order:** LIVE → OFFLINE → PENDING
- **Poll interval:** 5 seconds (auto-refresh)
- **Empty state:** Shows `OnboardingWizard` (3-step wizard) when no agents exist
- **Cards show:** label, hostname, OS, status dot, CPU / MEM / DISK bars, last seen

### Agent Detail View (click any agent card)
Opened at `/remote-agents` with selected agent state. Shows:
- **Live metric bars:** CPU, Memory, Disk with color thresholds (teal < 60%, amber < 85%, red >= 85%)
- **Metric history chart:** 30-point sparkline (CPU + Memory over time)
- **Top Processes panel:** Table sorted by CPU or Memory, toggle button
- **AI Thinking Panel:** Animated 3-step trace of the latest AI decision
- **Open Alerts:** Severity badge, category, title, threshold, resolve button
- **Command Center:** Send actions to the agent (restart, cleanup, etc.)
- **Command History:** Past commands with status (pending/ok/error)
- **Execution mode selector:** dry_run / manual_approval / auto_safe

### AI Thinking Panel (`AgentThinkingPanel`)
Displays the most recent entry from `ai_history`. Shows 3 animated steps:
1. `Analyzing anomaly: {category} ({severity})`
2. `Comparing actions by context success rate...`
3. `Selected: {action} — confidence {X}%`

Status badge colors:
- `dry_run` → grey
- `needs_approval` → amber
- `queued` → teal
- `needs_review` → red

---

## 9. Known Issues & Current State

### Issue 1 — AI History is In-Memory Only
`_AI_HISTORY` in `runtime.py` is a Python dict. It resets on every Render deployment or server restart. After a fresh deploy, the "Recent AI Decisions" panel and "Agent Thinking" panel will be empty until new alerts fire and the LLM is called again.

**Fix needed:** Persist `_AI_HISTORY` entries to the `AgentActionLog` DB table and read them back on startup.

### Issue 2 — LLM Fallback Until NVIDIA_API_KEY Set in Render
`NVIDIA_API_KEY` is declared in `render.yaml` as `sync: false` (must be set manually in Render dashboard). Until it's set, every alert triggers `rule_based_fallback()` with `confidence=0.4`.

**Fix:** Go to Render → `aiops-core` service → Environment → set `NVIDIA_API_KEY`.

### Issue 3 — Org Isolation
Each logged-in user has their own `org_id` in their JWT. Agents are scoped to an org. If a user generates a token manually (not from the dashboard UI), the agent may be registered under a different org and won't appear for the current logged-in user.

**Fix:** Always generate tokens from the dashboard `+ NEW AGENT` button.

### Issue 4 — Load Average Always `null` on Windows
`psutil.getloadavg()` is not supported on Windows. `load_avg_1m/5m/15m` will always be `None` for Windows agents. The LLM prompt shows `null / null / null` for load average.

**Improvement opportunity:** Substitute a CPU rolling average or simply omit load avg from the LLM prompt on Windows.

### Issue 5 — Temperature Always `null` on Most Windows Machines
`psutil.sensors_temperatures()` requires hardware support. Most consumer Windows machines return nothing.

---

## 10. Key Files

| File | Role |
|---|---|
| `desktop_agent/resilo_agent.py` | Source for the agent script users download and run |
| `~/.resilo_agent.json` | Agent config on the user's machine (agent_key, org_id, backend_url) |
| `~/.resilo_buffer.json` | Offline metric buffer (up to 20 payloads) |
| `app/api/runtime.py` | All backend endpoints: heartbeat, agent list/detail, alert management, SSE |
| `app/agents/langchain_agent.py` | LLM analysis, rule fallback, safe-action guards |
| `app/core/database.py` | `Agent`, `MetricSnapshot`, `AlertRecord`, `AgentActionLog` ORM models |
| `dashboard/src/components/RemoteAgents.js` | Full Remote Agents UI (list, detail, wizard, command center) |
| `dashboard/src/components/OnboardingWizard.js` | 3-step onboarding: label → token → waiting |
| `dashboard/src/services/resiloApi.js` | `agentsApi` — calls `GET/POST /api/orgs/{org_id}/agents` |
| `dashboard/src/services/api.js` | `agentApi` — calls `/agents/onboard`, `/agents/register` |

---

## 11. Metrics Thresholds (Alert Triggers)

| Metric | Alert fires | Alert auto-resolves |
|---|---|---|
| CPU | > 85% | < 80% |
| Memory | > 90% | < 85% |
| Disk | > 95% | no auto-resolve |

Alert severity levels: `critical`, `high`, `medium` (mapped from category + metric value).

---

## 12. Improvement Opportunities for the AI Agent

1. **Persist AI decisions to DB** — Read `AgentActionLog` on startup to repopulate `_AI_HISTORY`. Decisions survive server restarts.

2. **Windows load average substitute** — When `load_avg` is null (Windows), compute a 1-minute CPU rolling average from the last N `MetricSnapshot` rows and pass it to the LLM.

3. **Process-level context enrichment** — The top processes are already sent to the LLM. Next step: correlate process names with known alert patterns (e.g. if `chrome.exe` is top CPU and alert is CPU, confidence that killing/notifying is safe is high vs. `sqlservr.exe` where action risk is much higher).

4. **Confidence calibration** — The LLM returns a raw confidence float. Currently used as a pass/fail gate at 0.75. A better approach: use it to choose between `notify_only` vs. `restart_service` dynamically within the prompt, not just as a gate.

5. **Action feedback loop** — `AgentActionLog` tracks success/failure of executed commands. `get_action_success_rates()` already reads this and passes it to the LLM. As the agent builds a history, the LLM can learn which actions work for this specific machine.

6. **Alert deduplication** — Currently a new `AlertRecord` fires every heartbeat cycle while the metric stays above threshold. Add a "cooldown" — only create a new alert if the previous one for the same category resolved or is older than N minutes.

7. **Multi-metric correlation** — LLM currently sees metrics individually. If CPU is high AND net_established is high AND disk_write_mbps is high simultaneously, that pattern suggests a specific cause (e.g. database under load) that rule-based fallback cannot detect.
