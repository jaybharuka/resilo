# SOC2 Type I — Logging and Monitoring Evidence

**Control Domain:** Logging, Monitoring, and Alerting
**Last Reviewed:** 2026-04-07
**Owner:** Engineering / Security Team
**Status:** Implemented

---

## CC7.1 — Detection of Security Events

**Requirement:** The entity detects security events through monitoring and analysis.

**Implementation:**
- Structured audit logs written to PostgreSQL `audit_logs` table for all security-relevant events
- Every log entry includes: `event`, `user_id`, `org_id`, `ip`, `timestamp`, `status`, `error_message`
- Prometheus metrics scraped every 15 seconds; alerts fire on anomaly thresholds
- Failed authentication attempts trigger immediate audit log entry and increment `auth_failures_total` Prometheus counter

**Security Events Logged:**
| Event | audit `action` | Severity |
|---|---|---|
| User login | `user_login` | INFO |
| Failed login | `user_login_failed` | WARN |
| SSO login | `sso_login` | INFO |
| Password reset | `password_reset` | INFO |
| Token refresh | `token_refresh` | DEBUG |
| Role escalation | `role_change` | WARN |
| Cross-tenant attempt | blocked at middleware; `401/403` | ERROR |
| Remediation executed | `remediation_executed` | INFO |
| Admin action | `admin_action` | WARN |
| API key created/revoked | `apikey_create`, `apikey_revoke` | INFO |

**Evidence Files:**
- `app/core/audit.py` — `AuditService.write()` implementation
- `app/core/metrics.py` — Prometheus counters

---

## CC7.2 — Monitoring of System Components

**Requirement:** The entity monitors system components for anomalies and failures.

**Implementation:**
- Prometheus scrapes all services every 15 seconds (configured in `prometheus.yml`)
- Kubernetes liveness, readiness, and startup probes on every deployment
- Alertmanager configured with alert rules (`alert_rules.yml`)
- OpenTelemetry traces exported for distributed request tracing (`otel/instrumentation.py`)
- Health endpoint `/health/deep` reports DB connectivity and migration status

**Monitored Metrics:**
| Metric | Type | Alert Threshold |
|---|---|---|
| `http_requests_total` | Counter | Rate spike > 10x baseline |
| `http_request_duration_seconds` | Histogram | p99 > 2s |
| `auth_failures_total` | Counter | > 10 failures/min |
| `remediation_jobs_failed_total` | Counter | > 5 failures/10 min |
| `db_connection_pool_size` | Gauge | < 2 connections available |

**Evidence Files:**
- `prometheus.yml` — scrape config
- `alertmanager.yml` — alert routing
- `alert_rules.yml` — threshold definitions
- `otel/instrumentation.py` — distributed tracing
- `app/api/health_api.py` — health endpoints

---

## CC7.3 — Audit Log Integrity

**Requirement:** Audit logs are complete, tamper-evident, and retained appropriately.

**Implementation:**
- Audit logs stored in append-only PostgreSQL table `audit_logs`
- No `UPDATE` or `DELETE` permissions granted to application DB user on `audit_logs`
- Application DB user has `INSERT` and `SELECT` only on `audit_logs`
- Logs retained for 90 days (configurable via `RETENTION_POLICIES["audit_logs"]` in `app/core/retention.py`)
- Each log entry has an immutable UUID primary key and server-generated `created_at` timestamp

**Append-Only Enforcement (PostgreSQL):**
```sql
REVOKE UPDATE, DELETE ON audit_logs FROM app_user;
GRANT SELECT, INSERT ON audit_logs TO app_user;
```

**Evidence Files:**
- `app/core/audit.py` — write-only `AuditService`
- `app/core/retention.py` — `RETENTION_POLICIES` (90 days for audit_logs)
- `alembic/versions/001_initial_postgresql_schema.py` — `audit_logs` table schema

---

## CC7.4 — Incident Detection and Response Logging

**Requirement:** Security incidents are detected, logged, and escalated.

**Implementation:**
- Alert correlation engine (`app/remediation/alert_correlation.py`) correlates anomalies
- Critical alerts trigger notification via configured channels (Slack, email, Discord)
- All remediation actions logged with pre/post state and executor identity
- Incident timeline reconstructable from `audit_logs` by `org_id` and time range

**Evidence Files:**
- `app/remediation/alert_correlation.py` — correlation logic
- `app/integrations/notification_service.py` — incident alerting
- `app/core/audit.py` — incident action logging

---

## CC7.5 — Log Protection from Unauthorized Access

**Requirement:** Audit logs are protected from modification or deletion by unauthorized users.

**Implementation:**
- `audit_logs` table accessible only to `app_user` (INSERT/SELECT) and `dba_user` (full access)
- DBA-level access requires MFA and is separately audited
- Log access by non-admin users blocked at API level (no `GET /audit-logs` for non-admins)
- Kubernetes secrets storing DB credentials have RBAC-restricted access

**Evidence Files:**
- `app/auth/rbac.py` — admin-only audit log access
- Kubernetes RBAC manifests — secret access restrictions

---

*This document is part of the Resilo SOC2 Type I evidence package. Update quarterly or after any monitoring configuration change.*
