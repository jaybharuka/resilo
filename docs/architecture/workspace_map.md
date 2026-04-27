# Workspace Map

This document describes the cleaned workspace layout and where key files now live.

## Root (kept intentionally)

These files remain at root because they are environment-level entry/config assets:

- `README.md`, `README_START.md`
- `requirements.txt`, `docker-compose.yml`
- `aiops_config.yaml`, `enterprise_config.yaml`
- `prometheus.yml`, `alert_rules.yml`, `dynamic_alert_rules.yml`, `alertmanager.yml`
- `Dockerfile.auth`, `Dockerfile.core`

## Application Code Layout

Primary backend code is organized under `app/` by domain:

- `app/api/`: API servers, gateways, HTTP proxy
- `app/auth/`: Auth service and RBAC
- `app/core/`: Orchestrator, workflow engine, core runtime services
- `app/monitoring/`: Monitoring and runtime metrics components
- `app/analytics/`: Predictive and notification analytics
- `app/remediation/`: Alert correlation and remediation engines
- `app/integrations/`: External integrations and remote agent
- `app/security/`: Security and compliance modules

## Recently Relocated Files

Moved from root into domain folders:

- `auto_scaler.py` -> `app/monitoring/auto_scaler.py`
- `load_balancer.py` -> `app/monitoring/load_balancer.py`
- `realtime_streamer.py` -> `app/monitoring/realtime_streamer.py`
- `enhanced_analytics_service.py` -> `app/analytics/enhanced_analytics_service.py`
- `notification_analytics.py` -> `app/analytics/notification_analytics.py`
- `smart_orchestration.py` -> `app/core/smart_orchestration.py`
- `remote_agent.py` -> `app/integrations/remote_agent.py`
- `notification_config.py` -> `app/integrations/notification_config.py`
- `proxy.py` -> `app/api/proxy.py`
- `patch_ui.py` -> `scripts/patch_ui.py`

## Documentation Layout

- `aiops_documentation/` stores long-form docs.
- `aiops_documentation/reports/` stores status and completion reports moved from root.
- `aiops_documentation/architecture/` stores architecture and structural maps.

## Operational Scripts

- `scripts/start_backend.ps1`: Flask backend
- `scripts/start_core.ps1`: FastAPI core service
- `scripts/start_auth.ps1`: FastAPI auth service
- `scripts/start_dashboard.ps1`: dashboard app
- `scripts/start_all.ps1`: combined startup
- `scripts/stop_all.ps1`: stop local services

## Housekeeping Rules

- Python caches (`__pycache__/`, `*.pyc`) are ignored.
- Temp/editor artifacts (`*.tmp`, `*.temp`, `*.bak`, `*.orig`) are ignored.
- Test/tool caches (`.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`) are ignored.

