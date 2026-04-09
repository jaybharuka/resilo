# Resilo — architecture

## System overview

Resilo is a multi-tenant AIOps platform that combines real-time infrastructure monitoring,
intelligent alerting, and automated remediation. It authenticates users and service agents
via JWT/SSO, ingests metrics from polling agents, and surfaces actionable insights through
a React dashboard and chat integrations (Discord, Teams).

---

## Component map

| Component | Path | Responsibility |
|-----------|------|----------------|
| **Auth API** | `app/api/auth_api.py` | JWT issuance, refresh, 2FA (TOTP), SSO (SAML), session management |
| **API Server** | `app/api/api_server.py` | Flask REST layer — rate limiting, CORS, per-org request routing |
| **API Gateway** | `app/api/api_gateway.py` | Request routing, API key validation, per-key rate limiting |
| **Core API** | `app/api/core_api.py` | FastAPI service — org metrics, alert CRUD, browser metric ingestion |
| **SSO Handler** | `app/core/sso_handler.py` | SAML assertion validation, user provisioning on first SSO login |
| **WMI Poller** | `app/integrations/wmi_poller.py` | Agentless Windows metric collection via WinRM + Fernet encryption |
| **Discord Bot** | `app/integrations/discord_bot.py` | Alert dispatch and slash-command interface for Discord |
| **Teams Integration** | `app/integrations/teams_integration.py` | Adaptive card alerts and webhook delivery for Microsoft Teams |
| **Analytics service** | `app/analytics/` | Dynamic thresholds, alert correlation, predictive failure detection |
| **AIOps Monitor** | `app/monitoring/intelligent_aiops_monitor.py` | Root-cause analysis, ML anomaly detection, automated remediation |
| **Metrics exporter** | `metrics-exporter/metrics_exporter.py` | Prometheus scrape endpoint (port 8001) for system + app metrics |
| **Bot analytics** | `bot/analytics_service.py` | Prometheus query wrapper + psutil fallback for dashboard charts |
| **Dashboard** | `dashboard/` | React + Node/Express front-end; proxies to Flask:5000 and FastAPI:8000 |

---

## Port map

| Port | Service |
|------|---------|
| 3000 | React dev server (CRA / craco) |
| 3002 | Node/Express proxy + Socket.IO |
| 5000 | Flask API server |
| 5001 | FastAPI Auth API |
| 8000 | FastAPI Core API |
| 8001 | Prometheus metrics exporter |
| 9090 | Prometheus (external) |

---

## Data flow

### Authenticated API call (happy path)

```
Browser → Node:3002 → Flask:5000
  1. Browser sends JWT in Authorization header.
  2. Node proxy forwards to Flask (path-rewrite preserves /api prefix).
  3. Flask validates JWT, resolves org_id from token claims.
  4. OrgContextMiddleware attaches org_id to request context.
  5. Route handler queries PostgreSQL (RLS enforced at DB layer).
  6. Response flows back through Node → Browser.
```

### Metric ingestion (agent path)

```
Agent → Core API:8000 /ingest/heartbeat
  1. Agent sends X-Agent-Key header + JSON payload.
  2. Core API validates key hash against api_keys table.
  3. Metrics written to PostgreSQL under agent's org_id.
  4. Analytics service picks up new data on next threshold cycle.
  5. If threshold breached → alert created → notification_router dispatches
     to configured channels (Discord / Teams / Slack / Telegram).
```

---

## Infrastructure

| Layer | Technology |
|-------|-----------|
| Container | Docker (3 images: auth, core, dashboard) |
| Orchestration | Kubernetes via Helm chart (`helm/aiops-bot/`) |
| Database | PostgreSQL 15 with Alembic migrations |
| Cache | Redis (response caching, session store) |
| Observability | Prometheus + Grafana + OpenTelemetry + ELK |
| Tracing | Jaeger via OTLP exporter |
| Secrets | Environment variables from `.env` / secrets manager; `secrets/` and `vault/local/` gitignored |
| CI/CD | GitHub Actions (integrity, security scan, migrations, load tests, deploy) |

---

## Security model

- **Auth**: short-lived JWTs (access) + opaque refresh tokens stored as SHA-256 hashes
- **CORS**: strict origin allowlist — no wildcard `*` in any response
- **Rate limiting**: per-IP (429) and per-email lockout (403) on `/auth/login`
- **Input validation**: `email[:254]`, `password[:1000]` length caps at API boundary
- **Secrets**: all secrets loaded via `app.core.secrets.require_secret()` — fails at startup if missing
- **RLS**: PostgreSQL row-level security enforces tenant isolation at the database layer
- **SAST**: bandit runs on every push; gitleaks scans full commit history

---

## Decision log

| Decision | Rationale |
|----------|-----------|
| FastAPI alongside Flask | FastAPI for async-heavy auth and ingestion paths; Flask retained for legacy dashboard routes |
| Alembic for migrations | Type-safe, reversible schema changes; integrates with SQLAlchemy models |
| Opaque refresh tokens (hash stored) | Token value never persisted — breach of DB does not expose live sessions |
| Field-level encryption (Fernet) | Protects PII (WMI credentials, TOTP seeds) without full-DB encryption overhead |
| `require_secret()` fail-fast | Misconfigured deployments crash immediately at startup rather than serving with insecure fallbacks |
| Separate auth port (5001) | Allows independent scaling and deployment of the auth service |
| RLS over application-layer tenancy | DB-enforced isolation survives application bugs; cannot be bypassed by query construction |
