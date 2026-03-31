# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AIOps Bot is an AI-powered operations monitoring and automation platform with a multi-service Python backend (FastAPI + legacy Flask) and a React frontend. It provides real-time system monitoring, AI-powered insights, multi-channel notifications, and autonomous operations for multi-tenant enterprise environments.

## Commands

### Backend Services

```bash
# Install dependencies
pip install -r requirements.txt

# Auth service (FastAPI, port 5001)
uvicorn app.api.auth_api:app --port 5001 --reload

# Core API (FastAPI, port 8000)
uvicorn app.api.core_api:app --port 8000 --reload

# Seed initial admin user
python scripts/seed_admin.py

# Legacy Flask API (port 5000) — being deprecated
python app/api/api_server.py

# Interactive launcher (setup, chatbots, monitoring subsystems)
python launch.py
```

### Frontend

```bash
cd dashboard
npm install
npm start           # Dev server (port 3000, via craco)
npm run build       # Production build
npm run server      # Express server (port 3002)
npm run start-all   # Concurrent: dev + express server
npm test            # Jest via craco
```

### Docker (Full Stack)

```bash
docker-compose up                    # All 15 services
docker-compose up timescaledb nginx  # DB + proxy only
```

### Windows Scripts

```powershell
.\scripts\start_dashboard.ps1   # Backend + frontend
.\scripts\stop_all.ps1
.\scripts\restart_backend.ps1
```

## Default Ports

| Service             | Port |
|---------------------|------|
| Auth API (FastAPI)  | 5001 |
| Core API (FastAPI)  | 8000 |
| Legacy Flask API    | 5000 |
| Frontend dev        | 3000 |
| Express server      | 3002 |
| Nginx (TLS)         | 443  |
| Prometheus          | 9090 |
| Grafana             | 3000 |
| Jaeger UI           | 16686|
| TimescaleDB         | 5432 |

## Architecture

### Three-Layer API Design

The backend has three API layers; `core_api` and `auth_api` are the active ones:

1. **`app/api/auth_api.py`** (FastAPI, port 5001) — JWT issuance, user management, TOTP/2FA (pure-Python RFC 6238, no pyotp), email-based password reset via SMTP, invite tokens. Rate limited at Nginx: 20 req/min login.

2. **`app/api/core_api.py`** (FastAPI, port 8000) — Unified platform for agents, metrics, alerts, remediation, anomaly detection, and daily summaries. Multi-tenant: all queries scoped by `org_id`. Rate limited at Nginx: 100 req/min API, 30 req/min heartbeat. Has background anomaly detection engine and OpenTelemetry instrumentation.

3. **`app/api/api_server.py`** (Flask, port 5000) — **Legacy, being deprecated.** Synchronous, in-memory rate limiting with `threading.Lock`. Still used for backward compatibility.

### Request Flow (via Nginx)

```
Client → Nginx (443)
  /auth/*   → auth-api  :5001
  /users    → auth-api  :5001
  /api/*    → core-api  :8000
  /ingest/* → core-api  :8000  (agent heartbeat)
  /*        → React build (static)
```

### Authentication & RBAC

- **Auth flow**: login → JWT access token (24h) + refresh token (30d), both HS256
- **2FA**: password auth returns temp token; client must POST TOTP code to complete login
- **Rate limiting**: Per-IP 10 attempts/min + per-email lockout (5 failures → 15-min lockout)
- **RBAC** defined in `app/auth/rbac.py`. Permission matrix:
  - `admin`: wildcard (`*`)
  - `devops`: agents, metrics, alerts, remediation r/w/execute
  - `viewer`: read-only on agents, metrics, alerts, remediation
  - `manager`/`employee`: legacy aliases for devops/viewer

  FastAPI `Depends()` helpers in `rbac.py` enforce permissions at route level.

### Database

- **PostgreSQL + TimescaleDB** (replaces SQLite). Connection in `app/core/database.py`.
- Async SQLAlchemy 2.0 (`asyncpg`): pool size 5, max overflow 10, pre-ping enabled.
- `DATABASE_URL` env defaults to `postgresql+asyncpg://aiops:aiops@localhost:5432/aiops`.
- Key tables: `Organization`, `User`, `UserSession`, `Agent`, `MetricSnapshot` (hypertable), `AlertRecord`, `RemediationRecord`, `AuditLog`, `WMITarget`.
- TimescaleDB retention policy controlled by `TIMESCALE_RETENTION_DAYS` (default 30).
- All resource tables are **multi-tenant**: always filter by `org_id`.

### Frontend (React)

Located in `dashboard/src/`. Uses craco (not react-scripts directly) for build overrides.
- State: Zustand
- UI: Material-UI + Tailwind CSS + Framer Motion + Recharts
- Real-time: Socket.io-client v4.7
- `dashboard/server.js` — Express server (separate from React dev server)

### Key Environment Variables

Copy `dashboard/.env.example` to `dashboard/.env`. Backend variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Shared JWT signing secret |
| `JWT_ACCESS_TTL` | Access token TTL in seconds (default 86400) |
| `JWT_REFRESH_TTL` | Refresh token TTL (default 2592000) |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` | Email for password reset |
| `TIMESCALE_RETENTION_DAYS` | Metrics retention (default 30) |
| `DISCORD_BOT_TOKEN`, `SLACK_WEBHOOK_URL` | Notification integrations |
| `DEMO_MODE` | Enable demo features |

### Observability Stack (Docker Compose)

- **Prometheus + Grafana** — metrics dashboards
- **ELK stack** (Elasticsearch, Logstash, Kibana, Filebeat) — log aggregation; core_api emits JSON logs via `jsonlogger`
- **Jaeger** — distributed tracing via OpenTelemetry (instrumented in `core_api.py`)
- **HashiCorp Vault** — secrets management (port 8200)

### AI Integration

- **Google Gemini** (`app/integrations/gemini_integration.py`) — primary LLM for chat and analysis
- **Hugging Face** (`app/integrations/huggingface_ai_integration.py`) — sentiment analysis, issue classification (transformers/torch are optional; commented out in `requirements.txt`)

### Pre-commit Hooks

`.pre-commit-config.yaml` runs **gitleaks** on staged files for secret detection. Do not bypass with `--no-verify`.
