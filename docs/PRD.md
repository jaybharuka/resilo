# Resilo — Product Requirements Document

## One-Line Summary
Resilo is an AI-powered AIOps platform that monitors remote machines in real time, detects anomalies, and autonomously remediates infrastructure issues — no VPN, no port forwarding.

---

## Problem
DevOps and IT teams managing distributed machines (remote employees, edge devices, servers) have no lightweight way to:
- Monitor CPU / memory / disk in real time without a VPN
- Get alerted AND auto-remediated when thresholds breach
- Audit what the AI decided and why

Existing solutions (Datadog, PagerDuty) are expensive, heavy, and require network access. Resilo works over plain HTTPS from anywhere.

---

## Target Users
| Persona | Pain |
|---|---|
| SaaS DevOps team (5–50 engineers) | Remote machine health, alert fatigue |
| IT Admin at mid-size company | Employee laptop monitoring, no VPN |
| Solo founder / indie hacker | Cheap Datadog alternative |

---

## Core Features

### 1. Remote Agent
- Lightweight Python agent (`resilo_agent.py`) deployed on any machine
- Pushes `cpu`, `memory`, `disk`, `network`, `temperature`, `processes` every 3s
- Zero-config: one env var (`RESILO_ONBOARD_TOKEN`) + one command
- Windows EXE build via PyInstaller (no Python required on target machine)

### 2. Real-Time Dashboard
- Live metric cards per agent (LIVE / OFFLINE / PENDING status)
- Time-series charts (60-point history)
- Alert feed with severity badges
- Activity timeline per agent
- SSE-based push updates (no polling in UI)

### 3. AI Anomaly Detection + Auto-Remediation
- Rule-based thresholds: CPU > 85% = critical, Memory > 90% = high
- LangChain agent (NVIDIA NIM LLM) analyzes each alert
- Three execution modes:
  - `dry_run` — log only, no action
  - `manual_approval` — queue for human review
  - `auto_safe` — automatically execute safe actions
- Safe actions: `scale_memory`, `disk_cleanup`, `restart_service`, `notify_only`, `noop`
- AI DECISIONS panel shows reasoning + confidence per decision
- Learning feedback loop tracks success/failure rate per action

### 4. Multi-Tenant Auth
- JWT access tokens + refresh tokens (httpOnly cookies)
- Org-scoped data isolation
- Role-based access: `admin`, `member`, `viewer`
- Google OAuth support
- TOTP 2FA

### 5. Alerts & Incidents
- Auto-created alerts when thresholds breach
- Auto-resolved when metrics recover
- Manual incident declaration
- Alert history with filtering

---

## Non-Goals (v1)
- No mobile app
- No Kubernetes / container monitoring
- No on-prem deployment (SaaS-first)
- No billing / payment system yet

---

## Success Metrics
- Agent installs in < 2 minutes
- Alert fires within 10s of threshold breach
- AI queues remediation command within 30s of alert
- Dashboard loads in < 1s

---

## Current Status
- ✅ Core backend (FastAPI, PostgreSQL)
- ✅ Auth service (JWT, OAuth, 2FA)
- ✅ Remote agent (Python + Windows EXE)
- ✅ React dashboard (real-time SSE)
- ✅ LangChain AI agent with auto-remediation
- ✅ Demo pipeline script (`demo_ai_pipeline.py`)
- 🔧 Go agent (in progress — `agent/go-agent/`)
- ⬜ Billing
- ⬜ Mobile notifications
