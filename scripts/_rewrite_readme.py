"""Rewrites README.md as clean UTF-8."""
import pathlib

readme = """\
# Resilo - AI-Powered Remote Monitoring and Auto-Remediation

> Monitor any machine in real time. Let AI detect, analyze, and fix issues automatically. No VPN. No port forwarding. Zero config.

## What it does

Resilo runs a lightweight agent on any machine (Windows, macOS, Linux). The agent pushes live system metrics (CPU, memory, disk, network, temperature) to the Resilo backend over plain HTTPS. When thresholds are breached, an AI agent analyzes the alert and -- depending on the configured execution mode -- automatically queues and executes safe remediation commands.

**Full loop in under 30 seconds:**
```
Agent pushes metrics -> Threshold breached -> Alert created
-> Investigation Engine analyzes -> Command queued -> Agent executes -> Alert resolves
```

---

## Services and Ports

| Service | Port | Description |
|---|---|---|
| React Dashboard | 3000 | Frontend (CRA dev server) |
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
.venv\\Scripts\\activate        # Windows
pip install -r requirements.txt

# Node deps
cd dashboard && npm install && cd ..

# Configure
copy .env.dev .env          # edit DATABASE_URL, JWT_SECRET

# Start everything (Windows)
run-dev.bat

# Stop everything
stop-dev.bat
```

Open **http://localhost:3000** -- default admin: `admin@company.local / [ADMIN_DEFAULT_PASSWORD from .env]`

---

## Architecture

```
+----------------+    HTTPS    +---------------------+
| Remote Agent   | ----------> | FastAPI Core  :8000  |
| (Python/Win)   | <-- cmd --- | Investigation Engine |
+----------------+             | LLM: Qwen2.5:7b      |
                               | Embeddings: MiniLM   |
        | SQLAlchemy           +---------------------+
        v
+----------------+   SSE/REST  +---------------------+
| React SPA :3000| <---------- | PostgreSQL    :5432  |
+----------------+             +---------------------+
        |
+----------------+             +---------------------+
| FastAPI Auth   |             | Ollama (local LLM)  |
|    :5001       |             | qwen2.5:7b          |
+----------------+             +---------------------+
```

---

## AI Pipeline

```
Desktop Agent
    |
Metrics + Logs + Context
    |
Investigation Engine
    |
Semantic Memory (all-MiniLM-L6-v2, local)
    |
Evidence Planner
    |
Qwen2.5:7B via Ollama (local, free)
    |
Confidence Routing
    |
Remediation
```

**No external AI billing required.** Both embeddings and LLM inference run locally.

---

## AI Benchmark

Benchmarked against 23 real-world incident scenarios (CPU spikes, OOM, disk failures,
DNS cascades, K8s evictions, RDS failovers, and more).

### LLM comparison

| Model | Backend | Top-1 RCA Accuracy | Action Accuracy | Avg Time | Monthly Cost |
|---|---|---|---|---|---|
| Gemini 2.0 Flash | Google API | **100%** | **95.7%** | 24.9s | Paid (API credits) |
| Qwen2.5 7B | Ollama (local, CPU) | TBD* | TBD* | ~107s** | **Rs. 0** |

*Qwen2.5 7B benchmark in progress -- table will be updated with final numbers.
**CPU-only inference (Intel Iris Xe iGPU not supported by Ollama). A discrete NVIDIA GPU reduces this to 5-15s.

Gemini best run: commit `bc512fe` (100% Top-1, 95.7% Action Accuracy, 24.9s avg).

### Embedding / Clustering comparison

Semantic incident memory benchmarked against 9 clustering fixtures
(single-cluster, multi-cluster, chaining-risk, concurrent-outage cases):

| Model | Backend | F1 Score | False Correlation Rate | Cost |
|---|---|---|---|---|
| gemini-embedding-001 | Google API | 0.81 | 0.11 | Paid |
| all-MiniLM-L6-v2 | sentence-transformers (local) | **0.70** | **0.037** | **Rs. 0** |

FCR = False Correlation Rate -- fraction of unrelated incident pairs incorrectly merged.
MiniLM trades 11pp F1 for 3x better FCR and zero API cost.

```bash
# Run benchmarks yourself
python scripts/benchmark_engine.py --ab        # LLM: A/B static vs planner
python scripts/cluster_benchmark.py --verbose  # Clustering quality metrics
python scripts/_calibrate_threshold.py         # Find optimal similarity threshold
```

---

## Key Features

### Remote Agent
- Pushes CPU, memory, disk, network, temperature every 3s over plain HTTPS
- Zero-config install: one env var + one command
- Windows EXE build (no Python required on target): `desktop_agent/build_exe.bat`
- Offline buffering with automatic retry

### AI Investigation Engine
- Multi-stage pipeline: hypothesis generation -> evidence planning -> root cause analysis
- Semantic incident memory: stores past RCAs as embeddings, retrieved at investigation time
- Cross-incident correlation: clusters related alerts by semantic similarity (threshold=0.50)
- Three execution modes per agent: `dry_run`, `manual_approval`, `auto_safe`
- Safe actions: `scale_memory`, `disk_cleanup`, `restart_service`, `notify_only`, `noop`
- Confidence routing: auto-execute only when confidence >= 0.75

### Dashboard
- Real-time metrics via SSE (no polling)
- Agent status: LIVE / OFFLINE / PENDING with clickable filters
- AI DECISIONS panel with full reasoning, confidence, and action history
- Incident cluster panel: avg/min similarity with chaining risk indicator

### Auth
- JWT access tokens (15 min) + refresh tokens (7 days, httpOnly cookie)
- Google OAuth2, TOTP 2FA, org-scoped multi-tenancy
- Roles: `admin`, `member`, `viewer`

---

## Project Structure

```
resilo/
+-- app/
|   +-- api/
|   |   +-- runtime.py              # Core API: heartbeat, agents, AI pipeline
|   |   +-- investigation_engine.py # Multi-stage LLM investigation
|   |   +-- correlation_engine.py   # Semantic incident clustering
|   |   +-- memory_store.py         # Embedding-based incident memory
|   |   +-- core_api.py             # FastAPI app factory
|   |   +-- auth_api.py             # Auth service
|   +-- core/
|       +-- database.py             # SQLAlchemy models
+-- dashboard/
|   +-- src/
|       +-- components/             # React components
|       +-- services/               # API clients
+-- desktop_agent/
|   +-- resilo_agent.py             # Core agent logic
|   +-- resilo_gui.py               # Tkinter GUI
|   +-- build_exe.bat               # Build Windows EXE
+-- scripts/
|   +-- benchmark_engine.py         # LLM accuracy benchmark (23 scenarios)
|   +-- cluster_benchmark.py        # Clustering quality benchmark (9 fixtures)
|   +-- _calibrate_threshold.py     # Similarity threshold calibration
+-- cluster_fixtures/               # 9 benchmark fixtures (JSON)
+-- test_scenarios/                 # 23 investigation test cases (JSON)
+-- alembic/versions/               # Database migrations (013 applied)
+-- run-dev.bat                     # Start all services
+-- stop-dev.bat                    # Kill all services
```

---

## Environment Variables

```env
# LLM backend (local Ollama -- zero cost)
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b

# Gemini (fallback -- set LLM_BACKEND=gemini to use)
GEMINI_API_KEY=your-key
GEMINI_MODEL=gemini-2.0-flash-lite

# Database
DATABASE_URL=postgresql+asyncpg://aiops:aiops@localhost:5432/aiops

# Auth
JWT_SECRET=your-secret-here
ADMIN_DEFAULT_PASSWORD=your-admin-password

# Google OAuth (optional)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

---

## API Reference (Core -- :8000)

| Method | Path | Description |
|---|---|---|
| `POST` | `/ingest/heartbeat` | Agent pushes metrics |
| `GET` | `/agent/command` | Agent polls for queued commands |
| `POST` | `/agents/onboard` | Generate registration token |
| `POST` | `/agents/register` | Exchange token for agent key |
| `PATCH` | `/api/orgs/{org_id}/agents/{id}/execution-mode` | Set AI execution mode |
| `GET` | `/api/orgs/{org_id}/agents/{id}` | Agent detail + AI history |
| `GET` | `/api/orgs/{org_id}/clusters` | Active incident clusters |
| `GET` | `/stream` | SSE real-time updates |

## API Reference (Auth -- :5001)

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
"""

pathlib.Path("README.md").write_text(readme, encoding="utf-8")
print(f"Written {len(readme)} chars as UTF-8")
