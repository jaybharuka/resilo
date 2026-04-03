# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AIOps Bot is an AI-powered operations monitoring and automation platform. It combines a Python Flask backend (74+ modules) with a React frontend dashboard, providing real-time system monitoring, AI-powered insights, multi-channel notifications, and autonomous operations.

## Commands

### Backend


```bash
# Install dependencies
pip install -r requirements.txt

# Run main API server (port 5000)
python api_server.py

# Run orchestrator
python aiops_orchestrator.py

# Interactive launcher (menu-driven)
python launch.py

# Check imports / validate environment
python check_imports.py
```

### Frontend

```bash
cd dashboard
npm install
npm start          # Dev server (port 3001)
npm run build      # Production build
npm run server     # Express backend server
```

### One-Click Launch (Windows)

```bash
start_dashboard.bat          # Backend + frontend
.\scripts\start_all.ps1 -Port 3001 -BindHost "127.0.0.1"
.\scripts\stop_all.ps1
```

### Docker

```bash
docker-compose up
```

## Default Ports

| Service    | Port |
|------------|------|
| Frontend   | 3001 (fallback 3011) |
| API Backend | 5000 |
| Prometheus | 9090 |
| Metrics Exporter | 8001 |
| Bot Service | 8080 |

## Architecture

### Backend (Python)

The backend is organized around a central orchestrator with modular, domain-specific services:

- **`api_server.py`** — Flask REST API (primary entry point). Serves `/api/health`, `/api/system`, `/api/insights`, `/api/alerts`, `/api/chat`, `/api/analyze`. Initializes `EnhancedAIOpsBot` and `HuggingFaceAIEngine`.
- **`aiops_orchestrator.py`** — Central event-driven orchestration engine. Manages component lifecycle, pub/sub messaging, dependency resolution, and health monitoring.
- **`realtime_api_server.py`** — FastAPI server with WebSocket support for real-time data streaming.
- **`launch.py`** — Menu-driven interactive launcher for running subsystems.
- **`auth_system.py`** — Authentication and RBAC (Admin/Manager/Employee roles).

**Domain modules (all standalone, pluggable):**
- AI/ML: `enhanced_aiops_chatbot.py`, `huggingface_ai_integration.py`, `gemini_integration.py`, `adaptive_ml.py`
- Monitoring: `performance_monitor.py`, `intelligent_aiops_monitor.py`, `alert_correlation.py`
- Integrations: `discord_bot.py`, `slack_notifier.py`, `teams_integration.py`, `notification_hub.py`
- Analytics: `advanced_predictive_analytics.py`, `business_intelligence_engine.py`
- Automation: `autonomous_operations.py`, `workflow_orchestration_engine.py`, `intelligent_remediation.py`
- Security: `advanced_security_compliance_suite.py`, `audit_logging_system.py`, `threat_intelligence.py`

### Frontend (React)

Located in `dashboard/src/`:
- **`App.js`** — Root app, routing setup
- **`components/MultiRoleDashboard.js`** — Role-aware dashboard (Admin/Manager/Employee views)
- **`components/`** — 20+ feature components: `RealtimeChat`, `AiInsights`, `Alerts`, `Analytics`, `DeviceManagementPortal`, etc.
- **`server.js`** — Express backend for the dashboard

Uses: Material-UI, Recharts, Framer Motion, Socket.io-client, Axios, Tailwind CSS.

### Databases (SQLite)

All in the root directory:
- `aiops_auth.db` — Users and auth
- `audit_logs.db` — Audit trail
- `compliance.db`, `configuration.db`, `dashboard.db`, `data_integration.db`, `notifications.db`, `workflows.db`

### Key Configuration Files

| File | Purpose |
|------|---------|
| `aiops_config.yaml` | Main system config (components, health checks, orchestrator) |
| `enterprise_config.yaml` | Enterprise-specific settings |
| `.env.example` | Environment variables template (Discord, Slack, Email, logging) |
| `api_config.json` | API integration config |
| `alert_rules.yml` | Alert rule definitions |
| `alertmanager.yml` | Alert manager config |
| `prometheus.yml` | Prometheus scrape config |

## AI Integration

Dual AI engine architecture:
- **Google Gemini Pro** (`gemini_integration.py`) — Primary LLM for chat and analysis
- **Hugging Face** (`huggingface_ai_integration.py`) — Sentiment analysis, issue classification, anomaly detection (transformers/torch are optional, commented out in requirements.txt)

## Environment Variables

Copy `.env.example` to `.env`. Key variables:
- `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, `DISCORD_ALERT_CHANNEL`
- `SLACK_WEBHOOK_URL`, `SLACK_BOT_TOKEN`
- `EMAIL_SMTP_SERVER`, `EMAIL_USERNAME`, `EMAIL_PASSWORD`
- `LOG_LEVEL` (default: INFO)
- `DEMO_MODE` (enable/disable demo features)when
