# Resilo — Architecture Overview

## System Purpose

Resilo is an AI-assisted SRE platform that automates the first 10 minutes of incident response: from metric collection through root-cause analysis, evidence-based reasoning, and remediation routing.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Desktop Agent (Python)                                          │
│  Runs on monitored host. Collects metrics, logs, process state. │
│  Heartbeats every 30s → POST /api/heartbeat                     │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTPS (JWT)
┌────────────────────────▼────────────────────────────────────────┐
│  FastAPI Core  (port 8000)                                       │
│                                                                  │
│  ┌──────────────┐   ┌─────────────────┐   ┌─────────────────┐  │
│  │ Heartbeat    │   │ Investigation   │   │ Remediation     │  │
│  │ Handler      │──▶│ Engine          │──▶│ Router          │  │
│  └──────────────┘   └────────┬────────┘   └────────┬────────┘  │
│                               │                     │           │
│  ┌──────────────┐   ┌────────▼────────┐   ┌────────▼────────┐  │
│  │ Incident     │   │ Semantic Memory │   │ Remediation     │  │
│  │ Manager      │   │ Store           │   │ Job Queue       │  │
│  └──────────────┘   └─────────────────┘   └─────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ PostgreSQL  (SQLAlchemy async ORM + pgvector)             │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                         │ REST + SSE
┌────────────────────────▼────────────────────────────────────────┐
│  React Dashboard  (port 3000)                                    │
│  RemoteAgents · Investigations · Evaluation · Approvals          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Auth  (port 5001)                                       │
│  JWT issue · Org management · RBAC · Invite flow                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Responsibilities

### Desktop Agent (`desktop_agent/resilo_agent.py`)
- Collects: CPU, memory, disk, network, top processes, load average, swap, battery, disk partitions
- Extended collectors: open ports, failed services, disk inodes
- Offline buffering: up to 20 heartbeats cached to `~/.resilo_buffer.json` during network outages
- Auto-restart safe-list: only PROTECTED_SERVICES may be auto-restarted (max 3/hour)

### FastAPI Core (`app/api/core_api.py`)
- Central API: heartbeat ingestion, alert management, investigation triggers, SSE event stream
- Startup: schema migration via `ALTER TABLE IF NOT EXISTS` ensures (zero-downtime safe)
- Background tasks: investigation runs async, does not block heartbeat response

### Investigation Engine (`app/api/investigation_engine.py`)
The core AI reasoning pipeline. See [investigation-flow.md](investigation-flow.md) for full stage detail.

### Semantic Memory Store (`app/api/memory.py`)
Incident memory with pgvector embeddings. See [memory-system.md](memory-system.md).

### Remediation Router (`app/api/remediation.py`)
Routes actions to auto_execute / manual_approval / investigation_only based on confidence + safe-list. See [remediation.md](remediation.md).

### Benchmark Engine (`scripts/benchmark_engine.py`)
Offline evaluation suite. See [benchmarking.md](benchmarking.md).

---

## Data Flow — Normal Incident

```
1. Agent heartbeat arrives with cpu=97%, load=7.8, top_processes=[python3:94%]
2. Heartbeat handler: alert created (severity=critical), investigation triggered
3. Investigation Engine:
   Stage 1:   Collect evidence (logs, context_collector, top_processes)
   Stage 1.5: Evidence Planner (optional LLM-driven adaptive collection)
   Stage 2:   Semantic memory search (pgvector cosine similarity)
   Stage 3:   Hypothesis generation (Gemini LLM)
   Stage 4:   Root cause analysis (Gemini LLM)
   Stage 5:   Action routing (confidence threshold rules)
4. Result persisted: investigations table (RCA, hypotheses, evidence, llm_cost, evidence_contribution)
5. Memory saved: incident_memory table (embedded for future retrieval)
6. SSE event pushed to dashboard
7. Remediation job queued (if auto_execute) or approval requested (if manual_approval)
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Agent | Python 3.12, psutil, asyncio |
| Backend | FastAPI, SQLAlchemy (async), Alembic |
| Database | PostgreSQL + pgvector |
| LLM | Google Gemini (via google-generativeai) |
| Embeddings | pgvector cosine similarity (text→float[] via Gemini embed) |
| Frontend | React 18, react-router-dom, lucide-react |
| Auth | JWT (HS256), bcrypt, RBAC |
| Dev | uvicorn --reload, python-dotenv |

---

## Security Model

- All agent→backend communication is JWT-authenticated
- Org isolation: every DB query is scoped to `org_id` from token
- RBAC: `admin`, `devops`, `viewer` roles; auto_execute restricted to admin/devops
- Safe-list: only explicitly named services may be auto-restarted
- Remediation confidence gate: `confidence < 0.75` → manual_approval regardless of routing
