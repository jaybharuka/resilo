# Resilo — Tech Stack Document

## Architecture Overview
```
┌─────────────┐     HTTPS      ┌──────────────────┐
│ Remote      │ ─────────────► │ FastAPI Core      │
│ Agent       │  heartbeat/cmd │ :8000             │
│ (Python/Go) │               └──────┬───────────┘
└─────────────┘                      │ SQLAlchemy async
                                     ▼
┌─────────────┐               ┌──────────────────┐
│ React SPA   │ ◄──SSE/REST──► │ FastAPI Auth      │
│ :3000       │               │ :5001             │
│ (CRA)       │               └──────────────────┘
└──────┬──────┘                      │
       │ proxy                       ▼
┌──────▼──────┐               ┌──────────────────┐
│ Node/Express│               │ PostgreSQL        │
│ :3011       │               │ :5432             │
└─────────────┘               └──────────────────┘
                                     ▲
                               ┌─────┴────────────┐
                               │ LangChain Agent   │
                               │ (NVIDIA NIM LLM)  │
                               └──────────────────┘
```

---

## Backend

### FastAPI Core (`app/api/runtime.py`, `core_api.py`)
- **Framework**: FastAPI (Python 3.12)
- **ASGI Server**: Uvicorn with `--reload` in dev
- **ORM**: SQLAlchemy 2.0 async (`asyncpg` driver)
- **Database**: PostgreSQL 15 (TimescaleDB compatible)
- **Key endpoints**:
  - `POST /ingest/heartbeat` — agent metric ingestion
  - `GET /agent/command` — agent polls for queued commands
  - `POST /agents/onboard` — generate short-lived registration token
  - `POST /agents/register` — exchange token for permanent agent key
  - `PATCH /api/orgs/{org_id}/agents/{agent_id}/execution-mode`
  - `GET /api/orgs/{org_id}/agents/{agent_id}` — agent detail + AI history
  - `GET /stream` — SSE real-time updates

### FastAPI Auth (`app/api/auth_api.py`)
- JWT access tokens (15 min) + refresh tokens (7 days, httpOnly cookie)
- bcrypt password hashing
- TOTP 2FA
- Google OAuth2
- Org-scoped multi-tenancy
- Rate limiting on login endpoint

### AI Agent (`app/agents/langchain_agent.py`)
- **Framework**: LangChain 0.3.25
- **LLM**: NVIDIA NIM (`meta/llama-3.1-8b-instruct` via OpenAI-compatible API)
- **Tools**: `scale_memory`, `disk_cleanup`, `restart_service`, `notify_only`, `noop`
- **Safe actions**: `frozenset` controls which actions can auto-execute
- **Confidence calibration**: blends LLM score with historical success rate

---

## Frontend

### React SPA (`dashboard/src/`)
- **Framework**: Create React App (CRA) with craco
- **Port**: 3000 (locked)
- **Routing**: React Router v6
- **State**: React hooks (`useState`, `useCallback`, `useEffect`) — no Redux
- **HTTP**: Axios with interceptors for JWT auto-attach
- **Real-time**: SSE (`EventSource`) for metric updates
- **Icons**: Lucide React
- **Styling**: Inline styles with design token constants (no Tailwind in components)
- **Key components**: `RemoteAgents`, `AgentDetail`, `Dashboard`, `AIAssistant`, `Alerts`

### Node/Express (`dashboard/server.js`)
- **Port**: 3011
- **Role**: API gateway, Socket.IO, static file serving in prod
- **Proxy rules**:
  - `/auth`, `/users` → FastAPI Auth :5001
  - `/agents`, `/orgs`, `/alerts` → FastAPI Core :8000 (`CORE_API_URL`)
  - Everything else → Flask :5000 (legacy)

### Proxy config (dev)
- CRA setupProxy routes `/agents`, `/orgs`, `/alerts`, `/remediation` → `localhost:8000`
- CRA setupProxy routes `/auth`, `/users`, `/stream` → `localhost:5001`

---

## Desktop Agent

### Python Agent (`desktop_agent/resilo_agent.py`, `resilo_gui.py`)
- **Dependencies**: `psutil`, `tkinter`, `ctypes`
- **Metrics**: CPU, memory, disk, network I/O, temperature, load avg, processes
- **Commands**: `free_memory` (Windows `EmptyWorkingSet`), `disk_cleanup`
- **Config**: `~/.resilo_agent.json`
- **Build**: PyInstaller single-file EXE (`build_exe.bat`)
- **CI**: GitHub Actions (`build-agent.yml`) → artifact upload

### Go Agent (`agent/go-agent/`) ← In Progress
- Metrics collected in `metrics.go`
- Main loop in `main.go`
- Lighter weight than Python agent

---

## Infrastructure / DevOps

| Layer | Tool |
|---|---|
| Local dev | `run-dev.bat` / `stop-dev.bat` |
| Database | PostgreSQL + asyncpg |
| Migrations | SQLAlchemy auto-create (dev) |
| CI/CD | GitHub Actions |
| Deployment | Render (backend), Netlify (frontend) |
| Env management | `.env.dev` (dev), `.env` (prod) |
| Package management | pip + `requirements.txt` |

---

## Key Environment Variables
```env
# Backend
DATABASE_URL=postgresql+asyncpg://...
JWT_SECRET=...
NVIDIA_API_KEY=...          # Required for LangChain AI agent
CORE_API_URL=http://localhost:8000   # Node → FastAPI Core proxy target

# Auth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
FRONTEND_URL=http://localhost:3000

# React (all blank in dev — CRA proxy handles routing)
REACT_APP_API_BASE_URL=
REACT_APP_AUTH_API_URL=
REACT_APP_BACKEND_URL=
```

---

## Dependencies (key packages)
```
fastapi==0.115+
sqlalchemy==2.0+
asyncpg
uvicorn
langchain==0.3.25
langchain-openai==0.3.16
psutil
python-jose (JWT)
passlib[bcrypt]
pyotp (TOTP)
```
