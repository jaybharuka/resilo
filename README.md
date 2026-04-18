# Resilo — AI-Powered Remote Monitoring & Auto-Remediation

> Monitor any machine in real time. Let AI detect, analyze, and fix issues automatically. No VPN. No port forwarding. Zero config.

## What it does

Resilo runs a lightweight agent on any machine (Windows, macOS, Linux). The agent pushes live system metrics (CPU, memory, disk, network, temperature) to the Resilo backend over plain HTTPS. When thresholds are breached, an AI agent analyzes the alert and — depending on the configured execution mode — automatically queues and executes safe remediation commands.

**Full loop in under 30 seconds:**
```
Agent pushes metrics ? Threshold breached ? Alert created
? LangChain AI analyzes ? Command queued ? Agent executes ? Alert resolves
```

---

## Services & Ports

| Service | Port | Description |
|---|---|---|
| React Dashboard | 3000 | Frontend (CRA dev server) |
| Node/Express | 3011 | API gateway, Socket.IO |
| FastAPI Core | 8000 | Metrics, agents, AI pipeline |
| FastAPI Auth | 5001 | JWT, OAuth, 2FA |
| PostgreSQL | 5432 | Primary database |

---

## Quick Start (Dev)

**Prerequisites:** Python 3.12+, Node 18+, PostgreSQL 15

```bash
# Clone
git clone https://github.com/jaybharuka/resilo.git
cd resilo

# Python deps
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Node deps
cd dashboard && npm install && cd ..

# Configure
copy .env.dev .env            # edit DATABASE_URL, JWT_SECRET, NVIDIA_API_KEY

# Start everything (Windows)
run-dev.bat

# Stop everything
stop-dev.bat
```

Open **http://localhost:3000** — default admin: `admin@company.local / Admin@1234`

---

## Architecture

```
+-------------+     HTTPS      +----------------------+
¦ Remote      ¦ -------------? ¦ FastAPI Core  :8000   ¦
¦ Agent       ¦  heartbeat     ¦ runtime.py            ¦
¦ (Python/Go) ¦ ?---- cmd ---- ¦ LangChain AI agent    ¦
+-------------+                +-----------------------+
                                          ¦ SQLAlchemy
+-------------+   SSE / REST             ?
¦ React SPA   ¦ ?------------ +----------------------+
¦ :3000       ¦               ¦ PostgreSQL  :5432     ¦
+-------------+               +----------------------+
       ¦ CRA proxy
+------?------+               +----------------------+
¦ Node/Express¦               ¦ FastAPI Auth  :5001   ¦
¦ :3011       ¦               ¦ JWT, OAuth, 2FA       ¦
+-------------+               +----------------------+
```

---

## Key Features

### Remote Agent
- Pushes CPU, memory, disk, network, temperature every 3s over plain HTTPS
- Zero-config install: one env var + one command
- Windows EXE build (no Python required on target): `desktop_agent/build_exe.bat`
- Go agent in progress: `agent/go-agent/`

### AI Anomaly Detection
- Thresholds: CPU > 85% = critical, Memory > 90% = high
- LangChain + NVIDIA NIM LLM analyzes each alert asynchronously
- Three execution modes per agent:
  - `dry_run` — log only
  - `manual_approval` — queue for human review
  - `auto_safe` — auto-execute safe actions
- Safe actions: `scale_memory`, `disk_cleanup`, `restart_service`, `notify_only`, `noop`
- Learning feedback loop tracks success rate per action

### Dashboard
- Real-time metrics via SSE (no polling)
- Agent status: LIVE / OFFLINE / PENDING with clickable filters
- AI DECISIONS panel — full reasoning + confidence per decision
- Activity timeline, learning feedback, alert history

### Auth
- JWT access tokens (15 min) + refresh tokens (7 days, httpOnly cookie)
- Google OAuth2, TOTP 2FA, org-scoped multi-tenancy
- Roles: `admin`, `member`, `viewer`

---

## Project Structure

```
resilo/
+-- app/
¦   +-- api/
¦   ¦   +-- runtime.py         # Core API — heartbeat, agents, AI pipeline
¦   ¦   +-- core_api.py        # FastAPI app factory
¦   ¦   +-- auth_api.py        # Auth service
¦   +-- agents/
¦       +-- langchain_agent.py # LangChain AI agent + tools
+-- dashboard/
¦   +-- src/
¦   ¦   +-- components/        # React components (RemoteAgents, Dashboard…)
¦   ¦   +-- services/          # API clients (api.js, resiloApi.js)
¦   ¦   +-- setupProxy.js      # CRA dev proxy rules
¦   +-- server.js              # Node/Express gateway
+-- desktop_agent/
¦   +-- resilo_agent.py        # Core agent logic
¦   +-- resilo_gui.py          # Tkinter GUI (PyInstaller target)
¦   +-- build_exe.bat          # Build Windows EXE
¦   +-- demo_ai_pipeline.py    # Full AI pipeline demo script
+-- agent/go-agent/            # Go agent (in progress)
+-- docs/
¦   +-- PRD.md
¦   +-- DESIGN.md
¦   +-- TECH_STACK.md
+-- .env.dev                   # Dev environment config
+-- run-dev.bat                # Start all 4 services
+-- stop-dev.bat               # Kill all services
```

---

## Environment Variables

```env
# .env.dev — single source of truth for local dev
ENV=development
PORT=3011
CORE_API_URL=http://localhost:8000

DATABASE_URL=postgresql+asyncpg://aiops:aiops@localhost:5432/aiops
JWT_SECRET=your-secret-here
NVIDIA_API_KEY=your-nvidia-nim-key   # Required for AI agent

# Google OAuth (optional)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
FRONTEND_URL=http://localhost:3000
```

---

## AI Pipeline Demo

Run the full detect ? analyze ? remediate loop in one command:

```bash
# Option 1: Auto-creates a demo agent (admin org)
python desktop_agent/demo_ai_pipeline.py

# Option 2: Use YOUR token from dashboard ? + New Agent
python desktop_agent/demo_ai_pipeline.py --token resilo_xxx...
```

Expected output:
```
? AI PIPELINE COMPLETE
  ISSUE    : CPU 96% + Memory 94% — CRITICAL thresholds breached
  AI ACTION: scale_memory
  TARGET   : system
```

Then open **http://localhost:3000/remote-agents** ? click the agent ? AI DECISIONS panel.

---

## API Reference (Core — :8000)

| Method | Path | Description |
|---|---|---|
| `POST` | `/ingest/heartbeat` | Agent pushes metrics |
| `GET` | `/agent/command` | Agent polls for queued commands |
| `POST` | `/agents/onboard` | Generate registration token (JWT required) |
| `POST` | `/agents/register` | Exchange token for agent key |
| `PATCH` | `/api/orgs/{org_id}/agents/{id}/execution-mode` | Set AI execution mode |
| `GET` | `/api/orgs/{org_id}/agents/{id}` | Agent detail + AI history |
| `GET` | `/stream` | SSE real-time updates |

## API Reference (Auth — :5001)

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Email/password login |
| `POST` | `/auth/register` | Register new org |
| `POST` | `/auth/refresh` | Refresh access token |
| `POST` | `/auth/2fa/setup` | Setup TOTP |
| `GET` | `/auth/google` | Google OAuth redirect |

---

## Contributing

```bash
git checkout -b feature/my-feature
git commit -m "feat: my feature"
git push origin feature/my-feature
# open PR
```

---

## License

MIT
